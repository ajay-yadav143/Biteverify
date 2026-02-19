import pandas as pd

def detect_clusters(df):
    if df.empty:
        return pd.DataFrame()

    cluster = df.groupby("customer_id")["final_score"].mean().reset_index()
    cluster = cluster.sort_values("final_score", ascending=False)
    return cluster
