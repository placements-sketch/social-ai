"""
app/utm.py
UTM link generation + attribution helpers.

Convention (matches Shop Zetu's existing UTM generator app):
  utm_source=Social-ai-assistant
  utm_medium=Instagram
  utm_campaign=conv_{conversation_id}
  utm_content=msg_{message_id}

Token format stored on messages.utm_token:
  conv_473_msg_8821

This is the compact human-readable form. Easy to eyeball in DB queries
and reversible via parse_utm_token().
"""

import re
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

# Storefront domain used for all product links.
STOREFRONT_DOMAIN = 'https://www.shopzetu.com'

# UTM constants matching the existing UTM generator app's convention.
UTM_SOURCE = 'Social-ai-assistant'
UTM_MEDIUM = 'Instagram'


def build_utm_token(conversation_id: int, message_id: int) -> str:
    """
    Compact token stored on messages.utm_token, for cheap attribution lookups.
    Format: 'conv_{conv_id}_msg_{msg_id}'
    """
    return f"conv_{conversation_id}_msg_{message_id}"


def parse_utm_token(token: str) -> dict | None:
    """
    Reverse: given 'conv_473_msg_8821' return {'conversation_id': 473, 'message_id': 8821}.
    Returns None if the token doesn't match the expected shape.
    """
    if not token:
        return None
    match = re.match(r'^conv_(\d+)_msg_(\d+)$', token.strip())
    if not match:
        return None
    return {
        'conversation_id': int(match.group(1)),
        'message_id': int(match.group(2)),
    }


def build_product_url(
    handle: str,
    conversation_id: int,
    message_id: int,
    variant_params: dict | None = None,
) -> str:
    """
    Build a UTM-tagged product URL for the AI to include in a message.
    
    Args:
        handle: Product handle from Shopify (e.g., 'stylish-sisters-warm-heavy-pullover').
        conversation_id: The Message model FK to Conversation.id — used for utm_campaign.
        message_id: The Message.id itself — used for utm_content.
        variant_params: Optional dict of variant selectors like {'Color': 'Prussian Blue', 'Size': 'S'}.
                        Pass ONLY when the AI is recommending a specific variant.
    
    Returns:
        Full URL like:
          https://www.shopzetu.com/products/{handle}?Color=Prussian+Blue&Size=S&utm_source=Social-ai-assistant&utm_medium=Instagram&utm_campaign=conv_473&utm_content=msg_8821
    """
    if not handle:
        return STOREFRONT_DOMAIN  # fallback — homepage
    
    base_url = f"{STOREFRONT_DOMAIN}/products/{handle}"
    
    # Query params: variants first, then UTMs, matching the existing app's order
    params = {}
    if variant_params:
        for k, v in variant_params.items():
            if v is not None and v != '':
                params[k] = str(v)
    
    params['utm_source'] = UTM_SOURCE
    params['utm_medium'] = UTM_MEDIUM
    params['utm_campaign'] = f"conv_{conversation_id}"
    params['utm_content'] = f"msg_{message_id}"
    
    return f"{base_url}?{urlencode(params)}"


def extract_utm_token_from_url(url: str) -> str | None:
    """
    Reverse-lookup: given a landing URL captured by Shopify on a customer's
    order, extract our utm_campaign + utm_content back into the compact token.
    
    Returns None if the URL doesn't have our UTM signature (i.e., the order
    didn't come from a DM link).
    
    Example input:
      https://www.shopzetu.com/products/foo?utm_source=Social-ai-assistant&utm_campaign=conv_473&utm_content=msg_8821
    Returns:
      'conv_473_msg_8821'
    """
    if not url:
        return None
    
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
    except Exception:
        return None
    
    # Must be OUR source — filter out unrelated marketing links
    source = (params.get('utm_source', [''])[0] or '').strip()
    if source != UTM_SOURCE:
        return None
    
    campaign = (params.get('utm_campaign', [''])[0] or '').strip()
    content = (params.get('utm_content', [''])[0] or '').strip()
    
    # Both must exist and match our conv_/msg_ format
    conv_match = re.match(r'^conv_(\d+)$', campaign)
    msg_match = re.match(r'^msg_(\d+)$', content)
    if not conv_match or not msg_match:
        return None
    
    return f"conv_{conv_match.group(1)}_msg_{msg_match.group(1)}"