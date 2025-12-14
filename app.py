import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, Alignment, PatternFill
from urllib.parse import urljoin
import urllib3

# ================= CONFIG =================
st.set_page_config(
    page_title="Redirect Auditor Pro",
    layout="wide",
    page_icon="🔗"
)

MAX_WORKERS = 15
DEFAULT_TIMEOUT = 10
MAX_REDIRECTS = 10

# ================= HEADERS =================
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ================= STATUS MAP =================
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
    500: "Server Error"
}

# ================= HELPERS =================
def get_server(headers: dict) -> str:
    joined = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    if "akamai" in joined:
        return "Akamai"
    return headers.get("Server", "Unknown")

def normalize(url: str) -> str:
    return url.rstrip("/")

# ================= CORE LOGIC =================
def check_redirection_chain(url, verify_ssl, timeout):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    chain = []
    visited = set()
    current = normalize(url)

    for step in range(MAX_REDIRECTS):
        if current in visited:
            chain.append({
                "URL": current,
                "Status Code": "Loop",
                "Status": "Redirect Loop",
                "Server": "N/A"
            })
            break

        visited.add(current)

        try:
            # HEAD = origin truth
            head = requests.head(
                current,
                allow_redirects=False,
                timeout=timeout,
                headers=BROWSER_HEADERS,
                verify=verify_ssl
            )

            code = head.status_code
            status = STATUS_NAMES.get(code, "Unknown")
            server = get_server(head.headers)

            chain.append({
                "URL": current,
                "Status Code": code,
                "Status": status,
                "Server": server
            })

            if code in (301, 302, 303, 307, 308):
                location = head.headers.get("Location")
                if not location:
                    break
                current = normalize(urljoin(current, location))
            else:
                break

        except requests.RequestException:
            chain.append({
                "URL": current,
                "Status Code": "Error",
                "Status": "Connection Error",
                "Server": "N/A"
            })
            break

    return chain

# ================= EXCEL =================
def generate_excel(summary_df, detail_df):
    output = BytesIO()
    wb = Workbook()

    def style_header(ws):
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2F3E46")
            c.alignment = Alignment(horizontal="center")

    ws1 = wb.active
    ws1.title = "Summary"
    ws1.append(summary_df.columns.tolist())
    style_header(ws1)
    for r in dataframe_to_rows(summary_df, index=False, header=False):
        ws1.append(r)

    ws2 = wb.create_sheet("Redirect Chain")
    ws2.append(detail_df.columns.tolist())
    style_header(ws2)
    for r in dataframe_to_rows(detail_df, index=False, header=False):
        ws2.append(r)

    wb.save(output)
    output.seek(0)
    return output

# ================= SIDEBAR =================
with st.sidebar:
    st.markdown("## ⚙️ Controls")

    uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type="xlsx")
    pasted_urls = st.text_area("Paste URLs (one per line)", height=140)

    verify_ssl = st.toggle("Verify SSL", True)
    timeout = st.slider("Timeout (sec)", 3, 30, DEFAULT_TIMEOUT)

    run_btn = st.button("▶ Run Analysis", type="primary", use_container_width=True)
    clear_btn = st.button("🧹 Clear All Inputs", use_container_width=True)

if clear_btn:
    st.session_state.clear()
    st.rerun()

# ================= MAIN =================
st.title("🔗 Redirect Auditor Pro")

st.markdown("""
**What this tool does**
- Detects **true redirect status** (301 vs 302) for AEM/Akamai
- Shows **full redirect chains**
- Exports **client-ready Excel reports**
""")

# ================= INPUT PROCESS =================
urls = []

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    if "Original URL" not in df.columns:
        st.error("Excel must contain 'Original URL' column")
    else:
        urls.extend(df["Original URL"].dropna().astype(str).tolist())

if pasted_urls:
    urls.extend([u.strip() for u in pasted_urls.splitlines() if u.strip()])

urls = list(dict.fromkeys(urls))

# ================= EXECUTION =================
if run_btn and urls:
    results = []

    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        futures = {
            pool.submit(check_redirection_chain, u, verify_ssl, timeout): u
            for u in urls
        }

        for f in as_completed(futures):
            results.append((futures[f], f.result()))

    summary_rows = []
    detail_rows = []

    for orig, chain in results:
        final = chain[-1]
        summary_rows.append({
            "Original URL": orig,
            "Final URL": final["URL"],
            "Final Status Code": final["Status Code"],
            "Server": final["Server"],
            "Redirect Count": len(chain) - 1
        })

        for i, step in enumerate(chain, 1):
            detail_rows.append({
                "Original URL": orig,
                "Step": i,
                "Hop URL": step["URL"],
                "Status Code": step["Status Code"],
                "Status": step["Status"],
                "Server": step["Server"]
            })

    df_summary = pd.DataFrame(summary_rows)
    df_detail = pd.DataFrame(detail_rows)

    st.subheader("📊 Summary")
    st.dataframe(df_summary, use_container_width=True)

    st.subheader("⛓️ Redirect Chains")
    for o, c in results:
        with st.expander(o):
            st.dataframe(pd.DataFrame(c), use_container_width=True)

    excel = generate_excel(df_summary, df_detail)
    st.download_button(
        "📥 Download Excel Report",
        excel,
        "redirect_audit.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif run_btn:
    st.warning("Please provide at least one URL.")
