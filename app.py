import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

# === Configuration ===
MAX_WORKERS = 20
TIMEOUT = 5

# === HTTP Status Descriptions ===
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

# === Helper Functions ===

def fetch_server_header(url, timeout=TIMEOUT):
    try:
        head_resp = requests.head(url, timeout=timeout, allow_redirects=True)
        server = head_resp.headers.get('Server', 'N/A')
        return server
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
            server = r.headers.get('Server', None)

            # Try to get server from redirect location if missing
            if not server and r.status_code in (301, 302, 303, 307, 308):
                redirect_url = r.headers.get('Location')
                if redirect_url:
                    server = fetch_server_header(redirect_url)

            steps.append({
                'Step': i + 1,
                'Redirected URL': r.headers.get('Location') or r.url,
                'Status Code': r.status_code,
                'Status Description': status_names.get(r.status_code, 'Unknown'),
                'Server': server or 'N/A'
            })

        # Add final step info
        server_final = response.headers.get('Server', None)
        server_final = server_final if server_final else fetch_server_header(response.url)

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

def validate_urls(urls):
    blocked_urls = [url for url in urls if "avnhc" in url.lower()]
    valid_urls = [url for url in urls if "avnhc" not in url.lower()]
    return valid_urls, blocked_urls

# === Streamlit UI ===
st.set_page_config(page_title="URL Status & Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Status & Redirect Checker")

st.markdown("""
Upload an Excel file **or paste a list of URLs** (one per line).  
The app will check HTTP status codes and redirections, including full redirect chain and server info.

---

🔒 **Privacy Notice**  
Uploaded or pasted data is never stored or shared. All processing happens in-memory and is deleted after your session ends.
""")

# Upload Excel
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

with st.expander("📄 Download sample Excel format"):
    sample_df = pd.DataFrame({"Original URL": ["https://example.com", "https://abc.com"]})
    sample_buffer = BytesIO()
    sample_df.to_excel(sample_buffer, index=False)
    sample_buffer.seek(0)

    st.download_button(
        label="⬇️ Download Sample Excel",
        data=sample_buffer,
        file_name="sample_urls.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.markdown("📌 Format: One column named **Original URL**, one URL per row.")

# Paste URLs manually
st.markdown("#### Or paste URLs manually below:")
text_input = st.text_area("🔽 Paste URLs (one per line):", height=150)

# Extract and validate URLs
url_list = []
blocked_urls_excel = []
blocked_urls_text = []

if uploaded_file is not None:
    try:
        df_input = pd.read_excel(uploaded_file)
        df_input.columns = ['Original URL'] + list(df_input.columns[1:])
        all_urls = df_input['Original URL'].dropna().astype(str).tolist()
        url_list, blocked_urls_excel = validate_urls(all_urls)
        if blocked_urls_excel:
            st.error(f"❌ The following URLs from your Excel are blocked because they contain 'avnhc':\n\n" +
                     "\n".join(blocked_urls_excel))
    except Exception as e:
        st.error(f"❌ Error reading Excel file: {e}")

if text_input.strip():
    input_urls = [line.strip() for line in text_input.strip().splitlines() if line.strip()]
    input_valid_urls, blocked_urls_text = validate_urls(input_urls)
    url_list.extend(input_valid_urls)
    if blocked_urls_text:
        st.error(f"❌ The following pasted URLs are blocked because they contain 'avnhc':\n\n" +
                 "\n".join(blocked_urls_text))

# Remove duplicates
url_list = list(dict.fromkeys(url_list))

if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs. Please wait...")

    all_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_redirect_chain, url): url for url in url_list}
        for future in as_completed(futures):
            url = futures[future]
            try:
                all_results[url] = future.result()
            except Exception as e:
                all_results[url] = [{
                    'Step': 1,
                    'Redirected URL': 'Error',
                    'Status Code': 'Error',
                    'Status Description': str(e),
                    'Server': 'N/A'
                }]

    # Prepare for display
    st.success("✅ URL checking complete!")

    # Display each URL chain with arrows and table
    for url, steps in all_results.items():
        st.markdown(f"##### URL: {url}")

        # Build arrow chain string: Step1Status → Step2Status → StepNStatus
        chain_parts = []
        for step in steps:
            code = step['Status Code']
            desc = step['Status Description']
            chain_parts.append(f"{code}({desc})")
        chain_display = " → ".join(chain_parts)
        st.markdown(f"**Redirect Chain:** {chain_display}")

        # Show table with details per step
        df_steps = pd.DataFrame(steps)
        df_steps_display = df_steps[['Step', 'Redirected URL', 'Status Code', 'Status Description', 'Server']]
        st.dataframe(df_steps_display, use_container_width=True)

        # Final URL check (working or not)
        final_url = steps[-1]['Redirected URL']
        final_status_live = check_final_url_status(final_url)
        st.markdown(f"**Final URL Status:** {final_status_live}")

        st.markdown("---")

    # Prepare data for Excel export
    rows = []
    for url, steps in all_results.items():
        for step in steps:
            rows.append({
                'Original URL': url,
                'Step': step['Step'],
                'Redirected URL': step['Redirected URL'],
                'Status Code': step['Status Code'],
                'Status Description': step['Status Description'],
                'Server': step['Server']
            })

    df_export = pd.DataFrame(rows)

    # Format Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "URL Results"

    for r_idx, row in enumerate(dataframe_to_rows(df_export, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = Font(bold=True)

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = max_length + 2

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    st.download_button(
        label="📥 Download Results as Excel",
        data=buffer,
        file_name="url_status_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif not url_list and not blocked_urls_excel and not blocked_urls_text:
    st.warning("📌 Please either upload an Excel file or paste URLs to begin.")

# === Footer ===
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)