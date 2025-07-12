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

# === Utility: Get server name from headers ===
def get_server_name(headers):
    akamai_indicators = ["AkamaiGHost","akamaitechnologies.com","X-Akamai-Transformed"]

    # Combine headers into one searchable string
    combined_headers = " | ".join(f"{k}: {v}" for k, v in headers.items())

    for akamai_marker in akamai_indicators:
        if akamai_marker.lower() in combined_headers.lower():
            return "Akamai"

    # Fallback to general server header inspection
    server_headers_priority = ["Server","X-Powered-By","X-Cache","Via","CF-RAY","X-Amz-Cf-Id","X-CDN"]
    
    for key in server_headers_priority:
        if key in headers:
            return f"{key}: {headers[key]}"
    
    return "Unknown"


# === URL blocking check ===
def is_blocked_url(url):
    return "b2b-b" in url.lower()

# === Check one URL redirection chain ===
def check_redirection_chain(url):
    visited = set()
    chain = []
    current_url = url
    try:
        while True:
            if current_url in visited:
                # loop detected
                chain.append({
                    'URL': current_url,
                    'Status': 'Loop detected',
                    'Status Code': 'Loop',
                    'Server': 'N/A'
                })
                break

            visited.add(current_url)
            resp = requests.get(current_url, timeout=TIMEOUT, allow_redirects=False)
            status = resp.status_code
            status_text = status_names.get(status, 'Unknown')
            server = get_server_name(resp.headers)
            chain.append({
                'URL': current_url,
                'Status': status_text,
                'Status Code': status,
                'Server': server
            })

            if status in (301, 302, 303, 307, 308):
                redirect_url = resp.headers.get('Location')
                if not redirect_url:
                    break
                # Absolute URL handling
                if redirect_url.startswith('/'):
                    from urllib.parse import urljoin
                    redirect_url = urljoin(current_url, redirect_url)
                current_url = redirect_url
            else:
                break
    except Exception as e:
        chain.append({
            'URL': current_url,
            'Status': 'Error',
            'Status Code': 'Error',
            'Server': 'N/A'
        })
    return chain

# === Render redirect chain in markdown for UI ===
def render_redirect_chain(chain):
    if not chain:
        return "No redirection data."

    display = "🔗 **Redirect Chain:**  \n"
    indent = "  "*4
    for i, step in enumerate(chain):
        status_code = step['Status Code']
        url = step['URL']
        server = step['Server']
        status_text = step['Status']

        # Colored icon based on status code
        icon = "⚫"
        if isinstance(status_code, int):
            if 200 <= status_code < 300:
                icon = "🟢"
            elif 300 <= status_code < 400:
                icon = "🟡"
            elif 400 <= status_code < 600:
                icon = "🔴"
        elif status_code == 'Loop':
            icon = "🔄"
        elif status_code == 'Error':
            icon = "❌"

        indent = " " * (4 * i)
        display += f"{indent} └─> {icon} {status_code} → `{url}`  [**{status_text}**, Server: {server}]\n"+ "\n&nbsp;"
    return display
# === Streamlit UI ===
st.set_page_config(page_title="URL Status & Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Status & Redirect Checker")

st.markdown("""
Upload an Excel file **or paste URLs** (one per line).  
The app will check HTTP status codes and follow redirects, showing full redirect chains.

---

🔒 **Privacy Notice**  
Uploaded or pasted data is never stored or shared. All processing happens in-memory only.

---
🟢 200 → All good! | 🟡 301 → This page has permanently moved somewhere else. | 🔴 404 → Oops! The page was not found. | 🔄 Loop → The URL keeps redirecting back and forth. | ❌ Error → Couldn’t check this URL, please try again later.
""")

# --- Upload Excel ---
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

# --- Sample file download ---
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

# --- Text input option ---
st.markdown("#### Or paste URLs manually below:")
text_input = st.text_area("🔽 Paste URLs (one per line):", height=150)

# --- Collect URLs from input ---
urls = []
errors_blocked = []

if uploaded_file is not None:
    try:
        df_in = pd.read_excel(uploaded_file)
        df_in.columns = [str(c) for c in df_in.columns]
        if 'Original URL' not in df_in.columns:
            st.error("❌ Excel must have column named 'Original URL'.")
            st.stop()
        urls = df_in['Original URL'].dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"❌ Error reading Excel file: {e}")

if text_input.strip():
    urls += [line.strip() for line in text_input.strip().splitlines() if line.strip()]

# Remove duplicates and blocked URLs
urls_unique = []
for url in urls:
    if is_blocked_url(url):
        errors_blocked.append(url)
    elif url not in urls_unique:
        urls_unique.append(url)

if errors_blocked:
    st.warning(f"⚠️ The following URLs contain the forbidden string 'Preview link' and will be skipped:\n" + "\n".join(errors_blocked))

if not urls_unique:
    st.warning("📌 Please upload or paste valid URLs to proceed.")
    st.stop()

# --- Check URLs with concurrency ---
st.info(f"🔍 Checking {len(urls_unique)} unique URLs. Please wait...")

results = {}
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(check_url_chain, url) for url in urls_unique]
    for future in futures:
        results.append(future.result())

# === Generate Summary Sheet ===
df_summary = pd.DataFrame([
    {"Original URL": orig, "Final URL": final_url, "Status Code": status_code, "Server": server}
    for orig, _, final_url, status_code, server in results
]).drop_duplicates()

st.success("✅ URL checking complete!")

# --- Prepare DataFrame for display and export ---
all_rows = []
for orig_url, chain in results.items():
    for idx, step in enumerate(chain):
        all_rows.append({
            "Original URL": orig_url,
            "Redirect Step": idx + 1,
            "Redirected URL": step['URL'],
            "Status Code": step['Status Code'],
            "Status Description": step['Status'],
            "Server": step['Server']
        })

df_results = pd.DataFrame(all_rows)

# --- Filter/Search UI ---
st.markdown("### 🔎 Filter / Search URLs")
search_term = st.text_input("Search in Original or Redirected URLs or Server names:")

if search_term:
    df_filtered = df_results[
        df_results["Original URL"].str.contains(search_term, case=False, na=False) |
        df_results["Redirected URL"].str.contains(search_term, case=False, na=False) |
        df_results["Server"].str.contains(search_term, case=False, na=False) |
        df_results["Status Code"].astype(str).str.contains(search_term, case=False, na=False)    ]
else:
    df_filtered = df_results

# --- Show data in table ---
st.markdown("### 📋 URL Status & Redirect Results")

# Center align table via st.markdown and CSS
st.markdown(
    """
    <style>
    .dataframe tbody tr th, .dataframe tbody tr td {
        text-align: center !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.dataframe(df_filtered, use_container_width=True)

# --- Download Excel with formatting ---
def to_excel(df):
    wb = Workbook()
    ws = wb.active
    ws.title = "URL Redirect Results"

    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
       ws1.append(row)
    for cell in ws1[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for col in ws1.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws1.column_dimensions[col[0].column_letter].width = max_len + 5
    
    ws2 = wb.create_sheet("Redirection Tracking")
    for row in dataframe_to_rows(df_tracking, index=False, header=True):
        ws2.append(row)
    for cell in ws2[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for col in ws2.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws2.column_dimensions[col[0].column_letter].width = max_len + 5

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

excel_data = to_excel(df_filtered)

st.download_button(
    label="📥 Download Results as Excel",
    data=excel_data,
    file_name="url_status_with_redirect_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- Show redirect chains as collapsible markdown ---
st.markdown("### 🔗 Redirect Chains Preview (expand below)")

for orig_url, chain in results.items():
    with st.expander(orig_url, expanded=False):
        st.markdown(render_redirect_chain(chain))

# --- Footer ---
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)
