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
USER_AGENT = "Mozilla/5.0 (Redirect-Analyzer)"
REDIRECT_CODES = (301, 302, 303, 307, 308)

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

# ================= UI SETUP =================
st.set_page_config("URL Redirect Analyzer", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
thead tr th, tbody tr td { text-align:center !important; }
</style>
""", unsafe_allow_html=True)

st.title("🔗 Bulk URL Redirect Analyzer")
st.caption("Accurate 301/302 Detection • AEM & Akamai Safe")

st.markdown("""
**How it works**
- Uses `HEAD` for origin (AEM) redirect detection
- Falls back to `GET` when HEAD is blocked
- Shows full redirect chains (A → B → C)
- Exports clean Excel reports

---
""")

# ================= SESSION HELPERS =================
def clear_all():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

# ================= UTILITIES =================
def get_server_name(headers):
    text = " ".join(f"{k}:{v}".lower() for k, v in headers.items())
    if "akamai" in text:
        return "Akamai"
    return headers.get("Server", "Unknown")

def fetch_response(url):
    """HEAD first, fallback to GET"""
    try:
        r = requests.head(
            url,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT}
        )
        if r.status_code not in (403, 405):
            return r, "HEAD"
    except:
        pass

    try:
        r = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT}
        )
        return r, "GET"
    except:
        return None, None

# ================= REDIRECT LOGIC =================
def check_redirection_chain(start_url):
    visited = set()
    chain = []
    current_url = start_url

    while True:
        if current_url in visited:
            chain.append({
                "URL": current_url,
                "Method": "Loop",
                "Status Code": "Loop",
                "Status": "Redirect Loop",
                "Server": "N/A",
                "Location": ""
            })
            break

        visited.add(current_url)

        resp, method = fetch_response(current_url)

        if not resp:
            chain.append({
                "URL": current_url,
                "Method": "N/A",
                "Status Code": "Error",
                "Status": "Request Failed",
                "Server": "N/A",
                "Location": ""
            })
            break

        code = resp.status_code
        status = STATUS_NAMES.get(code, "Unknown")
        server = get_server_name(resp.headers)

        location = resp.headers.get("Location", "")
        if location.startswith("/"):
            location = urljoin(current_url, location)

        chain.append({
            "URL": current_url,
            "Method": method,
            "Status Code": code,
            "Status": status,
            "Server": server,
            "Location": location
        })

        if code in REDIRECT_CODES and location:
            current_url = location
        else:
            break

    return chain

# ================= INPUT UI =================
col1, col2, col3 = st.columns([2,1,1])

with col1:
    uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type="xlsx")

with col2:
    text_input = st.text_area("Paste URLs (one per line)", height=120)

with col3:
    st.markdown("### Actions")
    run = st.button("▶ Run Analysis", use_container_width=True)
    clear = st.button("🧹 Clear All", use_container_width=True)

if clear:
    clear_all()

# ================= URL COLLECTION =================
urls = []

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    urls += df.iloc[:,0].dropna().astype(str).tolist()

if text_input.strip():
    urls += [u.strip() for u in text_input.splitlines() if u.strip()]

urls = list(dict.fromkeys(urls))

if not run:
    st.stop()

if not urls:
    st.warning("Please provide at least one URL.")
    st.stop()

# ================= PROCESS =================
st.info(f"Analyzing {len(urls)} URLs...")

results = []

with ThreadPoolExecutor(MAX_WORKERS) as executor:
    future_map = {executor.submit(check_redirection_chain, url): url for url in urls}

    for future in as_completed(future_map):
        url = future_map[future]
        try:
            results.append((url, future.result()))
        except:
            results.append((url, [{
                "URL": url,
                "Method": "N/A",
                "Status Code": "Error",
                "Status": "Execution Error",
                "Server": "N/A",
                "Location": ""
            }]))

st.success("Analysis completed.")

# ================= DATA =================
summary = []
flat = []

for orig, chain in results:
    final = chain[-1]
    summary.append({
        "Original URL": orig,
        "Final URL": final["URL"],
        "Final Status": final["Status Code"],
        "Redirect Count": len(chain) - 1,
        "Server": final["Server"]
    })

    for i, step in enumerate(chain, 1):
        flat.append({"Original URL": orig, "Step": i, **step})

df_summary = pd.DataFrame(summary)
df_chain = pd.DataFrame(flat)

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

excel = export_excel(df_summary, df_chain)

st.download_button(
    "📥 Download Excel Report",
    excel,
    "redirect_analysis.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.markdown("""
---
<div style="text-align:center;font-size:12px;color:gray;">
© 2025 Meet Chauhan — Redirect Analyzer
</div>
""", unsafe_allow_html=True)
