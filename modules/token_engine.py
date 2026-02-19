import hashlib
import time

SECRET_KEY = "bitverify_ultra_secret_key"

def generate_token(username):
    timestamp = str(int(time.time()))
    raw = username + timestamp + SECRET_KEY
    token = hashlib.sha256(raw.encode()).hexdigest()
    return token, timestamp

def validate_token(username, token, timestamp, expiry_seconds=3600):
    now = int(time.time())
    if now - int(timestamp) > expiry_seconds:
        return False

    expected_raw = username + timestamp + SECRET_KEY
    expected_token = hashlib.sha256(expected_raw.encode()).hexdigest()

    return token == expected_token
