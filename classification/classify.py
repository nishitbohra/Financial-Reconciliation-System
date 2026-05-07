import pandas as pd


class ClassificationEngine:
    @staticmethod
    def classify(recon_results_df: pd.DataFrame, txn_df: pd.DataFrame, set_df: pd.DataFrame) -> pd.DataFrame:
        df = recon_results_df.copy()

        # helper lookups
        dup_sets = set_df['transaction_ref'].value_counts()
        dup_refs = set(dup_sets[dup_sets > 1].index.tolist())

        def classify_row(row):
            anomaly = ''
            explanation = ''

            # DUPLICATE_SETTLEMENT
            if row['settlement_id'] and row.get('transaction_id') and row.get('transaction_id') in dup_refs:
                anomaly = 'DUPLICATE_SETTLEMENT'
                explanation = f"Settlement replayed: {row['settlement_id']} matches {row['transaction_id']} with amount {row.get('settled_amount', '')}. Original settlement exists."
                return anomaly, explanation

            # ORPHAN_REFUND
            if row['settlement_id'] and str(row.get('transaction_ref', '')).startswith('ORPHAN-'):
                anomaly = 'ORPHAN_REFUND'
                explanation = f"Refund settlement {row['settlement_id']} for {row.get('settled_amount', 0)} INR has no matching transaction. Possible manual refund or lineage loss."
                return anomaly, explanation

            # DELAYED_SETTLEMENT: flag if settlement landed in a different (later) calendar month
            tx_id = row.get('transaction_id')
            s_id = row.get('settlement_id')
            if tx_id and s_id:
                tx_row = txn_df[txn_df['transaction_id'] == tx_id]
                s_row = set_df[set_df['settlement_id'] == s_id]
                if not tx_row.empty and not s_row.empty:
                    tx_ts = pd.Timestamp(tx_row.iloc[0]['transaction_timestamp'])
                    set_ts = pd.Timestamp(s_row.iloc[0]['settlement_timestamp'])
                    tx_month = (tx_ts.year, tx_ts.month)
                    set_month = (set_ts.year, set_ts.month)
                    if set_month > tx_month:
                        delay_days_val = (set_ts - tx_ts).days
                        anomaly = 'DELAYED_SETTLEMENT'
                        explanation = (
                            f"Settlement for {tx_id} landed in {set_ts.strftime('%B %Y')} "
                            f"but transaction was in {tx_ts.strftime('%B %Y')} "
                            f"({delay_days_val} days late — cross-month settlement)."
                        )
                        return anomaly, explanation

            # ROUNDING_DRIFT
            if row['match_status'] == 'MATCHED' and row['amount_delta'] is not None and abs(row['amount_delta']) > 0 and abs(row['amount_delta']) <= 0.05:
                anomaly = 'ROUNDING_DRIFT'
                explanation = f"Matched with minor rounding difference of {row['amount_delta']} INR. Contributes to aggregate drift."
                return anomaly, explanation

            # UNMATCHED_TRANSACTION
            if row['match_status'] == 'UNMATCHED':
                txn = txn_df[txn_df['transaction_id'] == row['transaction_id']]
                if not txn.empty:
                    t = txn.iloc[0]
                    anomaly = 'UNMATCHED_TRANSACTION'
                    explanation = f"No settlement found for {row['transaction_id']} ({t['payment_method']}, {t['amount']} INR). Pending or failed settlement expected."
                    return anomaly, explanation

            # ORPHAN_SETTLEMENT
            if row['match_status'] == 'ORPHAN':
                anomaly = 'ORPHAN_SETTLEMENT'
                explanation = f"Settlement {row['settlement_id']} references unknown transaction {row.get('transaction_ref', '')}. Requires manual investigation."
                return anomaly, explanation

            # RECONCILED
            if row['match_status'] == 'MATCHED':
                anomaly = 'RECONCILED'
                explanation = f"Fully reconciled via {row.get('rule_applied', 'UNKNOWN')}."
                return anomaly, explanation

            return '', ''

        # ensure settled_amount and transaction_ref available
        merged = df.merge(set_df[['settlement_id', 'settled_amount', 'transaction_ref']], how='left', on='settlement_id')
        merged = merged.merge(txn_df[['transaction_id', 'payment_method', 'amount']], how='left', on='transaction_id')

        results = []
        for _, r in merged.iterrows():
            anomaly, explanation = classify_row(r)
            r['anomaly_type'] = anomaly
            r['explanation'] = explanation if explanation else r.get('explanation', '')
            results.append(r)

        out = pd.DataFrame(results)
        out.to_csv('outputs/classified_exceptions.csv', index=False)
        return out
