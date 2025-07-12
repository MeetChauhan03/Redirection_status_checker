import streamlit as st
import pandas as pd
import requests
from urllib.parse import urljoin
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

# --- CONFIG ---
TIMEOUT = 6
MAX_WORKERS = 15
BLOCKED_KEYWORD = "avnhc"

status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect',
    400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
    404: 'Not Found', 500: 'Internal Server Error'
}

# --- HELPER FUNCTION: Check full redirection chain ---
def trace_redirection_chain(url):
    visited = set()
    chain = []
    current_url = url

    try:
        while current_url and current_url not in visited:
            visited.add(current_url)
            resp = requests.get(current_url, timeout=TIMEOUT, allow_redirects=False)
            status = resp.status_code
            location = resp.headers.get("Location")
            server = resp.headers.get("Server", "Unknown")
            desc = status_names.get(status, "Unknown")

            chain.append({
                "URL": current_url,
                "Status Code": status,
                "Status Description": desc,
                "Redirected To": location or "",
                "Server": server
            })

            if status in (301, 302, 303, 307, 308) and location:
                current_url = urljoin(current_url, location)
            else:
                break

    except Exception as e:
        chain.append({
            "URL": current_url,
            "Status Code": "Error",
            "Status Description": "Error",
            "Redirected To": "",
            "Server": "N/A"
        })

    return chain

# --- DISPLAY FORMATTER ---
def render_chain_ui(chain):
    output = "🔗 **Redirect Chain:**\n"
    indent = "  "
    for step in chain:
        code = step['Status Code']
        url = step['URL']
        server = step['Server']
        desc = step['Status Description']

        icon = "🟢" if isinstance(code, int) and 200 <= code < 300 else (
               "🟡" if isinstance(code, int) and 300 <= code < 400 else "🔴")

        output += f"{indent}└─ {icon} {code} → `{url}`  [**{desc}**, Server: {server}]\n"
        indent += "    "

    return output

# --- STREAMLIT UI ---
st.set_page_config("URL Status Checker", layout="wide")
st.title("🔗 Bulk URL Redirection & Status Checker")

st.markdown("Upload an Excel file **or paste URLs** (one per line). Redirect history and server info will be shown.")

uploaded_file = st.file_uploader("📁 Upload Excel File", type="xlsx")
st.markdown("#### Or paste URLs below:")
text_input = st.text_area("🔽 One URL per line", height=150)

# --- GET URLS ---
urls = []
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        if 'Original URL' not in df.columns:
            st.error("Excel must have a column 'Original URL'")
            st.stop()
        urls = df['Original URL'].dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

if text_input:
    urls += [line.strip() for line in text_input.splitlines() if line.strip()]

# --- REMOVE DUPLICATES / BLOCKED ---
clean_urls = []
blocked = []
for u in urls:
    if BLOCKED_KEYWORD in u.lower():
        blocked.append(u)
    elif u not in clean_urls:
        clean_urls.append(u)

if blocked:
    st.warning(f"Blocked URLs (contain '{BLOCKED_KEYWORD}') skipped:\n" + "\n".join(blocked))

if not clean_urls:
    st.info("Please upload or enter URLs to begin.")
    st.stop()

# --- PROCESS ---
st.info(f"🔎 Checking {len(clean_urls)} URLs...")
all_results = {}

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(trace_redirection_chain, url): url for url in clean_urls}
    for f in as_completed(futures):
        url = futures[f]
        try:
            all_results[url] = f.result()
        except:
            all_results[url] = []

st.success("✅ Redirect tracking completed!")

# --- DISPLAY CHAINS ---
st.markdown("### 🔗 Redirection Chains")
for original_url, chain in all_results.items():
    with st.expander(original_url, expanded=False):
        st.markdown(render_chain_ui(chain))

# --- FORMAT TO EXCEL ---
rows = []
for orig, chain in all_results.items():
    for i, step in enumerate(chain):
        rows.append({
            "Original URL": orig,
            "Step": i + 1,
            "Redirected URL": step["URL"],
            "Status Code": step["Status Code"],
            "Status Description": step["Status Description"],
            "Server": step["Server"]
        })

df_out = pd.DataFrame(rows)

# --- SEARCH FILTER ---
st.markdown("### 🔎 Filter results:")
query = st.text_input("Filter by URL or Server:")
if query:
    df_view = df_out[
        df_out["Original URL"].str.contains(query, case=False) |
        df_out["Redirected URL"].str.contains(query, case=False) |
        df_out["Server"].str.contains(query, case=False)
    ]
else:
    df_view = df_out

st.dataframe(df_view.style.set_properties(**{'text-align': 'center'}), use_container_width=True)

# --- EXCEL DOWNLOAD ---
def format_excel(df):
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
        for c_idx, val in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            if r_idx == 1:
                cell.font = Font(bold=True)
    for col in ws.columns:
        length = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = length + 5
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

buffer = format_excel(df_out)
st.download_button(
    label="📥 Download Excel",
    data=buffer,
    file_name="url_redirect_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- FOOTER ---
st.markdown("---\n<div style='text-align: center;'>© 2025 Meet Chauhan. All rights reserved.</div>", unsafe_allow_html=True)
