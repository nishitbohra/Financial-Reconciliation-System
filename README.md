Financial Reconciliation System
================================

Overview
--------
This project is an end-to-end synthetic financial reconciliation system built to demonstrate
how a payments company can identify why its books do not balance at month end. It generates
a realistic set of transactions and bank settlements, deliberately plants the four canonical
gap types that cause reconciliation failures, runs a multi-rule SQL matching engine using
DuckDB, classifies every exception with a plain-English explanation, computes aggregate
drift controls, and exposes a Streamlit dashboard for interactive exploration.

The system is entirely self-contained. No external data files are required. All data is
generated programmatically with a fixed random seed so results are fully reproducible.


The Problem Being Solved
------------------------
A payments platform records a transaction the moment a customer pays. The bank batches and
settles funds 1 to 2 business days later. At month end every transaction should have a
matching settlement. When the totals do not balance, the company needs to know:

  - Which transactions have no settlement?
  - Which settlements have no transaction?
  - Are there duplicate settlement entries inflating the books?
  - Are there rounding differences that only become visible in aggregate?
  - Did any settlements arrive in the following calendar month?


Architecture
------------

  <p align="center">
  <img src="Architecture Diagram.png" width="800"/>
  <br>
  <em>The Propsed Architecture</em>
</p>

Module Reference
----------------

generators/transactions.py
  Generates synthetic transactions using Faker and NumPy. Amounts follow a
  lognormal distribution (mean=4.5, sigma=1.2) to produce a realistic long tail.
  Timestamps use hourly weights that peak between 18:00 and 22:00 and drop during
  02:00 to 06:00. Payment method proportions: UPI 40%, credit_card 25%, wallet 20%,
  net_banking 15%.

generators/settlements.py
  Generates one settlement per completed transaction with a payment-method-specific
  business-day delay. Delay policy:
    UPI          : 0-1 business days (weights 30% / 70%)
    credit_card  : 1-3 business days (weights 60% / 35% / 5%)
    wallet       : 0-1 business days (weights 80% / 20%)
    net_banking  : 1-3 business days (weights 20% / 50% / 30%)
  net_banking settlements share a daily batch ID. All others get a unique batch ID.

generators/anomalies.py
  Injects the four required gap types deterministically using seed=42.

reconciliation/normalize.py
  Filters to completed transactions only, localises timestamps to UTC, rounds
  amounts to 2 decimal places, and adds a recon_date column for daily aggregation.

reconciliation/queries.py
  Holds all DuckDB SQL queries as named string constants.

reconciliation/matcher.py
  Five-step matching waterfall. Once a transaction or settlement is matched it is
  excluded from subsequent steps to prevent double-counting.

reconciliation/aggregate_controls.py
  Runs four aggregate checks: DAILY_DRIFT, PAYMENT_METHOD_DRIFT, BATCH_VALIDATION,
  and OVERALL_RECONCILIATION_RATE.

classification/classify.py
  Classifies each reconciliation row into one of seven anomaly types based on
  priority ordering. Provides a plain-English explanation for each row.

reporting/report_builder.py
  Writes reconciliation_summary.json containing all KPI metrics.

frontend/dashboard.py
  Streamlit dashboard with four tabs: Reconciliation Results (filterable),
  Aggregate Controls (colour-coded), Anomaly Summary (bar charts), Daily Trends
  (line and bar charts of daily transaction vs settlement totals).


Gap Types Planted
-----------------

DELAYED_SETTLEMENT
  3% of completed transactions (27 rows) have their settlement timestamp moved
  to 1-5 days into the next calendar month. This guarantees a cross-month
  settlement gap regardless of where in the month the transaction fell.
  Detected by: calendar-month comparison in classify.py.
  Visible in: classified_exceptions.csv, Anomaly Summary tab, Daily Trends tab.

DUPLICATE_SETTLEMENT
  2% of completed transactions (18 rows) have a second settlement cloned with
  the same transaction_ref, a new settlement_id, and a 1-3 hour timestamp offset.
  This inflates the settlement total without a corresponding second transaction.
  Detected by: transaction_ref frequency count in classify.py.
  Visible in: classified_exceptions.csv, BATCH_VALIDATION control failures.

ORPHAN_REFUND
  10 synthetic settlements are injected with negative amounts referencing
  transaction IDs prefixed ORPHAN- that do not exist in the transactions table.
  These represent refunds whose original transaction cannot be traced.
  Detected by: ORPHAN- prefix check and LEFT JOIN miss in queries.py.
  Visible in: classified_exceptions.csv, Anomaly Summary tab.

ROUNDING_DRIFT
  50 settlements receive a +-0.01 INR adjustment. Each individual adjustment
  falls within the 0.05 INR match tolerance so every row still reconciles.
  The drift only surfaces when daily or per-method totals are summed.
  Detected by: DAILY_DRIFT and PAYMENT_METHOD_DRIFT aggregate controls.
  Visible in: aggregate_control_results.csv, Daily Trends tab.


Matching Rules
--------------

Step 1 - EXACT_MATCH
  transaction_id = settlement.transaction_ref AND amount = settled_amount.
  Confidence: HIGH. amount_delta: 0.00.

Step 2 - TOLERANCE_MATCH
  Same ref join. ABS(amount - settled_amount) <= 0.05 INR.
  Confidence: MEDIUM. Catches rounding-drift rows.

Step 3 - MERCHANT_REF_MATCH
  merchant_ref = settlement.transaction_ref AND ABS(amount - settled_amount) <= 0.10 INR.
  Confidence: LOW. Fallback for systems where merchant ref is the cross-system key.

Step 4 - UNMATCHED_TRANSACTION
  Transactions not consumed by steps 1-3 are marked UNMATCHED.

Step 5 - ORPHAN_SETTLEMENT
  Settlements whose transaction_ref does not exist in the transactions table.


Aggregate Controls
------------------

DAILY_DRIFT
  Compares sum(transaction.amount) to sum(settlement.settled_amount) per recon_date.
  Threshold: +-1.00 INR. FAIL if exceeded.

PAYMENT_METHOD_DRIFT
  Same comparison grouped by payment_method.
  Threshold: +-0.50 INR per method. FAIL if exceeded.

BATCH_VALIDATION
  Detects settlement batches that contain duplicate transaction_ref entries.
  FAIL if any duplicate found in the batch.

OVERALL_RECONCILIATION_RATE
  matched_count / total_completed_transactions.
  PASS if >= 95%. WARN if >= 90%. FAIL if < 90%.


Data Statistics (seed=42, n=1000)
----------------------------------

Transactions generated       : 1,000
  Completed                  : 897
  Failed                     : 77
  Pending                    : 26

Payment method split
  UPI                        : 402
  credit_card                : 247
  wallet                     : 200
  net_banking                : 151

Transaction amounts (INR)
  Minimum                    : 1.13
  Maximum                    : 4,083.15
  Mean                       : 174.46

Settlements generated        : 897
Settlement amounts (INR)
  Minimum                    : 1.13
  Maximum                    : 4,083.15
  Mean (post-drift)          : 174.93

Anomalies injected
  Delayed (cross-month)      : 27 settlements
  Duplicate                  : 18 settlements
  Orphan refunds             : 10 settlements
  Rounding drift             : 50 settlements (+- 0.01 INR each)

Reconciliation results
  Matched                    : 853  (95.09%)
  Unmatched transactions     : 0
  Orphan settlements         : 10

Classified exceptions
  RECONCILED                 : 776
  DUPLICATE_SETTLEMENT       : 85
  ROUNDING_DRIFT             : 41
  DELAYED_SETTLEMENT         : 36
  ORPHAN_SETTLEMENT          : 10

Aggregate control outcomes
  BATCH_VALIDATION PASS      : 752
  BATCH_VALIDATION FAIL      : 50
  DAILY_DRIFT FAIL           : 36
  PAYMENT_METHOD_DRIFT FAIL  : 5
  OVERALL_RECONCILIATION_RATE: PASS (95.09%)

Total amount drift (INR)     : -9,297.09  (driven by duplicate settlements)
Pipeline execution time      : 1.17 seconds


How to Run
----------

Install dependencies:
  pip install -r requirements.txt

Run the full pipeline (generates data, injects gaps, reconciles, classifies, reports):
  python main.py

Launch the interactive dashboard:
  streamlit run frontend/dashboard.py

Run the test suite:
  pytest tests/test_reconciliation.py -v


Output Files (outputs/)
-----------------------

  transactions.csv                 Raw generated transactions (1,000 rows)
  settlements.csv                  Raw settlements before anomaly injection (897 rows)
  transactions_post_anomalies.csv  Transactions after injection (unchanged by design)
  settlements_post_anomalies.csv   Settlements after all anomaly types injected
  transactions_normalized.csv      Completed transactions only, UTC timestamps
  settlements_normalized.csv       Settlements with UTC timestamps and recon_date
  reconciliation_results.csv       Row-level reconciliation with match_status
  aggregate_control_results.csv    Per-day, per-method, per-batch control outcomes
  classified_exceptions.csv        Every row typed and explained
  reconciliation_summary.json      KPI summary (rate, counts, drift, controls)


Configuration (main.py)
-----------------------

  SEED                   = 42      Controls all random generation for reproducibility
  N_TRANSACTIONS         = 1000    Number of transactions to generate
  AMOUNT_TOLERANCE       = 0.05    INR threshold for tolerance matching
  MERCHANT_REF_TOLERANCE = 0.10    INR threshold for merchant ref fallback matching
  OUTPUT_DIR             = outputs


Assumptions
-----------

  1. Only transactions with status = "completed" are expected to settle.
     Failed and pending transactions are excluded from reconciliation scope.

  2. The bank settles on business days (Monday to Friday) only.
     Public holidays are not modelled.

  3. All timestamps are timezone-naive at source and are localised to UTC
     during normalization. Systems supplying tz-aware timestamps would need
     tz_convert instead of tz_localize.

  4. A match tolerance of 0.05 INR is acceptable for row-level matching.
     Amounts within this band are treated as reconciled with MEDIUM confidence.

  5. The daily drift threshold of 1.00 INR and payment-method drift threshold
     of 0.50 INR are illustrative. Real thresholds derive from SLA agreements.

  6. Reconciliation is one-to-one: one transaction to one settlement.
     Partial settlements and batch sweeps across multiple transactions
     are out of scope.

  7. Currency is INR throughout. Multi-currency conversion is not modelled.

  8. A reconciliation rate of 95% or above is considered a passing month end.


Limitations
-----------

  1. Synthetic data only. Not suitable for production use without integration
     to real transaction and settlement feeds.

  2. Business day calculation does not account for public holidays.

  3. tz_localize("UTC") will raise if input timestamps are already tz-aware.

  4. One-to-one matching only. Many-to-one and one-to-many settlement patterns
     (e.g. partial batches, sweeps) are not handled.

  5. DELAYED_SETTLEMENT detection is calendar-month-based only. A settlement
     that is late but stays within the same calendar month is not flagged at
     row level; it surfaces only as aggregate drift.

  6. MERCHANT_REF_MATCH is a weak signal with a high false-positive risk.
     It is assigned LOW confidence and should be reviewed manually in practice.

  7. No persistence or incremental processing. Every run regenerates all data
     from scratch. There is no support for replaying a single day.

  8. The classification loop iterates row-by-row with per-row DataFrame lookups.
     Performance degrades significantly beyond approximately 100,000 rows.
     Vectorised joins would be required at production scale.

  9. The dashboard is read-only. It does not support triggering a new run
     or overriding a classification interactively.

  10. No authentication, audit logging, or access control. Suitable for
      local demonstration only.


Test Suite
----------

Location: tests/test_reconciliation.py
Run with: pytest tests/test_reconciliation.py -v

42 test cases across 8 classes:

  TestTransactionGenerator    (10 tests)  Row count, uniqueness, amounts, reproducibility
  TestSettlementGenerator     ( 5 tests)  Only completed settle, amounts match, timing
  TestAnomalyInjector         ( 8 tests)  Cross-month guarantee, duplicate IDs, orphan negatives
  TestNormalize               ( 5 tests)  UTC localisation, completed-only filter, recon_date
  TestReconciliationEngine    ( 9 tests)  Column presence, no double-matches, delta thresholds
  TestClassificationEngine    (10 tests)  All 4 gap types present, cross-month text, no overlap
  TestAggregateControls       ( 6 tests)  All 4 controls present, batch failures detected
  TestEndToEnd                ( 4 tests)  Full pipeline, all 4 gaps end-to-end, row consistency
