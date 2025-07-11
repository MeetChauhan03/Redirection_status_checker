import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

# === Config ===
MAX_WORKERS = 20
TIMEOUT = 5

status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect',
    400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
    404: 'Not Found', 500: 'Internal Server Error'
}

def fetch_server_header(url, timeout=TIMEOUT):
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        return resp.headers.get('Server', 'N/A')
    except:
        return 'N/A'

def check_redirect_chain(url):
    try:
        session = requests.Session()
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        history = response.history
        steps = []

        for i, r in enumerate(history):
            location = r.headers.get('Location') or r.url
            server = r.headers.get('Server') or fetch_server_header(location)
            steps.append({
                'Step': i + 1,
                'Redirected URL': location,
                'Status Code': r.status_code,
                'Status Description': status_names.get(r.status_code, 'Unknown'),
                'Server': server or 'N/A'
            })

        server_final = response.headers.get('Server') or fetch_server_header(response.url)
        steps.append({
            'Step': len(steps) + 1,
            'Redirected URL': response.url,
            'Status Code': response.status_code,
            'Status Description': status_names.get(response.status_code, 'Unknown'),
            'Server': server_final or 'N/A'
        })

        return steps
    except Exception as e:
        return [{
            'Step': 1,
            'Redirected URL': 'Error',
            'Status Code': 'Error',
            'Status Description': str(e),
            'Server': 'N/A'
        }]

def clean_urls(urls):
    allowed = [u for u in urls if "avnhc" not in u.lower()]
    blocked = [u for u in urls if "avnhc" in u.lower()]
    return allowed, blocked

# === UI ===
st.set_page_config(page_title="🔗 URL Status & Redirect Chain Checker", layout="wide")
st.markdown("<h1 style='text-align: center;'>🔗 URL Status & Redirect Chain Checker</h1>", unsafe_allow_html=True)

st.markdown("""
<div style='background-color:#f9f9f9; padding:15px; border-radius:10px'>
Upload an Excel file or paste URLs below.  
We'll check the full redirect chain, server used, and status code.

🔐 <b>Privacy:</b> No data is stored. All processing is done in-memory and deleted after session.
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type="xlsx")

with col2:
    st.markdown("📄 Download Sample Format")
    sample_df = pd.DataFrame({"Original URL": ["https://example.com", "https://abc.com"]})
    buffer = BytesIO()
    sample_df.to_excel(buffer, index=False)
    st.download_button("⬇️ Sample Excel", data=buffer.getvalue(), file_name="sample_urls.xlsx")

text_input = st.text_area("🔽 Or paste URLs (one per line):", height=140)

# === Get URLs ===
url_list = []
blocked_urls = []

if uploaded_file:
    df_input = pd.read_excel(uploaded_file)
    urls = df_input.iloc[:, 0].dropna().astype(str).tolist()
    valid, blocked = clean_urls(urls)
    url_list.extend(valid)
    blocked_urls.extend(blocked)

if text_input.strip():
    pasted = [line.strip() for line in text_input.strip().splitlines() if line.strip()]
    valid, blocked = clean_urls(pasted)
    url_list.extend(valid)
    blocked_urls.extend(blocked)

url_list = list(dict.fromkeys(url_list))

if blocked_urls:
    st.warning(f"❌ Blocked URLs (contain 'avnhc'):\n" + "\n".join(blocked_urls))

# === Process ===
if url_list:
    st.info(f"🔍 Processing {len(url_list)} URLs...")
    results = {}

    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures = {executor.submit(check_redirect_chain, url): url for url in url_list}
        for f in as_completed(futures):
            results[futures[f]] = f.result()

    # === Display Results ===
    full_rows = []

    for url, steps in results.items():
        with st.expander(f"🔗 {url}", expanded=False):
            chain_text = " ➤ ".join([f"[{s['Status Code']}] {s['Redirected URL']}" for s in steps])
            st.markdown(f"**Redirect Chain:** `{chain_text}`")

            df_chain = pd.DataFrame(steps)
            df_chain = df_chain[["Step", "Redirected URL", "Status Code", "Status Description", "Server"]]
            st.dataframe(df_chain, use_container_width=True, height=220)

            for step in steps:
                full_rows.append({
                    "Original URL": url,
                    **step
                })

    df_export = pd.DataFrame(full_rows)

    # === Export to Excel ===
    wb = Workbook()
    ws = wb.active
    ws.title = "URL Results"
    for r_idx, row in enumerate(dataframe_to_rows(df_export, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = Font(bold=True)

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 2

    excel_out = BytesIO()
    wb.save(excel_out)
    excel_out.seek(0)

    st.download_button("📥 Download Full Report", data=excel_out,
                       file_name="url_status_results.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("📌 Upload an Excel file or paste URLs to begin.")

# === Footer ===
st.markdown("""
---
<div style='text-align: center; color: grey;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)
