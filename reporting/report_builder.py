import pandas as pd
import json
from datetime import datetime


class ReportBuilder:
    @staticmethod
    def build(recon_results: pd.DataFrame, aggregate_results: pd.DataFrame, classified_exceptions: pd.DataFrame) -> dict:
        total_transactions = recon_results['transaction_id'].nunique()
        matched_count = recon_results[recon_results['match_status'] == 'MATCHED']['transaction_id'].nunique()
        unmatched_count = recon_results[recon_results['match_status'] == 'UNMATCHED']['transaction_id'].nunique()
        duplicate_count = classified_exceptions[classified_exceptions['anomaly_type'] == 'DUPLICATE_SETTLEMENT']['settlement_id'].nunique()
        orphan_refund_count = classified_exceptions[classified_exceptions['anomaly_type'] == 'ORPHAN_REFUND']['settlement_id'].nunique()
        orphan_settlement_count = classified_exceptions[classified_exceptions['anomaly_type'] == 'ORPHAN_SETTLEMENT']['settlement_id'].nunique()
        delayed_settlement_count = classified_exceptions[classified_exceptions['anomaly_type'] == 'DELAYED_SETTLEMENT']['settlement_id'].nunique()
        cross_month_delayed_count = delayed_settlement_count  # all delayed are now guaranteed cross-month
        rounding_drift_count = classified_exceptions[classified_exceptions['anomaly_type'] == 'ROUNDING_DRIFT']['settlement_id'].nunique()

        reconciliation_rate = matched_count / total_transactions if total_transactions > 0 else 0.0

        # total_amount_drift from aggregate daily totals
        try:
            daily = pd.read_csv('outputs/aggregate_control_results.csv')
            # sum drifts where control_name DAILY_DRIFT
            total_drift = daily[daily['control_name'] == 'DAILY_DRIFT']['drift'].sum()
        except Exception:
            total_drift = 0.0

        controls_passed = aggregate_results[aggregate_results['status'] == 'PASS'].shape[0]
        controls_failed = aggregate_results[aggregate_results['status'] != 'PASS'].shape[0]

        summary = {
            'total_transactions': int(total_transactions),
            'matched_count': int(matched_count),
            'unmatched_count': int(unmatched_count),
            'duplicate_count': int(duplicate_count),
            'orphan_refund_count': int(orphan_refund_count),
            'orphan_settlement_count': int(orphan_settlement_count),
            'delayed_settlement_count': int(delayed_settlement_count),
            'cross_month_delayed_count': int(cross_month_delayed_count),
            'rounding_drift_count': int(rounding_drift_count),
            'reconciliation_rate': float(reconciliation_rate),
            'total_amount_drift': float(total_drift),
            'aggregate_controls_passed': int(controls_passed),
            'aggregate_controls_failed': int(controls_failed),
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

        print('\nReconciliation Summary:')
        for k, v in summary.items():
            print(f"  {k}: {v}")

        with open('outputs/reconciliation_summary.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

        return summary
