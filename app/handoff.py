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


# Default keywords that escalate. Easy to extend; later move to AISettings.
HANDOFF_KEYWORDS = [
    "refund", "complaint", "complain", "speak to manager", "manager",
    "lawyer", "legal", "lawsuit", "sue", "cancel my order", "cancel order",
    "angry", "furious", "scam", "fraud", "broken", "damaged", "missing",
    "never received", "where is my order", "wrong item",
]

# Intents from detect_intents() that escalate.
HANDOFF_INTENTS = {"complaint"}

# Bridging reply. Hard-coded for now — wired to AISettings in a later milestone.
BRIDGING_REPLY = (
    "Thanks for reaching out — I'm connecting you with a member of our team "
    "who'll get back to you shortly. We appreciate your patience."
)


def check_handoff(message: str, intents: list[str], conversation: Conversation) -> dict | None:
    """
    Decide whether this message should hand the conversation off to a human.

    Returns:
        - dict with {'reason': 'keyword'|'intent'|'rule', 'detail': str,
                     'bridging_reply': str} if handoff triggered
        - None if AI should continue handling
    """
    text = (message or "").lower()

    # 1. Keyword trigger
    for kw in HANDOFF_KEYWORDS:
        if kw in text:
            return _trigger(conversation, reason="keyword", detail=kw)

    # 2. Intent trigger
    matched_intent = next((i for i in (intents or []) if i in HANDOFF_INTENTS), None)
    if matched_intent:
        return _trigger(conversation, reason="intent", detail=matched_intent)

    # 3. Automation rule trigger
    rule_match = _match_automation_rule(text)
    if rule_match:
        return _trigger(conversation, reason="rule", detail=rule_match.name)

    return None


def _trigger(conversation: Conversation, reason: str, detail: str) -> dict:
    """Flip the conversation into human_override and record the handoff."""
    from app.assignment import pick_next_agent

    conversation.ai_enabled = False
    conversation.status = "human_override"
    conversation.handoff_reason = reason
    conversation.updated_at = datetime.utcnow()

    # Auto-assign to the agent with the lightest current load.
    # Skip if already assigned (e.g. agent was already handling it).
    if conversation.assigned_to is None:
        agent = pick_next_agent()
        if agent is not None:
            conversation.assigned_to = agent.id
            conversation.assigned_at = datetime.utcnow()
            conversation.assigned_by = None  # system-assigned, no human actor
            log_event("info", "handoff",
                      f"Auto-assigned conversation {conversation.id} to agent {agent.email}")

    log_row = Log(
        level="info",
        source="handoff",
        message=f"Handoff triggered ({reason}: {detail})",
        conversation_id=conversation.id,
        payload={"reason": reason, "detail": detail},
    )
    db.session.add(log_row)
    db.session.commit()

    log_event("info", "handoff",
              f"Conversation {conversation.id} handed off — {reason}: {detail}")

    return {
        "reason": reason,
        "detail": detail,
        "bridging_reply": BRIDGING_REPLY,
    }


def _match_automation_rule(text: str) -> AutomationRule | None:
    """
    Find an enabled automation rule whose action escalates and whose trigger
    keywords appear in the message.

    A rule's `trigger` is treated as a comma-separated list of keywords
    embedded somewhere in its text (matches existing seed format like
    'Message contains: "price", "how much", "bei"'). Crude but effective.
    """
    escalation_terms = ("notify_agent", "escalate", "human", "flag for human")

    rules = AutomationRule.query.filter_by(enabled=True).all()
    for rule in rules:
        action_lc = (rule.action or "").lower()
        if not any(t in action_lc for t in escalation_terms):
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

