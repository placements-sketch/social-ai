import re

def detect_intent(message: str):
    msg = message.lower().strip()

    # ---1. GREETINGS ---
    if re.search(r"\b(hi|hello|hey|goo morning|good evening)\b", msg):
        return "greeting"
    
    # ---2. PRICE RELATED ---
    if "price" in msg or "how much" in msg or "cost" in msg:
        return "price_query"
    
    # ---3. STOCK/AVAILABILITY ---
    if "available" in msg or "stock" in msg or "do you have" in msg:
        return "stock_query"
    
    # ---4. DELIVERY ---
    if "delivery" in msg or "ship" in msg or "how long" in msg:
        return "delivery_query"
    
    # ---5. COMPLAINT / ESCALATION ---
    if any(word in msg for word in ["refund", "angry", "bad", "scam", "manager", "complain"]):
        return "escalation"
    
    # ---6. SPAM / IRRELEVANT ---
    if len(msg) < 3:
        return "spam"
    
    # --- DEFAULT ---
    return "ai_fallback"