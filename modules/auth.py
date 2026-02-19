import json
import os
import hashlib
from datetime import datetime

USERS_DB = "database/users.json"

os.makedirs("database", exist_ok=True)

# ─────────────────────────────
# Initialize DB
# ─────────────────────────────
if not os.path.exists(USERS_DB):
    with open(USERS_DB, "w") as f:
        json.dump({}, f)


# ─────────────────────────────
# Password Hashing
# ─────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ─────────────────────────────
# Load Users
# ─────────────────────────────
def load_users():
    with open(USERS_DB, "r") as f:
        return json.load(f)


# ─────────────────────────────
# Save Users
# ─────────────────────────────
def save_users(users):
    with open(USERS_DB, "w") as f:
        json.dump(users, f, indent=2)


# ─────────────────────────────
# Register User
# ─────────────────────────────
def register_user(username, password, role="agent"):
    users = load_users()

    if username in users:
        return False, "Username already exists"

    users[username] = {
        "password": hash_password(password),
        "role": role,
        "created_at": datetime.now().isoformat(),
        "cases_handled": 0
    }

    save_users(users)
    return True, "User registered successfully"


# ─────────────────────────────
# Authenticate User
# ─────────────────────────────
def authenticate_user(username, password):
    users = load_users()

    if username not in users:
        return False, None

    if users[username]["password"] == hash_password(password):
        return True, users[username]["role"]

    return False, None


# ─────────────────────────────
# Increment Case Counter
# ─────────────────────────────
def increment_cases(username):
    users = load_users()
    if username in users:
        users[username]["cases_handled"] += 1
        save_users(users)
