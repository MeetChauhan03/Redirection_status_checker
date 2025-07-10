import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 20
TIMEOUT = 5

status_names = {
    200: 'OK',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    307: 'Temporary Redirect',
    308: 'Permanent Redirect',
    400: 'Bad Request',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Not Found',
    500: 'Internal Server Error'
}

def check_url(row_idx, url):
    try:
        response = requests.get(url, timeout=TIMEOUT, allow_redirects=False)
        original_status = response.status_code
        original_status_text = f"{original_status} - {status_names.get(original_status, 'Unknown')}"

        if original_status in (301, 302, 303, 307, 308):
            redirect_url = response.headers.get('Location')
            try:
                redirect_resp = requests.get(redirect_url, timeout=TIMEOUT)
                redirect_status = redirect_resp.status_code
                redirect_status_text = f"{redirect_status} - {status_names.get(redirect_status, 'Unknown')}"
            except requests.RequestException:
                redirect_status_text = 'Error'
        else:
            redirect_url = ''
            redirect_status_text = ''
    except requests.RequestException:
        original_status_text = 'Error'
        redirect_url = ''
        redirect_status_text = ''

    return row_idx, original_status_text, redirect_url, redirect_status_text

st.title("🔗 Bulk URL Status & Redirect Checker")
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx) with URLs in Column A", type="xlsx")

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)

    if 'Original URL' not in df.columns:
        df.columns = ['Original URL'] + list(df.columns[1:])

    url_data = df['Original URL'].dropna().tolist()

    st.info(f"Checking {len(url_data)} URLs, please wait...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_url, idx, url) for idx, url in enumerate(url_data)]

        for future in as_completed(futures):
            results.append(future.result())

    # Sort results back by original row order
    results.sort()

    # Add results to dataframe
    df['Original Status'] = [r[1] for r in results]
    df['Redirect URL'] = [r[2] for r in results]
    df['Redirect Status'] = [r[3] for r in results]

    st.success("✅ URL checking complete!")
    st.dataframe(df)

    # Download link
    st.download_button("📥 Download Results as Excel", df.to_excel(index=False), file_name="url_status_results.xlsx")
