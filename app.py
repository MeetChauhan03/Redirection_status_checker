import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font

# === Configuration ===
MAX_WORKERS = 20
TIMEOUT = 8

status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect', 400: 'Bad Request',
    401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 500: 'Internal Server Error'
}

st.set_page_config(page_title="URL Redirect Tracker", layout="wide")
st.title("🔁 Full URL Redirect Tracker + Server Info")

st.markdown("""
Upload an Excel file or paste URLs below. This app tracks full redirection chains, status codes, and server headers.

🔒 Your data is processed in-memory only.
""")

uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

with st.expander("📄 Download sample Excel format"):
    sample_df = pd.DataFrame({"Original URL": ["https://example.com"]})
    sample_buffer = BytesIO()
    sample_df.to_excel(sample_buffer, index=False)
    sample_buffer.seek(0)
    st.download_button("⬇️ Download Sample Excel", sample_buffer, file_name="sample_urls.xlsx")
    st.caption("Must contain a column named 'Original URL'.")

st.markdown("#### Or paste URLs below (one per line):")
text_input = st.text_area("🔽 Paste URLs:", height=150)

def get_redirect_chain(url):
    try:
        session = requests.Session()
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        history = response.history
        steps = []

        for i, r in enumerate(history):
            steps.append({
                'Original URL': url,
                'Step': i + 1,
                'Redirected URL': r.headers.get('Location') or r.url,
                'Status Code': r.status_code,
                'Status Description': status_names.get(r.status_code, 'Unknown'),
                'Server': r.headers.get('Server', 'N/A'),
                'Final URL': response.url,
                'Final Status': f"{response.status_code} - {status_names.get(response.status_code, 'Unknown')}"
            })

        if not steps:
            steps.append({
                'Original URL': url,
                'Step': 1,
                'Redirected URL': url,
                'Status Code': response.status_code,
                'Status Description': status_names.get(response.status_code, 'Unknown'),
                'Server': response.headers.get('Server', 'N/A'),
                'Final URL': response.url,
                'Final Status': f"{response.status_code} - {status_names.get(response.status_code, 'Unknown')}"
            })

        return steps

    except requests.RequestException as e:
        return [{
            'Original URL': url,
            'Step': 1,
            'Redirected URL': 'Error',
            'Status Code': 'Error',
            'Status Description': str(e),
            'Server': 'N/A',
            'Final URL': 'Error',
            'Final Status': 'Error'
        }]

# === Collect URL list
url_list = []
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        df.columns = ['Original URL'] + list(df.columns[1:])
        url_list = df['Original URL'].dropna().tolist()
    except Exception as e:
        st.error(f"❌ Error reading Excel file: {e}")
elif text_input.strip():
    url_list = [line.strip() for line in text_input.strip().splitlines() if line.strip()]

# === Process URLs
if url_list:
    st.info(f"🔍 Processing {len(url_list)} URLs...")
    all_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(get_redirect_chain, url) for url in url_list]
        for future in as_completed(futures):
            all_results.extend(future.result())

    df_result = pd.DataFrame(all_results)

    st.success("✅ URL tracking complete!")

    # === VISUAL CHAIN UI ===
    grouped = df_result.groupby("Original URL")

    for url, group in grouped:
        with st.expander(f"🔗 {url}"):
            for _, row in group.iterrows():
                status = row["Status Code"]
                color = (
                    "green" if status == 200 else
                    "orange" if str(status).startswith("3") else
                    "red"
                )
                st.markdown(
                    f"""
                    <div style='padding: 8px 12px; margin: 6px 0; background-color: #f9f9f9;
                        border-left: 5px solid {color}; border-radius: 4px;'>
                        <b>Step {row["Step"]}</b>: <a href="{row["Redirected URL"]}" target="_blank">{row["Redirected URL"]}</a><br>
                        <b>Status:</b> {row["Status Code"]} - {row["Status Description"]}<br>
                        <b>Server:</b> {row["Server"]}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            st.markdown(
                f"""✅ <b>Final URL:</b> <a href="{group['Final URL'].iloc[-1]}" target="_blank">{group['Final URL'].iloc[-1]}</a><br>
                📶 <b>Final Status:</b> {group['Final Status'].iloc[-1]}""",
                unsafe_allow_html=True
            )

    # === Excel Export
    wb = Workbook()
    ws = wb.active
    ws.title = "Redirect Results"
    headers = list(df_result.columns)
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for _, row in df_result.iterrows():
        ws.append(row.tolist())

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 2

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    st.download_button(
        label="📥 Download Results as Excel",
        data=output,
        file_name="url_redirect_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif not uploaded_file and not text_input:
    st.warning("📌 Please upload an Excel or paste some URLs to begin.")

# === Footer ===
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)
