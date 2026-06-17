import streamlit as st
import pandas as pd
from datetime import datetime, date
import gspread

# Set page configuration
st.set_page_config(page_title="NAMI Hours Logger", page_icon="📝", layout="centered")

# --- Database Setup (Google Sheets) ---
def load_data():
    try:
        # Load credentials from Streamlit Secrets
        creds_dict = dict(st.secrets["connections"]["gsheets"])
        spreadsheet_url = creds_dict.pop("spreadsheet")
        
        # Connect to Google Sheets via gspread
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open_by_url(spreadsheet_url)
        worksheet = sh.sheet1
        
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return pd.DataFrame(columns=["log_date", "hours", "task_type", "notes"])
        
        # Ensure log_date is correctly ordered
        if 'log_date' in df.columns:
            df = df.sort_values(by='log_date', ascending=False)
        return df
    except Exception as e:
        # If the sheet doesn't exist yet, is empty, or errors out
        return pd.DataFrame(columns=["log_date", "hours", "task_type", "notes"])

def save_data(df):
    creds_dict = dict(st.secrets["connections"]["gsheets"])
    spreadsheet_url = creds_dict.pop("spreadsheet")
    
    gc = gspread.service_account_from_dict(creds_dict)
    sh = gc.open_by_url(spreadsheet_url)
    worksheet = sh.sheet1
    
    # Write the entire dataframe back to the sheet
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.fillna("").values.tolist())

# --- App Layout ---
st.title("📝 Meghan's NAMI Hours Log")

task_types = [
    "Admin/Email (A/E)", 
    "Outreach (O)", 
    "Meeting/Internal (MI)", 
    "Meeting/External (ME)", 
    "Conference/Education (EC)", 
    "Policy (P)", 
    "Programming", 
    "Other"
]

tab1, tab2, tab3 = st.tabs(["➕ Log Hours", "✏️ Edit Entries", "📄 Generate Invoice"])

# --- Tab 1: Log Hours ---
with tab1:
    st.header("Log New Task")
    
    if "form_key" not in st.session_state:
        st.session_state.form_key = 1
        
    with st.form(f"log_form_{st.session_state.form_key}"):
        log_date = st.date_input("Date", value=date.today())
        hours = st.number_input("Number of Hours", min_value=0.25, step=0.25, format="%f")
        task_type = st.selectbox("Task Type", task_types)
        notes = st.text_area("Notes (Optional)")
        
        submitted = st.form_submit_button("Save Entry", use_container_width=True)
        if submitted:
            new_row = pd.DataFrame([{
                "log_date": log_date.strftime("%Y-%m-%d"),
                "hours": hours,
                "task_type": task_type,
                "notes": notes
            }])
            df = load_data()
            updated_df = pd.concat([df, new_row], ignore_index=True)
            save_data(updated_df)
            st.success("✅ Hours logged successfully!")
            
    if st.button("➕ New Task (Clear Form)", use_container_width=True):
        st.session_state.form_key += 1
        st.rerun()

# --- Tab 2: Edit Entries ---
with tab2:
    st.header("Review & Edit Past Entries")
    st.info("Edit the cells directly and click 'Save Changes' below. To delete an entry, check the 'Delete' box on the left, then save.")
    
    df = load_data()
    
    if not df.empty:
        # Convert log_date to datetime for the data editor
        df['log_date'] = pd.to_datetime(df['log_date']).dt.date
        df.insert(0, "Delete", False)
        
        edited_df = st.data_editor(
            df,
            column_config={
                "Delete": st.column_config.CheckboxColumn("🗑️ Delete", default=False),
                "log_date": st.column_config.DateColumn("Date", required=True),
                "hours": st.column_config.NumberColumn("Hours", required=True, min_value=0.25, step=0.25),
                "task_type": st.column_config.SelectboxColumn("Task Type", options=task_types, required=True),
                "notes": st.column_config.TextColumn("Notes")
            },
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor"
        )
        
        if st.button("Save Changes", type="primary"):
            final_df = edited_df[~edited_df['Delete']].copy()
            final_df = final_df.drop(columns=['Delete'])
            
            # format dates back to string
            final_df['log_date'] = final_df['log_date'].astype(str)
            
            save_data(final_df)
            st.success("✅ Changes saved successfully!")
            st.rerun()
    else:
        st.write("No hours logged yet.")

# --- Tab 3: Generate Invoice ---
with tab3:
    st.header("Generate Monthly Invoice")
    
    df = load_data()
    if df.empty:
        st.warning("No data available to generate an invoice.")
    else:
        df['log_date'] = pd.to_datetime(df['log_date'])
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", df['log_date'].min().date())
        with col2:
            end_date = st.date_input("End Date", df['log_date'].max().date())
            
        rate_per_hour = st.number_input("Hourly Rate ($)", value=30.0, step=1.0)
        
        if st.button("Preview Invoice", type="primary"):
            # Filter data
            mask = (df['log_date'].dt.date >= start_date) & (df['log_date'].dt.date <= end_date)
            invoice_df = df.loc[mask]
            
            if invoice_df.empty:
                st.error("No records found in this date range.")
            else:
                total_hours = invoice_df['hours'].sum()
                total_due = total_hours * rate_per_hour
                month_str = start_date.strftime("%B %Y") if start_date.replace(day=1) == end_date.replace(day=1) else f"{start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')}"
                
                # Format data for the table - no grouping so notes are preserved
                summary_df = invoice_df.copy()
                summary_df['Date'] = summary_df['log_date'].dt.strftime('%m/%d/%Y')
                summary_df = summary_df.rename(columns={'hours': 'Time Worked', 'task_type': 'Tasks', 'notes': 'Notes'})
                summary_df['Notes'] = summary_df['Notes'].fillna("")
                summary_df = summary_df[['Date', 'Time Worked', 'Tasks', 'Notes']]
                summary_df = summary_df.sort_values(by='Date')
                
                # --- HTML Invoice Rendering ---
                invoice_html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
body {{
    font-family: Arial, sans-serif;
    color: black;
}}
.invoice-container {{
    width: 100%;
    max-width: 800px;
    margin: 0 auto;
}}
.invoice-header {{
    text-align: center;
    font-weight: bold;
    font-size: 20px;
    margin-bottom: 20px;
}}
.invoice-info-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 10px;
}}
.invoice-info-table th, .invoice-info-table td {{
    border: 1px solid black;
    padding: 8px;
    text-align: left;
}}
.invoice-info-table th {{
    width: 30%;
    text-transform: uppercase;
}}
.invoice-data-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 20px;
}}
.invoice-data-table th, .invoice-data-table td {{
    border: 1px solid black;
    padding: 8px;
    text-align: center;
}}
.invoice-data-table th {{
    background-color: #d3d3d3; /* Light grey header like the PDF */
}}
.invoice-data-table td:nth-child(3), .invoice-data-table td:nth-child(4) {{
    text-align: left; /* Keep tasks and notes left-aligned */
}}
@media print {{
    .no-print {{ display: none !important; }}
}}
</style>
</head>
<body>
<div class="invoice-container">
    <div class="invoice-header">NAMI Charlotte Contractor Monthly Invoice</div>
    
    <table class="invoice-info-table">
        <tr><th>NAME</th><td>Meghan Talbott</td></tr>
        <tr><th>TITLE</th><td>Advocacy Coordinator</td></tr>
        <tr><th>CELL PHONE</th><td>415-250-6936</td></tr>
        <tr><th>EMAIL ADDRESS</th><td>meghantalbott@namicharlotte.org</td></tr>
        <tr><th>ADDRESS</th><td>12231 Westbranch Pkwy, Davidson 28036</td></tr>
        <tr><th>MONTH</th><td>{month_str}</td></tr>
        <tr><th>HOURS WORKED</th><td>{total_hours}</td></tr>
        <tr><th>TOTAL DUE</th><td>${total_due:,.0f}</td></tr>
    </table>
    
    <p style="font-size: 14px;">*Payment will be made via direct deposit</p>
    
    <table class="invoice-data-table">
        <tr>
            <th style="text-align: left;">Date</th>
            <th>Time Worked</th>
            <th style="text-align: left;">Tasks</th>
            <th style="text-align: left;">Notes</th>
        </tr>
"""
                
                # Fill table rows
                current_date = None
                for _, row in summary_df.iterrows():
                    # Only print the date if it's the first task for that date
                    date_display = row['Date'] if row['Date'] != current_date else ""
                    current_date = row['Date']
                    
                    invoice_html += f"""
        <tr>
            <td style="text-align: left;">{date_display}</td>
            <td>{row['Time Worked']}</td>
            <td style="text-align: left;">{row['Tasks']}</td>
            <td style="text-align: left;">{row['Notes']}</td>
        </tr>
"""
                
                invoice_html += """
    </table>
    <br><br>
    <div class="no-print" style="text-align: center;">
        <button onclick="window.print()" style="padding: 10px 20px; font-size: 16px; cursor: pointer; background-color: #4CAF50; color: white; border: none; border-radius: 5px;">🖨️ Print Invoice</button>
    </div>
</div>
</body>
</html>
"""
                
                st.markdown("---")
                
                # Render using components.html which is immune to markdown parsing issues
                import streamlit.components.v1 as components
                components.html(invoice_html, height=800, scrolling=True)
                
                # Provide download button for bulletproof printing fallback
                st.info("If the Print button above doesn't work well, click Download below, open the downloaded file, and print it directly!")
                st.download_button(
                    label="💾 Download Invoice as HTML", 
                    data=invoice_html, 
                    file_name=f"NAMI_Invoice_{start_date.strftime('%Y_%m')}.html", 
                    mime="text/html"
                )

