import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

# ==== Constants ====
TIMEOUT = 5
MAX_WORKERS = 15
BLOCKED_TERM = "avnhc"

STATUS_NAMES = {
    200: "OK",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    500: "Internal Server Error"
}

# ==== Helper Functions ====

def get_server_name(headers):
    akamai_indicators = [
        "AkamaiGHost", "akamaitechnologies.com", "X-Akamai-Transformed"
    ]
    combined = " | ".join(f"{k}: {v}" for k, v in headers.items())
    for marker in akamai_indicators:
        if marker.lower() in combined.lower():
            return "Akamai"

    fallback_headers = ["Server", "X-Powered-By", "X-Cache", "Via"]
    for key in fallback_headers:
        if key in headers:
            return f"{headers[key]}"
    return "Unknown"

def follow_redirects(url):
    visited = set()
    chain = []
    current_url = url
    try:
        while current_url and current_url not in visited:
            visited.add(current_url)
            response = requests.get(current_url, timeout=TIMEOUT, allow_redirects=False)
            status = response.status_code
            server = get_server_name(response.headers)
            chain.append({
                "Status Code": status,
                "URL": current_url,
                "Status": STATUS_NAMES.get(status, "Unknown"),
                "Server": server
            })
            if status in (301, 302, 303, 307, 308):
                current_url = response.headers.get("Location")
            else:
                break
        return chain
    except Exception:
        return [{"Status Code": "Error", "URL": current_url, "Status": "Error", "Server": "Unknown"}]

def check_url_chain(url):
    if BLOCKED_TERM in url:
        return url, [], "Blocked", "Blocked", "Blocked"
    chain = follow_redirects(url)
    final = chain[-1] if chain else {"URL": url, "Status Code": "Error", "Status": "Error", "Server": "Unknown"}
    return url, chain, final["URL"], final["Status Code"], final["Server"]

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
        indent = "&nbsp;" * (4 * i)
        lines.append(f"{indent}└─&gt; {icon} {status_code} → <code>{url}</code> [<strong>{status_text}</strong>, Server: {server}]<br>")
    return "<div style='white-space: pre-wrap; font-family: monospace; font-size: 0.9em'>" + "".join(lines) + "</div>"

# ==== UI ====

st.set_page_config("🔗 URL Redirect Checker", layout="wide")
st.title("🔗 URL Status & Redirection Tracker")

st.markdown("""
Upload an Excel file or paste URLs manually to track redirect chains, final status, and servers.

- ✅ Tracks full redirection chains  
- ✅ Highlights final destination  
- ✅ Shows redirect server (e.g., Akamai)  
- ✅ Blocks URLs with `"avnhc"`  
- ✅ Outputs downloadable Excel with two sheets  
""")

uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type=["xlsx"])
text_input = st.text_area("📌 Paste URLs here (one per line):", height=150)

url_list = []
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    url_list = df.iloc[:, 0].dropna().tolist()
elif text_input.strip():
    url_list = [line.strip() for line in text_input.splitlines() if line.strip()]

if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs. Please wait...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_url_chain, url) for url in url_list]
        for future in as_completed(futures):
            results.append(future.result())

    df_summary = pd.DataFrame([
        {
            "Original URL": original,
            "Final URL": final_url,
            "Status Code": status_code,
            "Server": server
        } for original, _, final_url, status_code, server in results
    ]).drop_duplicates()

    df_tracking = []
    for original, chain, _, _, _ in results:
        for step in chain:
            df_tracking.append({
                "Original URL": original,
                "Step URL": step["URL"],
                "Status Code": step["Status Code"],
                "Status": step["Status"],
                "Server": step["Server"]
            })

    df_tracking = pd.DataFrame(df_tracking)

    # === Search Filter ===
    search = st.text_input("🔎 Filter URLs or Servers:")
    if search:
        df_summary = df_summary[
            df_summary["Original URL"].str.contains(search, case=False, na=False) |
            df_summary["Final URL"].str.contains(search, case=False, na=False) |
            df_summary["Server"].str.contains(search, case=False, na=False)
        ]

    st.dataframe(df_summary, use_container_width=True)

    # === Download Excel ===
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Final URL Summary"
    for r in dataframe_to_rows(df_summary, index=False, header=True):
        ws1.append(r)
    for cell in ws1[1]:
        cell.font = Font(bold=True)

    ws2 = wb.create_sheet("Full Redirect Tracking")
    for r in dataframe_to_rows(df_tracking, index=False, header=True):
        ws2.append(r)
    for cell in ws2[1]:
        cell.font = Font(bold=True)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    st.download_button("📥 Download Results (2 Sheets)", buffer, "redirect_report.xlsx")

    # === Show redirect chains visually ===
    st.markdown("---")
    st.subheader("🔗 Redirect Chains")
    for original, chain, _, _, _ in results:
        st.markdown(f"**{original}**", unsafe_allow_html=True)
        st.markdown(render_redirect_chain(chain), unsafe_allow_html=True)

else:
    st.warning("📌 Please upload an Excel file or paste URLs above to begin.")

st.markdown("<hr><center style='font-size: 0.9em; color: gray;'>© 2025 Meet Chauhan. All rights reserved.</center>", unsafe_allow_html=True)
