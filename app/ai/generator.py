"""
app/ai/generator.py
AI reply generation using Anthropic Claude.

Accepts a LIST of intents so Claude can address every question in a single reply.

To activate real Claude calls:
  1. pip install anthropic
  2. Set ANTHROPIC_API_KEY in .env
  3. Set USE_MOCK_AI = False below
"""

import time
from app.utils.logger import log_event

import os
USE_MOCK_AI = os.getenv("USE_MOCK_AI", "false").lower() == "true"

# ─────────────────────────────────────────────
# AISettings → prompt translation helpers
# ─────────────────────────────────────────────

_TONE_DIRECTIVES = {
    'friendly':    "Tone: warm and approachable, like a helpful friend. Use natural conversational language.",
    'luxury':      "Tone: refined and sophisticated. Use elegant vocabulary. Avoid slang or abbreviations.",
    'gen_z':       "Tone: playful and current. Use casual phrasing naturally where it fits. Occasional lowercase is fine.",
    'minimalist':  "Tone: brief and direct. No fluff or filler. Get to the answer in as few words as possible.",
    'bold_sales':  "Tone: confident and persuasive. Highlight value and momentum. Move toward a purchase.",
}


def _slider_bucket(value: int, buckets: list[tuple[int, str]]) -> str:
    """Pick the bucket directive matching the slider's 0-100 value."""
    for ceiling, directive in buckets:
        if value <= ceiling:
            return directive
    return buckets[-1][1]


def _formal_directive(value: int) -> str:
    return _slider_bucket(value, [
        (25,  "Use casual language freely. Contractions are good (you're, we'll, that's)."),
        (50,  "Lean casual but stay polite. Mix contractions and full forms naturally."),
        (75,  "Lean professional. Avoid slang. Light contractions are fine."),
        (100, "Use formal language. No contractions. Address the customer respectfully."),
    ])


def _length_directive(value: int) -> str:
    return _slider_bucket(value, [
        (25,  "Keep replies under 2 sentences when possible."),
        (50,  "Aim for 2-3 sentences. Concise but complete."),
        (75,  "4-6 sentences is fine. Provide context where useful."),
        (100, "Be thorough — up to 8 sentences. Anticipate follow-up questions."),
    ])


def _sales_directive(value: int) -> str:
    return _slider_bucket(value, [
        (25,  "Just answer the question. No upselling, no calls to action."),
        (50,  "Answer the question first. Light sales nudge only if naturally relevant."),
        (75,  "After answering, suggest a related product or invite them to order if it fits."),
        (100, "Every reply should move toward a sale. Close with a clear call to action (e.g., 'Would you like to place an order?')."),
    ])


def _rules_directives(rules: dict) -> list[str]:
    """Translate response_rules JSON into prompt instructions."""
    out = []
    if rules.get('auto_greet'):
        out.append("If this is the customer's first message in the conversation, start with a brief greeting.")
    if rules.get('mention_delivery_in_kenya'):
        out.append("When relevant, naturally mention that you deliver across Kenya.")
    if rules.get('use_emoji'):
        out.append("Use emojis sparingly (1-2 per reply maximum) where they feel natural.")
    else:
        out.append("Do not use emojis.")
    if rules.get('always_offer_alternatives_when_out_of_stock'):
        out.append("If a product is out of stock, suggest 1-2 similar alternatives or offer to notify when restocked.")
    return out


def _load_ai_settings():
    """
    Load the active AISettings row. Returns None if loading fails — the
    caller will fall back to defaults so a DB hiccup never blocks a reply.
    """
    try:
        from app.models import AISettings
        return AISettings.query.get(1)
    except Exception as e:
        log_event("warn", "ai.generator.settings_load_failed",
                  f"Could not load AI settings, using defaults: {e}")
        return None

def generate_reply(message: str, intents: list[str], context_data: dict, channel: str,
                   history: list[dict] | None = None) -> dict:
    """
    Generates a customer support reply that addresses ALL detected intents.
    
    Args:
        message:      The customer's original message.
        intents:      All detected intents e.g. ["stock_inquiry", "price_inquiry"]
        context_data: Dict with product, stock, delivery_asked, etc. from Shopify.
        channel:      'instagram_dm' | 'instagram_comment' | 'whatsapp' | etc.
        history:      Optional list of prior turns, each {'role': 'user'|'assistant', 'content': str}

    Returns:
        Dict with:
          reply       (str)    - the text to send to the customer
          elapsed_ms  (int)    - how long the call took
          tokens_used (int)    - input + output tokens, or 0 if mock/failure
          model       (str)    - the model that responded, or 'mock'
    """
    start = time.perf_counter()
    if USE_MOCK_AI:
        result = {
            'reply':       _mock_reply(intents, context_data),
            'tokens_used': 0,
            'model':       'mock',
        }
    else:
        result = _claude_reply(message, intents, context_data, channel, history=history)
    result['elapsed_ms'] = int((time.perf_counter() - start) * 1000)
    return result


# ─────────────────────────────────────────────
# Mock reply — no API key needed
# ─────────────────────────────────────────────

def _mock_reply(intents: list[str], context_data: dict) -> str:
    """Builds a reply addressing every detected intent. Used during development."""
    product  = context_data.get("product", {})
    stock    = context_data.get("stock", {})
    location = context_data.get("delivery_location")
    parts    = []

    if "greeting" in intents:
        parts.append("Hi there! 👋 Welcome to our store.")

    if "stock_inquiry" in intents:
        name = product.get("name", "that item")
        qty  = stock.get("quantity", 0)
        if qty > 0:
            parts.append(f"Yes, the {name} is available — we have {qty} units in stock! ✅")
        else:
            parts.append(f"Unfortunately the {name} is currently out of stock 😔 "
                         "Would you like to be notified when it's back?")

    if "product_inquiry" in intents:
        name     = product.get("name", "this item")
        variants = product.get("variants", [])
        if variants:
            parts.append(f"It comes in: {', '.join(str(v) for v in variants)}.")
        else:
            desc = product.get("description", "a beautiful piece from our latest collection")
            parts.append(f"Here's more about {name}: {desc}.")

    if "price_inquiry" in intents:
        name  = product.get("name", "this item")
        price = product.get("price", "KES 1,800")
        parts.append(f"The {name} is priced at {price}.")

    if "delivery_inquiry" in intents:
        if location:
            parts.append(f"We deliver to {location}! 🚚 Delivery takes 1–3 business days and costs KES 350.")
        else:
            parts.append("We deliver nationwide across Kenya. 🚚 Delivery costs KES 350 and takes 1–3 business days.")

    if "order_status" in intents:
        parts.append("For your order status, please share your order number and I'll look it up right away.")

    if "complaint" in intents:
        parts.append("I'm really sorry to hear that 😔 Please DM us your order details and we'll make it right.")

    if intents == ["unknown"]:
        return ("Thanks for reaching out! I'm not sure I fully understood your question. "
                "Could you tell me which product you're asking about, or what you'd like to know?")

    if any(i in intents for i in ("stock_inquiry", "product_inquiry", "price_inquiry")):
        parts.append("Would you like to place an order? 😊")

    return " ".join(parts)


# ─────────────────────────────────────────────
# Real Claude reply
# ─────────────────────────────────────────────

def _claude_reply(message: str, intents: list[str], context_data: dict, channel: str,
                  history: list[dict] | None = None) -> dict:
    """
    Calls Anthropic Claude with a system prompt composed from the live AISettings row.
    Returns a dict with reply text, tokens used, and the model that responded.
    On failure, falls back to mock and returns it with zeroed token counts.
    """
    try:
        import anthropic
        from flask import current_app

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        model  = current_app.config.get("CLAUDE_MODEL", "claude-haiku-4-5")
        max_tokens = current_app.config.get("CLAUDE_MAX_TOKENS", 300)

        # ── Build Shopify context block (unchanged from before) ──────────
        context_lines = []

        if "product" in context_data:
            p        = context_data["product"]
            variants = ", ".join(str(v) for v in p.get("variants", [])) or "N/A"
            context_lines.append(
                f"Product: {p.get('name')} | "
                f"Price: {p.get('price')} | "
                f"Variants: {variants} | "
                f"Description: {p.get('description', 'N/A')}"
            )

        if "stock" in context_data:
            s = context_data["stock"]
            context_lines.append(f"Stock (Shopify): {s.get('quantity', 0)} units available")

        if context_data.get("delivery_asked"):
            loc = context_data.get("delivery_location", "their location")
            context_lines.append(
                f"Customer asked about delivery to: {loc}. "
                f"Standard delivery: KES 350, 1–3 business days nationwide."
            )

        if context_data.get("order_status_asked"):
            context_lines.append(
                "Customer asked about an order. Ask for their order number if not provided."
            )

        context_block = "\n".join(context_lines) if context_lines else "No specific product data available."
        intents_str   = ", ".join(intents) if intents else "general inquiry"

        # ── Compose the system prompt from AISettings ────────────────────
        settings = _load_ai_settings()

        if settings is not None:
            base_prompt   = settings.system_prompt
            tone          = settings.tone or 'friendly'
            slider_formal = settings.slider_formal
            slider_length = settings.slider_length
            slider_sales  = settings.slider_sales
            rules         = settings.response_rules or {}
        else:
            # DB failed — use hardcoded fallbacks. Reply still works.
            base_prompt   = ("You are a helpful customer support assistant for a Kenyan "
                             "online fashion and beauty store.")
            tone          = 'friendly'
            slider_formal = 40
            slider_length = 50
            slider_sales  = 60
            rules         = {'use_emoji': True, 'mention_delivery_in_kenya': True}

        tone_line   = _TONE_DIRECTIVES.get(tone, _TONE_DIRECTIVES['friendly'])
        rules_lines = _rules_directives(rules)

        system_prompt = f"""{base_prompt}

You are responding via {channel.replace('_', ' ')}.

--- Response style ---
{tone_line}
{_formal_directive(slider_formal)}
{_length_directive(slider_length)}
{_sales_directive(slider_sales)}

--- Rules ---
{chr(10).join(f"- {r}" for r in rules_lines)}

--- Context for this message ---
Customer's detected intents: {intents_str}
{context_block}

--- Critical constraints (never override these) ---
- Address every question the customer asked — do not skip any.
- Never invent stock levels — use only the Shopify data above.
- Never invent prices — use only the data above.
- If you don't know something, say so and offer to find out.
- Stay in character as a human shop assistant. Do not mention being an AI."""

        # ── Build messages: prior conversation history + current message ─
        messages = []
        if history:
            for h in history:
                role = h.get('role')
                content = h.get('content')
                if role in ('user', 'assistant') and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )

        reply_text = response.content[0].text.strip()

        # Capture token usage for cost monitoring + analytics
        usage = getattr(response, 'usage', None)
        tokens_in  = getattr(usage, 'input_tokens',  0) if usage else 0
        tokens_out = getattr(usage, 'output_tokens', 0) if usage else 0
        tokens_total = tokens_in + tokens_out

        actual_model = getattr(response, 'model', model)

        return {
            'reply':       reply_text,
            'tokens_used': tokens_total,
            'model':       actual_model,
        }

    except Exception as e:
        log_event("error", "ai.generator.failure",
                  f"Claude API call failed — falling back to mock reply",
                  payload={
                      "error": str(e),
                      "channel": channel,
                      "intents": intents,
                  })
        return {
            'reply':       _mock_reply(intents, context_data),
            'tokens_used': 0,
            'model':       'mock',
        }