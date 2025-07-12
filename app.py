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
    400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
    404: 'Not Found', 500: 'Internal Server Error'
}

# === Helpers ===
def is_valid_url(url):
    try:
        p = urlparse(url.strip())
        return p.scheme in ('http', 'https') and p.netloc
    except:
        return False

def is_blocked_url(url):
    return 'b2b-b' in url.lower()

def get_server_name(headers):
    markers = ["AkamaiGHost", "akamaitechnologies.com", "X-Akamai-Transformed"]
    hdrs = " | ".join(f"{k}: {v}" for k, v in headers.items())
    for m in markers:
        if m.lower() in hdrs.lower():
            return "Akamai"
    for key in ["Server", "X-Powered-By", "X-Cache", "Via", "CF-RAY", "X-Amz-Cf-Id", "X-CDN"]:
        if key in headers:
            return f"{key}: {headers[key]}"
    return "Unknown"

def check_redirection_chain(url):
    visited, chain = set(), []
    current = url
    try:
        while True:
            if current in visited:
                chain.append({'URL': current, 'Status': 'Loop detected', 'Status Code': 'Loop', 'Server': 'N/A'})
                break
            visited.add(current)
            resp = requests.get(current, timeout=TIMEOUT, allow_redirects=False)
            sc = resp.status_code
            stxt = status_names.get(sc, 'Unknown')
            server = get_server_name(resp.headers)
            chain.append({'URL': current, 'Status': stxt, 'Status Code': sc, 'Server': server})
            if sc in (301,302,303,307,308):
                loc = resp.headers.get('Location')
                if not loc: break
                current = urljoin(current, loc)
            else:
                break
    except:
        chain.append({'URL': current, 'Status': 'Error', 'Status Code': 'Error', 'Server': 'N/A'})
    return chain

def get_status_fill(c):
    try: c = int(c)
    except: return PatternFill(start_color="FFFFFF", fill_type=None)
    if 200<=c<300: col="C6EFCE"
    elif 300<=c<400: col="FFF2CC"
    elif 400<=c<600: col="F8CBAD"
    else: col="FFFFFF"
    return PatternFill(start_color=col, fill_type="solid")

def adjust_column_widths(ws):
    for col in ws.columns:
        w = max(len(str(cell.value)) for cell in col if cell.value) + 4
        ws.column_dimensions[col[0].column_letter].width = w

def to_excel(df_sum, df_full):
    wb = Workbook()
    ws1 = wb.active; ws1.title = "Summary"
    for ridx,row in enumerate(dataframe_to_rows(df_sum, index=False, header=True),1):
        ws1.append(row)
        for cell in ws1[ridx]:
            if ridx==1:
                cell.font=Font(bold=True); cell.alignment=Alignment(horizontal="center")
            else:
                cell.fill = get_status_fill(row[2])
    adjust_column_widths(ws1)

    ws2 = wb.create_sheet("Tracking")
    for url, grp in df_full.groupby("Original URL"):
        ws2.append([f"Redirect Chain for: {url}"])
        ws2.append([])
        for i,row in enumerate(dataframe_to_rows(grp, index=False, header=True)):
            ws2.append(row)
            if i>0:
                for cell in ws2[ws2.max_row]:
                    cell.fill = get_status_fill(row[3])
        ws2.append([])
    adjust_column_widths(ws2)

    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return buf

# === UI ===
st.set_page_config("URL Status & Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Status & Redirect Checker")

# Session state for clear
if "clear_triggered" not in st.session_state:
    st.session_state.clear_triggered = False
if "text_input" not in st.session_state:
    st.session_state.text_input = ""

# Clear button
if st.button("🧹 Clear All"):
    st.session_state.text_input = ""
    st.session_state.clear_triggered = True
    st.rerun()
if st.session_state.clear_triggered:
    st.session_state.clear_triggered = False

st.markdown("Upload **OR** Paste URLs below (one per line).")

# Sample Excel download
with st.expander("📄 Sample Excel format"):
    df_s = pd.DataFrame({"Original URL":["https://example.com","https://abc.com"]})
    buf = BytesIO(); df_s.to_excel(buf, index=False); buf.seek(0)
    st.download_button("⬇️ Download Sample Excel", buf, "sample.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type="xlsx")
text_input = st.text_area("🔽 Paste URLs manually:", key="text_input", height=150)

# Input logic
urls = []
if uploaded_file and not text_input.strip():
    df = pd.read_excel(uploaded_file)
    if 'Original URL' not in df.columns:
        st.error("Excel must have 'Original URL' column."); st.stop()
    urls = df['Original URL'].dropna().astype(str).tolist()
elif text_input.strip() and not uploaded_file:
    urls = [l.strip() for l in text_input.splitlines()]
else:
    st.info("📌 Provide *either* Excel *or* manual URLs.")
    st.stop()

# Validate / Clean URLs
valid, skipped = [], []
for u in urls:
    if is_blocked_url(u) or not is_valid_url(u):
        skipped.append(u)
    else:
        valid.append(u)

if not valid:
    st.warning("No valid URLs to process."); st.stop()
if skipped:
    st.warning("Skipped invalid/blocked URLs:\n" + "\n".join(skipped))

st.info(f"🔍 Checking {len(valid)} URLs...")
results = {}
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {ex.submit(check_redirection_chain, u):u for u in valid}
    for f in as_completed(futures):
        u = futures[f]
        try: results[u] = f.result()
        except: results[u] = [{'URL':u,'Status':'Error','Status Code':'Error','Server':'N/A'}]
st.success("✅ Done!")

# Prepare dataframes
sum_rows, all_rows = [], []
for o,chain in results.items():
    fin = chain[-1]
    sum_rows.append({"Original URL":o,"Final URL":fin["URL"],"Status Code":fin["Status Code"],"Server":fin["Server"]})
    for i, step in enumerate(chain):
        all_rows.append({
            "Original URL":o, "Redirect Step":i+1, "Redirected URL":step["URL"],
            "Status Code":step["Status Code"], "Status Description":step["Status"], "Server":step["Server"]
        })
df_sum = pd.DataFrame(sum_rows)
df_full = pd.DataFrame(all_rows)

# Search/filter
search = st.text_input("🔎 Search URLs or servers:")
df_disp = df_full[df_full.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)] if search else df_full
st.dataframe(df_disp, use_container_width=True)

# Excel export
out = to_excel(df_sum, df_full)
st.download_button("📥 Download Results as Excel", out, "results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Redirect chain preview
st.markdown("### 🔗 Redirect Chain Preview")
for o, chain in results.items():
    with st.expander(o):
        for step in chain:
            st.markdown(f"`{step['Status Code']}` → **{step['Status']}** → `{step['URL']}`  *(Server: {step['Server']})*")

# Footer
st.markdown("---\n<div style='text-align:center;color:gray;'>© 2025 Meet Chauhan.</div>", unsafe_allow_html=True)
