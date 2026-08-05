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
# Extended thinking is switched OFF for this endpoint. The task is explaining
# from text that is already in front of the model — there is nothing to reason
# out — and leaving it on had a real cost: the reasoning shared the token
# budget with the answer, so replies came back cut off mid-sentence or, twice,
# with no text at all. Off, a typical answer costs ~250 output tokens instead
# of 2,000+, and comes back noticeably faster.
NO_THINKING = {'type': 'disabled'}
MAX_ANSWER_TOKENS = 900

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


# ── What each role can actually do ───────────────────────────────────────────
# Read off the real guards in the code (channels.py, customers.py,
# ai_settings.py, automation.py, settings.py, logs.py, analytics.py) and the
# navigation in Sidebar.jsx — NOT from the explainers, which describe features
# without saying who can reach them.
#
# This matters more than it looks. Without it the assistant cheerfully talks an
# agent through changing a setting on a page their role cannot open, and they
# waste ten minutes discovering that themselves. Worse, it implies the platform
# is broken when it is working exactly as designed.
#
# KEEP IN SYNC when role guards change. It is a deliberate second copy: the
# guards live across a dozen route files and cannot be summarised at runtime,
# and a stale note here is still better than the assistant guessing.
ROLE_MODEL = """
WHO CAN DO WHAT (authoritative — the docs do not all cover this):

Three roles: agent, supervisor, admin.

Pages in the left-hand menu:
- Dashboard, Inbox, Analytics, Activity ....... everyone
- Products .................................... supervisor and admin only
- AI & Automation, Users, Settings ............ admin only
- Customer Profiling .......................... currently switched off for everyone

Inside the Inbox:
- An AGENT sees only conversations assigned to them, plus unclaimed ones
  waiting for a human. They do not see conversations the AI is handling, or
  ones assigned to a colleague.
- Supervisors and admins see every conversation.
- Anyone can claim an unclaimed conversation, reply, and resolve.

Viewing versus changing, elsewhere in the app:
- Channels, AI settings, automation rules: supervisors can LOOK, only admins
  can CHANGE.
- Customer records: supervisors and admins can look, only admins can change.
- System settings: admins only, both viewing and changing.
- Agent performance figures in Analytics: supervisors and admins only.

If someone asks how to do something their role cannot do, say so kindly and
tell them who to ask — an admin, or their supervisor. Do not walk them through
steps they will be blocked from taking.
"""


SYSTEM_INSTRUCTIONS = (
    "You are the in-app help assistant for the Shop Zetu Social AI platform.\n\n"
    "WHO YOU ARE TALKING TO. Customer experience agents — the people answering "
    "Instagram messages all day. They are not engineers. Most have never seen a "
    "database, an API or a line of code, and nothing about their job requires them to. "
    "They are asking because something on screen confused them and they want to get "
    "back to work.\n\n"
    "HOW TO WRITE\n"
    "- LENGTH IS THE HARDEST RULE HERE. Three short paragraphs maximum, or about "
    "120 words. Answer exactly what was asked and stop. Do not add background "
    "nobody asked for. If there is more worth knowing, end with one line offering "
    "it — 'Want me to explain how that gets decided?' — and let them ask. A wall "
    "of text stands between an agent and their next customer, so extra thoroughness "
    "here is a cost, not a kindness.\n"
    "- Plain, everyday English. Short sentences.\n"
    "- Describe what they SEE — 'the green chip at the top of the inbox', not 'the "
    "by_status count'. Talk about buttons, labels and screens.\n"
    "- Banned unless they used the word first: endpoint, API, database, column, table, "
    "query, SQL, webhook, cache, boolean, null, backend, frontend, deploy, token. If "
    "one of these is genuinely the answer, explain it in ordinary words instead — "
    "'the system checks with Instagram every few minutes' beats 'a polling job'.\n"
    "- NEVER show a file name or a code word, and never use backticks. Not "
    "MESSAGES_EXPLAINED.md, not handoff.py, not human_escalate, not by_status. "
    "These mean nothing to the reader and make the answer look like it was meant "
    "for someone else. Say what the thing is called ON SCREEN, or describe what it "
    "does: 'the rule hands the chat to a person', never 'the human_escalate "
    "action'.\n"
    "- No headings, and no bold mini-titles at the start of list items.\n"
    "- Warm and direct. Answer first, then a sentence of why if it helps.\n"
    "- Never make them feel silly for asking.\n\n"
    "WHAT TO ANSWER FROM\n"
    "Two sources: the documents above, and the 'WHO CAN DO WHAT' notes below. The notes "
    "override the documents on anything about permissions — the documents describe "
    "features without always saying who can reach them.\n\n"
    "RULES\n"
    "1. If you genuinely do not know, say so: 'I'm not sure about that one — worth "
    "asking your supervisor.' Never guess from what is generally true of other "
    "software. A confident wrong answer is the worst outcome here, because they will "
    "act on it with a real customer.\n"
    "2. Answer for THIS person's role. If they cannot do the thing they are asking "
    "about, say who can, kindly — do not walk them through steps that will be blocked.\n"
    "3. Explain why, when the why is useful. It is usually more reassuring than the "
    "what: knowing a number is counted a certain way stops them worrying it is broken.\n"
    "4. Use their first name naturally — a greeting, or when reassuring them. Not in "
    "every message; that reads like a script.\n"
    "5. Never invent numbers, settings or figures.\n"
    "6. You cannot see live data — no customers, orders, conversations or sales "
    "figures. If asked, say plainly that you explain how things work, and that for real "
    "numbers they should look at the Dashboard or Analytics page.\n"
    "7. Do not cite documents or guides. The reader cannot open them and does not "
    "care which one an answer came from. Just answer.\n"
    "8. Do not bold the start of each list item as a mini-heading. Write the point "
    "as a plain sentence. Bold at most one or two words in a whole reply, and only "
    "when something genuinely needs emphasis."
)


ROLE_WORDS = {
    'agent': 'a customer experience agent',
    'supervisor': 'a supervisor',
    'admin': 'an administrator',
}


def _who_is_asking(user):
    """
    Tells the assistant who it is talking to, so it can use their name and
    answer for their actual permissions.

    Taken from the signed-in session, never from anything the browser sends —
    otherwise someone could claim to be an admin in the request body and be
    told how admin-only screens work.
    """
    first = (user.full_name or '').strip().split(' ')[0] or user.email.split('@')[0]
    role_phrase = ROLE_WORDS.get(user.role, f'a {user.role}')
    return (
        f"WHO IS ASKING: {first}, {role_phrase}.\n"
        f"Address them as {first}. Answer for what {role_phrase} can actually do — "
        f"see the permissions notes above."
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
            thinking=NO_THINKING,
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
                # Everything below the breakpoint may vary per request. The
                # person's name and role MUST live here rather than in the
                # cached block — putting them above would give every user a
                # different prefix, so nobody would ever hit the cache and the
                # corpus would be re-read at full price on every question.
                {'type': 'text', 'text': ROLE_MODEL},
                {'type': 'text', 'text': _who_is_asking(user)},
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
        return jsonify({
            'error': 'That answer got cut short. Ask again, or try a shorter question.'
        }), 502

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
