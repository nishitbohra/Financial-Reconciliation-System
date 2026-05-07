import pandas as pd


def normalize(transactions_df: pd.DataFrame, settlements_df: pd.DataFrame):
    tx = transactions_df.copy()
    st = settlements_df.copy()

    # 1. Filter completed
    tx = tx[tx["status"] == "completed"].copy()

    # 2. Cast timestamps to UTC-aware
    tx["transaction_timestamp"] = pd.to_datetime(tx["transaction_timestamp"]).dt.tz_localize("UTC")
    st["settlement_timestamp"] = pd.to_datetime(st["settlement_timestamp"]).dt.tz_localize("UTC")

    # 3. Round amounts
    tx["amount"] = tx["amount"].round(2)
    st["settled_amount"] = st["settled_amount"].round(2)

    # 4. Add recon_date
    tx["recon_date"] = tx["transaction_timestamp"].dt.date
    st["recon_date"] = st["settlement_timestamp"].dt.date

    return tx.reset_index(drop=True), st.reset_index(drop=True)
