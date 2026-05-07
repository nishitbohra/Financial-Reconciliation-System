import streamlit as st
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title='Financial Reconciliation Dashboard', layout='wide')

@st.cache_data
def load_summary():
    try:
        with open('outputs/reconciliation_summary.json') as f:
            return json.load(f)
    except Exception:
        return None

@st.cache_data
def load_recon_results():
    try:
        return pd.read_csv('outputs/reconciliation_results.csv')
    except Exception:
        return pd.DataFrame()

@st.cache_data
def load_aggregate():
    try:
        return pd.read_csv('outputs/aggregate_control_results.csv')
    except Exception:
        return pd.DataFrame()

@st.cache_data
def load_classified():
    try:
        return pd.read_csv('outputs/classified_exceptions.csv')
    except Exception:
        return pd.DataFrame()

summary = load_summary()
st.title('Financial Reconciliation Dashboard')
if summary:
    st.subheader(f"Generated at: {summary.get('generated_at')}")
else:
    st.subheader('No summary available yet')

# KPI row
col1, col2, col3, col4, col5 = st.columns(5)
if summary:
    col1.metric('Reconciliation Rate', f"{summary.get('reconciliation_rate',0)*100:.2f}%")
    col2.metric('Unmatched Transactions', summary.get('unmatched_count', 0))
    col3.metric('Duplicate Settlements', summary.get('duplicate_count', 0))
    col4.metric('Cross-Month Delayed', summary.get('cross_month_delayed_count', summary.get('delayed_settlement_count', 0)))
    col5.metric('Total Amount Drift (INR)', f"{summary.get('total_amount_drift', 0):.2f}")
else:
    col1.metric('Reconciliation Rate', 'N/A')
    col2.metric('Unmatched Transactions', 'N/A')
    col3.metric('Duplicate Settlements', 'N/A')
    col4.metric('Cross-Month Delayed', 'N/A')
    col5.metric('Total Amount Drift (INR)', 'N/A')

recon_df = load_recon_results()
agg_df = load_aggregate()
class_df = load_classified()

tabs = st.tabs(['Reconciliation Results', 'Aggregate Controls', 'Anomaly Summary', 'Daily Trends'])

with tabs[0]:
    st.header('Reconciliation Results')
    anomaly_opts = [''] + sorted(class_df['anomaly_type'].dropna().unique().tolist())
    pm_opts = [''] + sorted(recon_df['payment_method'].dropna().unique().tolist()) if 'payment_method' in recon_df.columns else ['']
    sel_anomalies = st.multiselect('Anomaly Type', options=anomaly_opts)
    sel_methods = st.multiselect('Payment Method', options=pm_opts)
    date_range = st.date_input('Date Range')

    filtered = recon_df.copy()
    if sel_anomalies:
        filtered = filtered[filtered['anomaly_type'].isin(sel_anomalies)] if 'anomaly_type' in filtered.columns else filtered
    if sel_methods:
        filtered = filtered[filtered['payment_method'].isin(sel_methods)] if 'payment_method' in filtered.columns else filtered

    st.markdown(f"Row count: {len(filtered)}")
    if not filtered.empty:
        display_cols = ['transaction_id', 'settlement_id', 'match_status', 'anomaly_type', 'amount_delta', 'delay_days', 'explanation']
        available = [c for c in display_cols if c in filtered.columns]
        st.dataframe(filtered[available])
    else:
        st.info('No reconciliation results available yet.')

with tabs[1]:
    st.header('Aggregate Controls')
    if agg_df.empty:
        st.info('No aggregate controls available yet.')
    else:
        def color_row(row):
            if row['status'] == 'PASS':
                return ['background-color: #d4ffd4'] * len(row)
            if row['status'] == 'WARN':
                return ['background-color: #fff4c2'] * len(row)
            return ['background-color: #ffd4d4'] * len(row)
        st.dataframe(agg_df.style.apply(color_row, axis=1))

with tabs[2]:
    st.header('Anomaly Summary')
    if class_df.empty:
        st.info('No classified exceptions yet.')
    else:
        anom_counts = class_df['anomaly_type'].value_counts()
        st.bar_chart(anom_counts)
        unmatched = class_df[class_df['anomaly_type'] == 'UNMATCHED_TRANSACTION']
        if not unmatched.empty and 'payment_method' in unmatched.columns:
            st.bar_chart(unmatched['payment_method'].value_counts())
        st.dataframe(class_df[class_df['anomaly_type'] != 'RECONCILED'])

with tabs[3]:
    st.header('Daily Trends')
    try:
        daily = pd.read_csv('outputs/aggregate_control_results.csv')
        daily_only = daily[daily['control_name'] == 'DAILY_DRIFT']
        if not daily_only.empty:
            df = daily_only.copy()
            df['recon_date'] = pd.to_datetime(df['scope'])
            df = df.sort_values('recon_date')
            st.line_chart(df.set_index('recon_date')[['expected_value', 'actual_value']])
            st.bar_chart(df.set_index('recon_date')['drift'])
        else:
            st.info('No daily drift data available.')
    except Exception:
        st.info('Unable to load daily trends.')
