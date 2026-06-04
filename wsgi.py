import sys
import os

# Ensure the root directory is in the Python path so config.py can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

try:
    from app import create_app
    app = create_app()
    print("[WSGI] App created successfully", file=sys.stderr)
except Exception as e:
    print(f"[WSGI ERROR] Failed to create app: {str(e)}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    raise

if __name__ == "__main__":
    app.run()
