from google import genai
from app.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
print("Available Gemini Models:")
try:
    models = client.models.list_models()
    for m in models:
        # Only print models that support generateContent
        if "generateContent" in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Failed to list models: {e}")
