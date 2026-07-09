import base64
import hashlib
import hmac

import pytest
from flask import Flask, request

from app.routes import _verify_shopify_hmac

SECRET = "test_secret"


def _sign(body: bytes, secret: str) -> str:
    """Compute the base64 HMAC-SHA256 exactly as Shopify does."""
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


@pytest.fixture
def flask_app():
    return Flask(__name__)


def test_valid_signature_passes(flask_app, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    body = b'{"id":123,"title":"Test"}'
    sig = _sign(body, SECRET)
    with flask_app.test_request_context(data=body, headers={"X-Shopify-Hmac-Sha256": sig}):
        ok, err = _verify_shopify_hmac(request)
    assert ok is True
    assert err is None


def test_forged_signature_is_rejected(flask_app, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    body = b'{"id":123}'
    with flask_app.test_request_context(data=body, headers={"X-Shopify-Hmac-Sha256": "not-a-real-sig"}):
        ok, err = _verify_shopify_hmac(request)
    assert ok is False


def test_missing_header_is_rejected(flask_app, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    with flask_app.test_request_context(data=b"{}"):
        ok, err = _verify_shopify_hmac(request)
    assert ok is False


def test_wrong_secret_is_rejected(flask_app, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    body = b'{"id":123}'
    sig = _sign(body, "a_different_secret")   # signed with the wrong key
    with flask_app.test_request_context(data=body, headers={"X-Shopify-Hmac-Sha256": sig}):
        ok, err = _verify_shopify_hmac(request)
    assert ok is False


def test_kill_switch_bypasses_verification(flask_app, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    with flask_app.test_request_context(data=b"{}", headers={"X-Shopify-Hmac-Sha256": "anything"}):
        ok, err = _verify_shopify_hmac(request)
    assert ok is True