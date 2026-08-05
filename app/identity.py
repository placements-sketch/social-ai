"""
app/identity.py
Turning platform IDs into names people recognise.

A customer's identity reaches us as an `external_id` — on Instagram that's an
IGSID, a 16-digit number. We store the username on `users.name` when we learn
it, but plenty of text was built from `User.handle`, which is `name or
external_id`. So anywhere the name wasn't known *at the moment the text was
written*, the raw ID was baked into it permanently: notification titles,
log messages, the Live Activity feed.

Usernames often arrive later, when the thread is created or a profile fetch
succeeds. Resolving at READ time rather than write time means those rows start
reading correctly without being rewritten.

One module so the rule has one definition. Everything that renders customer
identity goes through here.
"""
import re

from app import db
from app.models import Conversation, User

# Candidate identifiers inside free text. Long digit runs cover IGSIDs and
# Facebook PSIDs; the second form catches the seeded/handle-style ids that are
# not numeric. Being a candidate means nothing on its own — a token is only ever
# substituted if it turns out to BE a customer external_id, so Shopify order
# numbers and product ids in the same sentence are left alone.
_CANDIDATE = re.compile(r'\b(\d{8,}|[A-Za-z][A-Za-z0-9_.]{5,})\b')


def normalise_handle(name):
    """
    Strip a leading '@' and surrounding space.

    Some stored names carry the '@' and some don't, and the UI prepends one —
    which rendered the inconsistent ones as '@@amina_ke'.
    """
    if not name:
        return None
    cleaned = name.strip().lstrip('@').strip()
    return cleaned or None


def handles_for_external_ids(external_ids):
    """{external_id: name} for the ids we have a name for. One query."""
    ids = {e for e in external_ids if e}
    if not ids:
        return {}
    out = {}
    for name, ext in (db.session.query(User.name, User.external_id)
                      .filter(User.external_id.in_(ids))
                      .filter(User.name.isnot(None))
                      .all()):
        handle = normalise_handle(name)
        if handle:
            out.setdefault(ext, handle)
    return out


def handles_for_conversations(conversation_ids):
    """
    {conversation_id: name} and {external_id: name}, resolved through the
    conversation's customer. One query.

    This is the stronger of the two lookups: a row that knows which
    conversation it belongs to can be resolved even when its own payload never
    recorded an identifier.
    """
    ids = {c for c in conversation_ids if c}
    if not ids:
        return {}, {}
    by_conv, by_ext = {}, {}
    for conv_id, name, ext in (
        db.session.query(Conversation.id, User.name, User.external_id)
        .join(User, User.id == Conversation.user_id)
        .filter(Conversation.id.in_(ids))
        .all()
    ):
        handle = normalise_handle(name)
        if handle:
            by_conv[conv_id] = handle
            if ext:
                by_ext.setdefault(ext, handle)
    return by_conv, by_ext


def candidate_ids(*texts):
    """Every token in these strings that could be a customer external_id."""
    found = set()
    for t in texts:
        if t:
            found.update(_CANDIDATE.findall(t))
    return found


PLATFORM_LABELS = {
    'instagram': 'Instagram user',
    'facebook':  'Facebook user',
    'tiktok':    'TikTok user',
    'whatsapp':  'WhatsApp user',
}


def display_for_external_id(external_id, channel=None):
    """
    What to show when we have no username: "Instagram user · 4283".

    Six customers here will NEVER resolve. Their IGSIDs were issued to the
    Instagram account this app was connected as before the switch, and Meta
    answers "object does not exist" for every one — no token we can hold will
    ever read them. Confirmed by the fact that 16 of 22 conversations DO have
    handles: a missing scope or a bad token would have failed all 22.

    So the raw 17-digit number is permanent for those threads, and showing it
    is the worst option: it looks like a field that failed to load, and an
    agent cannot tell two customers apart by scanning digit strings. The last
    four are stable, distinguishable, and honest about being partial.
    """
    ext = str(external_id or '').strip()
    if not ext:
        return 'Unknown customer'
    # Only long platform ids get this treatment. A phone number or a handle
    # someone typed is already readable and must pass through untouched.
    if ext.isdigit() and len(ext) >= 15:
        # Named after the platform it actually came from. Facebook PSIDs are
        # the same 17-digit shape as Instagram IGSIDs, so a hardcoded
        # "Instagram user" mislabelled every Facebook customer — telling an
        # agent the wrong app to open if they wanted to check the thread.
        return f'{PLATFORM_LABELS.get((channel or "").split("_")[0], "Customer")} · {ext[-4:]}'
    return ext


def humanise(text_value, mapping):
    """
    Replace known external ids in free text with '@username'.

    Only ids present in `mapping` are touched, so anything that merely looks
    like an id — a Shopify customer number, a product id, a timestamp — is left
    exactly as it was. An id already written as '@1234' becomes '@name' rather
    than '@@name'.
    """
    if not text_value or not mapping:
        return text_value
    out = text_value
    # Longest first: substituting a short id that is a prefix of a longer one
    # would corrupt the longer one.
    for ext in sorted(mapping, key=len, reverse=True):
        if ext and ext in out:
            out = re.sub(r'@?' + re.escape(ext), '@' + mapping[ext], out)
    return out


def resolve_notifications(rows):
    """
    id -> handle map for a page of notifications.

    Notifications don't carry a conversation_id or a payload; they link by
    (resource_type, resource_id). Only rows whose resource actually IS a
    conversation are followed — resource_id is also used for channel ids, user
    ids and rule ids, and joining those against conversations would attach the
    wrong customer's name to the text.
    """
    conv_ids, ext_ids = set(), set()
    for r in rows:
        if getattr(r, 'resource_type', None) == 'conversation':
            rid = getattr(r, 'resource_id', None)
            try:
                conv_ids.add(int(rid))
            except (TypeError, ValueError):
                pass
        ext_ids.update(candidate_ids(getattr(r, 'title', None),
                                     getattr(r, 'body', None)))

    _by_conv, by_ext = handles_for_conversations(conv_ids)
    unresolved = {e for e in ext_ids if e and e not in by_ext}
    by_ext.update(handles_for_external_ids(unresolved))
    return by_ext


def resolve_rows(rows, text_fields, conversation_attr='conversation_id',
                 payload_attr='payload', payload_id_key='user_external_id'):
    """
    Batch-resolve a list of ORM rows and return {row_index: handle}.

    Collects candidates from the given text fields, the payload identifier and
    the conversation link, resolves them all in at most two queries, and hands
    back both the per-row handle and the id->handle map for text substitution.

    Returns (handles_by_index, id_to_handle).
    """
    conv_ids, ext_ids = set(), set()
    for r in rows:
        conv_ids.add(getattr(r, conversation_attr, None))
        payload = getattr(r, payload_attr, None) or {}
        if isinstance(payload, dict):
            ext_ids.add(payload.get(payload_id_key))
        ext_ids.update(candidate_ids(*[getattr(r, f, None) for f in text_fields]))

    by_conv, by_ext = handles_for_conversations(conv_ids)
    unresolved = {e for e in ext_ids if e and e not in by_ext}
    by_ext.update(handles_for_external_ids(unresolved))

    handles = {}
    for i, r in enumerate(rows):
        payload = getattr(r, payload_attr, None) or {}
        ext = payload.get(payload_id_key) if isinstance(payload, dict) else None
        handle = by_conv.get(getattr(r, conversation_attr, None))
        if not handle and ext:
            handle = by_ext.get(ext)
        if handle:
            handles[i] = handle
    return handles, by_ext
