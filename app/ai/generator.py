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
import re
USE_MOCK_AI = os.getenv("USE_MOCK_AI", "false").lower() == "true"

LOW_STOCK_THRESHOLD = 3


def first_text(resp) -> str:
    """
    The first TEXT block of a Claude response.

    Every call site here read `resp.content[0].text`, which assumes the first
    block is text. It is not when the model returns reasoning first — the block
    is a ThinkingBlock with no `.text`, and the whole call died with
    "'ThinkingBlock' object has no attribute 'text'". That took out image
    verification silently: the exception was caught, the verdict came back None,
    and matching fell through to guessing.

    Scans for the first block that actually carries text instead of trusting
    position, so reasoning blocks, tool blocks or anything else added later are
    skipped rather than fatal.
    """
    for block in (getattr(resp, "content", None) or []):
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return ""


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

# Words that mean a reply is putting a specific product forward, as opposed to
# answering about delivery, sizing or an order. Deliberately conservative: a
# false positive attributes a sale to a recommendation that never happened,
# which is worse than missing one.
# Matched on WORD BOUNDARIES, not as substrings. Plain `in` matching made
# "Delivery to Mombasa takes 2-3 days" look like a product recommendation,
# because "ta-KES-" contains "kes" — which would have attributed delivery
# answers to sales and quietly corrupted the very metric this exists to build.
_RECOMMEND_MARKERS = (
    r'ksh', r'kes', r'price[ds]?', r'costs?', r'available in', r'in stock',
    r'we have', r'check it out', r'grab', r'order it', r'shop it',
)
_RECOMMEND_RE = re.compile(
    r'\b(?:' + '|'.join(_RECOMMEND_MARKERS) + r')\b', re.IGNORECASE)


def _reply_recommends_a_product(reply_text: str) -> bool:
    """True when the reply looks like it is offering a specific product."""
    return bool(_RECOMMEND_RE.search(reply_text or ''))


def generate_reply(message: str, intents: list[str], context_data: dict, channel: str,
                   history: list[dict] | None = None, image_urls: list | None = None) -> dict:
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
        result = _claude_reply(message, intents, context_data, channel, history=history, image_urls=image_urls)
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

def _fetch_image_b64(url: str):
    """Fetch an image (e.g. an IG attachment) → (base64, media_type), or (None, None)."""
    import base64, requests
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 403:                     # some IG CDN URLs need the token
            from app.integrations.meta import _get_meta_credentials
            _, token = _get_meta_credentials()
            if token:
                r = requests.get(url, params={"access_token": token}, timeout=10)
        if r.status_code >= 400:
            return None, None
        media_type = (r.headers.get("Content-Type", "image/jpeg").split(";")[0]).strip()
        if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            media_type = "image/jpeg"
        return base64.b64encode(r.content).decode("utf-8"), media_type
    except Exception as e:
        log_event("warn", "ai.generator.image_fetch_failed", str(e)[:200])
        return None, None


def describe_product_in_image(image_urls: list) -> dict | None:
    """
    Stage 2 vision: look at the customer's photo and return the product's
    attributes for the catalogue lookup.

    Returns a dict — {name, type, colour, details, phrase} — or None on any
    failure, in which case the pipeline continues text-only.

    Returns the parts SEPARATELY, not just a phrase, and that is the point.
    A description flattened into words has to be matched by ranking every one
    of 7,000+ products by keyword overlap, and a phrase like "colourful dress
    with fringe" ranks badly against titles written by a merchandiser. Garment
    TYPE and COLOUR can instead be used to filter — throwing away everything
    that is not even the right kind of item before any ranking happens.

    Returned rather than stashed on the function: webhooks are handled on a
    thread pool, so shared mutable state here would let two customers' photos
    overwrite each other's attributes.
    """
    if not image_urls:
        return None
    try:
        import anthropic
        from flask import current_app

        blocks = []
        for u in image_urls[:2]:
            b64, media_type = _fetch_image_b64(u)
            if b64:
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                })
        if not blocks:
            return None
        blocks.append({
            "type": "text",
            "text": (
                "Identify the main fashion or beauty product in this image.\n\n"
                "FIRST: if the image contains readable text naming the product — a "
                "screenshot of a product page, a post with the title written on it, a "
                "price tag, a label — copy those exact words. A real product name beats "
                "any description you could write, because it can be looked up directly.\n\n"
                "Reply on ONE line in exactly this format:\n"
                "  NAME | TYPE | COLOUR | DETAILS\n\n"
                "  NAME    - the product name if it is written in the image, else -\n"
                "  TYPE    - the single garment noun: dress, top, trousers, skirt, "
                "jacket, shoes, bag, set, kaftan. One word. Never blank.\n"
                "  COLOUR  - the one or two dominant colours, or 'multicolour' for a "
                "print with no single dominant colour\n"
                "  DETAILS - 2-4 further words: pattern, cut, fabric, trim\n\n"
                "TYPE and COLOUR are used to narrow a catalogue of thousands, so be "
                "literal and conventional with them — the word a shop would use.\n\n"
                "Example: Vivo Lani Maxi Dress | dress | black white | satin print maxi\n"
                "Example: - | mules | tan | leather pointed flat\n"
                "Example: - | dress | multicolour | tie dye fringe midi"
            ),
        })

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        model = current_app.config.get("CLASSIFIER_MODEL") or current_app.config.get("CLAUDE_MODEL", "claude-haiku-4-5")
        resp = client.messages.create(
            model=model,
            # Room for a product name plus descriptors — 30 tokens truncated
            # mid-name once the prompt started asking for on-image text.
            max_tokens=80,
            messages=[{"role": "user", "content": blocks}],
        )
        text = first_text(resp).strip().replace("\n", " ")[:220].strip()

        # Parsed into parts as well as returned whole. Callers that just want a
        # search phrase keep working; the caller that can narrow the catalogue
        # by garment type and colour now has them separately, which is the
        # difference between ranking 7,000 products by fuzzy keyword and
        # filtering to the few dozen that are even the right kind of thing.
        parts = [p.strip() for p in text.split("|")]
        while len(parts) < 4:
            parts.append("")
        name, gtype, colour, details = parts[0], parts[1], parts[2], parts[3]
        if name.strip() in ("-", "—", ""):
            name = ""

        attrs = {
            "name": name,
            "type": gtype.lower(),
            "colour": colour.lower(),
            "details": details.lower(),
            # What the old callers expect: one space-separated search phrase.
            "phrase": " ".join(p for p in (name, gtype, colour, details) if p).strip(),
        }

        log_event("info", "ai.vision.describe",
                  f"Vision product attributes: {attrs['phrase']!r} "
                  f"(type={attrs['type']!r} colour={attrs['colour']!r})",
                  payload={"raw": text, **attrs})
        return attrs
    except Exception as e:
        log_event("warn", "ai.vision.describe_failed", str(e)[:200])
        return None

def verify_product_match(customer_image_urls: list, candidates: list) -> dict | None:
    """
    Vision re-rank. Keyword search ranks by NAME similarity, which knows nothing
    about how a garment actually looks — that's why "navy wide leg pants" can
    return a polka-dot pair. So we show Claude the customer's photo and the
    candidate product photos side by side and ask which one it really is.

    Returns {"index": int, "confidence": "high"|"low"} for a match,
    {"index": None, ...} when nothing matches, or None if the check couldn't run
    (caller then falls back to the keyword ranking).
    """
    if not customer_image_urls or not candidates:
        return None
    try:
        import json as _json
        import anthropic
        from concurrent.futures import ThreadPoolExecutor
        from flask import current_app

        cust_b64, cust_type = _fetch_image_b64(customer_image_urls[0])
        if not cust_b64:
            return None

        def _first_image_url(p):
            imgs = p.get("images") or []
            if not imgs:
                return None
            first = imgs[0]
            if isinstance(first, dict):
                return first.get("src") or first.get("url")
            return first

        shortlist = []
        for i, p in enumerate(candidates[:12]):
            u = _first_image_url(p)
            if u:
                shortlist.append((i, p, u))
        if not shortlist:
            return None

        # Product images are separate HTTP fetches — do them in parallel so the
        # customer isn't waiting on 8 sequential round-trips.
        with ThreadPoolExecutor(max_workers=8) as pool:
            fetched = list(pool.map(lambda t: _fetch_image_b64(t[2]), shortlist))

        blocks = [
            {"type": "text", "text": "CUSTOMER'S PHOTO — identify this exact item:"},
            {"type": "image", "source": {"type": "base64", "media_type": cust_type, "data": cust_b64}},
            {"type": "text", "text": "CATALOGUE CANDIDATES:"},
        ]
        usable = []
        for (orig_i, p, _u), (b64, mtype) in zip(shortlist, fetched):
            if not b64:
                continue
            # No product name — it biases the model toward whichever title
            # reads most like the description instead of judging the image.
            blocks.append({"type": "text", "text": f"Candidate {len(usable)}:"})
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": mtype, "data": b64}})
            usable.append(orig_i)
        if not usable:
            return None

        blocks.append({"type": "text", "text": (
            "Which candidate is the SAME garment as the customer's photo?\n\n"
            "Think it through before answering:\n"
            "1. Describe the customer's garment precisely — silhouette, waistline, how the "
            "front is constructed (plain, wrapped, overlapping, pleated, panelled, split), "
            "hem width, drape, fastenings.\n"
            "2. Say which candidates share ALL of those construction details. Most candidates "
            "will be the same colour and the same broad cut — that is NOT a match.\n"
            "3. Choose the one matching every detail, or null if none genuinely do.\n\n"
            "Use \"high\" ONLY when the distinctive construction details are clearly identical. "
            "If your choice rests mainly on colour and general shape, that is \"low\".\n\n"
            "Finish with a single JSON object on its own line, with nothing after it:\n"
            "{\"match\": <candidate number or null>, \"confidence\": \"high\" or \"low\"}"
        )})

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        # Fine-grained visual discrimination is the one spot where a stronger
        # model clearly pays for itself — this fires once per image message,
        # not on every turn. Override with VISION_RERANK_MODEL if needed.
        import os as _os
        model = _os.getenv("VISION_RERANK_MODEL") or "claude-sonnet-5"
        resp = client.messages.create(
            model=model, max_tokens=700,
            messages=[{"role": "user", "content": blocks}],
        )

        raw = first_text(resp).strip()
        # The model sometimes adds commentary after the JSON, which breaks a bare
        # json.loads ("Extra data: line 4 ..."). Pull out the first object only.
        import re as _re
        objs = _re.findall(r'\{[^{}]*\}', raw)
        if not objs:
            log_event("warn", "ai.vision.verify_failed", f"No JSON in verdict: {raw[:300]!r}")
            return None
        data = _json.loads(objs[-1])
        m = data.get("match")
        conf = (data.get("confidence") or "low").lower()

        # Log the WHOLE shortlist — if the right product isn't in here, the
        # problem is search recall, not the re-ranker.
        cand_names = [candidates[i].get("name") for i in usable]

        if m is None:
            log_event("info", "ai.vision.verify",
                      f"Vision re-rank: NO match. Candidates were: {cand_names}",
                      payload={"candidates": cand_names})
            return {"index": None, "confidence": conf}

        m = int(m)
        if not (0 <= m < len(usable)):
            return None
        chosen = usable[m]
        log_event("info", "ai.vision.verify",
                  f"Vision re-rank picked {candidates[chosen].get('name')!r} ({conf}) from: {cand_names}",
                  payload={"chosen": candidates[chosen].get("name"),
                           "confidence": conf, "candidates": cand_names})
        return {"index": chosen, "confidence": conf}

    except Exception as e:
        log_event("warn", "ai.vision.verify_failed", str(e)[:200])
        return None

def _classify_failure(exc) -> tuple[str, str]:
    """
    Map an exception from the Claude call to a stable (reason, detail) pair, so
    failures can be grouped by cause (rate limits vs timeouts vs bad output…).
    """
    name = type(exc).__name__
    msg = str(exc)
    low = msg.lower()

    # Anthropic SDK error types (matched by class name to avoid a hard import)
    if name in ('RateLimitError',) or '429' in low or 'rate limit' in low:
        return 'rate_limit', msg[:200]
    if name in ('APITimeoutError',) or 'timeout' in low or 'timed out' in low:
        return 'timeout', msg[:200]
    if name in ('AuthenticationError', 'PermissionDeniedError') or '401' in low or '403' in low:
        return 'auth', msg[:200]
    if name in ('BadRequestError',) or '400' in low:
        return 'bad_request', msg[:200]
    if name in ('InternalServerError', 'APIStatusError', 'APIError') or '500' in low or 'overloaded' in low or '529' in low:
        return 'api_error', msg[:200]
    if name in ('APIConnectionError', 'ConnectionError') or 'connection' in low:
        return 'network', msg[:200]
    if name in ('JSONDecodeError', 'KeyError', 'IndexError', 'AttributeError'):
        return 'bad_output', msg[:200]   # response came back but wasn't shaped as expected
    return 'unknown', f"{name}: {msg[:180]}"

def _claude_reply(message: str, intents: list[str], context_data: dict, channel: str,
                  history: list[dict] | None = None, image_urls: list | None = None) -> dict:
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

                # TELL THE MODEL TO USE THE LINK.
                #
                # Every product line above carries "| URL: https://…", and the
                # code downstream greps the finished reply for that URL to
                # record which product was recommended. But nothing ever
                # instructed the model to include it. The only mentions of
                # links in this whole prompt were prohibitions — "MUST NOT
                # include a product link", "do NOT link any other product" —
                # so a URL appeared in a reply only by chance.
                #
                # That is why messages.product_url has zero rows and
                # conversion_attributions is empty: the first link in the
                # attribution chain was never asked to exist. Without it we
                # cannot say which recommendations led to sales, which is the
                # one number that proves the assistant earns its keep.
                if first_product_url:
                    context_lines.append(
                        "\nWHEN YOU RECOMMEND ONE OF THE PRODUCTS ABOVE: paste its URL "
                        "exactly as written, on its own line at the end of your reply. "
                        "Copy it character for character — the tracking parameters on it "
                        "are how we know the sale came from you. Never shorten it, never "
                        "rewrite it, and never invent a link for a product not listed here. "
                        "If you are not recommending a specific product, do not include a URL."
                    )

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
            delivery_block = ""
            try:
                from app.settings import format_delivery_for_prompt
                delivery_block = format_delivery_for_prompt()
            except Exception as e:
                log_event("warn", "ai.generator.delivery_inject_failed", str(e))
            if delivery_block:
                context_lines.append(
                    f"Customer asked about delivery to: {loc}.\n"
                    f"Delivery information (use ONLY what's below — never invent rates or timings):\n"
                    f"{delivery_block}\n"
                    f"If their location isn't listed, tell them you'll confirm exact pricing and timing with the team."
                )
            else:
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

        # Set by an automation rule with the `include_price` action. This is the
        # one rule action that shapes the reply instead of replacing it, so it
        # arrives as a directive on context_data rather than as canned text.
        if context_data.get("force_include_price"):
            context_lines.append(
                "An automation rule requires it: state the price of the product "
                "explicitly in this reply, in KES. Do not leave the customer to ask for it."
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

        business_block = ""
        try:
            from app.settings import format_business_for_prompt
            business_block = format_business_for_prompt()
        except Exception as e:
            log_event("warn", "ai.generator.business_info_inject_failed", str(e))

        _si_parts = [p for p in (business_block, locations_block) if p]
        store_info_section = (
            "\n\n--- Store info ---\n" + "\n".join(_si_parts)
            if _si_parts else ""
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
- Stay in character as a human shop assistant. Do not mention being an AI.
- Sound like a person who works here and has other messages waiting, not like an
  assistant performing helpfulness. Specifically, NEVER:
    * open with filler — "No worries!", "Great question!", "Absolutely!",
      "I'd be happy to", "Sure thing!". Start with the answer.
    * close by restating what you just did or offering more help — "That'll help
      me track down exactly what you're after", "Let me know if you need
      anything else!". Stop when the answer stops.
    * pad a question with examples in brackets, or ask two questions at once.
    * use more than one exclamation mark in a reply.
  A real shop assistant answers in one or two lines and trusts the customer to
  come back. Length is a cost to them, not a service.
- NEVER ask the customer to describe a product that is ours to know. If they
  sent a photo, you have already seen it — asking "what colour is it?" or "is it
  trousers or a skirt?" puts our job onto them and reads as though nobody looked.
  When a suggestion is rejected ("not the ones", "no", "that's not it"), do NOT
  ask for a description. Instead, in this order:
    1. Offer the OTHER products from the catalogue data above by name — the
       search returned more than one candidate and only the first was named.
    2. If those are exhausted or there were none, say plainly that you can't
       place it from the photo and offer to have a colleague check, or ask for
       the shopzetu.com link. Asking for a LINK is fine; asking them to describe
       our own stock is not."""

        # Vision directive — only when the customer actually sent a photo
        if image_urls:
            system_prompt += (
                "\n\n--- Image from the customer ---\n"
                "The customer sent a photo. Look at it carefully. If it shows a product, identify it "
                "(type, colour, style) and match it to the product data above when possible, then answer "
                "their question (availability, price, etc.). If it isn't one of the listed products, describe "
                "what you see and offer to help find it. Never claim stock or price you don't have data for."
            )

        # Match came from an image and was NOT visually confirmed — hedge.
        if context_data.get('image_only_match'):
            system_prompt += (
                "\n\n--- Important: UNCONFIRMED image match ---\n"
                "This product was guessed from an image only; the customer never named it. Visually "
                "similar items are easy to confuse, so treat the match as UNCONFIRMED.\n"
                "In this reply you MUST NOT:\n"
                "  - state a price or any stock/size numbers\n"
                "  - include a product link or URL\n"
                "  - assert the product name as fact\n"
                "Instead, name the likely match tentatively and ask them to confirm before you give "
                "details — e.g. \"These look like our [product] — is that the one? Confirm and I'll "
                "send you the price, sizes and link right away.\" Once they confirm, give full details."
            )

        # Vision re-rank confirmed the match — safe to be specific.
        if context_data.get('image_match_verified'):
            system_prompt += (
                "\n\n--- Image match confirmed ---\n"
                "The single product in the catalogue data above was visually confirmed against the "
                "customer's photo — it IS the item they sent. Refer to it by that exact name and "
                "price. Do NOT name, suggest, or link any other product in this reply."
            )

        # Vision re-rank found nothing — admit it rather than guess.
        if context_data.get('image_match_failed'):
            system_prompt += (
                "\n\n--- Product not found — hand over to a colleague ---\n"
                "You compared the customer's photo against the catalogue and NONE of the products "
                "matched it. Do NOT name, price, or link any product, and do NOT guess at a similar "
                "one.\n"
                "Do NOT ask the customer to identify it for you — no 'what colour is it', no "
                "'is it a dress or a skirt', and do not ask them to go and find a link. They sent "
                "a photo; identifying our own stock is our job, not theirs.\n"
                "Instead: say warmly and briefly that you want to get them the right piece and are "
                "bringing in a colleague who knows the collection, and that someone will come back "
                "to them shortly. Then stop. You are ALREADY in a DM with them — never tell them to "
                "'DM us', check the bio, or contact another channel."
            )

        # IG comment: the image is the POST, and its caption often names the item.
        post_caption = context_data.get('post_caption')
        if post_caption:
            system_prompt += (
                f"\n\n--- Post context ---\n"
                f"This is a comment on an Instagram post captioned: \"{post_caption[:300]}\". "
                f"The image shown is that post. The customer's comment refers to the product in it."
            )

        # ── Build the current user turn (attach image blocks if present) ─
        user_content = message
        if image_urls:
            blocks = []
            for u in image_urls[:3]:
                b64, media_type = _fetch_image_b64(u)
                if b64:
                    blocks.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    })
            if blocks:
                blocks.append({"type": "text", "text": message or "(image sent with no caption)"})
                user_content = blocks

        # ── Build messages: prior conversation history + current message ─
        messages = []
        if history:
            for h in history:
                role = h.get('role')
                content = h.get('content')
                if role in ('user', 'assistant') and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_content})

        import time
        _start = time.time()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        elapsed_ms = int((time.time() - _start) * 1000)

        reply_text = first_text(response).strip()

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

        # Only surface a product card when the reply ACTUALLY recommends a
        # product — i.e. it includes a product URL. Previously this fell back to
        # the first in-stock product whenever ANY product was fetched into
        # context, which is why generic answers ("how do I buy?", "what's my
        # size?") wrongly got a product card attached.
        product_url = None
        if reply_text:
            import re
            # Domain comes from the same constant that BUILDS the links, rather
            # than a second hardcoded copy. The two could drift — and if they
            # ever did, extraction would silently return nothing and
            # attribution would go quiet without a single error.
            from app.utm import STOREFRONT_DOMAIN
            pattern = re.escape(STOREFRONT_DOMAIN.rstrip('/')) + r'/products/[^\s<>\)"\']+'
            match = re.search(pattern, reply_text)
            if match:
                product_url = match.group(0)

        # Fallback. The model recommended something but did not paste the link —
        # it paraphrased, or dropped it. We still know which product was put in
        # front of the customer, so record that rather than losing the
        # attribution entirely.
        #
        # This fallback was designed: `_first_product_url` has been stashed
        # since the UTM work went in, with a comment calling it a "post-hoc
        # attribution fallback". It was set and never read by anything.
        if not product_url and reply_text:
            candidate = (context_data or {}).get('_first_product_url')
            if candidate and _reply_recommends_a_product(reply_text):
                product_url = candidate

        return {
            'reply':       reply_text,
            'tokens_used': tokens_total,
            'model':       actual_model,
            'elapsed_ms':  elapsed_ms,
            'utm_token':   utm_token,
            'product_url': product_url,
        }

    except Exception as e:
        reason, detail = _classify_failure(e)
        # conversation_id matters: without it a failure can't be tied to the
        # customer it happened to, so it couldn't be counted against the
        # success rate and agents never saw failures on their own chats.
        # The caller already puts it in context_data for UTM building.
        log_event("error", "ai.generator.failure",
                  f"Claude reply failed ({reason}) — fell back to mock reply",
                  payload={
                      "reason": reason,            # rate_limit | timeout | auth | bad_request | api_error | network | bad_output | unknown
                      "detail": detail,
                      "error_type": type(e).__name__,
                      "channel": channel,
                      "intents": intents,
                  },
                  conversation_id=(context_data or {}).get('_utm_conversation_id'))
        return {
            'reply':          _mock_reply(intents, context_data),
            'tokens_used':    0,
            'model':          'mock',
            'elapsed_ms':     0,
            'utm_token':      None,
            'product_url':    None,
            'failure_reason': reason,   # surfaced to the caller too, for the message record
        }