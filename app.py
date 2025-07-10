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

# === Status code descriptions ===
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

# === Streamlit UI ===
st.set_page_config(page_title="URL Status & Redirect Checker", layout="wide")
st.title("🔗 Bulk URL Status & Redirect Checker")

st.markdown("""
Upload an Excel file (`.xlsx`) with a list of URLs in the first column (A).  
The app will check the HTTP status and detect redirects.

---

🔒 **Privacy Notice**  
Your file is **never stored, saved, or shared**. All data is processed **in-memory** and deleted when you leave or refresh the page.
""")

uploaded_file = st.file_uploader("📁 Upload Excel file", type="xlsx")

# === URL checking logic ===
def check_url(row_idx, url):
    try:
        response = requests.get(url, timeout=TIMEOUT, allow_redirects=False)
        original_status = response.status_code
        original_status_text = f"{original_status} - {status_names.get(original_status, 'Unknown')}"

        if original_status in (301, 302, 303, 307, 308):
            redirect_url = response.headers.get('Location')
            try:
                redirect_resp = requests.get(redirect_url, timeout=TIMEOUT)
                redirect_status = redirect_resp.status_code
                redirect_status_text = f"{redirect_status} - {status_names.get(redirect_status, 'Unknown')}"
            except requests.RequestException:
                redirect_status_text = 'Error'
        else:
            redirect_url = ''
            redirect_status_text = ''
    except requests.RequestException:
        original_status_text = 'Error'
        redirect_url = ''
        redirect_status_text = ''

    return row_idx, original_status_text, redirect_url, redirect_status_text

# === Main logic ===
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)

        # Rename first column to 'Original URL' if unnamed
        df.columns = ['Original URL'] + list(df.columns[1:])
        url_data = df['Original URL'].dropna().tolist()

        st.info(f"🔍 Checking {len(url_data)} URLs. This may take a minute...")

        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(check_url, idx, url) for idx, url in enumerate(url_data)]

            for future in as_completed(futures):
                results.append(future.result())

        # Keep results in the original order
        results.sort()

        # Add results to DataFrame
        df['Original Status'] = [r[1] for r in results]
        df['Redirect URL'] = [r[2] for r in results]
        df['Redirect Status'] = [r[3] for r in results]

        st.success("✅ URL checking complete!")
        st.dataframe(df)

        # === Create clean downloadable Excel ===
        wb = Workbook()
        ws = wb.active
        ws.title = "URL Results"

        # Write header + data
        for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
            for c_idx, value in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                if r_idx == 1:
                    cell.font = Font(bold=True)

        # Auto-size columns
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

        # Save Excel to buffer
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        # Download button
        st.download_button(
            label="📥 Download Results as Excel",
            data=buffer,
            file_name="url_status_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"❌ Error processing file: {e}")
