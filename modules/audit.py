import json
import os
from datetime import datetime

AUDIT_DB = "database/audit_logs.json"

if not os.path.exists(AUDIT_DB):
    with open(AUDIT_DB, "w") as f:
        json.dump([], f)


def log_action(user, action):
    with open(AUDIT_DB, "r") as f:
        logs = json.load(f)

    logs.append({
        "user": user,
        "action": action,
        "timestamp": datetime.now().isoformat()
    })

    with open(AUDIT_DB, "w") as f:
        json.dump(logs, f, indent=2)
