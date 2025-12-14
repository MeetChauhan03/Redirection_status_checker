import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from urllib.parse import urljoin
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

# ================= CONFIG =================
MAX_WORKERS = 20
TIMEOUT = 6
USER_AGENT = "SEO-Redirect-Analyzer/1.0"
REDIRECT_CODES = (301, 302, 303, 307, 308)

STATUS_NAMES = {
    200: "OK",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    404: "Not Found",
    500: "Server Error"
}

# ================= UI =================
st.set_page_config("Advanced Redirect Chain Analyzer", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; }
thead tr th, tbody tr td { text-align:center !important; }
</style>
""", unsafe_allow_html=True)

st.title("🔗 Advanced Redirect Chain Analyzer")
st.caption("AEM • Akamai • Accurate 301/302 • Enterprise SEO Tool")

# ================= UTILITIES =================
def get_server_name(headers):
    text = " ".join(f"{k}:{v}".lower() for k, v in headers.items())
    if "akamai" in text:
        return "Akamai"
    return headers.get("Server", "Unknown")

def fetch_head(url):
    try:
        return requests.head(
            url,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT}
        )
    except:
        return None

def fetch_get(url):
    try:
        return requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT}
        )
    except:
        return None

# ================= REDIRECT LOGIC =================
def check_redirection_chain(start_url):
    visited = set()
    chain = []
    current_url = start_url

    while True:
        if current_url in visited:
            chain.append({
                "URL": current_url,
                "HEAD": "Loop",
                "GET": "Loop",
                "Meaning": "Redirect Loop",
                "Server": "N/A",
                "Location": ""
            })
            break

        visited.add(current_url)

        head = fetch_head(current_url)
        get = fetch_get(current_url)

        head_code = head.status_code if head else "Error"
        get_code = get.status_code if get else "Error"

        meaning = STATUS_NAMES.get(head_code, "Unknown")
        server = get_server_name(get.headers if get else {})

        location = ""

        # STRICT PRIORITY: HEAD → GET → STOP
        if head and head_code in REDIRECT_CODES:
            location = head.headers.get("Location", "")
        elif get and get_code in REDIRECT_CODES:
            location = get.headers.get("Location", "")

        if location.startswith("/"):
            location = urljoin(current_url, location)

        chain.append({
            "URL": current_url,
            "HEAD": head_code,
            "GET": get_code,
            "Meaning": meaning,
            "Server": server,
            "Location": location
        })

        if location and (head_code in REDIRECT_CODES or get_code in REDIRECT_CODES):
            current_url = location
        else:
            break

    return chain

# ================= INPUT =================
col1, col2 = st.columns([2,1])

with col1:
    uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type="xlsx")

with col2:
    sample = pd.DataFrame({"Original URL": ["https://example.com"]})
    buf = BytesIO()
    sample.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("Download Sample", buf, "sample.xlsx")

text_input = st.text_area("Or paste URLs (one per line)", height=120)

urls = []

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    urls += df.iloc[:,0].dropna().astype(str).tolist()

if text_input.strip():
    urls += [u.strip() for u in text_input.splitlines() if u.strip()]

urls = list(dict.fromkeys(urls))

if not urls:
    st.warning("Please provide URLs.")
    st.stop()

# ================= PROCESS =================
st.info(f"Checking {len(urls)} URLs...")

results = []

with ThreadPoolExecutor(MAX_WORKERS) as executor:
    future_map = {executor.submit(check_redirection_chain, url): url for url in urls}

    for future in as_completed(future_map):
        url = future_map[future]
        try:
            results.append((url, future.result()))
        except Exception:
            results.append((url, [{
                "URL": url,
                "HEAD": "Error",
                "GET": "Error",
                "Meaning": "Error",
                "Server": "N/A",
                "Location": ""
            }]))

st.success("Analysis completed.")

# ================= DATA PREP =================
summary = []
chains_flat = []

for orig, chain in results:
    final = chain[-1]
    summary.append({
        "Original URL": orig,
        "Final URL": final["URL"],
        "Origin Status (HEAD)": final["HEAD"],
        "Edge Status (GET)": final["GET"],
        "Redirect Count": len(chain) - 1,
        "Server/CDN": final["Server"]
    })

    for i, step in enumerate(chain, 1):
        chains_flat.append({"Original URL": orig, "Step": i, **step})

df_summary = pd.DataFrame(summary)
df_chain = pd.DataFrame(chains_flat)

# ================= DISPLAY =================
st.markdown("### Executive Summary")
st.dataframe(df_summary, use_container_width=True)

st.markdown("### Redirect Chains")
for orig, chain in results:
    with st.expander(orig):
        st.dataframe(pd.DataFrame(chain), use_container_width=True)

# ================= EXCEL =================
def status_fill(code):
    try:
        code = int(code)
        if 200 <= code < 300:
            return PatternFill("solid", fgColor="C6EFCE")
        if 300 <= code < 400:
            return PatternFill("solid", fgColor="FFF2CC")
        if code >= 400:
            return PatternFill("solid", fgColor="F8CBAD")
    except:
        return None

def export_excel(summary_df, chain_df):
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Summary"

    for r, row in enumerate(dataframe_to_rows(summary_df, index=False, header=True), 1):
        ws1.append(row)
        if r == 1:
            for c in ws1[r]:
                c.font = Font(bold=True)
        else:
            fill = status_fill(row[2])
            if fill:
                for c in ws1[r]:
                    c.fill = fill

    ws2 = wb.create_sheet("Redirect Chains")
    for r, row in enumerate(dataframe_to_rows(chain_df, index=False, header=True), 1):
        ws2.append(row)
        if r == 1:
            for c in ws2[r]:
                c.font = Font(bold=True)

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out

excel_file = export_excel(df_summary, df_chain)

st.download_button(
    "Download Excel Report",
    excel_file,
    "redirect_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.markdown("""
---
<div style="text-align:center;color:gray;font-size:12px">
© 2025 Meet Chauhan – Redirect Chain Analyzer
</div>
""", unsafe_allow_html=True)
