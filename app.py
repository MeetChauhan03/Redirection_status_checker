import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, Alignment

# Config
MAX_WORKERS = 20
TIMEOUT = 5
MAX_REDIRECTS = 10

# HTTP Status descriptions shortcut
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

# Helper to get server name from response headers
def get_server_name(headers):
    return headers.get("Server") or headers.get("X-Powered-By") or headers.get("Via") or "Unknown"

# Get redirect chain for a URL
def get_redirect_chain(url, timeout=TIMEOUT, max_redirects=MAX_REDIRECTS):
    chain = []
    visited_urls = set()
    current_url = url

    for _ in range(max_redirects):
        if current_url in visited_urls:
            # Loop detected
            chain.append({
                "Status Code": "Loop",
                "URL": current_url,
                "Server": "Unknown",
                "Status": "Redirect Loop Detected"
            })
            break
        visited_urls.add(current_url)

        try:
            resp = requests.get(current_url, timeout=timeout, allow_redirects=False)
            status_code = resp.status_code
            server = get_server_name(resp.headers)
            status_text = status_names.get(status_code, 'Unknown')

            chain.append({
                "Status Code": status_code,
                "URL": current_url,
                "Server": server,
                "Status": status_text
            })

            if status_code in (301, 302, 303, 307, 308):
                redirect_url = resp.headers.get('Location')
                if not redirect_url:
                    break
                # Handle relative redirect URLs
                if redirect_url.startswith('/'):
                    from urllib.parse import urljoin
                    redirect_url = urljoin(current_url, redirect_url)
                current_url = redirect_url
            else:
                break

        except requests.RequestException:
            chain.append({
                "Status Code": "Error",
                "URL": current_url,
                "Server": "Unknown",
                "Status": "Request Failed"
            })
            break

    return chain

# Render redirect chain nicely with indentation and icons
def render_redirect_chain(chain):
    if not chain:
        return "No redirection data."

    lines = ["🔗 <strong>Redirect Chain:</strong><br>"]

    for i, step in enumerate(chain):
        status_code = step['Status Code']
        url = step['URL']
        server = step['Server']
        status_text = step['Status']

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

        indent = "&nbsp;" * (4 * i)  # indent using HTML spaces
        lines.append(f"{indent}└─&gt; {icon} {status_code} → <code>{url}</code> [<strong>{status_text}</strong>, Server: {server}]<br>")

    html = "<div style='white-space: pre-wrap; font-family: monospace; font-size: 0.9em;'>" + "".join(lines) + "</div>"
    return html

# Check if URL contains forbidden string
def is_url_allowed(url):
    return "avnhc" not in url.lower()

# Function to process each URL, get chain and flatten for table/export
def process_url(idx, url):
    if not is_url_allowed(url):
        # Block URLs containing "avnhc"
        return {
            "Original URL": url,
            "Redirect Chain": [],
            "Final URL": "",
            "Final Status": "Blocked due to forbidden keyword",
            "Final Server": ""
        }
    chain = get_redirect_chain(url)
    final_step = chain[-1] if chain else {}
    return {
        "Original URL": url,
        "Redirect Chain": chain,
        "Final URL": final_step.get("URL", ""),
        "Final Status": f"{final_step.get('Status Code', '')} - {final_step.get('Status', '')}",
        "Final Server": final_step.get("Server", "")
    }

# Streamlit app starts here
st.set_page_config(page_title="Bulk URL Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Redirect & Status Checker")

st.markdown("""
Upload an Excel file with URLs or paste URLs (one per line).  
Redirect chains will be traced fully, showing status and server info.

**Note:** URLs containing "avnhc" are blocked for checking.
""")

# Upload Excel
uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type="xlsx")

# Sample file download
with st.expander("Sample Excel Format"):
    sample_df = pd.DataFrame({"Original URL": ["https://example.com", "https://www.bmw.de"]})
    buf = BytesIO()
    sample_df.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("Download Sample Excel", data=buf, file_name="sample_urls.xlsx")

# Text input
text_input = st.text_area("Or paste URLs here (one per line):", height=150)

# Collect URLs from input
urls = []
if uploaded_file:
    try:
        df_in = pd.read_excel(uploaded_file)
        if 'Original URL' not in df_in.columns:
            st.error("Excel must have a column named 'Original URL'.")
        else:
            urls = df_in['Original URL'].dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")

if text_input.strip():
    text_urls = [line.strip() for line in text_input.strip().splitlines() if line.strip()]
    urls.extend(text_urls)

# Remove duplicates and keep order
seen = set()
urls = [x for x in urls if not (x in seen or seen.add(x))]

if not urls:
    st.warning("Please upload an Excel or paste URLs to check.")
    st.stop()

st.info(f"Checking {len(urls)} URLs, please wait...")

results = []
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(process_url, i, url) for i, url in enumerate(urls)]
    for future in as_completed(futures):
        results.append(future.result())

# Sort results by original URL to keep consistent order
results.sort(key=lambda x: urls.index(x['Original URL']))

# Prepare data for table and Excel
table_rows = []
for res in results:
    chain_display = render_redirect_chain(res["Redirect Chain"])
    table_rows.append({
        "Original URL": res["Original URL"],
        "Final URL": res["Final URL"],
        "Final Status": res["Final Status"],
        "Final Server": res["Final Server"],
        "Redirect Chain": chain_display
    })

df_results = pd.DataFrame(table_rows)

# Search/filter input
search_term = st.text_input("🔍 Filter results (search URL, status, server):").strip()

if search_term:
    mask = (
        df_results["Original URL"].str.contains(search_term, case=False, na=False) |
        df_results["Final URL"].str.contains(search_term, case=False, na=False) |
        df_results["Final Status"].str.contains(search_term, case=False, na=False) |
        df_results["Final Server"].str.contains(search_term, case=False, na=False)
    )
    df_results = df_results[mask]

# Show table with redirect chain rendered as HTML
def make_clickable(html):
    return html

st.write(f"### Results ({len(df_results)})")

# Center table columns by applying style
def highlight_and_center(s):
    return ['text-align: center;' for _ in s]

styled_df = df_results.style.apply(highlight_and_center).format({
    "Redirect Chain": make_clickable
}).hide(axis="index")

st.write(styled_df.to_html(escape=False), unsafe_allow_html=True)

# Excel export: flatten redirect chain into text for export
def flatten_chain_for_excel(chain):
    if not chain:
        return ""
    lines = []
    for i, step in enumerate(chain):
        indent = " " * (4 * i)
        lines.append(f"{indent}→ {step['Status Code']} {step['Status']} | {step['URL']} | Server: {step['Server']}")
    return "\n".join(lines)

df_export = pd.DataFrame([
    {
        "Original URL": r["Original URL"],
        "Final URL": r["Final URL"],
        "Final Status": r["Final Status"],
        "Final Server": r["Final Server"],
        "Redirect Chain": flatten_chain_for_excel(r["Redirect Chain"])
    }
    for r in results
])

# Create Excel file
wb = Workbook()
ws = wb.active
ws.title = "URL Redirect Results"

for r_idx, row in enumerate(dataframe_to_rows(df_export, index=False, header=True), 1):
    for c_idx, value in enumerate(row, 1):
        ws.cell(row=r_idx, column=c_idx, value=value)

# Styling header
header_font = Font(bold=True)
for cell in ws[1]:
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center")

# Align all cells center horizontally except Redirect Chain (left align)
for row in ws.iter_rows(min_row=2):
    for cell in row[:-1]:
        cell.alignment = Alignment(horizontal="center")
    # Redirect Chain column left aligned
    row[-1].alignment = Alignment(horizontal="left")

# Save to BytesIO for download
excel_io = BytesIO()
wb.save(excel_io)
excel_io.seek(0)

st.download_button(
    label="📥 Download Results as Excel",
    data=excel_io,
    file_name="url_redirect_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
# === Footer ===
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)