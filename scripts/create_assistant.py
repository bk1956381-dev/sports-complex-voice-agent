import requests
from app.config import VAPI_API_KEY

url = "https://api.vapi.ai/assistant"

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

data = {
    "name": "Sports Complex Receptionist",
    "firstMessage": "Hello! Welcome to our sports complex. How can I help you today?",
}

response = requests.post(url, headers=headers, json=data)

print("Status:", response.status_code)
print("Response:", response.json())