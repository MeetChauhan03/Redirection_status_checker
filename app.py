import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

MAX_WORKERS = 20
TIMEOUT = 5

status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect',
    400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
    404: 'Not Found', 500: 'Internal Server Error'
}

# === Streamlit UI ===
st.set_page_config(page_title="URL Redirect Checker", layout="centered")
st.title("🔗 URL Redirect & Status Checker")

st.markdown("""
Upload an Excel file or paste URLs.  
We'll check the full redirection chain and HTTP status codes.

🛡️ **Private:** No data is stored. All work is in-memory.
""")

uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type="xlsx")

with st.expander("📄 Sample Excel Format"):
    sample_df = pd.DataFrame({"Original URL": ["https://example.com", "https://abc.com"]})
    buffer = BytesIO()
    sample_df.to_excel(buffer, index=False)
    buffer.seek(0)
    st.download_button("⬇️ Download Sample", data=buffer, file_name="sample_urls.xlsx")

text_input = st.text_area("📋 Or paste URLs (one per line):", height=150)

def clean_urls(urls):
    valid = [u.strip() for u in urls if u and "avnhc" not in u.lower()]
    blocked = [u.strip() for u in urls if "avnhc" in u.lower()]
    return valid, blocked

def check_redirect_chain(url):
    session = requests.Session()
    try:
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        steps = []

        for r in response.history:
            steps.append({
                "Redirected URL": r.headers.get('Location') or r.url,
                "Status Code": r.status_code,
                "Status Description": status_names.get(r.status_code, "Unknown"),
                "Server": r.headers.get('Server', 'N/A')
            })

        # Final URL
        steps.append({
            "Redirected URL": response.url,
            "Status Code": response.status_code,
            "Status Description": status_names.get(response.status_code, "Unknown"),
            "Server": response.headers.get('Server', 'N/A')
        })

        return steps

    except Exception as e:
        return [{
            "Redirected URL": "Error",
            "Status Code": "Error",
            "Status Description": str(e),
            "Server": "N/A"
        }]

# === Collect URLs ===
url_list = []
blocked = []

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        raw_urls = df.iloc[:, 0].dropna().astype(str).tolist()
        valid, blocked_input = clean_urls(raw_urls)
        url_list.extend(valid)
        blocked.extend(blocked_input)
    except Exception as e:
        st.error(f"❌ Error reading Excel: {e}")

if text_input.strip():
    raw_text_urls = text_input.strip().splitlines()
    valid, blocked_input = clean_urls(raw_text_urls)
    url_list.extend(valid)
    blocked.extend(blocked_input)

if blocked:
    st.warning("⚠️ Blocked URLs containing 'avnhc':\n" + "\n".join(blocked))

url_list = list(dict.fromkeys(url_list))  # Remove duplicates

# === Processing ===
if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs... Please wait.")
    results = []

    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures = {executor.submit(check_redirect_chain, url): url for url in url_list}
        for future in as_completed(futures):
            url = futures[future]
            steps = future.result()
            for idx, step in enumerate(steps):
                results.append({
                    "Original URL": url if idx == 0 else "",
                    "Step": idx + 1,
                    **step
                })

    df_results = pd.DataFrame(results)
    search = st.text_input("🔎 Filter URLs or status (optional):")
    if search:
        df_results = df_results[df_results.apply(lambda row: search.lower() in str(row).lower(), axis=1)]

    st.dataframe(df_results.style.set_properties(**{'text-align': 'center'}), use_container_width=True)

    # === Export Excel ===
    wb = Workbook()
    ws = wb.active
    ws.title = "URL Status"
    for i, row in enumerate(dataframe_to_rows(df_results, index=False, header=True), 1):
        for j, val in enumerate(row, 1):
            cell = ws.cell(i, j, val)
            if i == 1:
                cell.font = Font(bold=True)

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 3

    out = BytesIO()
    wb.save(out)
    st.download_button("📥 Download Excel", data=out.getvalue(),
                       file_name="url_redirect_report.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
elif not uploaded_file and not text_input:
    st.info("📌 Upload a file or paste URLs to begin.")

# === Footer ===
st.markdown("---")
st.markdown("<center style='color: gray;'>© 2025 Meet Chauhan</center>", unsafe_allow_html=True)
