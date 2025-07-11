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
st.set_page_config(page_title="URL Redirect Tracker", layout="wide")
st.title("🔁 Full URL Redirect Tracker + Server Info")

st.markdown("""
Upload an Excel file **or paste a list of URLs**.  
This tool checks for full redirection chains, status codes, final URL, and server info.

---

🔒 **Privacy:** Your data is never stored. Everything runs in-browser.
""")

# === Upload Excel ===
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

# === Download Sample File ===
with st.expander("📄 Download sample Excel format"):
    sample_df = pd.DataFrame({"Original URL": ["https://example.com"]})
    sample_buffer = BytesIO()
    sample_df.to_excel(sample_buffer, index=False)
    sample_buffer.seek(0)
    st.download_button("⬇️ Download Sample Excel", sample_buffer, file_name="sample_urls.xlsx")
    st.caption("Must contain a column named 'Original URL'")

# === Paste Text Input ===
st.markdown("#### Or paste URLs below (one per line):")
text_input = st.text_area("🔽 Paste URLs here:", height=150)

# === Get URLs ===
url_list = []

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        df.columns = ['Original URL'] + list(df.columns[1:])
        url_list = df['Original URL'].dropna().tolist()
    except Exception as e:
        st.error(f"❌ Error reading Excel: {e}")
elif text_input.strip():
    url_list = [line.strip() for line in text_input.strip().splitlines() if line.strip()]

# === Redirect Tracker Function ===
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

        if not steps:  # No redirect
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

# === Process URLs ===
if url_list:
    st.info(f"🔍 Processing {len(url_list)} URLs. Please wait...")
    all_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(get_redirect_chain, url) for url in url_list]
        for future in as_completed(futures):
            all_results.extend(future.result())

    df_result = pd.DataFrame(all_results)

    st.success("✅ URL checking complete!")
    st.dataframe(df_result, use_container_width=True)

    # === Save to Excel ===
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
    st.warning("📌 Please upload a file or paste URLs to begin.")

# === Footer ===
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)
