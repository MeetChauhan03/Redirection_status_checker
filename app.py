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

# === Helper: Get redirect chain with server headers ===
def get_redirect_chain(url):
    try:
        session = requests.Session()
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        history = response.history
        steps = []

        for i, r in enumerate(history):
            server = r.headers.get('Server', None)

            # If server header missing on redirect response, try HEAD request on Location
            if not server and r.status_code in (301, 302, 303, 307, 308):
                redirect_url = r.headers.get('Location')
                if redirect_url:
                    try:
                        head_resp = session.head(redirect_url, timeout=TIMEOUT, allow_redirects=False)
                        server = head_resp.headers.get('Server', 'N/A')
                    except:
                        server = 'N/A'

            steps.append({
                'Original URL': url,
                'Step': i + 1,
                'Redirected URL': r.headers.get('Location') or r.url,
                'Status Code': r.status_code,
                'Status Description': status_names.get(r.status_code, 'Unknown'),
                'Server': server or 'N/A',
                'Final URL': response.url,
                'Final Status': f"{response.status_code} - {status_names.get(response.status_code, 'Unknown')}"
            })

        server_final = response.headers.get('Server', 'N/A')

        if not steps:
            # No redirects, just the original URL response
            steps.append({
                'Original URL': url,
                'Step': 1,
                'Redirected URL': url,
                'Status Code': response.status_code,
                'Status Description': status_names.get(response.status_code, 'Unknown'),
                'Server': server_final,
                'Final URL': response.url,
                'Final Status': f"{response.status_code} - {status_names.get(response.status_code, 'Unknown')}"
            })
        else:
            # Make sure last step's server is updated to final server if missing
            steps[-1]['Server'] = server_final or steps[-1]['Server']

        return steps

    except requests.RequestException as e:
        return [{
            'Original URL': url,
            'Step': 1,
            'Redirected URL': 'Error',
            'Status Code': 'Error',
            'Status Description': str(e),
            'Server': 'N/A',
            'Final URL': 'Error',
            'Final Status': 'Error'
        }]

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

# === Upload Excel ===
uploaded_file = st.file_uploader("📁 Upload Excel file (.xlsx)", type="xlsx")

# === Sample file download ===
with st.expander("📄 Download sample Excel format"):
    sample_df = pd.DataFrame({
        "Original URL": [
            "https://example.com",
            "https://abc.com"
        ]
    })
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

# === Text input option ===
st.markdown("#### Or paste URLs manually below:")
text_input = st.text_area("🔽 Paste URLs (one per line):", height=150)

# === Extract URLs and validate ===
def validate_urls(urls):
    blocked_urls = [url for url in urls if "avnhc" in url.lower()]
    valid_urls = [url for url in urls if "avnhc" not in url.lower()]
    return valid_urls, blocked_urls

url_list = []

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

else:
    blocked_urls_excel = []

if text_input.strip():
    input_urls = [line.strip() for line in text_input.strip().splitlines() if line.strip()]
    input_valid_urls, blocked_urls_text = validate_urls(input_urls)
    url_list.extend(input_valid_urls)
    if blocked_urls_text:
        st.error(f"❌ The following pasted URLs are blocked because they contain 'avnhc':\n\n" +
                 "\n".join(blocked_urls_text))
else:
    blocked_urls_text = []

# Remove duplicates in url_list
url_list = list(dict.fromkeys(url_list))

# === Process URLs ===
if url_list:
    st.info(f"🔍 Checking {len(url_list)} URLs. Please wait...")

    all_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_redirect_chain, url): url for url in url_list}

        for future in as_completed(futures):
            results = future.result()
            all_results.extend(results)

    # Sort results by Original URL and Step
    all_results.sort(key=lambda x: (x['Original URL'], x['Step']))

    df = pd.DataFrame(all_results)

    st.success("✅ URL checking complete!")

    # UI: show chain visually
    def format_chain(group):
        parts = []
        for _, row in group.iterrows():
            part = f"{row['Status Code']}({row['Status Description']})"
            parts.append(part)
        return " > ".join(parts)

    grouped = df.groupby('Original URL')

    for original_url, group in grouped:
        st.markdown(f"**URL:** {original_url}")
        st.markdown(f"**Redirect Chain:**  {format_chain(group)}")
        # Show table for this URL
        st.table(group[["Step", "Redirected URL", "Status Code", "Status Description", "Server"]])

    # === Format Excel ===
    wb = Workbook()
    ws = wb.active
    ws.title = "URL Results"

    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
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
