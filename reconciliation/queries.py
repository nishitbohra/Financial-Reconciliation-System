EXACT_MATCH_QUERY = """
SELECT
  t.transaction_id,
  s.settlement_id,
  'EXACT_MATCH' AS rule_applied,
  0.0 AS amount_delta,
  'HIGH' AS confidence_level
FROM transactions t
JOIN settlements s
  ON t.transaction_id = s.transaction_ref
 AND t.amount = s.settled_amount
"""

TOLERANCE_MATCH_QUERY = """
SELECT
  t.transaction_id,
  s.settlement_id,
  'TOLERANCE_MATCH' AS rule_applied,
  (t.amount - s.settled_amount) AS amount_delta,
  'MEDIUM' AS confidence_level
FROM transactions t
JOIN settlements s
  ON t.transaction_id = s.transaction_ref
 AND ABS(t.amount - s.settled_amount) <= 0.05
"""

MERCHANT_REF_MATCH_QUERY = """
SELECT
  t.transaction_id,
  s.settlement_id,
  'MERCHANT_REF_MATCH' AS rule_applied,
  (t.amount - s.settled_amount) AS amount_delta,
  'LOW' AS confidence_level
FROM transactions t
JOIN settlements s
  ON t.merchant_ref = s.transaction_ref
 AND ABS(t.amount - s.settled_amount) <= 0.10
"""

DUPLICATE_DETECTION_QUERY = """
SELECT
  transaction_ref,
  COUNT(*) AS settlement_count,
  SUM(settled_amount) AS total_settled
FROM settlements
GROUP BY transaction_ref
HAVING COUNT(*) > 1
"""

ORPHAN_SETTLEMENT_QUERY = """
SELECT settlement_id, transaction_ref, settled_amount
FROM settlements s
LEFT JOIN transactions t
  ON t.transaction_id = s.transaction_ref
WHERE t.transaction_id IS NULL
"""

DAILY_TOTALS_QUERY = """
WITH tx AS (
  SELECT recon_date, SUM(amount) AS txn_total, COUNT(*) AS txn_count
  FROM transactions
  GROUP BY recon_date
), st AS (
  SELECT recon_date AS recon_date, SUM(settled_amount) AS set_total, COUNT(*) AS set_count
  FROM settlements
  GROUP BY recon_date
)
SELECT
  COALESCE(tx.recon_date, st.recon_date) AS recon_date,
  COALESCE(tx.txn_total, 0.0) AS txn_total,
  COALESCE(tx.txn_count, 0) AS txn_count,
  COALESCE(st.set_total, 0.0) AS set_total,
  COALESCE(st.set_count, 0) AS set_count,
  COALESCE(tx.txn_total, 0.0) - COALESCE(st.set_total, 0.0) AS daily_drift
FROM tx
FULL OUTER JOIN st USING (recon_date)
ORDER BY recon_date
"""

PAYMENT_METHOD_TOTALS_QUERY = """
SELECT payment_method, SUM(amount) AS txn_total, COUNT(*) AS txn_count
FROM transactions
GROUP BY payment_method
"""
