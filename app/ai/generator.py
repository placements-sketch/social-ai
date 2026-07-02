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

LOW_STOCK_THRESHOLD = 3


def _format_variants_inline(product: dict) -> tuple[str, str]:
    """
    Returns (in_stock_line, sold_out_note).

    in_stock_line: variants in stock, formatted for recommendation
      e.g. "BLACK / M (5 in stock), BLACK / L (2 left LOW)"

    sold_out_note: brief note of sold-out variants (for context, NOT recommendation)
      e.g. "Also sold out: BLACK / XL, BLACK / 2XL"
      Empty string if no sold-out variants.
    """
    details = product.get('variants_detail') or []
    if not details:
        return "", ""

    in_stock_parts = []
    sold_out_labels = []

    for v in details:
        qty = v.get('inventory_quantity')
        tracked = v.get('inventory_tracked', True)

        # Build the readable label from options
        opts = [str(v.get(k)) for k in ('option1', 'option2', 'option3') if v.get(k)]
        cleaned_opts = []
        for i, o in enumerate(opts):
            # Skip SKU-like option2 values (Shop Zetu uses option2 for internal codes)
            if i == 1 and len(o) >= 6 and any(c.isdigit() for c in o) and any(c.isalpha() for c in o):
                continue
            cleaned_opts.append(o)
        label = " / ".join(cleaned_opts) if cleaned_opts else v.get('title', 'Variant')

        # Sold out?
        if tracked and (qty is None or qty <= 0):
            sold_out_labels.append(label)
            continue

        if not tracked or qty is None:
            in_stock_parts.append(f"{label} (in stock)")
        elif qty <= LOW_STOCK_THRESHOLD:
            in_stock_parts.append(f"{label} ({qty} left LOW)")
        else:
            in_stock_parts.append(f"{label} ({qty} in stock)")

    in_stock_line = ", ".join(in_stock_parts)
    sold_out_note = f"Also sold out: {', '.join(sold_out_labels)}" if sold_out_labels else ""

    return in_stock_line, sold_out_note

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
        parts.append("Happy to check your order! Could you share the full name and email used to place the order?")

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

       # Prefer the multi-product list when available; fall back to single
        # product for compatibility with older callers.
        products = context_data.get("products") or (
            [context_data["product"]] if "product" in context_data else []
        )

        def _fmt_price(raw):
            s = str(raw) if raw is not None else ''
            if not s or s.upper() == 'N/A':
                return 'price on request'
            return s if 'KES' in s.upper() else f"KES {s}"

        def _is_in_stock(p):
            """A product is 'in stock' if quantity > 0, OR if quantity is None
            (untracked inventory — we don't know, so don't assume out)."""
            qty = p.get('stock_quantity')
            return qty is None or qty > 0

        if products:
            in_stock_products  = [p for p in products if _is_in_stock(p)]
            out_of_stock_products = [p for p in products if not _is_in_stock(p)]

            if in_stock_products:
                context_lines.append(
                    f"AVAILABLE PRODUCTS (recommend from these only — they're in stock):"
                )
                # UTM URL builder — one URL per product using shared conv_id + msg_id
                from app.utm import build_product_url
                utm_conv_id = context_data.get('_utm_conversation_id')
                utm_msg_id = context_data.get('_utm_message_id')

                # Track the first product's URL for post-hoc attribution fallback
                first_product_url = None

                for i, p in enumerate(in_stock_products, 1):
                    in_stock_line, sold_out_note = _format_variants_inline(p)
                    if not in_stock_line:
                        qty = p.get('stock_quantity')
                        in_stock_line = f"{qty} units in stock" if qty is not None else "stock available"

                    # Build the UTM-tagged URL for this product
                    handle = p.get('handle') or ''
                    product_url = None
                    if handle and utm_conv_id and utm_msg_id:
                        product_url = build_product_url(handle, utm_conv_id, utm_msg_id)
                        if first_product_url is None:
                            first_product_url = product_url

                    line = (
                        f"  {i}. {p.get('name')} — {_fmt_price(p.get('price'))} | "
                        f"Variants: {in_stock_line} | "
                        f"Description: {(p.get('description') or 'N/A')[:120]}"
                    )
                    if product_url:
                        line += f" | URL: {product_url}"

                    context_lines.append(line)
                    if sold_out_note:
                        context_lines.append(f"     {sold_out_note}")

                # Stash for return so services.py can save on the message
                context_data['_first_product_url'] = first_product_url

            if out_of_stock_products:
                context_lines.append(
                    f"OUT OF STOCK (do NOT recommend these as a purchase option; "
                    f"only mention if customer asks specifically, then pivot to an available product):"
                )
                for p in out_of_stock_products:
                    context_lines.append(
                        f"  - {p.get('name')} — {_fmt_price(p.get('price'))} (currently sold out)"
                    )

            if not in_stock_products and out_of_stock_products:
                context_lines.append(
                    "NOTE: All matched products are sold out. Be honest with the customer — "
                    "don't pretend they're available. Offer to take their details for restock "
                    "alerts or suggest browsing other categories."
                )

            if in_stock_products and len(in_stock_products) > 1:
                context_lines.append(
                    "Recommend the most relevant 1-2 available products with specific names and prices. "
                    "Don't list everything unless asked."
                )

        if context_data.get("delivery_asked"):
            loc = context_data.get("delivery_location", "their location")
            context_lines.append(
                f"Customer asked about delivery to: {loc}. "
                f"NOTE: No specific delivery details have been configured. "
                f"Tell the customer you'll check exact pricing and timing with the team "
                f"and confirm shortly — do not invent specifics."
            )

        # ── Order status (live Shopify lookup, verified by name + email) ──
        os_data = context_data.get("order_status")
        if os_data:
            state = os_data.get("state")
            if state == "found":
                lines = [
                    f"ORDER STATUS for {os_data.get('customer_name', 'the customer')} "
                    f"(identity verified by name + email). Report ONLY these real orders — "
                    f"never invent order numbers, items, amounts, or statuses:"
                ]
                for o in os_data.get("orders", []):
                    items = ", ".join(o.get("products", [])) or f"{o.get('items_count', 0)} item(s)"
                    total = o.get("total") or 0
                    cur   = o.get("currency", "KES")
                    fin   = o.get("financial_status") or "unknown"
                    ful   = o.get("fulfillment_status") or "unfulfilled"
                    lines.append(
                        f"  - Order #{o.get('order_number', '?')} "
                        f"({(o.get('order_date') or '')[:10]}): {items} | "
                        f"{cur} {total:,.0f} | payment: {fin} | delivery: {ful}"
                    )
                lines.append(
                    "Summarise warmly and clearly. Translate delivery status for the customer: "
                    "null/'unfulfilled' → 'not yet shipped', 'fulfilled' → 'shipped / on its way', "
                    "'partial' → 'partially shipped'."
                )
                context_lines.append("\n".join(lines))
            elif state == "no_orders":
                context_lines.append(
                    f"The customer ({os_data.get('customer_name', '')}) is verified but has NO orders "
                    f"on record. Tell them warmly you couldn't find any orders on their account, and "
                    f"offer to help place one or check a different email."
                )
            elif state == "name_mismatch":
                context_lines.append(
                    "The email matches an account but the NAME given does not. Do NOT reveal any order "
                    "details. Politely say the name and email don't seem to match and ask them to "
                    "double-check both."
                )
            elif state == "no_account":
                context_lines.append(
                    "No account was found under that email. Tell the customer you couldn't find an "
                    "account with that email, and ask them to double-check it or share the email used "
                    "at checkout."
                )
        elif context_data.get("order_status_asked"):
            context_lines.append(
                "Customer is asking about an order but hasn't given details yet. Ask for the full name "
                "and email used on the order so you can look it up. Do NOT ask for an order number."
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

        # Pull live store info (physical shop locations) from the cache.
        # When customers ask "where are your shops?" the AI can list real branches.
        locations_block = ""
        try:
            from app.store_info import format_locations_for_prompt
            locations_block = format_locations_for_prompt()
        except Exception as e:
            log_event("warn", "ai.generator.store_info_inject_failed", str(e))

        store_info_section = (
            f"\n\n--- Store info ---\n{locations_block}"
            if locations_block else ""
        )

        system_prompt = f"""{base_prompt}

You are responding via {channel.replace('_', ' ')}.

--- Response style ---
{tone_line}
{_formal_directive(slider_formal)}
{_length_directive(slider_length)}
{_sales_directive(slider_sales)}

--- Rules ---
{chr(10).join(f"- {r}" for r in rules_lines)}{store_info_section}

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

        import time
        _start = time.time()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        elapsed_ms = int((time.time() - _start) * 1000)

        reply_text = response.content[0].text.strip()

        # Capture token usage for cost monitoring + analytics
        usage = getattr(response, 'usage', None)
        tokens_in  = getattr(usage, 'input_tokens',  0) if usage else 0
        tokens_out = getattr(usage, 'output_tokens', 0) if usage else 0
        tokens_total = tokens_in + tokens_out

        actual_model = getattr(response, 'model', model)

        # Build the token that will be persisted on the message row
        utm_conv_id = context_data.get('_utm_conversation_id')
        utm_msg_id = context_data.get('_utm_message_id')
        utm_token = None
        if utm_conv_id and utm_msg_id:
            from app.utm import build_utm_token
            utm_token = build_utm_token(utm_conv_id, utm_msg_id)

        # Post-hoc: which product URL did the AI actually mention?
        # Falls back to the first in-stock product's URL if none matched.
        product_url = context_data.get('_first_product_url')
        if reply_text and product_url:
            # Look for any UTM'd URL in the reply
            import re
            match = re.search(r'https://www\.shopzetu\.com/products/[^\s<>\)"]+', reply_text)
            if match:
                product_url = match.group(0)

        return {
            'reply':       reply_text,
            'tokens_used': tokens_total,
            'model':       actual_model,
            'elapsed_ms':  elapsed_ms,
            'utm_token':   utm_token,
            'product_url': product_url,
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
            'elapsed_ms': 0,
            'utm_token':   None,
            'product_url': None,
        }