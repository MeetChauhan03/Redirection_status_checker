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

# === HTTP Status Descriptions ===
status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect', 400: 'Bad Request',
    401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 500: 'Internal Server Error'
}

# === Page Setup ===
st.set_page_config(page_title="URL Redirect Tracker", layout="wide")
st.title("🔁 Full URL Redirect Tracker + Server Info")

st.markdown("""
Upload an Excel file or paste URLs. The app will check all redirection steps, final URL, server headers, and HTTP statuses.

🔒 **Privacy Notice**  
All data is processed in memory and not saved or shared.
""")

# === File Upload ===
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

# === Sample File Download ===
with st.expander("📄 Download sample Excel format"):
    sample_df = pd.DataFrame({"Original URL": ["https://example.com"]})
    sample_buf = BytesIO()
    sample_df.to_excel(sample_buf, index=False)
    sample_buf.seek(0)
    st.download_button("⬇️ Download Sample Excel", sample_buf, file_name="sample_urls.xlsx")
    st.caption("Make sure the first column is named: **Original URL**.")

# === Text Paste Option ===
st.markdown("#### Or paste URLs (one per line):")
text_input = st.text_area("🔽 Paste URLs:", height=150)

# === Redirection Logic ===
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

# === Load URLs ===
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

# === Process URLs ===
if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs...")

    all_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(get_redirect_chain, url) for url in url_list]
        for future in as_completed(futures):
            all_results.extend(future.result())

    df_result = pd.DataFrame(all_results)

    st.success("✅ URL tracking complete!")

    # === Search Filter ===
    search_term = st.text_input("🔍 Filter results by Original URL or Final URL")
    if search_term:
        df_filtered = df_result[df_result.apply(lambda row:
            search_term.lower() in str(row['Original URL']).lower() or
            search_term.lower() in str(row['Final URL']).lower(), axis=1)]
    else:
        df_filtered = df_result.copy()

    # === Helper function for status color ===
    def color_for_status(code):
        if code == 200:
            return 'green'
        elif str(code).startswith('3'):
            return 'orange'
        elif str(code).startswith('4') or str(code).startswith('5'):
            return 'red'
        else:
            return 'gray'

    # === Display Redirect Chains as horizontal arrows ===
    if not df_filtered.empty:
        st.markdown("### 🔗 Redirect Chains")
        grouped = df_filtered.groupby("Original URL")
        for url, group in grouped:
            steps_html = ""
            for idx, row in group.iterrows():
                color = color_for_status(row["Status Code"])
                step_url = row["Redirected URL"]
                status = row["Status Code"]
                desc = row["Status Description"]
                server = row["Server"]
                steps_html += f"""
                <div style='display:inline-block; vertical-align:top; padding:10px; margin-right:5px; 
                            border-radius:8px; background-color:#f0f0f0; border: 3px solid {color}; min-width:250px;'>
                    <a href="{step_url}" target="_blank" style='color:#000; font-weight:bold; word-break: break-all;'>{step_url}</a><br>
                    <span style='color:{color}; font-weight:600;'>Status: {status} - {desc}</span><br>
                    <small>Server: {server}</small>
                </div>
                """
                if idx < group.index[-1]:
                    # Add arrow except after last step
                    steps_html += "<span style='font-size:28px; vertical-align: middle; color:#555; margin-right:5px;'>&rarr;</span>"

            st.markdown(f"""
            <div style='overflow-x:auto; white-space: nowrap; margin-bottom: 30px; padding: 5px; border-bottom: 1px solid #ddd;'>
                <b>Original URL:</b> {url}<br><br>
                {steps_html}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No results to display")

    # === Excel Export ===
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

    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    st.download_button(
        label="📥 Download Results as Excel",
        data=excel_buffer,
        file_name="url_redirect_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("📌 Upload an Excel file or paste URLs to begin.")

# === Footer ===
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)
