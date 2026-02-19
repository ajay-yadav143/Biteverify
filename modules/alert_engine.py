def check_alert(fraud_score, customer_risk):
    alerts = []

    if fraud_score > 80:
        alerts.append("🚨 Critical fraud score detected")

    if customer_risk > 70:
        alerts.append("⚠ High customer fraud history")

    return alerts
