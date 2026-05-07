import logging
import json

# Setup logging so we can see the fallback warnings
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

from app.services.scrutiny_extract import _ask_gemini

print("=== Testing Gemini API Availability ===")
try:
    # A simple prompt to verify it's working
    prompt = '{"test": "Say yes if you receive this."}'
    result = _ask_gemini(prompt)
    print("\n[SUCCESS] The API is available.")
    print("Response data:")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"\n[FAILED] Failed to connect: {e}")
