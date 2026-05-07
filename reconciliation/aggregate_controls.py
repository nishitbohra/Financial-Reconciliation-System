import pandas as pd
import duckdb


class AggregateControls:
    @staticmethod
    def run(txn_df: pd.DataFrame, set_df: pd.DataFrame, recon_results_df: pd.DataFrame) -> pd.DataFrame:
        conn = duckdb.connect(database=':memory:')
        conn.register('transactions', txn_df)
        conn.register('settlements', set_df)

        from reconciliation import queries
        # DAILY_DRIFT
        daily = conn.execute(queries.DAILY_TOTALS_QUERY).df()

        controls = []
        for _, r in daily.iterrows():
            drift = float(r['daily_drift'])
            status = 'PASS' if abs(drift) <= 1.0 else 'FAIL'
            controls.append({
                'control_name': 'DAILY_DRIFT',
                'scope': str(r['recon_date']),
                'expected_value': float(r['txn_total']),
                'actual_value': float(r['set_total']),
                'drift': drift,
                'status': status,
                'notes': 'Daily drift within threshold' if status == 'PASS' else 'Drift exceeds 1.00 INR',
            })

        # PAYMENT_METHOD_DRIFT: compare txn totals to settlement totals by payment method
        pm_tx = conn.execute('SELECT payment_method, SUM(amount) AS txn_total, COUNT(*) AS txn_count FROM transactions GROUP BY payment_method').df()
        pm_set = conn.execute('SELECT payment_method, SUM(settled_amount) AS set_total, COUNT(*) AS set_count FROM settlements GROUP BY payment_method').df()
        pm = pm_tx.merge(pm_set, on='payment_method', how='outer').fillna(0)
        for _, r in pm.iterrows():
            txn_total = float(r['txn_total'])
            set_total = float(r['set_total'])
            drift = txn_total - set_total
            status = 'PASS' if abs(drift) <= 0.5 else 'FAIL'
            controls.append({
                'control_name': 'PAYMENT_METHOD_DRIFT',
                'scope': r['payment_method'],
                'expected_value': txn_total,
                'actual_value': set_total,
                'drift': drift,
                'status': status,
                'notes': 'Per-method drift threshold 0.50 INR',
            })

        # BATCH_VALIDATION
        batches = set_df.groupby('settlement_batch_id').agg({'settlement_id': 'count', 'settled_amount': 'sum'}).reset_index()
        # detect duplicate count by checking settlements with same transaction_ref repeated
        dup_counts = set_df.groupby('transaction_ref').size().reset_index(name='count')
        dup_refs = dup_counts[dup_counts['count'] > 1]['transaction_ref'].tolist()
        for _, r in batches.iterrows():
            batch_id = r['settlement_batch_id']
            dup_in_batch = set_df[(set_df['settlement_batch_id'] == batch_id) & (set_df['transaction_ref'].isin(dup_refs))]
            dup_count = len(dup_in_batch)
            status = 'PASS' if dup_count == 0 else 'FAIL'
            controls.append({
                'control_name': 'BATCH_VALIDATION',
                'scope': batch_id,
                'expected_value': float(r['settled_amount']),
                'actual_value': float(r['settled_amount']),
                'drift': 0.0,
                'status': status,
                'notes': f'Duplicate_count={dup_count}',
            })

        # OVERALL_RECONCILIATION_RATE
        total_completed = len(txn_df)
        matched_count = recon_results_df[recon_results_df['match_status'] == 'MATCHED']['transaction_id'].nunique()
        rate = matched_count / total_completed if total_completed > 0 else 0.0
        status = 'PASS' if rate >= 0.95 else ('WARN' if rate >= 0.90 else 'FAIL')
        controls.append({
            'control_name': 'OVERALL_RECONCILIATION_RATE',
            'scope': 'overall',
            'expected_value': float(total_completed),
            'actual_value': float(matched_count),
            'drift': float(total_completed - matched_count),
            'status': status,
            'notes': f'Reconciliation rate {rate:.4f}',
        })

        df = pd.DataFrame(controls)
        df.to_csv('outputs/aggregate_control_results.csv', index=False)
        return df
