"""
app/integrations/meta_poller.py
Polls Meta Graph API for new Instagram DMs and routes them through
process_message — the same pipeline webhooks use.

Why polling: Meta dev-mode strips content from webhook events, but the
Graph API conversations endpoint returns full message content. So during
dev / pre-app-review, polling is how we get real messages flowing.

Once the app is live (post-review), webhooks become the preferred path
and this poller can be disabled by setting IG_POLL_ENABLED=false.
"""

import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from app.utils.logger import log_event

GRAPH_API_VERSION = "v25.0"

def _conversations_url():
    """Build the FB Graph conversations URL for the configured Page."""
    from app.integrations.meta import _get_meta_credentials
    page_id, _ = _get_meta_credentials()  # NEW

    if not page_id:
        return None
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/conversations"

POLL_INTERVAL_SECONDS = int(os.getenv("IG_POLL_INTERVAL_SECONDS", "60"))

# Asking for thread contents inline times out with subcode 2534084 ("too many
# conversations with users who do not have a role on app") on busy accounts —
# even WITH Advanced Access. So we fetch bare thread IDs first, then hydrate
# each thread on its own. The list call still times out above a small limit,
# and the ceiling moves, so try a descending ladder and take the first that
# answers.
POLL_THREAD_LIMITS = [5, 3, 1]
POLL_MESSAGE_LIMIT = int(os.getenv("IG_POLL_MESSAGE_LIMIT", "10"))

# Polling returns a thread's recent history, not just what's new. Without a
# cutoff the first cycle would replay days of messages through process_message
# and auto-reply to every one of them. Only act on messages this fresh.
POLL_MAX_AGE_MINUTES = int(os.getenv("IG_POLL_MAX_AGE_MINUTES", "15"))


def _is_too_old(created_time: str) -> bool:
    """True if a Graph created_time ('2026-07-28T09:36:19+0000') is stale."""
    if not created_time:
        return False  # no timestamp — let the dedupe check decide
    try:
        ts = datetime.strptime(created_time, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - ts
    return age > timedelta(minutes=POLL_MAX_AGE_MINUTES)

# Module-level guard so we don't start the thread twice in debug mode
# (Flask debug reloader spawns a second process; only the reloader-child
# should start the poller).
_poller_started = False
_poller_lock = threading.Lock()


def start_poller(app=None):
    """
    Start the background poll loop when IG_POLL_ENABLED is truthy.

    Webhooks stay the preferred path and already handle comments. Polling is
    the bridge for DMs, which Meta withholds from our app entirely until App
    Review grants Advanced Access to instagram_manage_messages.
    """
    global _poller_started

    if os.getenv("IG_POLL_ENABLED", "false").lower() not in ("1", "true", "yes"):
        log_event("info", "ig_poller.disabled",
                  "IG_POLL_ENABLED not set — webhook-only mode")
        return

    if app is None:
        log_event("error", "ig_poller.no_app", "start_poller called without an app")
        return

    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True

    threading.Thread(target=_poller_loop, args=(app,),
                     daemon=True, name="ig-poller").start()
    log_event("info", "ig_poller.started",
              f"Polling every {POLL_INTERVAL_SECONDS}s")

def _poller_loop(app):
    """The actual loop. Each tick: fetch threads, process new messages."""
    while True:
        try:
            with app.app_context():
                _poll_once()
        except Exception as e:
            log_event("error", "ig_poller", f"Poll cycle crashed: {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


def _poll_once():
    """One polling cycle: fetch all conversations, route new inbound."""
    from app.integrations.meta import _get_meta_credentials
    page_id, token = _get_meta_credentials()
    url = _conversations_url()

    if not token or not url:
        return

    # Phase 1: bare thread IDs, newest-updated first. Walk the limit ladder
    # down until Graph answers instead of timing out.
    thread_ids = []
    last_err = None
    for limit in POLL_THREAD_LIMITS:
        try:
            r = requests.get(url, params={
                "platform": "instagram",
                "fields": "id",
                "limit": limit,
                "access_token": token,
            }, timeout=25)
        except requests.RequestException as e:
            # Graph stalls the connection rather than erroring when the thread
            # scan is too big, so this IS the timeout signal — keep walking the
            # ladder down instead of giving up.
            last_err = f"{type(e).__name__}: {e}"
            continue

        if r.status_code == 200:
            thread_ids = [t.get("id") for t in (r.json() or {}).get("data", []) if t.get("id")]
            break

        last_err = r.text[:300]
        # 2534084 = the thread-count timeout; anything else won't improve
        # by asking for fewer, so stop early.
        if "2534084" not in (last_err or ""):
            break

    if not thread_ids:
        log_event("error", "ig_poller.fetch",
                  "Could not list conversations at any limit",
                  payload={"response": last_err, "limits_tried": POLL_THREAD_LIMITS})
        return

    # Phase 2: hydrate each thread individually — cheap enough to succeed.
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
    threads = []
    for tid in thread_ids:
        try:
            d = requests.get(f"{base}/{tid}", params={
                "fields": "participants,updated_time,"
                          f"messages.limit({POLL_MESSAGE_LIMIT})"
                          "{id,message,from,to,created_time}",
                "access_token": token,
            }, timeout=20)
        except requests.RequestException as e:
            log_event("error", "ig_poller.thread", f"Network error on {tid}: {e}")
            continue

        if d.status_code != 200:
            log_event("error", "ig_poller.thread",
                      f"Thread fetch failed ({d.status_code})",
                      payload={"thread": tid, "response": d.text[:300]})
            continue

        threads.append(d.json())

    new_count = 0
    for thread in threads:
        new_count += _process_thread(thread)

    log_event("info", "ig_poller.cycle",
              f"Polled {len(threads)} threads, processed {new_count} new messages",
              payload={"threads": len(threads), "new_messages": new_count})


def _process_thread(thread: dict) -> int:
    """
    Process a single thread. Returns count of new messages routed.
    A message is "new" if no Message row exists with that external mid.
    """
    from app import db
    from app.models import Message, User
    from app.services import process_message

    # Build a quick id → username map from this thread's participants.
    participant_usernames = {
        p.get("id"): p.get("username")
        for p in (thread.get("participants") or {}).get("data", [])
        if p.get("id") and p.get("username")
    }

    # Patch User.name for every participant in this thread, regardless of
    # whether they have new unprocessed messages. This catches users created
    # via webhook (whose messages are already saved and would be deduped out
    # of the loop below) and ensures their username shows in the UI.
    our_ig_id = os.getenv("IG_BUSINESS_ACCOUNT_ID")
    our_page_id = os.getenv("FB_PAGE_ID")
    skip_ids = {x for x in (our_ig_id, our_page_id) if x}
    try:
        for participant_id, username in participant_usernames.items():
            if participant_id in skip_ids:
                continue  # don't patch our own business account
            user_row = User.query.filter_by(
                external_id=participant_id, channel="instagram_dm"
            ).first()
            if user_row and user_row.name != username:
                user_row.name = username
                db.session.commit()
    except Exception as e:
        log_event("error", "ig_poller.username_patch",
                  f"Failed to patch usernames: {e}",
                  payload={"error": str(e)})
        try:
            db.session.rollback()
        except Exception:
            pass

    # Identify which participant is the BUSINESS (us) vs the CUSTOMER.
    # We assume IG_PAGE_ACCESS_TOKEN belongs to the business account, so
    # the business participant is whoever sent the most recent OUTBOUND
    # message. Simpler heuristic: anyone matching our IG user ID env var,
    # falling back to the participant that ISN'T the message sender.
    our_ig_id = os.getenv("IG_BUSINESS_ACCOUNT_ID")
    our_page_id = os.getenv("FB_PAGE_ID")
    our_ids = {x for x in (our_ig_id, our_page_id) if x}

    messages = (thread.get("messages") or {}).get("data") or []
    if not messages:
        return 0

    # Graph API returns messages newest-first. Reverse so we process in order.
    messages_chronological = list(reversed(messages))

    processed = 0
    for msg in messages_chronological:
        mid = msg.get("id")
        text = msg.get("message")
        sender = (msg.get("from") or {})
        sender_id = sender.get("id")

        if not mid or not text or not sender_id:
            continue

        # Don't auto-reply to history the poll happened to return.
        if _is_too_old(msg.get("created_time")):
            continue

        # Skip our own outbound messages — those are already in the DB
        # (we wrote them when sending) and shouldn't be reprocessed.
        # Could be tagged with EITHER the IG business account ID OR the
        # FB Page ID depending on which API was used to send.
        if sender_id in our_ids:
            continue

        # Dedupe: have we already saved a message with this Graph mid?
        # We store the mid in Message.content_external_id if you have such a
        # column. Falling back: dedupe by (user external_id + text + created_time)
        # which is approximate but works at our scale.
        from app.models import User
        already_exists = (
            Message.query
            .join(User, Message.user_id == User.id)
            .filter(
                Message.channel == "instagram_dm",
                Message.content == text,
                User.external_id == sender_id,
            )
            .first()
        )

        if already_exists:
            continue

        # Route through the same pipeline as webhooks
        try:
            process_message(message=text, user_id=sender_id, channel="instagram_dm", external_id=mid)
            processed += 1

            # Patch the customer's User.name from the IG participant data,
            # so the platform UI shows "wittyselene" instead of the numeric ID.
            username = participant_usernames.get(sender_id)
            if username:
                user_row = User.query.filter_by(
                    external_id=sender_id, channel="instagram_dm"
                ).first()
                if user_row and user_row.name != username:
                    user_row.name = username
                    db.session.commit()
        except Exception as e:
            log_event("error", "ig_poller.process",
                      f"Failed to process message {mid}: {e}",
                      payload={"sender_id": sender_id, "mid": mid})

    return processed