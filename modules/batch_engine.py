import os
from modules.ela import run_ela
from modules.metadata import check_metadata
from modules.duplicate import check_duplicate
from modules.scorer import calculate_fraud_score

def analyze_batch(image_paths):
    results = []

    for path in image_paths:
        ela_img, ela_score = run_ela(path)
        meta = check_metadata(path)
        dup = check_duplicate(path)

        score = calculate_fraud_score(
            ela_score,
            meta["suspicion_score"],
            dup
        )

        results.append({
            "image": os.path.basename(path),
            "fraud_score": score["final_score"],
            "label": score["verdict"]["label"]
        })

    return results
