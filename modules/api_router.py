def route_request(service, payload=None):

    if service == "customer_risk":
        return 50, "Medium Risk"

    if service == "cluster_analysis":
        return {"status": "Cluster simulated"}

    return {"error": "Unknown service"}
