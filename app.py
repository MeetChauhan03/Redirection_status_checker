import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.parse import urljoin
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

# ================= CONFIG =================
MAX_WORKERS = 20
TIMEOUT = 6
REDIRECT_CODES = (301, 302, 303, 307, 308)

status_names = {
    200: "OK",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    404: "Not Found",
    500: "Server Error"
}

# ================= UI THEME =================
st.set_page_config("Advanced Redirect Chain Analyzer", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; }
.card {
    background: #0f172a;
    padding: 14px;
    border-radius: 12px;
    color: white;
}
.small { font-size: 13px; color: #cbd5f5; }
thead tr th { text-align: center !important; }
tbody tr td { text-align: center !important; }
</style>
""", unsafe_allow_html=True)

st.title("🔗 Advanced Redirect Chain Analyzer")
st.caption("AEM • Akamai • SEO-Safe • Enterprise-Grade Redirect Tool")

# ================= UTILITIES =================
def get_server_name(headers):
    akamai_keys = ["akamai", "x-akamai", "akamai-ghost"]
    combined = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    for key in akamai_keys:
        if key in combined:
            return "Akamai"
    return headers.get("Server", "Unknown")

def fetch_dual_response(url):
    head_resp, get_resp = None, None
    try:
        head_resp = requests.head(
            url,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": "SEO-Redirect-Checker"}
        )
    except:
        pass

    try:
        get_resp = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": "SEO-Redirect-Checker"}
        )
    except:
        pass

    return head_resp, get_resp

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
        head, get = fetch_dual_response(current_url)

        head_code = head.status_code if head else "Error"
        get_code = get.status_code if get else "Error"
        meaning = status_names.get(head_code, "Unknown")
        server = get_server_name(get.headers if get else {})

        location = ""
        source = head if head and head_code in REDIRECT_CODES else get
        if source:
            location = source.headers.get("Location", "")
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

        if head_code in REDIRECT_CODES or get_code in REDIRECT_CODES:
            if not location:
                break
            current_url = location
        else:
            break

    return chain

# ================= INPUT UI =================
col1, col2 = st.columns([2,1])

with col1:
    uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type="xlsx")

with col2:
    sample = pd.DataFrame({"Original URL": ["https://example.com"]})
    buf = BytesIO()
    sample.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("⬇ Sample File", buf, "sample_urls.xlsx")

text_input = st.text_area("Or paste URLs (one per line)", height=120)

# ================= URL COLLECTION =================
urls = []
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    urls += df.iloc[:,0].dropna().astype(str).tolist()

if text_input.strip():
    urls += [u.strip() for u in text_input.splitlines() if u.strip()]

urls = list(dict.fromkeys(urls))  # unique

if not urls:
    st.warning("Please provide URLs to proceed.")
    st.stop()

# ================= PROCESS =================
st.info(f"Checking {len(urls)} URLs…")

results = []
with ThreadPoolExecutor(MAX_WORKERS) as exe:
    futures = {exe.submit(check_redirection_chain, u): u for u in urls}
    for f in futures:
        results.append((futures[f], f.result()))

st.success("Redirect analysis completed.")

# ================= SUMMARY =================
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
        chains_flat.append({
            "Original URL": orig,
            "Step": i,
            **step
        })

df_summary = pd.DataFrame(summary)
df_chain = pd.DataFrame(chains_flat)

# ================= DISPLAY =================
st.markdown("### 📊 Executive Summary")
st.dataframe(df_summary, use_container_width=True)

st.markdown("### 🔗 Redirect Chains")
for orig, chain in results:
    with st.expander(orig):
        st.dataframe(pd.DataFrame(chain), use_container_width=True, height=200)

# ================= EXCEL EXPORT =================
def get_fill(code):
    try:
        c = int(code)
        if 200 <= c < 300:
            return PatternFill("solid", fgColor="C6EFCE")
        if 300 <= c < 400:
            return PatternFill("solid", fgColor="FFF2CC")
        if c >= 400:
            return PatternFill("solid", fgColor="F8CBAD")
    except:
        pass
    return None

def export_excel(df_summary, df_chain):
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Summary"

    for r, row in enumerate(dataframe_to_rows(df_summary, index=False, header=True), 1):
        ws1.append(row)
        if r == 1:
            for c in ws1[r]:
                c.font = Font(bold=True)
        else:
            for c in ws1[r]:
                c.fill = get_fill(row[2])

    ws2 = wb.create_sheet("Redirect Chains")
    for r, row in enumerate(dataframe_to_rows(df_chain, index=False, header=True), 1):
        ws2.append(row)
        if r == 1:
            for c in ws2[r]:
                c.font = Font(bold=True)
        else:
            for c in ws2[r]:
                c.fill = get_fill(row[3])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

excel = export_excel(df_summary, df_chain)

st.download_button(
    "📥 Download Excel Report",
    excel,
    "redirect_analysis_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.markdown("""
---
<div style="text-align:center;color:gray;font-size:13px">
© 2025 Meet Chauhan — Advanced Redirect Analyzer
</div>
""", unsafe_allow_html=True)
