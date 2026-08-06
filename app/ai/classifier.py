"""
app/ai/classifier.py
LLM-based inbound classification via Claude Haiku — replaces brittle keyword
intent detection with semantic understanding, and adds smart handoff detection
(explicit human requests, abuse, strong frustration).

Falls back to keyword detection on ANY failure (or in mock mode) so the
message pipeline never breaks.
"""

import os
import json

from app.utils.intent import detect_intents
from app.utils.logger import log_event
from app.ai.generator import first_text

USE_MOCK_AI = os.getenv("USE_MOCK_AI", "false").lower() == "true"

VALID_INTENTS = {
    "greeting", "stock_inquiry", "price_inquiry", "product_inquiry",
    "delivery_inquiry", "order_status", "complaint", "order_request",
    "praise", "unknown",
}

# Intents that carry no request. A public comment whose intents are ALL in this
# set is someone being nice, not someone waiting on us — see
# services.py::_is_praise_only. "unknown" is deliberately NOT here: it means the
# classifier couldn't tell, which is a reason to look closer, not to assume
# there is nothing to answer.
NON_ACTIONABLE_INTENTS = {"praise"}
VALID_HANDOFF_REASONS = {"explicit_human_request", "abuse", "frustration",
                         "complaint", "ready_to_order"}

_SYSTEM = """You classify inbound customer messages for a Kenyan fashion & beauty store's support assistant. Reply with ONLY a JSON object — no prose, no code fences.

Schema:
{"intents": [ ... ], "handoff": {"should": true|false, "reason": "explicit_human_request"|"abuse"|"frustration"|"complaint"|null}}

Allowed intents: greeting, stock_inquiry, price_inquiry, product_inquiry, delivery_inquiry, order_status, complaint, order_request, praise, unknown.

Intent guidance:
- Include EVERY intent that applies (a message can have several).
- Read meaning, not keywords: "you restock the tan mules?" -> ["stock_inquiry","product_inquiry"].
- Use "unknown" ONLY when nothing else fits.
- praise: compliments, excitement, emoji-only reactions, tagging a friend — anything appreciative that asks for NOTHING. "Love this 😍", "🔥🔥🔥", "gorgeous!", "@amina look". This decides whether a PUBLIC comment gets a reply at all, so it must be exact: return praise ALONE only when there is genuinely nothing to answer. If the message compliments AND asks something ("obsessed! does it come in navy?"), return praise together with the real intent — the question still gets answered.
- order_request: they want to BUY, and want us to handle it rather than checking out on the website. "How do I order?", "I want to buy this", "can you place the order for me", "how do I pay", "I'll take it". This is someone with their wallet out — not merely asking about a product. Price and stock questions on their own are NOT order_request.

Handoff — set should=true ONLY when a human is genuinely needed:
- ready_to_order: intent order_request applies — they want to place an order through us. A person has to take it from here, so hand off.
- explicit_human_request: they want a person ("get me a human", "can I talk to someone", "is anyone real").
- abuse: insults, hostility, threats, profanity aimed at the store ("you're stupid").
- frustration: STRONG frustration / clear escalation demand ("this is unacceptable", angrily demanding a refund).
- complaint: a real problem needing a person (wrong/damaged/missing item, payment issue).
Otherwise should=false with reason=null — mild dissatisfaction and ordinary questions should let the assistant try first."""


def _fallback(message):
    # `degraded` matters to the caller: the keyword detector has no concept of
    # praise, so a praise-only comment comes back as ["unknown"] here. Anything
    # deciding whether a public comment deserves a reply has to know the AI
    # never actually looked, and fall back to the old heuristic instead of
    # treating "not praise" as a judgement that was made.
    return {"intents": detect_intents(message),
            "handoff": {"should": False, "reason": None},
            "degraded": True}


def classify_message(message: str, history=None) -> dict:
    """
    Returns {"intents": [...], "handoff": {"should": bool, "reason": str|None}}.
    Never raises — degrades to keyword detection on any problem.
    """
    text = (message or "").strip()
    if not text:
        return {"intents": ["unknown"], "handoff": {"should": False, "reason": None},
                "degraded": True}
    if USE_MOCK_AI:
        return _fallback(text)

    try:
        import anthropic
        from flask import current_app

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        model = current_app.config.get("CLASSIFIER_MODEL") or current_app.config.get("CLAUDE_MODEL", "claude-haiku-4-5")

        # A little history helps judge escalation (e.g. repeated frustration).
        msgs = []
        if history:
            for h in history[-4:]:
                role, content = h.get("role"), h.get("content")
                if role in ("user", "assistant") and content:
                    msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": text})

        resp = client.messages.create(
            model=model,
            max_tokens=200,
            system=_SYSTEM,
            messages=msgs,
        )
        raw = first_text(resp).strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        intents = [i for i in data.get("intents", []) if i in VALID_INTENTS] or ["unknown"]
        h = data.get("handoff") or {}
        should = bool(h.get("should"))
        reason = h.get("reason") if h.get("reason") in VALID_HANDOFF_REASONS else None
        if should and reason is None:
            reason = "ai_detected"

        log_event("info", "ai.classifier",
                  f"Classified: intents={intents} handoff={should}",
                  payload={"intents": intents, "handoff_should": should, "handoff_reason": reason})
        return {"intents": intents, "handoff": {"should": should, "reason": reason},
                "degraded": False}

    except Exception as e:
        log_event("warn", "ai.classifier.fallback",
                  f"Classifier failed, keyword fallback: {str(e)[:200]}")
        return _fallback(text)