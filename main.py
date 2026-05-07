import os
import time
import logging
from generators.transactions import TransactionGenerator
from generators.settlements import SettlementGenerator
from generators.anomalies import AnomalyInjector
from reconciliation.normalize import normalize
from reconciliation.matcher import ReconciliationEngine
from reconciliation.aggregate_controls import AggregateControls
from classification.classify import ClassificationEngine
from reporting.report_builder import ReportBuilder
import pandas as pd

# CONSTANTS
SEED = 42
N_TRANSACTIONS = 1000
AMOUNT_TOLERANCE = 0.05
MERCHANT_REF_TOLERANCE = 0.10
OUTPUT_DIR = 'outputs'

if __name__ == '__main__':
    start = time.time()
    logging.basicConfig(level=logging.INFO)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    logging.info('Generating transactions...')
    tx = TransactionGenerator.generate(n=N_TRANSACTIONS, seed=SEED)
    tx.to_csv(os.path.join(OUTPUT_DIR, 'transactions.csv'), index=False)

    logging.info('Generating settlements...')
    st = SettlementGenerator.generate(tx, seed=SEED)
    st.to_csv(os.path.join(OUTPUT_DIR, 'settlements.csv'), index=False)

    logging.info('Injecting anomalies...')
    tx2, st2 = AnomalyInjector.inject(tx, st, seed=SEED)
    tx2.to_csv(os.path.join(OUTPUT_DIR, 'transactions_post_anomalies.csv'), index=False)
    st2.to_csv(os.path.join(OUTPUT_DIR, 'settlements_post_anomalies.csv'), index=False)

    logging.info('Normalizing datasets...')
    txn_df, set_df = normalize(tx2, st2)
    txn_df.to_csv(os.path.join(OUTPUT_DIR, 'transactions_normalized.csv'), index=False)
    set_df.to_csv(os.path.join(OUTPUT_DIR, 'settlements_normalized.csv'), index=False)

    logging.info('Reconciling...')
    recon = ReconciliationEngine.reconcile(txn_df, set_df)
    recon.to_csv(os.path.join(OUTPUT_DIR, 'reconciliation_results.csv'), index=False)

    logging.info('Running aggregate controls...')
    agg = AggregateControls.run(txn_df, set_df, recon)

    logging.info('Classifying exceptions...')
    classified = ClassificationEngine.classify(recon, txn_df, set_df)

    logging.info('Building report...')
    summary = ReportBuilder.build(recon, agg, classified)

    end = time.time()
    logging.info(f'Completed in {end - start:.2f} seconds')
