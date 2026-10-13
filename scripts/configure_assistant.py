import requests
from app.config import (
    VAPI_API_KEY,
    ELEVENLABS_VOICE_ID,
    VAPI_ASSISTANT_ID,
)

url = f"https://api.vapi.ai/assistant/{VAPI_ASSISTANT_ID}"

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

data = {
    "voice": {
        "provider": "11labs",
        "voiceId": ELEVENLABS_VOICE_ID,
    }
}

response = requests.patch(url, headers=headers, json=data)

print("Status:", response.status_code)
print("Response:", response.json())