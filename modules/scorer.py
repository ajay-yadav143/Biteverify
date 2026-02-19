# modules/scorer.py — BitVerify Enterprise
# Full 8-signal fraud scoring with all fixes applied

def get_verdict(score):
    if score < 35:
        return {
            "label":       "GENUINE IMAGE",
            "emoji":       "✅",
            "color":       "green",
            "action":      "Refund Approved",
            "description": "Image appears authentic with no manipulation detected.",
            "refund":      True
        }
    elif score < 65:
        return {
            "label":       "SUSPICIOUS IMAGE",
            "emoji":       "⚠️",
            "color":       "orange",
            "action":      "Manual Review",
            "description": "Some anomalies detected. Human verification recommended.",
            "refund":      None
        }
    else:
        return {
            "label":       "FAKE IMAGE",
            "emoji":       "❌",
            "color":       "red",
            "action":      "Refund Rejected",
            "description": "Strong manipulation signals detected.",
            "refund":      False
        }


def calculate_fraud_score(
    ela_score,
    metadata_score,
    duplicate_result,
    ai_score        = 0,
    patch_score     = 0,
    noise_score     = 0,
    frequency_score = 0,
    diffusion_score = 0
):
    # ── SAFE NORMALIZATION ───────────────────────────────────
    ela       = float(ela_score       or 0)
    metadata  = float(metadata_score  or 0) * 0.6
    ai_model  = float(ai_score        or 0)
    patch     = float(patch_score     or 0)
    noise     = float(noise_score     or 0)
    frequency = float(frequency_score or 0)
    diffusion = float(diffusion_score or 0)

    # ── SAFE DUPLICATE EXTRACTION ────────────────────────────
    is_duplicate  = duplicate_result.get("is_duplicate",  False)
    hash_distance = duplicate_result.get("hash_distance", 999)
    db_empty      = duplicate_result.get("db_was_empty",  False)

    # ── DUPLICATE SCORING ────────────────────────────────────
    if is_duplicate and hash_distance < 5:
        dup = 100
    elif is_duplicate:
        dup = 75
    elif db_empty or hash_distance == 999:
        dup = 0
    else:
        dup = max(0, 100 - hash_distance * 8)

    dup = round(min(max(dup, 0), 100), 2)

    # ── FULL BREAKDOWN (used in ALL return paths) ─────────────
    full_breakdown = {
        "AI Model Detection":    round(ai_model,  2),
        "ELA — Editing":         round(ela,        2),
        "Metadata Analysis":     round(metadata,   2),
        "Duplicate Check":       round(dup,        2),
        "Patch Anomaly":         round(patch,      2),
        "Noise Inconsistency":   round(noise,      2),
        "Frequency Anomaly":     round(frequency,  2),
        "Diffusion Artifacts":   round(diffusion,  2),
    }

    # ── HARD OVERRIDE 1: Exact duplicate ─────────────────────
    if dup >= 100:
        full_breakdown["Duplicate Check"] = 100
        return {
            "final_score": 100,
            "breakdown":   full_breakdown,
            "verdict": {
                "label":       "FAKE IMAGE — DUPLICATE",
                "emoji":       "❌",
                "color":       "red",
                "action":      "Refund Rejected",
                "description": "This exact image was already submitted in a previous complaint. Resubmitting the same image is clear fraud.",
                "refund":      False
            }
        }

    # ── HARD OVERRIDE 2: Strong AI model detection ────────────
    if ai_model > 80:
        return {
            "final_score": round(max(85, ai_model), 2),
            "breakdown":   full_breakdown,
            "verdict": {
                "label":       "AI-GENERATED / AI-EDITED IMAGE",
                "emoji":       "❌",
                "color":       "red",
                "action":      "Refund Rejected",
                "description": "Deep AI model detected high probability of generative editing (Gemini, DALL-E, Midjourney, etc.).",
                "refund":      False
            }
        }

    # ── HARD OVERRIDE 3: Heavy ELA editing ───────────────────
    if ela > 70:
        return {
            "final_score": round(max(70, ela * 0.9), 2),
            "breakdown":   full_breakdown,
            "verdict": {
                "label":       "FAKE IMAGE — HEAVILY EDITED",
                "emoji":       "❌",
                "color":       "red",
                "action":      "Refund Rejected",
                "description": "Heavy photo editing detected. Objects appear to have been digitally added or modified.",
                "refund":      False
            }
        }

    # ── ENTERPRISE WEIGHTED FUSION ────────────────────────────
    weights = {
        "AI":        0.25,
        "ELA":       0.15,
        "Duplicate": 0.15,
        "Patch":     0.10,
        "Noise":     0.10,
        "Frequency": 0.10,
        "Diffusion": 0.10,
        "Metadata":  0.05,
    }

    final_score = (
        ai_model  * weights["AI"]        +
        ela       * weights["ELA"]       +
        dup       * weights["Duplicate"] +
        patch     * weights["Patch"]     +
        noise     * weights["Noise"]     +
        frequency * weights["Frequency"] +
        diffusion * weights["Diffusion"] +
        metadata  * weights["Metadata"]
    )

    final_score = round(min(max(final_score, 0), 100), 2)

    # ── CONSISTENCY BOOST ─────────────────────────────────────
    # If 3+ independent signals agree the image is suspicious,
    # force the score above the FAKE threshold even if individually mild
    suspicious_signals = sum([
        ela       > 50,
        ai_model  > 60,
        patch     > 50,
        noise     > 50,
        frequency > 50,
        diffusion > 50,
    ])

    if suspicious_signals >= 3:
        final_score = max(final_score, 65)

    # ── ELA + METADATA COMBINED BOOST ────────────────────────
    # Even if not individually over threshold,
    # heavy editing + suspicious metadata = likely fake
    if ela > 45 and metadata > 30:
        final_score = max(final_score, 58)

    final_score = round(min(final_score, 100), 2)

    return {
        "final_score": final_score,
        "breakdown":   full_breakdown,
        "verdict":     get_verdict(final_score)
    }