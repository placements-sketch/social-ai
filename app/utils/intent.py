"""
app/utils/intent.py
Multi-intent detection — a single message can trigger multiple intents.

Example:
  "Hi, is this item available? If yes, in what other colors and how much is delivery to Kilimani?"
  → ["greeting", "stock_inquiry", "product_inquiry", "delivery_inquiry"]

Intents:
  greeting          — hello, hi, hey
  stock_inquiry     — asking about availability / stock
  price_inquiry     — asking about price / cost
  product_inquiry   — asking about a specific product's details (colors, sizes, etc.)
  delivery_inquiry  — asking about delivery, shipping, location
  order_status      — asking about an existing order
  complaint         — expressing dissatisfaction
  unknown           — nothing matched (fallback, only returned when list is empty)

Upgrade path: replace keyword rules with an LLM-based intent extraction call
              that returns a structured JSON list of intents.
"""

from typing import Literal

# All possible intent labels
Intent = Literal[
    "greeting",
    "stock_inquiry",
    "price_inquiry",
    "product_inquiry",
    "delivery_inquiry",
    "order_status",
    "complaint",
    "unknown",
]

# Each entry: (intent_label, [keywords])
# ALL matching intents are returned — not just the first one.
_INTENT_RULES: list[tuple[str, list[str]]] = [
    ("greeting", [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "hii", "habari", "sasa", "mambo", "niaje",
    ]),
    ("stock_inquiry", [
        "available", "in stock", "do you have", "is it available", "is this available",
        "stock", "ipo", "nina", "availability", "left", "remaining", "sold out",
    ]),
    ("price_inquiry", [
        "price", "cost", "how much", "bei", "pesa", "ksh", "kes", "charge",
        "how much is", "what does it cost", "what's the price",
    ]),
    ("product_inquiry", [
        "color", "colour", "colors", "colours", "sizes", "size", "variants",
        "what does it look like", "description", "details", "material",
        "collection", "dress", "shoes", "bag", "lipstick", "foundation",
        "serum", "moisturizer", "perfume", "outfit", "top", "skirt", "jeans",
        "item", "product", "style", "design",
    ]),
    ("delivery_inquiry", [
        "delivery", "deliver", "shipping", "ship", "courier", "nairobi",
        "mombasa", "kisumu", "nakuru", "kilimani", "westlands", "karen",
        "cbd", "thika", "eldoret", "how long", "when will it arrive",
        "how do i get", "pick up", "pickup", "collect",
    ]),
    ("order_status", [
        "order", "tracking", "track", "shipped", "when will", "my order",
        "order number", "reference", "dispatch", "where is my",
    ]),
    ("complaint", [
        "complaint", "unhappy", "disappointed", "wrong", "broken", "damaged",
        "refund", "return", "bad", "terrible", "awful", "not working",
        "didn't receive", "never arrived", "fake", "poor quality",
    ]),
]


def detect_intents(message: str) -> list[str]:
    """
    Returns ALL intents detected in the message.

    A single message like:
      "Hi, is this available in blue and how much does delivery to Kilimani cost?"
    returns:
      ["greeting", "stock_inquiry", "product_inquiry", "delivery_inquiry", "price_inquiry"]

    Returns ["unknown"] only if nothing matched at all.
    """
    text = message.lower()
    matched = []

    for intent, keywords in _INTENT_RULES:
        if any(kw in text for kw in keywords):
            matched.append(intent)

    return matched if matched else ["unknown"]


def detect_intent(message: str) -> str:
    """
    Backwards-compatible single-intent version.
    Returns the first (highest priority) matched intent.
    Used for DB storage — the full list is passed to the AI.
    """
    return detect_intents(message)[0]


def intents_to_label(intents: list[str]) -> str:
    """
    Converts a list of intents to a compact string for DB storage.
    e.g. ["stock_inquiry", "price_inquiry"] → "stock_inquiry|price_inquiry"
    """
    return "|".join(intents)
