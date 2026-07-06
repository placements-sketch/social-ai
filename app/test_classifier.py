from app import create_app
from app.ai.classifier import classify_message
import json

app = create_app()
app.app_context().push()

tests = [
    "Get me a human",
    "You're stupid!",
    "do you restock the tan mules?",
    "Hi, how much is delivery to Kilimani?",
    "my order never arrived and I want my money back NOW",
    "is the black wrap dress available in medium?",
    "just browsing, thanks",
]

for m in tests:
    print(f"{m!r}\n  -> {json.dumps(classify_message(m))}\n")