import streamlit as st
import json
import pandas as pd
import plotly.express as px

DB_PATH = "database/hashes.json"

def show_dashboard():

    st.title("📊 Fraud Analytics Dashboard")

    if not DB_PATH:
        st.warning("No data available")
        return

    with open(DB_PATH, "r") as f:
        data = json.load(f)

    if not data:
        st.warning("No fraud cases yet")
        return

    df = pd.DataFrame(data.values())

    col1, col2 = st.columns(2)

    col1.metric("Total Cases", len(df))

    fake_rate = round((df["label"] == "FAKE IMAGE").mean() * 100, 2)
    col2.metric("Fraud Rate %", fake_rate)

    fig = px.pie(df, names="label", title="Verdict Distribution")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df.sort_values("timestamp", ascending=False))
