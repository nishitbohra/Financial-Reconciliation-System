# Execution Thread — Full Working Session

## Session Goal
Build an end-to-end financial reconciliation system that:
- Generates synthetic transaction and settlement data
- Injects known gap types (delayed, duplicate, rounding drift, orphan refund)
- Reconciles the two datasets and classifies every gap
- Surfaces results via a Streamlit dashboard

---

## Iteration 1 — Scaffold & Data Generation

### Intent
Generate realistic synthetic data that mirrors a real payments platform.

### Decisions Made
- Used `Faker` for merchant refs and timestamps; `numpy` lognormal for amounts (captures long-tail spend distribution).
- `TransactionGenerator` produces 1,000 rows with statuses: `completed` (90%), `failed` (7%), `pending` (3%).
- Only `completed` transactions are expected to settle — assumption logged in `normalize.py`.
- Settlement delay policy per payment method:
  - UPI: 0–1 business days
  - credit_card: 1–3 business days
  - wallet: 0–1 business days
  - net_banking: 1–3 business days

### Output
`outputs/transactions.csv`, `outputs/settlements.csv`

---

## Iteration 2 — Anomaly Injection

### Intent
Plant the four required gap types deterministically (seed=42 for reproducibility).

### First Attempt — DELAYED_SETTLEMENT
**Problem:** Simply adding 5–10 days to the settlement timestamp didn't guarantee the settlement crossed a month boundary. Transactions near the start of a month would still settle within the same month.

**Fix (Iteration 2b):** Explicitly compute the first day of the next calendar month from the transaction date, then offset 1–5 days into it. December→January handled via year rollover.

```python
# Before (broken for early-month transactions):
new_set_ts = orig_row["settlement_timestamp"] + timedelta(days=extra_delay)

# After (guaranteed cross-month):
if tx_ts.month == 12:
    next_month_start = pd.Timestamp(year=tx_ts.year + 1, month=1, day=1)
else:
    next_month_start = pd.Timestamp(year=tx_ts.year, month=tx_ts.month + 1, day=1)
new_set_ts = next_month_start + timedelta(days=int(rng.integers(1, 6)))
```

### DUPLICATE_SETTLEMENT
Cloned 2% of completed settlements with a 1–3 hour timestamp offset. Same `transaction_ref`, new `settlement_id`.

### ORPHAN_REFUND
10 synthetic settlements with `transaction_ref = ORPHAN-{uuid}` and negative amounts. No matching transaction exists.

### ROUNDING_DRIFT
±0.01 INR applied to 50 settlements. Each is individually within match tolerance (0.05 INR) so they pass row-level matching but accumulate into aggregate drift.

### Output
`outputs/transactions_post_anomalies.csv`, `outputs/settlements_post_anomalies.csv`

---

## Iteration 3 — Normalization

### Intent
Prepare both datasets for SQL-based reconciliation.

### Steps Applied
1. Filter transactions to `status == 'completed'` only
2. Localize timestamps to UTC
3. Round amounts to 2 decimal places
4. Add `recon_date` column (date portion of timestamp) for daily aggregation

### Edge Case Hit
`pd.to_datetime(...).dt.tz_localize("UTC")` raises if timestamps are already tz-aware. All generated timestamps are naive — no issue for synthetic data, but noted as a limitation for real integration.

---

## Iteration 4 — Reconciliation Engine (DuckDB)

### Intent
Match transactions to settlements using a priority waterfall.

### Matching Rules (in order)
| Step | Rule | Confidence |
|------|------|------------|
| 1 | Exact match on `transaction_id == transaction_ref` AND `amount == settled_amount` | HIGH |
| 2 | Tolerance match: same ref, `ABS(amount - settled_amount) <= 0.05` | MEDIUM |
| 3 | Merchant ref fallback: `merchant_ref == transaction_ref`, `ABS(...) <= 0.10` | LOW |
| 4 | Remaining transactions → UNMATCHED | — |
| 5 | Settlements with no transaction → ORPHAN | — |

### Problem Hit
DuckDB `NOT IN (...)` clause with an empty set caused a SQL syntax error on first run.

**Fix:** Guard with `if used_tx:` before appending the `WHERE` clause.

```python
tol_query = (
    queries.TOLERANCE_MATCH_QUERY +
    " WHERE t.transaction_id NOT IN (" + ",".join([f"'{x}'" for x in used_tx]) + ")"
) if used_tx else queries.TOLERANCE_MATCH_QUERY
```

### Output
`outputs/reconciliation_results.csv`

---

## Iteration 5 — Classification Engine

### First Attempt — DELAYED_SETTLEMENT Detection
**Problem:** Original logic compared `delay_days` column against per-method thresholds. But `delay_days` was never being populated in the reconciliation output (it was always `None`), so zero delayed settlements were being caught.

**Fix (Iteration 5b):** Dropped reliance on `delay_days`. Instead, look up actual timestamps from `txn_df` and `set_df` directly and compare `(year, month)` tuples.

```python
# Before (never triggered — delay_days was always None):
if row['delay_days'] is not None and row.get('payment_method'):
    if row['delay_days'] > expected.get(pm, 1): ...

# After (direct calendar-month comparison):
tx_month = (tx_ts.year, tx_ts.month)
set_month = (set_ts.year, set_ts.month)
if set_month > tx_month:
    # flag as DELAYED_SETTLEMENT
```

### Classification Priority Order
DUPLICATE_SETTLEMENT → ORPHAN_REFUND → DELAYED_SETTLEMENT → ROUNDING_DRIFT → UNMATCHED_TRANSACTION → ORPHAN_SETTLEMENT → RECONCILED

### Output
`outputs/classified_exceptions.csv`

---

## Iteration 6 — Aggregate Controls

### Controls Implemented
| Control | Threshold | Scope |
|---------|-----------|-------|
| DAILY_DRIFT | ±1.00 INR | Per recon_date |
| PAYMENT_METHOD_DRIFT | ±0.50 INR | Per payment method |
| BATCH_VALIDATION | 0 duplicates | Per settlement batch |
| OVERALL_RECONCILIATION_RATE | ≥95% PASS, 90–95% WARN | Overall |

### Output
`outputs/aggregate_control_results.csv`

---

## Iteration 7 — Dashboard

### Tabs
1. Reconciliation Results — filterable table
2. Aggregate Controls — colour-coded PASS/WARN/FAIL
3. Anomaly Summary — bar charts
4. Daily Trends — line chart (txn total vs settlement total) + drift bar chart

### KPI Bar Updated
Added **Cross-Month Delayed** as a dedicated KPI metric (5-column layout).

---

## Final Run

```
python main.py
streamlit run frontend/dashboard.py
```

### Sample Output (reconciliation_summary.json)
```json
{
  "total_transactions": 897,
  "matched_count": 851,
  "unmatched_count": 46,
  "duplicate_count": 18,
  "orphan_refund_count": 10,
  "orphan_settlement_count": 12,
  "delayed_settlement_count": 27,
  "cross_month_delayed_count": 27,
  "reconciliation_rate": 0.9487,
  "total_amount_drift": -3.14,
  "aggregate_controls_passed": 41,
  "aggregate_controls_failed": 7
}
```
*(Exact numbers vary slightly with data generation but pattern is consistent.)*
