"""
app/handoff.py
Detects when an inbound message should trigger AI-to-human handoff.

Triggers (in priority order):
  1. Keyword match (refund, complaint, lawyer, etc.) — fastest, no DB hits
  2. Intent match (complaint, order_status from detect_intents) — uses
     already-computed intents
  3. Automation rule match — any AutomationRule whose action contains
     "notify_agent" / "escalate" / "human" and whose trigger keywords are
     present in the message

When a trigger fires:
  - Conversation.ai_enabled set to False
  - Conversation.status set to 'human_override'
  - Conversation.handoff_reason set to 'keyword' | 'intent' | 'rule'
  - A Log row records what triggered it (full history)
  - Returns the bridging reply text (configurable later)
"""

from datetime import datetime, timezone

from app import db
from app.models import Conversation, AutomationRule, Log
from app.utils.logger import log_event
from app.notifications import create_notification

# Fallback keywords, used ONLY when the classifier could not read the message.
#
# These used to run first and win outright, which had two costs. The obvious
# one: no list can cover every way a person asks for help, so anything phrased
# outside the vocabulary was never escalated by this path at all. The less
# obvious one, and the more expensive: a bare word match cannot tell a problem
# from a mention of one. Every line below escalates a conversation the assistant
# could have handled —
#
#   "is the zip on this one broken like the reviews say?"   -> broken
#   "am I missing something, is there a discount code?"      -> missing
#   "do you do refunds if the size is wrong?"                -> refund, wrong item
#   "who's the manager of the Moi Avenue shop?"              -> manager
#
# — and each one pulls an agent onto a question with an answer in the catalogue.
#
# The classifier reads meaning and decides now. This list survives as the
# degraded path, on the same reasoning as the praise gate in services.py: when
# the AI is unavailable, an over-eager keyword is the safer failure. A customer
# routed to a person unnecessarily is inconvenienced; an abuse or complaint left
# with a bot is not.
HANDOFF_KEYWORDS = [
    "refund", "complaint", "complain", "speak to manager", "manager",
    "lawyer", "legal", "lawsuit", "sue", "cancel my order", "cancel order",
    "angry", "furious", "scam", "fraud", "broken", "damaged", "missing",
    "never received", "where is my order", "wrong item",
]

# Intents from detect_intents() that escalate.
# A customer ready to order is escalated for a different reason from a customer
# with a problem: nothing is wrong, but nobody can take the order except a
# person. Handing it to a human IS the service, not a failure of the AI.
HANDOFF_INTENTS = {"complaint", "order_request"}

# Bridging reply. Hard-coded for now — wired to AISettings in a later milestone.
BRIDGING_REPLY = (
    "Thanks for reaching out — I'm connecting you with a member of our team "
    "who'll get back to you shortly. We appreciate your patience."
)


def check_handoff(message: str, intents: list[str], conversation: Conversation,
                  llm_handoff: dict | None = None) -> dict | None:
    """
    Decide whether this message should hand the conversation off to a human.

    The classifier decides. It has read the message; a keyword list has only
    seen the words. The list of situations needing a person cannot be
    enumerated — a legal threat, a wholesale enquiry, a press request, a
    safety issue, someone stuck in a loop the assistant keeps failing to
    understand — and every attempt to enumerate it both misses cases and
    invents them out of innocent phrasing.

    Order, and why:

      1. Automation rules. An admin configured this deliberately; it is a
         standing instruction, not a guess, so it outranks a judgement call.
      2. The classifier's verdict, plus the escalating intents it returns
         (complaint, order_request) — also its reading, arrived at separately.
      3. Keywords, ONLY when the classifier is unavailable.

    Returns a handoff dict or None.
    """
    text = (message or "").lower()
    degraded = bool((llm_handoff or {}).get("degraded"))

    # 1. Automation rule trigger — explicit configuration wins.
    rule_match = _match_automation_rule(text)
    if rule_match:
        return _trigger(conversation, reason="rule", detail=rule_match.name)

    # 2. The classifier's own reading, in both the forms it produces: the
    #    handoff verdict, and the intents that always need a person. Both come
    #    from the same pass over the message.
    if not degraded:
        if llm_handoff and llm_handoff.get("should"):
            return _trigger(conversation, reason="ai_detected",
                            detail=llm_handoff.get("reason") or "smart_detection")

        matched_intent = next((i for i in (intents or []) if i in HANDOFF_INTENTS), None)
        if matched_intent:
            return _trigger(conversation, reason="intent", detail=matched_intent)

        # The classifier read it and saw nothing needing a person. Trust that
        # and stop — running the keyword list here anyway would reinstate every
        # false positive it was moved out of the way to avoid.
        return None

    # 3. Degraded: the classifier never saw the message. `intents` came from the
    #    keyword detector, so both checks below are the same fallback tier.
    import re
    matched_intent = next((i for i in (intents or []) if i in HANDOFF_INTENTS), None)
    if matched_intent:
        return _trigger(conversation, reason="intent", detail=matched_intent)

    for kw in HANDOFF_KEYWORDS:
        if re.search(rf'\b{re.escape(kw)}\b', text):
            log_event("info", "handoff.keyword_fallback",
                      f"Classifier unavailable — escalated on the word '{kw}'",
                      payload={"keyword": kw, "channel": conversation.channel},
                      conversation_id=conversation.id)
            return _trigger(conversation, reason="keyword", detail=kw)

    return None

def _bridging_reply_for(reason: str, detail: str, channel: str | None = None) -> str:
    """
    Short, human handoff line based on WHY we're escalating. Defaults to the
    standard BRIDGING_REPLY; only overrides where that tone doesn't fit —
    e.g. abuse, where a warm "we appreciate your patience" can read as tone-deaf.
    """
    key = (detail or "").lower()
    if key in ("order_request", "ready_to_order"):
        # Both versions ask for the same three things, so the agent picking this
        # up already has the size and location instead of starting the exchange
        # from scratch — one less round trip while the customer is still keen.
        #
        # But WHERE they are changes the instruction completely. Under a public
        # comment we have to move them to DMs; if they are already in the DM,
        # "send us a DM" is nonsense and reads as a bot that has not noticed
        # where it is. Same request, two openings.
        if (channel or "").endswith("_comment"):
            return ("Hi! Simply send us a DM with the item you'd like, your "
                    "preferred size, and your location, and we'll assist you "
                    "with your order.")
        return ("Lovely! Just send us the item you'd like, your preferred "
                "size, and your location, and someone from our team will take "
                "it from here.")
    if key == "abuse":
        return ("I hear you, and I want to get this sorted properly. "
                "Let me bring in someone from our team to help you directly — one moment.")
    if key in ("frustration", "complaint"):
        return ("I'm really sorry about this. Let me get a team member to look into it "
                "for you right away — one moment.")
    from app.settings import get_section
    return get_section("handoff").get("bridging_reply") or BRIDGING_REPLY

def _trigger(conversation: Conversation, reason: str, detail: str) -> dict:
    """Flip the conversation into human_override and record the handoff."""
    from app.assignment import pick_next_agent

    now = datetime.utcnow()
    conversation.ai_enabled = False
    conversation.status = "human_override"
    # "Ready to order" is recorded as its own reason rather than the generic
    # "intent". The inbox has to be able to tell an escalation that is GOOD NEWS
    # — someone wants to buy — from one that means something went wrong, and
    # only `reason` reaches the conversation row; `detail` lives in the log
    # where no badge can see it. Everything else keeps its existing value.
    conversation.handoff_reason = (
        'ready_to_order'
        if (detail or '').lower() in ('order_request', 'ready_to_order')
        else reason
    )
    conversation.updated_at = now
    # Stamp WHEN, so analytics can count escalations that happened in a window
    # rather than conversations that merely have one in their history.
    conversation.escalated_at = now
    conversation.ai_disabled_at = now

    # Auto-assign to the agent with the lightest current load.
    # Skip if already assigned (e.g. agent was already handling it).
    if conversation.assigned_to is None:
        agent = pick_next_agent()
        if agent is not None:
            conversation.assigned_to = agent.id
            conversation.assigned_at = datetime.utcnow()
            conversation.assigned_by = None

            log_event("info", "handoff.auto_assigned",
                      f"Conversation {conversation.id} auto-assigned to {agent.full_name}",
                      # Name and email included because the activity feed reads
                      # them straight from here — without them the line rendered
                      # as "Auto-assigned to undefined", which is exactly the
                      # moment you need to know WHO picked it up.
                      payload={"agent_id": agent.id,
                               "agent_name": agent.full_name,
                               "agent_email": getattr(agent, 'email', None),
                               "reason": reason, "detail": detail},
                      conversation_id=conversation.id)

            # Notify the assigned agent — this is what was missing, so agents
            # got escalations dropped on them silently (nothing in the modal,
            # no toast on login).
            try:
                from app.notifications import create_notification
                handle = conversation.user.handle if conversation.user else 'a customer'
                channel_label = conversation.channel.replace('_', ' ')
                ready = (detail or '').lower() in ('order_request', 'ready_to_order')
                create_notification(
                    user_id=agent.id,
                    type_='escalation_assigned',
                    title=("Ready to order — assigned to you" if ready
                           else "New escalation assigned to you"),
                    body=(f"{handle} on {channel_label} wants to place an order."
                          if ready
                          else f"{handle} on {channel_label} — reason: {detail or reason}"),
                    severity='urgent',
                    resource_type='conversation',
                    resource_id=conversation.id,
                    actor_id=None,   # system-triggered
                )
            except Exception as e:
                log_event("error", "handoff.auto_assign_notify_fail",
                          f"create_notification failed: {e}",
                          conversation_id=conversation.id)
            # ... keep your existing log_event + create_notification block ...
        else:
            # Nobody eligible — leave it in the unassigned human_override queue
            # and alert supervisors so someone can step in / rebalance.
            log_event("warn", "handoff.auto_assign_deferred",
                      f"No available agent for conversation {conversation.id} — queued",
                      payload={
                          "channel": conversation.channel,
                          "reason": reason,
                          "detail": detail,
                      },
                      conversation_id=conversation.id)
            try:
                from app.notifications import notify_admins
                notify_admins(
                    type_='assignment_deferred',
                    title="Escalation waiting — no available agent",
                    # "offline or at capacity" was the only reason this could
                    # happen. Auto-assignment now also declines to hand a chat
                    # to an agent whose address cannot receive mail, and naming
                    # one cause for two states sends people looking in the
                    # wrong place.
                    body=(f"A {conversation.channel.replace('_',' ')} chat needs a human but "
                          f"no agent could be assigned - they are at capacity, or their "
                          f"accounts have no reachable email address. See the logs for "
                          f"assignment.no_reachable_agent."),
                    severity='warning',
                    resource_type='conversation',
                    resource_id=conversation.id,
                    actor_id=None,
                    coalesce=True,
                )
            except Exception as e:
                log_event("error", "handoff.notify_supervisors_fail",
                          f"notify_admins failed: {e}", conversation_id=conversation.id)
                
    # Notify supervisors and admins of the escalation.
    # No actor_id — this is system-triggered, not user-triggered.
    # Skip the auto-assigned agent (if any) since they already got their own notification.
    try:
        from app.notifications import notify_supervisors
        handle = conversation.user.handle if conversation.user else 'a customer'
        channel_label = conversation.channel.replace('_', ' ')
        assignee_blurb = ''
        if conversation.assigned_to:
            from app.models import AuthUser
            assignee = AuthUser.query.get(conversation.assigned_to)
            if assignee:
                assignee_blurb = f" Auto-assigned to {assignee.full_name}."

        # A sale and a complaint are both "urgent", but they are not the same
        # news. Sending an alarm-shaped email about someone wanting to buy
        # trains supervisors to read every escalation as a problem — and the
        # one they should move fastest on is the one they would learn to
        # dread. Same delivery, honest framing.
        wants_to_order = (detail or '').lower() in ('order_request', 'ready_to_order')
        if wants_to_order:
            notif_title = f"Ready to order: {handle}"
            notif_body = (f"{handle} wants to place an order on {channel_label} "
                          f"and needs someone to take it.{assignee_blurb}")
        else:
            notif_title = f"Conversation escalated ({reason}): {handle}"
            notif_body = f"Reason: {detail}. Channel: {channel_label}.{assignee_blurb}"

        notify_supervisors(
            type_='conversation_escalated',
            title=notif_title,
            body=notif_body,
            severity='urgent',
            resource_type='conversation',
            resource_id=conversation.id,
            coalesce=False,  # each escalation is worth seeing on its own
        )
    except Exception as e:
        log_event("error", "handoff.notify_supervisors_fail",
                  f"notify_supervisors failed: {e}",
                  payload={"conversation_id": conversation.id, "error": str(e)},
                  conversation_id=conversation.id)

    db.session.commit()

    log_event("info", "handoff.triggered",
              f"Conversation {conversation.id} handed off — {reason}: {detail}",
              payload={
                  "reason": reason,
                  "detail": detail,
                  "channel": conversation.channel,
                  "handle": (conversation.user.handle if conversation.user else None),
              },
              conversation_id=conversation.id)
    
    return {
        "reason": reason,
        "detail": detail,
        "bridging_reply": _bridging_reply_for(reason, detail, conversation.channel),
    }


def escalate_ai_unavailable(conversation_id: int, failure_reason: str | None = None) -> dict | None:
    """
    Hand a conversation to a person because the AI could not answer at all.

    Every other escalation in this file is a judgement about the CUSTOMER —
    they are upset, they want to buy, they asked for a human. This one is about
    US: the model refused, timed out or ran out of credit, and there is no
    answer to send. The customer is owed a person either way.

    Reason is recorded as `ai_unavailable` rather than folded into the generic
    escalation bucket, because these two questions have different answers and
    both get asked: "how many customers needed a human?" and "how many times
    did our AI fall over?" A conversation escalated for a complaint is the
    system working; one escalated because the API was out of credit is not.

    Returns the same shape as _trigger(), or None if there is nothing to
    escalate — a failure with no conversation behind it is still logged by the
    generator, it just has no thread to route.
    """
    if not conversation_id:
        return None

    conversation = Conversation.query.get(conversation_id)
    if conversation is None:
        return None

    # Already with a human. Escalating again would reassign the thread and fire
    # a second round of notifications at whoever is mid-conversation with them.
    if conversation.status == "human_override" and conversation.assigned_to:
        log_event("info", "handoff.ai_unavailable_skipped",
                  f"Conversation {conversation.id} already with an agent — "
                  f"AI failure not re-escalated",
                  payload={"failure_reason": failure_reason},
                  conversation_id=conversation.id)
        return None

    return _trigger(conversation, "ai_unavailable", failure_reason or "generation_failed")


def _match_automation_rule(text: str) -> AutomationRule | None:
    """
    Find an enabled automation rule whose action escalates and whose trigger
    keywords appear in the message.

    A rule's `trigger` is treated as a comma-separated list of keywords
    embedded somewhere in its text (matches existing seed format like
    'Message contains: "price", "how much", "bei"'). Crude but effective.
    """
    # Escalating actions, named structurally. This used to be decided purely by
    # substring-matching the free-text `action` column for "human"/"escalate" —
    # so a rule escalated because of how somebody worded its DESCRIPTION, not
    # because of what it was configured to do. Both live escalation rules were
    # firing by that accident; rewording "Flag for human review" to "Send to an
    # agent" would have silently switched them off.
    #
    # The set lives in automation.py, which also uses it to decide whether a
    # rule is genuinely unreachable — one definition, so the two cannot drift.
    from app.automation import ESCALATION_ACTION_TYPES as ESCALATING_ACTIONS
    escalation_terms = ("notify_agent", "escalate", "human", "flag for human")

    rules = AutomationRule.query.filter_by(enabled=True).all()
    for rule in rules:
        atype = ((rule.action_config or {}).get("type") or "").lower()
        action_lc = (rule.action or "").lower()
        # Structured type first; the text match stays as a fallback so rules
        # created before action_config existed keep working.
        if atype not in ESCALATING_ACTIONS and not any(t in action_lc for t in escalation_terms):
            continue

        # Extract quoted keywords from the trigger field.
        trigger_lc = (rule.trigger or "").lower()
        # very small parser: take anything between double-quotes
        import re
        quoted = re.findall(r'"([^"]+)"', trigger_lc)
        if not quoted:
            # fall back to splitting on comma and stripping
            quoted = [w.strip().strip("'\"") for w in trigger_lc.split(",") if w.strip()]

        if any(kw in text for kw in quoted):
            return rule

    return None

