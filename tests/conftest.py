import os

# Set before any app module imports, so module-level env reads have safe values.
os.environ.setdefault("SHOPIFY_CLIENT_SECRET", "test_secret")
os.environ.setdefault("WEBHOOK_SIGNATURE_REQUIRED", "true")
os.environ.setdefault("USE_MOCK_AI", "true")