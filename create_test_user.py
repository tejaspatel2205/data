import os
import json
import random
import requests

ADMIN_KEY = os.environ.get('ADMIN_API_TOKEN', 'token')
ADMIN_URL = 'http://localhost:18057'

def main() -> None:
    email = f"testuser{random.randint(100000, 999999)}@example.com"
    user_payload = {
        "email": email,
        "name": "Test User",
        "max_concurrent_bots": 2,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Admin-API-Key": ADMIN_KEY,
    }

    # Create user
    resp_user = requests.post(
        f"{ADMIN_URL}/admin/users",
        headers=headers,
        data=json.dumps(user_payload),
        timeout=60,
    )
    resp_user.raise_for_status()
    user = resp_user.json()
    user_id = user["id"]

    # Create token
    resp_token = requests.post(
        f"{ADMIN_URL}/admin/users/{user_id}/tokens",
        headers=headers,
        timeout=60,
    )
    resp_token.raise_for_status()
    token = resp_token.json()["token"]

    print(f"EMAIL={email}")
    print(f"USER_ID={user_id}")
    print(f"API_TOKEN={token}")

if __name__ == "__main__":
    main()
