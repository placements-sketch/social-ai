"""
Test the login endpoint
"""
import requests
import json

url = "http://127.0.0.1:5000/api/auth/login"
payload = {
    "email": "admin@company.com",
    "password": "admin123"
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
