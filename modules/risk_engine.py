import json
import os

CASES_DB = "database/cases.json"
BLACKLIST_DB = "database/blacklist.json"

os.makedirs("database", exist_ok=True)

if not os.path.exists(CASES_DB):
    with open(CASES_DB, "w") as f:
        json.dump({}, f)

if not os.path.exists(BLACKLIST_DB):
    with open(BLACKLIST_DB, "w") as f:
        json.dump({}, f)


def load_cases():
    with open(CASES_DB, "r") as f:
        return json.load(f)


def save_cases(cases):
    with open(CASES_DB, "w") as f:
        json.dump(cases, f, indent=2)


def load_blacklist():
    with open(BLACKLIST_DB, "r") as f:
        return json.load(f)


def save_blacklist(data):
    with open(BLACKLIST_DB, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────
# Add Case
# ─────────────────────────────
def log_case(case_data):
    cases = load_cases()
    case_id = f"case_{len(cases)+1}"
    cases[case_id] = case_data
    save_cases(cases)


# ─────────────────────────────
# Customer Risk Score
# ─────────────────────────────
def calculate_customer_risk(customer_id):
    cases = load_cases()

    total = 0
    fraud = 0

    for case in cases.values():
        if case["customer_id"] == customer_id:
            total += 1
            if case["label"] == "FAKE IMAGE":
                fraud += 1

    if total == 0:
        return 0, "LOW"

    percentage = round((fraud / total) * 100, 2)

    if percentage < 30:
        tier = "LOW"
    elif percentage < 60:
        tier = "MEDIUM"
    elif percentage < 80:
        tier = "HIGH"
    else:
        tier = "CRITICAL"

    return percentage, tier


# ─────────────────────────────
# Auto Blacklist
# ─────────────────────────────
def auto_blacklist(customer_id, tier):
    if tier == "CRITICAL":
        blacklist = load_blacklist()
        blacklist[customer_id] = "Auto-blacklisted due to critical fraud pattern"
        save_blacklist(blacklist)
        return True
    return False
