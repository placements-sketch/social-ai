"""
app/ai/generator.py
AI reply generation using Anthropic Claude.

Accepts a LIST of intents so Claude can address every question in a single reply.

To activate real Claude calls:
  1. pip install anthropic
  2. Set ANTHROPIC_API_KEY in .env
  3. Set USE_MOCK_AI = False below
"""

from app.utils.logger import log_event

USE_MOCK_AI = True  # Flip to False once your Anthropic key is configured


def generate_reply(message: str, intents: list[str], context_data: dict, channel: str) -> str:
    """
    Generates a customer support reply that addresses ALL detected intents.

    Args:
        message:      The customer's original message.
        intents:      All detected intents e.g. ["stock_inquiry", "price_inquiry"]
        context_data: Dict with product, stock, delivery_asked, etc. from Shopify.
        channel:      'instagram_dm' | 'instagram_comment' | 'whatsapp' | etc.

    Returns:
        A single reply string addressing every question asked.
    """
    if USE_MOCK_AI:
        return _mock_reply(intents, context_data)
    return _claude_reply(message, intents, context_data, channel)


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

def _claude_reply(message: str, intents: list[str], context_data: dict, channel: str) -> str:
    """
    Calls Anthropic Claude Messages API with full multi-intent context.
    Requires: pip install anthropic  and  ANTHROPIC_API_KEY in .env
    """
    try:
        import anthropic
        from flask import current_app

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        model  = current_app.config.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        max_tokens = current_app.config.get("CLAUDE_MAX_TOKENS", 400)

        # Build context block from Shopify data
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
            context_lines.append(
                f"Stock (Shopify): {s.get('quantity', 0)} units available"
            )

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
        intents_str   = ", ".join(intents)

        system_prompt = f"""You are a friendly, professional customer support agent for a fashion & beauty brand based in Nairobi, Kenya.
You are responding via {channel.replace('_', ' ')}.

IMPORTANT: The customer's message contains MULTIPLE questions. You MUST address ALL of them in a single reply.
Detected topics in this message: {intents_str}

Reply guidelines:
- Address every question asked — do not skip any
- Keep the total reply to 4–6 sentences maximum
- Be warm, concise, and on-brand
- Never invent stock levels — use only the Shopify data provided below
- Never invent prices — use only the data provided below
- If you don't know something, say so and offer to find out

--- Product & Inventory Context (from Shopify) ---
{context_block}
--- End Context ---"""

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": message}
            ]
        )

        return response.content[0].text.strip()

    except Exception as e:
        log_event("error", "ai.generator.failure",
                  f"Claude API call failed — falling back to mock reply",
                  payload={
                      "error": str(e),
                      "channel": channel,
                      "intents": intents,
                  })
        return _mock_reply(intents, context_data)
