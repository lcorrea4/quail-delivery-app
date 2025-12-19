

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import calendar

# --- Normalize store names for grouping ---
def normalize_store(name):
    if pd.isna(name):
        return ""
    name = name.lower().replace(" ", "")
    if "publix" in name:
        return "Publix"
    elif "sedano" in name:
        return "Sedanos"
    elif "fresco" in name:
        return "Fresco y Mas"
    else:
        return "Other"

# Abbreviate completed store names to match df_sheet["Name"]
def abbreviate_completed_id(store_id):
    store_id = store_id.strip().lower()
    if store_id.startswith("publix"):
        return "P" + store_id.replace("publix", "").strip().title().replace(" ", "")
    elif store_id.startswith("sedano") or store_id.startswith("sedano's"):
        return "S" + store_id.replace("sedano's", "").replace("sedanos", "").strip().title().replace(" ", "")
    elif store_id.startswith("fresco"):
        return "F" + store_id.replace("fresco y mas", "").strip().title().replace(" ", "")
    else:
        return store_id.title().replace(" ", "")

# Helper to calculate bucket
def get_bucket_date(visit_date):
    if pd.isna(visit_date):
        return None
    visit_date = pd.to_datetime(visit_date)
    day = visit_date.day
    bucket_day = (day // 5) * 5
    if bucket_day == 0:
        bucket_day = 5
    try:
        return visit_date.replace(day=bucket_day)
    except ValueError:
        next_month = (visit_date + pd.DateOffset(months=1)).replace(day=1)
        last_day = (next_month - pd.Timedelta(days=1)).day
        return visit_date.replace(day=last_day)

# --- Define cross-out function ---
def cross_out_stores(cell_value, completed_ids):
    if pd.isna(cell_value) or not isinstance(cell_value, str):
        return cell_value

    parts = cell_value.replace("<br>", ", ").split(",")
    crossed_parts = []
    for name in parts:
        name = name.strip()
        if any(store_id.strip().lower() in name.lower() for store_id in completed_ids):
            crossed_parts.append(f"<span style='text-decoration: line-through; color: #999;'>❌ {name}</span>")
        else:
            crossed_parts.append(name)

    # Wrap every 8 entries with line breaks
    wrapped = []
    for i in range(0, len(crossed_parts), 8):
        wrapped.append(", ".join(crossed_parts[i:i+8]))
    return "<br>".join(wrapped)

def abbreviate_store_name(name):
    if pd.isna(name):
        return name
    name = name.strip().lower()
    if "publix" in name:
        return "P" + name.replace("publix", "").strip().title().replace(" ", "")
    elif "sedano" in name:
        return "S" + name.replace("sedano's", "").replace("sedanos", "").strip().title().replace(" ", "")
    elif "fresco" in name:
        return "F" + name.replace("fresco y mas", "").strip().title().replace(" ", "")
    else:
        return name.title().replace(" ", "")

def wrap_text_after_n_commas(text, limit=8):
    if pd.isna(text) or not isinstance(text, str):
        return text
    items = [item.strip() for item in text.split(",")]
    wrapped = []
    for i in range(0, len(items), limit):
        wrapped.append(", ".join(items[i:i+limit]))
    return "<br>".join(wrapped)

# --- Google Sheet Setup ---
# Define scope and authenticate
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
# spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
try:
    spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
except gspread.exceptions.APIError as e:
    print("Google Sheets API Error:", e.response.text)

sheet = spreadsheet.worksheet("Sheet1")

# Create a second worksheet to track completed store numbers
try:
    sheet_completed = spreadsheet.worksheet("Completed")
except gspread.exceptions.WorksheetNotFound:
    sheet_completed = spreadsheet.add_worksheet(title="Completed", rows="100", cols="20")

st.set_page_config(layout="wide")
st.title("🥚 Quail Egg Delivery Manager")

# Load completed store numbers
try:
    completed_vals = sheet_completed.get_all_values()
    completed_set = set()
    if completed_vals:
        for row in completed_vals:
            for item in row:
                if item.strip():
                    completed_set.add(item.strip())
    else:
        completed_set = set()
except Exception as e:
    st.error(f"Error loading completed stores: {e}")
    completed_set = set()

# Open and read the file
with open("store_list.txt", "r") as file:
    raw_store_list = file.read()

with st.expander("📤 Upload Excel File", expanded=False):
    uploaded_file = st.file_uploader("Upload your Excel File", type=["xlsx"])
    
    if uploaded_file:
        try:
            sheet_completed.clear()
            
            # --- Load and slice raw data ---
            raw_df = pd.read_excel(uploaded_file, sheet_name="Sheet1", header=None)
    
            start_row = raw_df[2][raw_df[2] == "QUAIL EGGS X 10 (QUAIL EGGS X 10)"].index[0] + 1
            end_row = raw_df[2][raw_df[2] == "Total QUAIL EGGS X 10 (QUAIL EGGS X 10)"].index[0] - 1
            target_cols = [5, 7, 9, 11, 13, 15, 17, 19, 21]
            df_hist = raw_df.loc[start_row:end_row, target_cols].copy()
    
            df_hist.columns = [
                "Type", "Date", "Num", "Memo", "Name",
                "Qty", "Sales Price", "Amount", "Balance"
            ]

            store_days = []
            for line in raw_store_list.strip().splitlines():
                cleaned = line.lstrip("- ").strip()
                if " - " in cleaned:
                    store_name, days = cleaned.rsplit(" - ", 1)
                    store_days.append((store_name.strip(), int(days.strip())))
            days_df = pd.DataFrame(store_days, columns=["Name", "depletion_days_estimate"])
    
            # --- Merge and Upload ---
            df_hist = df_hist.merge(days_df, on="Name", how="left")
            sheet.clear()
            set_with_dataframe(sheet, df_hist)
    
            st.success("✅ Data cleaned and saved to Google Sheets successfully!")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# --- View Google Sheet Section ---
with st.expander("📄 View Current Google Sheet Data", expanded=False):
    try:
        df_sheet = get_as_dataframe(sheet).dropna(how="all")
        if not df_sheet.empty:
            st.dataframe(df_sheet, use_container_width=True)
        else:
            st.info("ℹ️ Google Sheet is currently empty.")
    except Exception as e:
        st.error(f"❌ Error loading Google Sheet: {e}")

# --- Compute Visit Date ---
df_sheet["Date"] = pd.to_datetime(df_sheet["Date"], errors="coerce")
df_sheet["Visit Date"] = df_sheet["Date"] + pd.to_timedelta(df_sheet["depletion_days_estimate"], unit="D")
df_sheet["Name2"] = df_sheet["Name"].apply(abbreviate_store_name)


with st.expander("Agenda Data", expanded = False):
    st.dataframe(df_sheet, use_container_width=True)

# Add these at the top of your script (with other session state initializations)
if 'moved_stores_history' not in st.session_state:
    st.session_state.moved_stores_history = []
if 'completed_stores_history' not in st.session_state:
    st.session_state.completed_stores_history = []

# --- Enhanced Move Stores Section with Undo ---
st.subheader("🔄 Reschedule Stores")

# Get unique upcoming bucket dates (grouped by week)
df_sheet["bucket_date"] = df_sheet["Visit Date"].apply(get_bucket_date)
bucket_dates = sorted(df_sheet["bucket_date"].dropna().unique())

# ✅ Compute the *current* bucket (e.g., 12/15 if today is 12/16)
today = pd.Timestamp(datetime.today().date())
today_bucket_date = get_bucket_date(today)

# ✅ Ensure current bucket is in the list, even if no stores are there yet
if today_bucket_date not in bucket_dates:
    bucket_dates = sorted(list(bucket_dates) + [today_bucket_date])

# ✅ Allow moving to *current* bucket and future buckets
future_buckets = [d for d in bucket_dates if d >= today_bucket_date]


# Input method selection
input_method = st.radio("Select input method:", 
                       ["Text Input", "Multiselect"], 
                       key="move_input_method")

stores_to_move = []
if input_method == "Text Input":
    move_input = st.text_input(
        "Enter store numbers (comma-separated, e.g., S11, P5):",
        key="move_stores_text"
    )
    if move_input.strip():
        stores_to_move = [x.strip().upper() for x in move_input.split(",") if x.strip()]
else:
    stores_to_move = st.multiselect(
        "Select stores to reschedule:",
        options=df_sheet["Name2"].unique(),
        format_func=lambda x: f"{x} (Current: {df_sheet[df_sheet['Name2']==x]['bucket_date'].iloc[0].strftime('%b %d')})",
        key="move_stores_multiselect"
    )

if stores_to_move:
    target_bucket = st.selectbox(
        "Move to which delivery week?",
        options=future_buckets,  # Now includes 6/20
        format_func=lambda d: f"{d.strftime('%b %d')} (Week {d.isocalendar()[1]})",
        key="target_bucket_select"
    )
    
    # Visual confirmation
    current_bucket = df_sheet[df_sheet["Name2"]==stores_to_move[0]]["bucket_date"].iloc[0]
    # st.write(f"Moving from {current_bucket.strftime('%b %d')} → {target_bucket.strftime('%b %d')}")
    
    if st.button("🔀 Reschedule Stores", key="move_stores_button"):
        moved_stores = []
        not_found_stores = []
        undo_info = []  # Store info for undo
        
        # Make a copy of the dataframe to modify
        df_to_update = df_sheet.copy()
        
        for store in stores_to_move:
            # Find the store in the dataframe (case-insensitive match)
            store_mask = df_to_update["Name2"].str.strip().str.upper() == store.upper()
            
            if store_mask.any():
                current_date = df_to_update.loc[store_mask, "Visit Date"].iloc[0]
                days_to_add = (target_bucket - current_date).days
                
                # Store original days for undo
                original_days = df_to_update.loc[store_mask, "depletion_days_estimate"].values[0]
                undo_info.append({
                    'store': store,
                    'original_days': original_days,
                    'new_days': original_days + days_to_add,
                    'timestamp': datetime.now()
                })
                
                # Update depletion days
                df_to_update.loc[store_mask, "depletion_days_estimate"] += days_to_add
                moved_stores.append(store)
            else:
                not_found_stores.append(store)
        
        if not_found_stores:
            st.warning(f"Stores not found: {', '.join(not_found_stores)}")
        
        if moved_stores:
            # Save undo info
            st.session_state.moved_stores_history.append(undo_info)
            
            # Update the Google Sheet with the modified data
            try:
                sheet.clear()
                set_with_dataframe(sheet, df_to_update)
                st.success(f"✅ Moved {len(moved_stores)} stores to {target_bucket.strftime('%b %d')}")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to update Google Sheet: {e}")
                st.error("Please try again or check your connection.")

# --- Undo Section (Updated with Unique Keys) ---
if st.session_state.get('moved_stores_history'):
    st.subheader("↩️ Undo Actions")
    
    # Create unique keys based on timestamp
    last_move = st.session_state.moved_stores_history[-1]
    undo_key = f"undo_move_{last_move[0]['timestamp'].timestamp()}"
    
    if st.button(
        "Undo Last Move",
        disabled=not st.session_state.moved_stores_history,
        key=undo_key  # Unique key based on timestamp
    ):
        df_to_update = df_sheet.copy()
        
        for move in last_move:
            store_mask = df_to_update["Name2"].str.strip().str.upper() == move['store'].upper()
            df_to_update.loc[store_mask, "depletion_days_estimate"] = move['original_days']
        
        try:
            sheet.clear()
            set_with_dataframe(sheet, df_to_update)
            st.session_state.moved_stores_history.pop()
            st.success(f"↩️ Restored original schedule for {len(last_move)} stores")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to undo move: {e}")

st.subheader("✅ Store Delivery")

# --- Updated Completed Stores Section ---
completed_input = st.text_input(
    "✅ Enter completed store numbers (comma-separated):",
    key="completed_stores_input"
)

if st.button("💾 Save Completed Stores", key="save_completed_button"):
    new_ids = [x.strip() for x in completed_input.split(",") if x.strip()]
    try:
        # Access or create "Completed" sheet
        try:
            completed_sheet = spreadsheet.worksheet("Completed")
        except gspread.exceptions.WorksheetNotFound:
            completed_sheet = spreadsheet.add_worksheet(title="Completed", rows="100", cols="1")
        
        # Load existing completed IDs from sheet
        existing_df = get_as_dataframe(completed_sheet).dropna(how="all")
        existing_ids = set()
        if not existing_df.empty and "store_id" in existing_df.columns:
            existing_ids = set(existing_df["store_id"].astype(str).str.strip())
        
        # Store previous state for undo
        st.session_state.completed_stores_history.append({
            'added_stores': new_ids,
            'previous_stores': list(existing_ids),
            'timestamp': datetime.now()
        })
        
        # Combine existing and new IDs, avoiding duplicates
        combined_ids = sorted(existing_ids.union(new_ids))
        
        # Save combined list back to sheet
        completed_sheet.clear()
        combined_df = pd.DataFrame({"store_id": combined_ids})
        set_with_dataframe(completed_sheet, combined_df)
                                                           
        st.success("✅ Completed stores saved!")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Failed to save completed stores: {e}")

# --- UNDO Section ---
st.subheader("↩️ Undo Actions")
col1, col2 = st.columns(2)

with col1:
    if st.button("Undo Last Move", 
                disabled=not st.session_state.moved_stores_history,
                key="undo_move_button"):
        last_move = st.session_state.moved_stores_history.pop()
        df_to_update = df_sheet.copy()
        
        for move in last_move:
            store_mask = df_to_update["Name2"].str.strip().str.upper() == move['store'].upper()
            df_to_update.loc[store_mask, "depletion_days_estimate"] = move['original_days']
        
        try:
            sheet.clear()
            set_with_dataframe(sheet, df_to_update)
            moved_stores = [m['store'] for m in last_move]
            st.success(f"↩️ Undid move for: {', '.join(moved_stores)}")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to undo move: {e}")

with col2:
    if st.button("Undo Last Completion", 
                disabled=not st.session_state.completed_stores_history,
                key="undo_completed_button"):
        last_completion = st.session_state.completed_stores_history.pop()
        try:
            completed_sheet = spreadsheet.worksheet("Completed")
            completed_sheet.clear()
            restored_df = pd.DataFrame({"store_id": last_completion['previous_stores']})
            set_with_dataframe(completed_sheet, restored_df)
            st.success(f"↩️ Undid completion of: {', '.join(last_completion['added_stores'])}")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to undo completion: {e}")

# --- Load completed stores from "Completed" sheet ---
try:
    completed_sheet = spreadsheet.worksheet("Completed")
    completed_df = get_as_dataframe(completed_sheet).dropna(how="all")
    completed_ids = completed_df["store_id"].astype(str).str.strip().tolist()
except Exception:
    completed_ids = []

# Normalize all completed IDs
completed_ids = [abbreviate_completed_id(x) for x in completed_ids]
    
df_sheet["bucket_date"] = df_sheet["Visit Date"].apply(get_bucket_date)

# --- Filter future or current buckets only ---
today = pd.Timestamp(datetime.today().date())
today_day = today.day
today_bucket_day = (today_day // 5) * 5
if today_bucket_day == 0:
    today_bucket_day = 5
today_bucket_date = today.replace(day=today_bucket_day)

df_sheet = df_sheet[df_sheet["bucket_date"] >= today_bucket_date]

df_sheet["store_group"] = df_sheet["Name"].apply(normalize_store)
df_sheet["Name"] = df_sheet["Name"].apply(abbreviate_store_name)

# --- Build 5-day agenda DataFrame ---
agenda_data = []
for bucket_date, group in df_sheet.groupby("bucket_date"):
    row = {
        "5-day-bucket-date": bucket_date.strftime("%-m/%-d"),  # e.g. 6/15
        "Publix": ", ".join(group[group["store_group"] == "Publix"]["Name"].unique()),
        "Sedanos": ", ".join(group[group["store_group"] == "Sedanos"]["Name"].unique()),
        "Fresco y Mas": ", ".join(group[group["store_group"] == "Fresco y Mas"]["Name"].unique()),
    }
    agenda_data.append(row)

agenda_df = pd.DataFrame(agenda_data)

# --- Apply wrapping and crossing out ---
for col in ["Publix", "Sedanos", "Fresco y Mas"]:
    if col in agenda_df.columns:
        agenda_df[col] = agenda_df[col].apply(lambda x: cross_out_stores(x, completed_ids))
        agenda_df[col] = agenda_df[col].apply(lambda x: wrap_text_after_n_commas(x, limit=8))

# Convert DataFrame to HTML
agenda_html = agenda_df.to_html(escape=False, index=False)

# Display as HTML in Streamlit
st.markdown("### 📅 5-Day Delivery Agenda!")
st.markdown(agenda_html, unsafe_allow_html=True)
