# modules/duplicate.py
import json
import os
import imagehash
from PIL import Image
from datetime import datetime

DB_PATH = "database/hashes.json"


# ─────────────────────────────────────────────────────────────
# SAFE DATABASE LOAD
# ─────────────────────────────────────────────────────────────
def load_database():
    os.makedirs("database", exist_ok=True)

    if not os.path.exists(DB_PATH):
        return {}

    try:
        with open(DB_PATH, "r") as f:
            return json.load(f)
    except Exception:
        # Corrupted DB fallback
        return {}


def save_database(db):
    os.makedirs("database", exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)


# ─────────────────────────────────────────────────────────────
# MULTI-HASH DUPLICATE DETECTION
# ─────────────────────────────────────────────────────────────
def compute_hashes(img):
    return {
        "phash": str(imagehash.phash(img)),
        "dhash": str(imagehash.dhash(img)),
        "whash": str(imagehash.whash(img))
    }


def hash_distance(h1, h2):
    return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)


def check_duplicate(image_path, threshold=10):

    # Load image safely
    try:
        with Image.open(image_path) as img:
            hashes = compute_hashes(img)
    except Exception:
        return {
            "is_duplicate": False,
            "hash_distance": 999,
            "similarity_score": 0,
            "matched_entry": None,
            "db_was_empty": True
        }

    db = load_database()

    if not db:
        return {
            "is_duplicate": False,
            "hash_distance": 999,
            "similarity_score": 0,
            "matched_entry": None,
            "db_was_empty": True
        }

    best_match = None
    best_distance = float("inf")

    for entry_id, entry in db.items():
        try:
            # Skip old-format entries safely
            if not all(k in entry for k in ["phash", "dhash", "whash"]):
                continue

            d1 = hash_distance(hashes["phash"], entry["phash"])
            d2 = hash_distance(hashes["dhash"], entry["dhash"])
            d3 = hash_distance(hashes["whash"], entry["whash"])

            # Fusion distance
            distance = (d1 + d2 + d3) / 3

            if distance < best_distance:
                best_distance = distance
                best_match = entry

        except Exception:
            continue

    # 🔥 CRITICAL FIX — prevent infinity crash
    if best_distance == float("inf"):
        return {
            "is_duplicate": False,
            "hash_distance": 999,
            "similarity_score": 0,
            "matched_entry": None,
            "db_was_empty": False
        }

    is_duplicate = best_distance <= threshold

    if best_distance == 0:
        similarity = 100
    elif is_duplicate:
        similarity = round(100 - (best_distance / threshold) * 30, 1)
    else:
        similarity = round(max(0, 100 - best_distance * 4), 1)

    return {
        "is_duplicate": is_duplicate,
        "hash_distance": int(best_distance),
        "similarity_score": similarity,
        "matched_entry": best_match if is_duplicate else None,
        "db_was_empty": False
    }


# ─────────────────────────────────────────────────────────────
# REGISTER IMAGE
# ─────────────────────────────────────────────────────────────
def register_image(image_path, label="unknown"):

    try:
        with Image.open(image_path) as img:
            hashes = compute_hashes(img)
    except Exception:
        return None

    db = load_database()

    # Prevent exact duplicates
    for entry in db.values():
        if entry.get("phash") == hashes["phash"]:
            return None

    entry_id = f"img_{len(db) + 1}"

    db[entry_id] = {
        "phash": hashes["phash"],
        "dhash": hashes["dhash"],
        "whash": hashes["whash"],
        "label": label,
        "timestamp": datetime.now().isoformat(),
        "filename": os.path.basename(image_path)
    }

    save_database(db)
    return entry_id


# ─────────────────────────────────────────────────────────────
# INTERPRET RESULT
# ─────────────────────────────────────────────────────────────
def interpret_duplicate(result):

    if result.get("db_was_empty"):
        return "First submission — no previous complaints to compare", "green"

    elif result["is_duplicate"] and result["hash_distance"] == 0:
        return "⚠️ IDENTICAL image found — exact duplicate submission!", "red"

    elif result["is_duplicate"]:
        return "Very similar image found — likely duplicate complaint", "red"

    elif result["similarity_score"] > 60:
        return "Somewhat similar to a past complaint — flagged for review", "orange"

    else:
        return "Image is unique — never submitted before", "green"
