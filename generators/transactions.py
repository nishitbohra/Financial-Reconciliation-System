from faker import Faker
import numpy as np
import pandas as pd
import uuid
from datetime import datetime, timedelta


class TransactionGenerator:
    @staticmethod
    def generate(n=1000, seed=42) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        fake = Faker()
        Faker.seed(seed)

        # timeframe: last 30 days
        end = datetime.utcnow()
        start = end - timedelta(days=30)

        # amount: lognormal long-tail
        amounts = np.round(np.random.default_rng(seed).lognormal(mean=4.5, sigma=1.2, size=n), 2)

        # payment method weights
        methods = ["UPI", "credit_card", "wallet", "net_banking"]
        method_probs = [0.40, 0.25, 0.20, 0.15]
        payment_methods = rng.choice(methods, size=n, p=method_probs)

        # hourly weights: peak 18-22, low 2-6
        hour_weights = np.ones(24)
        hour_weights[18:22] = 5.0  # 18-21 inclusive more likely
        hour_weights[22] = 3.0
        hour_weights[2:6] = 0.2
        hour_probs = hour_weights / hour_weights.sum()

        hours = rng.choice(np.arange(24), size=n, p=hour_probs)
        minutes = rng.integers(0, 60, size=n)
        seconds = rng.integers(0, 60, size=n)

        # statuses
        statuses = rng.choice(["completed", "failed", "pending"], size=n, p=[0.90, 0.07, 0.03])

        rows = []
        for i in range(n):
            tx_id = f"TXN-{uuid.uuid4()}"
            usr = f"USR-{uuid.uuid4()}"
            amt = float(amounts[i])
            curr = "INR"
            pm = payment_methods[i]

            # timestamp: random date between start and end with chosen hour
            rand_day = fake.date_time_between(start_date=start, end_date=end, tzinfo=None)
            timestamp = rand_day.replace(hour=int(hours[i]), minute=int(minutes[i]), second=int(seconds[i]), microsecond=0)

            status = statuses[i]
            merchant_ref = "MER-" + fake.bothify(text="?" * 8 + "#" * 0).upper()

            rows.append({
                "transaction_id": tx_id,
                "user_id": usr,
                "amount": round(amt, 2),
                "currency": curr,
                "payment_method": pm,
                "transaction_timestamp": timestamp,
                "status": status,
                "merchant_ref": merchant_ref,
            })

        df = pd.DataFrame(rows)
        # Deterministic ordering
        df = df.sort_values("transaction_timestamp").reset_index(drop=True)
        return df
