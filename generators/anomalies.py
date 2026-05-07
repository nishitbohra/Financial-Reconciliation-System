import pandas as pd
import numpy as np
import uuid
from datetime import timedelta
from copy import deepcopy


class AnomalyInjector:
    @staticmethod
    def inject(transactions_df: pd.DataFrame, settlements_df: pd.DataFrame, seed=42):
        rng = np.random.default_rng(seed)
        tx = transactions_df.copy()
        st = settlements_df.copy()

        completed = tx[tx["status"] == "completed"]
        n_completed = len(completed)

        # DELAYED_SETTLEMENT: pick 3% of completed txns
        # Guarantee settlement lands in the NEXT calendar month from the transaction date.
        delayed_count = max(1, int(round(0.03 * n_completed)))
        delayed_txns = completed.sample(n=delayed_count, random_state=seed)
        delayed_rows = []
        for _, d in delayed_txns.iterrows():
            # find original settlement
            orig = st[st["transaction_ref"] == d["transaction_id"]]
            if orig.empty:
                continue
            orig_row = orig.iloc[0]
            tx_ts = pd.Timestamp(d["transaction_timestamp"])

            # Calculate first day of the month after the transaction month
            if tx_ts.month == 12:
                next_month_start = pd.Timestamp(year=tx_ts.year + 1, month=1, day=1)
            else:
                next_month_start = pd.Timestamp(year=tx_ts.year, month=tx_ts.month + 1, day=1)

            # Place settlement 1–5 days into the next month (business days not required here,
            # as the point is to guarantee cross-month settlement)
            offset_days = int(rng.integers(1, 6))
            new_set_ts = next_month_start + timedelta(days=offset_days)

            new_row = orig_row.copy()
            new_row["settlement_id"] = f"SET-{uuid.uuid4()}"
            new_row["settlement_timestamp"] = new_set_ts.replace(hour=0, minute=0, second=0, microsecond=0)
            new_row["settlement_batch_id"] = f"BATCH-{new_set_ts.date().isoformat()}"
            new_row["note"] = "delayed_next_month"
            delayed_rows.append(new_row)

        # DUPLICATE_SETTLEMENT: pick 2% -> clone with 1-3 hours offset
        duplicate_count = max(1, int(round(0.02 * n_completed)))
        duplicate_txns = completed.sample(n=duplicate_count, random_state=seed + 1)
        duplicate_rows = []
        for _, d in duplicate_txns.iterrows():
            orig = st[st["transaction_ref"] == d["transaction_id"]]
            if orig.empty:
                continue
            orig_row = orig.iloc[0]
            offset_hours = int(rng.integers(1, 4))
            new_row = orig_row.copy()
            new_row["settlement_id"] = f"SET-{uuid.uuid4()}"
            new_row["settlement_timestamp"] = orig_row["settlement_timestamp"] + timedelta(hours=offset_hours)
            new_row["note"] = "duplicate"
            duplicate_rows.append(new_row)

        # ORPHAN_REFUND: 10 synthetic negative settlements
        orphan_rows = []
        for i in range(10):
            orphan_rows.append({
                "settlement_id": f"SET-{uuid.uuid4()}",
                "transaction_ref": f"ORPHAN-{uuid.uuid4()}",
                "settled_amount": -round(float(rng.lognormal(mean=3.0, sigma=1.0)), 2),
                "settlement_timestamp": pd.Timestamp.now().normalize(),
                "settlement_batch_id": f"BATCH-ORPHAN-{i}",
                "settlement_status": "settled",
                "payment_method": "manual",
                "note": "orphan_refund",
            })

        # ROUNDING_DRIFT: pick 50 settlements
        rounding_count = min(50, len(st))
        rounding_idx = rng.choice(st.index, size=rounding_count, replace=False)
        for idx in rounding_idx:
            delta = rng.choice([-0.01, 0.01])
            st.at[idx, "settled_amount"] = round(st.at[idx, "settled_amount"] + delta, 2)
            st.at[idx, "note"] = "rounding_drift"

        # Append delayed and duplicate rows
        if delayed_rows:
            st = pd.concat([st, pd.DataFrame(delayed_rows)], ignore_index=True)
        if duplicate_rows:
            st = pd.concat([st, pd.DataFrame(duplicate_rows)], ignore_index=True)
        if orphan_rows:
            st = pd.concat([st, pd.DataFrame(orphan_rows)], ignore_index=True)

        # Re-sort
        st = st.sort_values("settlement_timestamp").reset_index(drop=True)

        print(f"Injected anomalies: delayed={len(delayed_rows)}, duplicate={len(duplicate_rows)}, orphan_refunds={len(orphan_rows)}, rounding={rounding_count}")

        return tx, st
