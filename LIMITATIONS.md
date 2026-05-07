# Limitations & Known Constraints

## 1. Synthetic Data Only
All data is computer-generated using Faker and NumPy. Field distributions 
(amounts, timestamps, payment methods) are calibrated to feel realistic but 
are not sourced from a real payments system. Any thresholds (e.g., ±0.05 INR 
tolerance, 95% reconciliation pass rate) are illustrative — a real system 
would derive these from historical SLAs.

## 2. Business Day Handling Is Basic
`_business_add_days()` in `settlements.py` skips Saturday and Sunday only. 
It does not account for public holidays (e.g., Diwali, bank holidays in India). 
This would cause incorrect delay classifications if real bank calendars differ.

## 3. Timestamp Timezone Assumption
`normalize.py` calls `.tz_localize("UTC")` on all timestamps. This assumes 
all input data is naive (timezone-unaware). If integrated with a real system 
that supplies tz-aware timestamps, this will raise a `TypeError`. A 
`.tz_convert()` path would need to be added.

## 4. Matching Is One-to-One Only
The reconciliation engine assigns each transaction to at most one settlement 
and vice versa. Real-world scenarios include:
- One transaction settled in multiple partial batches
- Multiple transactions swept into one settlement batch
These many-to-many patterns are not handled.

## 5. Delayed Settlement Detection Is Cross-Month Only
`classify.py` flags a settlement as delayed only if it lands in a different 
calendar month from its transaction. Settlements that are genuinely late 
(e.g., 10 days late) but happen to stay within the same month are not flagged 
at row level — they only appear as drift in aggregate controls.

## 6. MERCHANT_REF_MATCH Is a Weak Signal
The merchant ref fallback match joins on `merchant_ref == transaction_ref`, 
which is an unlikely real-world relationship. In practice this rule would 
need domain-specific knowledge of how merchant references correlate across 
systems, and carries a HIGH false-positive risk (marked LOW confidence).

## 7. No Persistence / Database Backend
All state is held in memory during a single `python main.py` run and written 
to flat CSV/JSON files. There is no incremental reconciliation, no support for 
reprocessing a single day, and no idempotency guarantees if re-run.

## 8. Dashboard Is Read-Only and Static
The Streamlit dashboard reads pre-generated CSV files. It does not auto-refresh 
and does not allow users to trigger a new reconciliation run or override a 
classification interactively.

## 9. No Authentication or Access Control
Suitable for a local demo only. Any production deployment would need role-based 
access control, audit logging, and secure credential management.

## 10. Performance at Scale
The classification loop in `classify.py` iterates row-by-row with DataFrame 
lookups inside each iteration (`txn_df[txn_df['transaction_id'] == tx_id]`). 
At 1,000 rows this is acceptable (~1–2s). At 1,000,000+ rows this would be 
prohibitively slow — vectorised lookups or indexed joins would be required.
