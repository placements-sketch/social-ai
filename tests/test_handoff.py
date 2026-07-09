from app.handoff import _bridging_reply_for, BRIDGING_REPLY


def test_abuse_gets_a_distinct_calm_message():
    reply = _bridging_reply_for("ai_detected", "abuse")
    assert isinstance(reply, str) and reply.strip()
    # Abuse must NOT get the cheery default ("we appreciate your patience").
    assert reply != BRIDGING_REPLY


def test_frustration_opens_with_an_apology():
    assert "sorry" in _bridging_reply_for("intent", "frustration").lower()


def test_complaint_opens_with_an_apology():
    assert "sorry" in _bridging_reply_for("intent", "complaint").lower()