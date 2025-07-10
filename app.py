import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

# === Configuration ===
MAX_WORKERS = 20
TIMEOUT = 5

# === HTTP Status Descriptions ===
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

# === Streamlit UI ===
st.set_page_config(page_title="URL Status & Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Status & Redirect Checker")

st.markdown("""
Upload an Excel file **or paste a list of URLs** (one per line).  
The app will check HTTP status codes and redirections.

---

🔒 **Privacy Notice**  
Uploaded or pasted data is never stored or shared. All processing happens in-memory and is deleted after your session ends.
""")

# === Upload Excel ===
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

# === Sample file download ===
with st.expander("📄 Download sample Excel format"):
    sample_df = pd.DataFrame({
        "Original URL": [
            "https://example.com",
            "https://abc.com"
        ]
    })
    sample_buffer = BytesIO()
    sample_df.to_excel(sample_buffer, index=False)
    sample_buffer.seek(0)

    st.download_button(
        label="⬇️ Download Sample Excel",
        data=sample_buffer,
        file_name="sample_urls.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.markdown("📌 Format: One column named **Original URL**, one URL per row.")

# === Text input option ===
st.markdown("#### Or paste URLs manually below:")
col1, col2 = st.columns([3, 1])
with col1:
    text_input = st.text_area("🔽 Paste URLs (one per line):")

# === URL checking logic ===
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

    return row_idx, url, original_status_text, redirect_url, redirect_status_text

# === Get URLs from Excel or Text ===
url_list = []

if uploaded_file is not None:
    try:
        df_input = pd.read_excel(uploaded_file)
        df_input.columns = ['Original URL'] + list(df_input.columns[1:])
        url_list = df_input['Original URL'].dropna().tolist()
    except Exception as e:
        st.error(f"❌ Error reading Excel file: {e}")

elif text_input.strip():
    url_list = [line.strip() for line in text_input.strip().splitlines() if line.strip()]

# === Process URLs ===
if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs. Please wait...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_url, idx, url) for idx, url in enumerate(url_list)]

        for future in as_completed(futures):
            results.append(future.result())

    results.sort()

    df = pd.DataFrame(results, columns=[
        'Index', 'Original URL', 'Original Status', 'Redirect URL', 'Redirect Status'
    ]).drop(columns=['Index'])

    st.success("✅ URL checking complete!")
    st.dataframe(df, use_container_width=True)

    # === Format Excel ===
    wb = Workbook()
    ws = wb.active
    ws.title = "URL Results"

    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = Font(bold=True)

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = max_length + 2

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    st.download_button(
        label="📥 Download Results as Excel",
        data=buffer,
        file_name="url_status_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif not uploaded_file and not text_input:
    st.warning("📌 Please either upload an Excel file or paste URLs to begin.")

# === Footer ===
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)
