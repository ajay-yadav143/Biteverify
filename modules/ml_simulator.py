import time
import random

def simulate_training():
    progress = []
    accuracy = 0.5

    for epoch in range(1, 11):
        time.sleep(0.1)
        accuracy += random.uniform(0.01, 0.03)
        progress.append({
            "epoch": epoch,
            "accuracy": round(min(accuracy, 0.99), 4)
        })

    return progress
