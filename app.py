import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from urllib.parse import urlparse, urljoin
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, Alignment, PatternFill

# === Configs ===
MAX_WORKERS = 20
TIMEOUT = 5

status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect',
    400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found',
    500: 'Internal Server Error'
}

# === Helpers ===
def is_valid_url(url):
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
    except:
        return False

def is_blocked_url(url):
    return "b2b-b" in url.lower()

def get_server_name(headers):
    akamai_markers = ["AkamaiGHost", "akamaitechnologies.com", "X-Akamai-Transformed"]
    headers_joined = " | ".join(f"{k}: {v}" for k, v in headers.items())
    for marker in akamai_markers:
        if marker.lower() in headers_joined.lower():
            return "Akamai"
    for key in ["Server", "X-Powered-By", "X-Cache", "Via", "CF-RAY", "X-Amz-Cf-Id", "X-CDN"]:
        if key in headers:
            return f"{key}: {headers[key]}"
    return "Unknown"

def check_redirection_chain(url):
    visited, chain = set(), []
    current_url = url
    try:
        while True:
            if current_url in visited:
                chain.append({'URL': current_url, 'Status': 'Loop detected', 'Status Code': 'Loop', 'Server': 'N/A'})
                break
            visited.add(current_url)
            resp = requests.get(current_url, timeout=TIMEOUT, allow_redirects=False)
            status = resp.status_code
            status_text = status_names.get(status, 'Unknown')
            server = get_server_name(resp.headers)
            chain.append({'URL': current_url, 'Status': status_text, 'Status Code': status, 'Server': server})
            if status in (301, 302, 303, 307, 308):
                next_url = resp.headers.get('Location')
                if not next_url:
                    break
                current_url = urljoin(current_url, next_url)
            else:
                break
    except:
        chain.append({'URL': current_url, 'Status': 'Error', 'Status Code': 'Error', 'Server': 'N/A'})
    return chain

def get_status_fill(code):
    try: code = int(code)
    except: return PatternFill(start_color="FFFFFF", fill_type=None)
    if 200 <= code < 300:
        return PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    elif 300 <= code < 400:
        return PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    elif 400 <= code < 600:
        return PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")
    return PatternFill(start_color="FFFFFF", fill_type=None)

def adjust_column_widths(ws):
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 4

def to_excel(df_summary, df_tracking):
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "URL Redirect Results"
    for r_idx, row in enumerate(dataframe_to_rows(df_summary, index=False, header=True), 1):
        ws1.append(row)
        for cell in ws1[r_idx]:
            if r_idx == 1:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.fill = get_status_fill(row[2])
    adjust_column_widths(ws1)
    ws1.auto_filter.ref = ws1.dimensions

    ws2 = wb.create_sheet("Redirection Tracking")
    grouped = df_tracking.groupby("Original URL")
    for url, group in grouped:
        ws2.append([f"Redirect Chain for: {url}"])
        for cell in ws2[ws2.max_row]:
            cell.font = Font(bold=True, color="0000FF")
        ws2.append([])
        for r_idx, row in enumerate(dataframe_to_rows(group, index=False, header=True)):
            ws2.append(row)
            if r_idx > 0:
                for cell in ws2[ws2.max_row]:
                    cell.fill = get_status_fill(row[3])
        ws2.append([])
    adjust_column_widths(ws2)
    ws2.auto_filter.ref = ws2.dimensions
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

# === UI ===
st.set_page_config("URL Status & Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Status & Redirect Checker")

# Session state setup
if "clear_triggered" not in st.session_state:
    st.session_state.clear_triggered = False

# Reset state after rerun
if st.session_state.clear_triggered:
    st.session_state.clear_triggered = False
    st.rerun()

st.markdown("Upload an Excel file **OR** paste URLs manually (one per line).")

# Clear button
if st.button("🧹 Clear All"):
    st.session_state["text_input"] = ""
    st.session_state.clear_triggered = True
    st.rerun()

# Inputs
uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type="xlsx")
text_input = st.text_area("🔽 Or paste URLs manually:", height=150, key="text_input")

# Gather input
urls = []
if uploaded_file and not text_input.strip():
    df = pd.read_excel(uploaded_file)
    if 'Original URL' not in df.columns:
        st.error("Excel must contain 'Original URL' column.")
        st.stop()
    urls = df['Original URL'].dropna().astype(str).tolist()
elif text_input.strip() and not uploaded_file:
    urls = [line.strip() for line in text_input.strip().splitlines()]
else:
    st.info("📌 Please provide either an Excel file OR manual URLs (not both).")
    st.stop()

# Clean + validate
valid_urls = []
skipped = []
for url in urls:
    if is_blocked_url(url):
        skipped.append(url)
    elif is_valid_url(url):
        valid_urls.append(url)
    else:
        skipped.append(url)

if not valid_urls:
    st.warning("No valid URLs to process.")
    st.stop()

if skipped:
    st.warning(f"⏩ Skipped invalid or blocked URLs:\n" + "\n".join(skipped))

st.info(f"🔍 Checking {len(valid_urls)} valid URLs...")

# Process URLs
results = {}
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(check_redirection_chain, url): url for url in valid_urls}
    for future in as_completed(futures):
        url = futures[future]
        try:
            results[url] = future.result()
        except:
            results[url] = [{'URL': url, 'Status': 'Error', 'Status Code': 'Error', 'Server': 'N/A'}]

# Prepare data
summary_rows, all_rows = [], []
for orig_url, chain in results.items():
    final_step = chain[-1]
    summary_rows.append({
        "Original URL": orig_url,
        "Final URL": final_step["URL"],
        "Status Code": final_step["Status Code"],
        "Server": final_step["Server"]
    })
    for i, step in enumerate(chain):
        all_rows.append({
            "Original URL": orig_url,
            "Redirect Step": i + 1,
            "Redirected URL": step['URL'],
            "Status Code": step['Status Code'],
            "Status Description": step['Status'],
            "Server": step['Server']
        })

df_summary = pd.DataFrame(summary_rows)
df_results = pd.DataFrame(all_rows)

st.success("✅ Completed URL checks.")

# Filter UI
search = st.text_input("🔎 Search URLs or servers:")
if search:
    df_filtered = df_results[df_results.apply(lambda x: search.lower() in str(x).lower(), axis=1)]
else:
    df_filtered = df_results

st.dataframe(df_filtered, use_container_width=True)

# Download Excel
excel_data = to_excel(df_summary, df_results)
st.download_button(
    label="📥 Download Results as Excel",
    data=excel_data,
    file_name="url_status_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# Preview redirect chains
st.markdown("### 🔗 Redirect Chain Preview")
for orig_url, chain in results.items():
    with st.expander(orig_url):
        for step in chain:
            st.markdown(f"`{step['Status Code']}` → **{step['Status']}** → `{step['URL']}` (Server: {step['Server']})")

# Footer
st.markdown("---\n<div style='text-align:center'>© 2025 Meet Chauhan. All rights reserved.</div>", unsafe_allow_html=True)
