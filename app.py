import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

MAX_WORKERS = 20
TIMEOUT = 5

status_names = {
    200: 'OK', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other',
    307: 'Temporary Redirect', 308: 'Permanent Redirect',
    400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
    404: 'Not Found', 500: 'Internal Server Error'
}

def fetch_server_header(url, timeout=TIMEOUT):
    try:
        head_resp = requests.head(url, timeout=timeout, allow_redirects=True)
        return head_resp.headers.get('Server', 'N/A')
    except:
        return 'N/A'

def check_final_url_status(url):
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        code = resp.status_code
        desc = status_names.get(code, 'Unknown')
        return f"{code} - {desc}"
    except:
        return "Error"

def get_redirect_chain(url):
    try:
        session = requests.Session()
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        history = response.history
        steps = []
        for i, r in enumerate(history):
            location = r.headers.get('Location') or r.url
            server = r.headers.get('Server') or fetch_server_header(location)
            steps.append({
                'Step': i + 1,
                'Redirected URL': location,
                'Status Code': r.status_code,
                'Status Description': status_names.get(r.status_code, 'Unknown'),
                'Server': server or 'N/A'
            })
        server_final = response.headers.get('Server') or fetch_server_header(response.url)
        steps.append({
            'Step': len(steps) + 1,
            'Redirected URL': response.url,
            'Status Code': response.status_code,
            'Status Description': status_names.get(response.status_code, 'Unknown'),
            'Server': server_final or 'N/A'
        })
        return steps
    except requests.RequestException as e:
        return [{
            'Step': 1,
            'Redirected URL': 'Error',
            'Status Code': 'Error',
            'Status Description': str(e),
            'Server': 'N/A'
        }]

def clean_tracking_data(raw_results):
    cleaned_results = {}
    for url, steps in raw_results.items():
        cleaned_chain = []
        seen = set()
        for step in steps:
            key = (step['Redirected URL'], step['Status Code'])
            if key not in seen:
                seen.add(key)
                cleaned_chain.append(step)
        cleaned_results[url] = cleaned_chain
    return cleaned_results

def validate_urls(urls):
    blocked = [u for u in urls if "avnhc" in u.lower()]
    allowed = [u for u in urls if "avnhc" not in u.lower()]
    return allowed, blocked

def render_centered_table(df):
    html = df.to_html(index=False)
    style = """
    <style>
    table { margin: auto; border-collapse: collapse; }
    th, td { text-align: center !important; padding: 8px; border: 1px solid #ddd; }
    </style>
    """
    st.markdown(style + html, unsafe_allow_html=True)

# UI setup
st.set_page_config(page_title="URL Status Checker", layout="wide")
st.title("🔗 URL Status & Redirect Chain Checker")

st.markdown("Upload Excel or paste URLs. We'll track redirects, servers, and status codes.")

uploaded_file = st.file_uploader("📁 Upload Excel (.xlsx)", type="xlsx")

with st.expander("📄 Download sample Excel format"):
    sample = pd.DataFrame({"Original URL": ["https://example.com", "https://abc.com"]})
    buf = BytesIO()
    sample.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("⬇️ Sample Excel", data=buf, file_name="sample_urls.xlsx")

text_input = st.text_area("Or paste URLs (one per line):", height=150)

url_list = []
blocked_urls = []

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    urls = df.iloc[:, 0].dropna().astype(str).tolist()
    url_list, blocked1 = validate_urls(urls)
    blocked_urls.extend(blocked1)

if text_input.strip():
    pasted = [line.strip() for line in text_input.strip().splitlines() if line.strip()]
    valid, blocked2 = validate_urls(pasted)
    url_list.extend(valid)
    blocked_urls.extend(blocked2)

url_list = list(dict.fromkeys(url_list))

if blocked_urls:
    st.warning("❌ Blocked URLs (contain 'avnhc'):\n" + "\n".join(blocked_urls))

if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs...")
    all_results = {}
    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        jobs = {ex.submit(get_redirect_chain, url): url for url in url_list}
        for f in as_completed(jobs):
            url = jobs[f]
            try:
                all_results[url] = f.result()
            except:
                all_results[url] = []

    all_results = clean_tracking_data(all_results)
    st.success("✅ Done!")

    export_rows = []

    for url, steps in all_results.items():
        st.subheader(f"🔗 {url}")
        arrows = " → ".join([f"{s['Status Code']}({s['Status Description']})" for s in steps])
        st.markdown(f"**Redirect Chain:** {arrows}")

        df_steps = pd.DataFrame(steps)
        render_centered_table(df_steps)

        final_url = steps[-1]['Redirected URL']
        final_status = check_final_url_status(final_url)
        st.markdown(f"**Final URL Status:** `{final_status}`")
        st.markdown("---")

        for step in steps:
            export_rows.append({
                'Original URL': url,
                'Step': step['Step'],
                'Redirected URL': step['Redirected URL'],
                'Status Code': step['Status Code'],
                'Status Description': step['Status Description'],
                'Server': step['Server']
            })

    df_export = pd.DataFrame(export_rows)
    st.data_editor(df_export, use_container_width=True, num_rows="dynamic")

    wb = Workbook()
    ws = wb.active
    ws.title = "URL Results"
    for r_idx, row in enumerate(dataframe_to_rows(df_export, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = Font(bold=True)

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 2

    out = BytesIO()
    wb.save(out)
    out.seek(0)

    st.download_button("📥 Download Results", data=out, file_name="url_status_results.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Please upload a file or paste URLs to begin.")

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray'>© 2025 Meet Chauhan. All rights reserved.</div>", unsafe_allow_html=True)
