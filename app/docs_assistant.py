"""
Docs assistant — answers "how does this work?" from the written explainers.

Distinct from ai_assistant.py, which is the customer-analytics assistant: that
one answers questions about DATA for admins and supervisors by calling vetted
query tools. This one answers questions about the SYSTEM, for everyone
including agents, and touches no customer data at all.

Keeping them apart matters. The analytics assistant is admin-only precisely
because its answers contain customer records; a docs assistant restricted the
same way would be useless to the people with the most questions.

WHY THE WHOLE CORPUS IS SENT, WITH NO RETRIEVAL
The explainers total ~124 KB, roughly 31k tokens. That fits comfortably in one
request, so there is no reason to chunk-and-retrieve: retrieval exists to solve
a size problem we do not have, and it introduces one we would rather avoid —
the top-k missing the paragraph that actually answers the question, producing a
confident "the docs don't cover this" when they do. Prompt caching makes the
repeated corpus cheap after the first call.

If the corpus grows past ~150k tokens this has to change. That is a long way
off: it would take roughly ten times the documentation we have now.
"""
import os
import time

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

from app import limiter
from app.auth import current_user_id
from app.models import AuthUser
from app.utils.logger import log_event

docs_assistant_bp = Blueprint('docs_assistant', __name__)

MODEL = 'claude-sonnet-5'
MAX_ANSWER_TOKENS = 1200

# extras/ lives beside app/, not inside it.
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'extras')

# Files the assistant is allowed to read from. An allow-list by suffix rather
# than "everything in extras/", because that directory also holds exported
# analytics PDFs, a pptx, and throwaway test scripts — none of which are
# documentation, and one of which (create_test_users.py) contains credentials.
DOC_SUFFIXES = ('_EXPLAINED.md',)
DOC_EXTRA_FILES = ('ARCHITECTURE.md',)

_corpus_cache = {'text': None, 'files': [], 'loaded_at': 0}
# Re-read at most every 10 minutes, so editing an explainer shows up without a
# redeploy but a burst of questions doesn't hit the disk once per question.
CORPUS_TTL_SECONDS = 600


def _load_corpus(force=False):
    """(text, [filenames]). Cached in memory with a short TTL."""
    now = time.time()
    if not force and _corpus_cache['text'] is not None \
            and (now - _corpus_cache['loaded_at']) < CORPUS_TTL_SECONDS:
        return _corpus_cache['text'], _corpus_cache['files']

    parts, names = [], []
    try:
        for name in sorted(os.listdir(DOCS_DIR)):
            if not (name.endswith(DOC_SUFFIXES) or name in DOC_EXTRA_FILES):
                continue
            try:
                with open(os.path.join(DOCS_DIR, name), 'r', encoding='utf-8') as fh:
                    body = fh.read()
            except OSError as e:
                log_event('warning', 'docs_assistant.read_failed', f'{name}: {str(e)[:120]}')
                continue
            # The filename is the citation handle — the answer refers to it, so
            # it has to travel with the text rather than be inferred.
            parts.append(f'<document name="{name}">\n{body}\n</document>')
            names.append(name)
    except OSError as e:
        log_event('error', 'docs_assistant.corpus_missing', f'{DOCS_DIR}: {str(e)[:120]}')
        return '', []

    text = '\n\n'.join(parts)
    _corpus_cache.update({'text': text, 'files': names, 'loaded_at': now})
    return text, names


SYSTEM_INSTRUCTIONS = (
    "You are the in-app documentation assistant for the Shop Zetu Social AI platform. "
    "Staff — agents, supervisors and admins — ask you how the system works.\n\n"
    "Answer ONLY from the documents provided above. They are the written explainers for "
    "this exact system, including the reasoning behind decisions.\n\n"
    "Rules:\n"
    "1. If the documents do not cover something, say so plainly: 'The docs don't cover "
    "that.' Then say what related thing they DO cover. Never fill a gap with what is "
    "generally true of software — a confident wrong answer about this system is worse "
    "than no answer, because the person will repeat it to someone else.\n"
    "2. Name the document you drew from, e.g. 'MESSAGES_EXPLAINED.md'. The person often "
    "needs to go and read it before a meeting.\n"
    "3. Explain the WHY, not just the what. These docs exist so staff can defend the "
    "work when challenged; 'the chips are counted server-side' is less useful than "
    "'they're counted server-side because counting the loaded page made a chip read 27 "
    "above a list of 11.'\n"
    "4. Be concise and direct. Lead with the answer. Use short paragraphs; use a list "
    "only when the answer really is a list.\n"
    "5. Never invent numbers, column names, endpoints or settings. If you are unsure "
    "whether a detail is current, say which document you got it from and that it should "
    "be verified.\n"
    "6. You have no access to live data — no customers, orders, conversations or "
    "metrics. If asked for a number about the business, say that the Customer Profiling "
    "assistant answers data questions and you answer how-it-works questions."
)


@docs_assistant_bp.route('/docs/ask', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
def ask_docs():
    """
    Ask a question about how the platform works.

    Body: { "question": "...", "history": [{role, content}, ...] }

    Open to every signed-in role. The corpus is internal documentation about
    our own system and contains no customer data, so there is nothing here an
    agent should not see — and agents are the ones who most need it.
    """
    user = AuthUser.query.get(current_user_id())
    if not user:
        return jsonify({'error': 'User not found'}), 404

    body = request.get_json(silent=True) or {}
    question = (body.get('question') or '').strip()
    history = body.get('history') or []

    if not question:
        return jsonify({'error': 'question is required'}), 400
    if len(question) > 1000:
        return jsonify({'error': 'Question is too long — keep it under 1000 characters.'}), 400

    corpus, files = _load_corpus()
    if not corpus:
        # A specific failure, not "AI unavailable". This one means the docs
        # were not deployed alongside the app — a packaging problem someone can
        # actually fix, and it would otherwise look like a broken model.
        return jsonify({'error': 'Documentation is not available on this server.'}), 503

    api_key = current_app.config.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'AI is not configured on this server.'}), 503

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        log_event('error', 'docs_assistant.client_init', str(e)[:200])
        return jsonify({'error': 'AI is not configured on this server.'}), 503

    messages = []
    for h in history[-8:]:
        role, content = h.get('role'), h.get('content')
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': str(content)[:4000]})
    messages.append({'role': 'user', 'content': question})

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_ANSWER_TOKENS,
            system=[
                # Two blocks, and the order matters: the corpus is identical on
                # every request and carries the cache breakpoint, so it is
                # written to cache once and read back cheaply thereafter. Put
                # the instructions first and the cached prefix would end before
                # the expensive part.
                {
                    'type': 'text',
                    'text': f'The complete documentation for this platform:\n\n{corpus}',
                    'cache_control': {'type': 'ephemeral'},
                },
                {'type': 'text', 'text': SYSTEM_INSTRUCTIONS},
            ],
            messages=messages,
        )
    except Exception as e:
        log_event('error', 'docs_assistant.request_failed', str(e)[:300])
        return jsonify({'error': 'Could not reach the assistant. Try again.'}), 502

    # Extended thinking can put a reasoning block first, so content[0].text is
    # not safe — take the first block that actually has text. This exact
    # assumption has broken five call sites elsewhere in the codebase.
    answer = next((b.text for b in resp.content
                   if getattr(b, 'type', None) == 'text' and getattr(b, 'text', None)), '')

    if not answer:
        log_event('warning', 'docs_assistant.empty_answer', f'stop_reason={resp.stop_reason}')
        return jsonify({'error': 'The assistant returned nothing. Try rephrasing.'}), 502

    usage = getattr(resp, 'usage', None)
    log_event('info', 'docs_assistant.answered',
              f'{user.email} asked: {question[:120]}',
              payload={
                  'input_tokens': getattr(usage, 'input_tokens', None),
                  'cache_read': getattr(usage, 'cache_read_input_tokens', None),
                  'cache_write': getattr(usage, 'cache_creation_input_tokens', None),
              })

    return jsonify({'answer': answer, 'sources': files}), 200


@docs_assistant_bp.route('/docs/topics', methods=['GET'])
@jwt_required()
def docs_topics():
    """
    Which documents back the assistant. Shown in the empty state so people can
    see what it can be asked about rather than guessing at a blank box.
    """
    _corpus, files = _load_corpus()
    return jsonify({
        'available': bool(files),
        'documents': [
            {'file': f, 'title': f.replace('_EXPLAINED.md', '').replace('.md', '').replace('_', ' ').title()}
            for f in files
        ],
    }), 200
