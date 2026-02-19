import json
import os
from datetime import datetime

WEBHOOK_LOG = "database/webhooks.json"

if not os.path.exists(WEBHOOK_LOG):
    with open(WEBHOOK_LOG, "w") as f:
        json.dump([], f)

def send_webhook(event):
    with open(WEBHOOK_LOG, "r") as f:
        logs = json.load(f)

    logs.append({
        "event": event,
        "timestamp": datetime.now().isoformat()
    })

    with open(WEBHOOK_LOG, "w") as f:
        json.dump(logs, f, indent=2)
