import duckdb
import pandas as pd
from reconciliation import queries


class ReconciliationEngine:
    @staticmethod
    def reconcile(txn_df: pd.DataFrame, set_df: pd.DataFrame) -> pd.DataFrame:
        conn = duckdb.connect(database=':memory:')
        conn.register('transactions', txn_df)
        conn.register('settlements', set_df)

        matched = []
        used_tx = set()
        used_set = set()

        # Step 1: Exact matches
        exact = conn.execute(queries.EXACT_MATCH_QUERY).df()
        for _, r in exact.iterrows():
            matched.append({
                'transaction_id': r['transaction_id'],
                'settlement_id': r['settlement_id'],
                'match_status': 'MATCHED',
                'anomaly_type': '',
                'rule_applied': r['rule_applied'],
                'amount_delta': float(r['amount_delta']),
                'delay_days': None,
                'confidence_level': r['confidence_level'],
                'explanation': f"Exact match on transaction {r['transaction_id']} and settlement {r['settlement_id']}.",
            })
            used_tx.add(r['transaction_id'])
            used_set.add(r['settlement_id'])

        # Step 2: Tolerance matches on remaining
        tol_query = queries.TOLERANCE_MATCH_QUERY + " WHERE t.transaction_id NOT IN (" + ",".join([f"'{x}'" for x in used_tx]) + ")" if used_tx else queries.TOLERANCE_MATCH_QUERY
        tol = conn.execute(tol_query).df()
        for _, r in tol.iterrows():
            matched.append({
                'transaction_id': r['transaction_id'],
                'settlement_id': r['settlement_id'],
                'match_status': 'MATCHED',
                'anomaly_type': '',
                'rule_applied': r['rule_applied'],
                'amount_delta': float(r['amount_delta']),
                'delay_days': None,
                'confidence_level': r['confidence_level'],
                'explanation': f"Tolerance match within 0.05 for {r['transaction_id']} and {r['settlement_id']}.",
            })
            used_tx.add(r['transaction_id'])
            used_set.add(r['settlement_id'])

        # Step 3: Merchant ref matches on remaining
        mref_query = queries.MERCHANT_REF_MATCH_QUERY + " WHERE t.transaction_id NOT IN (" + ",".join([f"'{x}'" for x in used_tx]) + ")" if used_tx else queries.MERCHANT_REF_MATCH_QUERY
        mref = conn.execute(mref_query).df()
        for _, r in mref.iterrows():
            matched.append({
                'transaction_id': r['transaction_id'],
                'settlement_id': r['settlement_id'],
                'match_status': 'MATCHED',
                'anomaly_type': '',
                'rule_applied': r['rule_applied'],
                'amount_delta': float(r['amount_delta']),
                'delay_days': None,
                'confidence_level': r['confidence_level'],
                'explanation': f"Merchant ref match for transaction {r['transaction_id']} to settlement {r['settlement_id']}.",
            })
            used_tx.add(r['transaction_id'])
            used_set.add(r['settlement_id'])

        # Step 4: Unmatched transactions
        all_tx_ids = set(txn_df['transaction_id'].tolist())
        unmatched_tx = all_tx_ids - used_tx
        for txid in unmatched_tx:
            matched.append({
                'transaction_id': txid,
                'settlement_id': None,
                'match_status': 'UNMATCHED',
                'anomaly_type': '',
                'rule_applied': 'NONE',
                'amount_delta': None,
                'delay_days': None,
                'confidence_level': 'NONE',
                'explanation': f"No settlement found for transaction {txid} after all matching rules.",
            })

        # Step 5: Orphan settlements
        orphan_query = queries.ORPHAN_SETTLEMENT_QUERY
        orphans = conn.execute(orphan_query).df()
        for _, r in orphans.iterrows():
            matched.append({
                'transaction_id': None,
                'settlement_id': r['settlement_id'],
                'match_status': 'ORPHAN',
                'anomaly_type': '',
                'rule_applied': 'NONE',
                'amount_delta': None,
                'delay_days': None,
                'confidence_level': 'NONE',
                'explanation': f"Settlement {r['settlement_id']} references unknown transaction {r['transaction_ref']}.",
            })

        # Step 6: Duplicate detection
        dup = conn.execute(queries.DUPLICATE_DETECTION_QUERY).df()
        dup_tx_refs = set(dup['transaction_ref'].tolist()) if not dup.empty else set()
        # mark duplicates: any settlement rows with transaction_ref in dup_tx_refs
        dup_rows = set_df[set_df['transaction_ref'].isin(dup_tx_refs)]
        for _, r in dup_rows.iterrows():
            # find if already present in matched and mark as DUPLICATE
            for rec in matched:
                if rec['settlement_id'] == r['settlement_id']:
                    rec['match_status'] = 'DUPLICATE'
                    rec['anomaly_type'] = 'DUPLICATE_SETTLEMENT'
                    rec['explanation'] = f"Settlement replay detected: {r['settlement_id']} for transaction {r['transaction_ref']} with amount {r['settled_amount']}."

        recon_df = pd.DataFrame(matched)

        # compute delay_days for matched rows where possible
        # merge dates
        recon_df = recon_df.merge(txn_df[['transaction_id', 'transaction_timestamp', 'payment_method', 'amount']], how='left', on='transaction_id')
        recon_df = recon_df.merge(set_df[['settlement_id', 'settlement_timestamp', 'settled_amount', 'transaction_ref']], how='left', on='settlement_id')

        def compute_delay(row):
            try:
                if pd.isna(row['transaction_timestamp']) or pd.isna(row['settlement_timestamp']):
                    return None
                t = pd.to_datetime(row['transaction_timestamp']).date()
                s = pd.to_datetime(row['settlement_timestamp']).date()
                return (s - t).days
            except Exception:
                return None

        recon_df['delay_days'] = recon_df.apply(compute_delay, axis=1)

        # ensure amount_delta numeric
        recon_df['amount_delta'] = recon_df['amount_delta'].astype(float)

        # fill confidence for unmatched
        recon_df['confidence_level'] = recon_df['confidence_level'].fillna('NONE')

        # ensure explanation non-empty
        recon_df['explanation'] = recon_df['explanation'].fillna('No explanation available.')

        # Save intermediate
        recon_df.to_csv('outputs/reconciliation_intermediate.csv', index=False)

        return recon_df
