import random
import time

def generate_stream_event():
    customers = ["C1001","C1002","C2001","C3004","C4444"]
    labels = ["GENUINE IMAGE","FAKE IMAGE","NEEDS REVIEW"]

    return {
        "customer_id": random.choice(customers),
        "fraud_score": random.randint(5, 95),
        "label": random.choice(labels),
        "timestamp": time.strftime("%H:%M:%S")
    }
