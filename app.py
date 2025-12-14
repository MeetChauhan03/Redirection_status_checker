import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# === CONFIGURATION ===
st.set_page_config(page_title="Redirect Auditor", layout="wide")

# HEADERS TO MIMIC BROWSER (Fixes 301/302 AEM Issue)
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# ... (Include helper functions: get_server_name, is_blocked_url from previous code) ...

def check_chain_robust(url):
    # Implementation of the fixed logic with BROWSER_HEADERS
    # ... (See previous artifact for logic) ...
    pass 

# === UI LAYOUT ===
with st.sidebar:
    st.title("⚙️ Configuration")
    uploaded_file = st.file_uploader("Upload Excel", type="xlsx")
    raw_text = st.text_area("Paste URLs", height=150)
    st.divider()
    if st.button("▶ Run Audit", type="primary", use_container_width=True):
        st.session_state.run_check = True

# === MAIN CONTENT ===
st.title("🔗 Redirect Auditor")

if st.session_state.get("run_check"):
    # 1. Processing Logic
    progress_bar = st.progress(0)
    
    # 2. Display Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total URLs", len(urls))
    col2.metric("Success (200)", success_count)
    col3.metric("Redirects", redirect_count)
    col4.metric("Errors", error_count)

    # 3. Modern Data Table with Column Config
    st.dataframe(
        df_results,
        column_config={
            "Status Code": st.column_config.NumberColumn(
                "Status",
                format="%d",
            ),
            "Redirect Chain": st.column_config.ListColumn(
                "Hops"
            )
        },
        use_container_width=True
    )

# --- Filter/Search UI ---
st.markdown("### 🔎 Filter / Search URLs")
search_term = st.text_input("Search in Original or Redirected URLs or Status Codes or Server names:")

if search_term:
    df_filtered = df_results[
        df_results["Original URL"].str.contains(search_term, case=False, na=False) |
        df_results["Redirected URL"].str.contains(search_term, case=False, na=False) |
        df_results["Server"].str.contains(search_term, case=False, na=False) |
        df_results["Status Code"].astype(str).str.contains(search_term, case=False, na=False)    ]
else:
    df_filtered = df_results


    # 4. Excel Export Logic (Two Sheets)
    # ... Code to create Summary and Detail sheets ...

# --- Download Excel with formatting ---
def to_excel(df_summary, df_tracking):
    wb = Workbook()

    # === Sheet 1: Summary ===
    ws1 = wb.active
    ws1.title = "URL Redirect Results"

    for r_idx, row in enumerate(dataframe_to_rows(df_summary, index=False, header=True), 1):
        ws1.append(row)
        if r_idx == 1:
            for cell in ws1[r_idx]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")
        else:
            status_code = row[2]
            fill = get_status_fill(status_code)
            for cell in ws1[r_idx]:
                cell.fill = fill

    ws1.auto_filter.ref = ws1.dimensions  # Add Excel filter
    adjust_column_widths(ws1)

    # === Sheet 2: Redirection Tracking (Grouped) ===
    ws2 = wb.create_sheet("Redirection Tracking")

    grouped = df_tracking.groupby("Original URL")

    for url, group in grouped:
        ws2.append([f"Redirect Chain for: {url}"])
        for cell in ws2[ws2.max_row]:
            cell.font = Font(bold=True, color="0000FF")
        ws2.append([])

        for r_idx, row in enumerate(dataframe_to_rows(group, index=False, header=True)):
            ws2.append(row)
            if r_idx > 0:  # skip header row
                status_code = row[3]
                fill = get_status_fill(status_code)
                for cell in ws2[ws2.max_row]:
                    cell.fill = fill

        ws2.append([])  # Spacer

    adjust_column_widths(ws2)
    ws2.auto_filter.ref = ws2.dimensions

    # === Save to stream ===
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

# === Helpers ===
def get_status_fill(code):
    try:
        code = int(code)
    except:
        return PatternFill(start_color="FFFFFF", fill_type=None)

    if 200 <= code < 300:
        return PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")  # Green
    elif 300 <= code < 400:
        return PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")  # Yellow
    elif 400 <= code < 600:
        return PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")  # Red
    return PatternFill(start_color="FFFFFF", fill_type=None)

def adjust_column_widths(ws):
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 4

excel_data = to_excel(df_summary, df_results)

st.download_button(
    label="📥 Download Results as Excel",
    data=excel_data,
    file_name="url_status_with_redirect_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- Show redirect chains as collapsible markdown ---
st.markdown("### 🔗 Redirect Chains Preview (expand below)")

for orig_url, chain in results:
    with st.expander(orig_url, expanded=False):
        st.markdown(render_redirect_chain(chain))

# --- Footer ---
st.markdown("""
---
<div style='text-align: center; font-size: 0.9em; color: gray;'>
© 2025 Meet Chauhan. All rights reserved.
</div>
""", unsafe_allow_html=True)