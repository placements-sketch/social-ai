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
from datetime import datetime

import requests
from app.utils.logger import log_event

GRAPH_API_VERSION = "v25.0"

def _conversations_url():
    """Build the FB Graph conversations URL for the configured Page."""
    import os
    page_id = os.getenv("FB_PAGE_ID")
    if not page_id:
        return None
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/conversations"

POLL_INTERVAL_SECONDS = 60

# Module-level guard so we don't start the thread twice in debug mode
# (Flask debug reloader spawns a second process; only the reloader-child
# should start the poller).
_poller_started = False
_poller_lock = threading.Lock()


def start_poller(app):
    """
    Spawn the polling background thread. Called once from create_app().
    Idempotent — safe to call multiple times.
    """
    global _poller_started
    with _poller_lock:
        if _poller_started:
            return
        if os.getenv("IG_POLL_ENABLED", "true").lower() != "true":
            log_event("info", "ig_poller", "IG poller disabled via IG_POLL_ENABLED env var")
            return
        if not os.getenv("FB_ACCESS_TOKEN"):
            log_event("warning", "ig_poller", "FB_ACCESS_TOKEN not set — poller will not start")
            return
        if not os.getenv("FB_PAGE_ID"):
            log_event("warning", "ig_poller", "FB_PAGE_ID not set — poller will not start")
            return

        thread = threading.Thread(
            target=_poller_loop,
            args=(app,),
            daemon=True,
            name="ig_poller",
        )
        thread.start()
        _poller_started = True
        log_event("info", "ig_poller", "Instagram DM poller started (60s interval)")


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
    token = os.getenv("FB_ACCESS_TOKEN")
    url = _conversations_url()

    # TEMP DEBUG
    print(f"[POLL DEBUG] token first 30 chars: {(token or '')[:30]}")
    print(f"[POLL DEBUG] page id env: {os.getenv('FB_PAGE_ID')}")
    print(f"[POLL DEBUG] url: {url}")
    
    if not token or not url:
        return

    params = {
        "platform": "instagram",
        "fields": "id,messages{id,message,from,to,timestamp},participants,updated_time",
        "access_token": token,
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            log_event("error", "ig_poller.fetch",
                      f"Conversations fetch failed ({r.status_code})",
                      payload={"response": r.text[:400]})
            return

        threads = (r.json() or {}).get("data", [])
    except requests.RequestException as e:
        log_event("error", "ig_poller.fetch", f"Network error: {e}")
        return

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
    from app.models import Message
    from app.services import process_message

    # Identify which participant is the BUSINESS (us) vs the CUSTOMER.
    # We assume IG_PAGE_ACCESS_TOKEN belongs to the business account, so
    # the business participant is whoever sent the most recent OUTBOUND
    # message. Simpler heuristic: anyone matching our IG user ID env var,
    # falling back to the participant that ISN'T the message sender.
    our_ig_id = os.getenv("IG_BUSINESS_ACCOUNT_ID")

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

        # Skip our own outbound messages — those are already in the DB
        # (we wrote them when sending) and shouldn't be reprocessed.
        if our_ig_id and sender_id == our_ig_id:
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
            process_message(message=text, user_id=sender_id, channel="instagram_dm")
            processed += 1
        except Exception as e:
            log_event("error", "ig_poller.process",
                      f"Failed to process message {mid}: {e}",
                      payload={"sender_id": sender_id, "mid": mid})

    return processed