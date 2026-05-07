import pandas as pd
import numpy as np
import uuid
from datetime import timedelta


class SettlementGenerator:
    @staticmethod
    def _business_add_days(dt, days):
        # add business days only
        current = dt
        added = 0
        while added < days:
            current = current + timedelta(days=1)
            if current.weekday() < 5:  # Mon-Fri
                added += 1
        return current

    @staticmethod
    def generate(transactions_df: pd.DataFrame, seed=42) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        rows = []

        # mapping delays probabilities
        policy = {
            "UPI": ([0, 1], [0.30, 0.70]),
            "credit_card": ([1, 2, 3], [0.60, 0.35, 0.05]),
            "wallet": ([0, 1], [0.80, 0.20]),
            "net_banking": ([1, 2, 3], [0.20, 0.50, 0.30]),
        }

        for _, r in transactions_df.iterrows():
            if r["status"] != "completed":
                continue
            pm = r["payment_method"]
            delays, probs = policy[pm]
            delay = rng.choice(delays, p=probs)

            settled_amount = float(round(r["amount"], 2))
            base_ts = r["transaction_timestamp"]
            settlement_ts = SettlementGenerator._business_add_days(base_ts, int(delay))

            batch_id = None
            if pm == "net_banking":
                batch_id = f"BATCH-{settlement_ts.date().isoformat()}"
            else:
                batch_id = f"BATCH-{uuid.uuid4()}"

            rows.append({
                "settlement_id": f"SET-{uuid.uuid4()}",
                "transaction_ref": r["transaction_id"],
                "settled_amount": settled_amount,
                "settlement_timestamp": settlement_ts.replace(hour=0, minute=0, second=0, microsecond=0),
                "settlement_batch_id": batch_id,
                "settlement_status": "settled",
                "payment_method": pm,
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("settlement_timestamp").reset_index(drop=True)
        return df
