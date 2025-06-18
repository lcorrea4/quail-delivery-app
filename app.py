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
spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
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

with st.expander("Agenda Data", expanded = False):
    st.dataframe(df_sheet, use_container_width=True)

completed_input = st.text_input("✅ Enter completed store numbers (comma-separated):")

if st.button("💾 Save Completed Stores"):
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
        
        # Combine existing and new IDs, avoiding duplicates
        combined_ids = sorted(existing_ids.union(new_ids))
        
        # Save combined list back to sheet
        completed_sheet.clear()
        combined_df = pd.DataFrame({"store_id": combined_ids})
        set_with_dataframe(completed_sheet, combined_df)
                                                           
        st.success("✅ Completed stores saved!")
    except Exception as e:
        st.error(f"❌ Failed to save completed stores: {e}")

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
st.markdown("### 📅 5-Day Delivery Agenda")
st.markdown(agenda_html, unsafe_allow_html=True)























# import streamlit as st
# import pandas as pd
# from datetime import datetime, timedelta
# import gspread
# from oauth2client.service_account import ServiceAccountCredentials
# from gspread_dataframe import get_as_dataframe, set_with_dataframe
# import json
# from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
# import calendar

# # --- Normalize store names for grouping ---
# def normalize_store(name):
#     if pd.isna(name):
#         return ""
#     name = name.lower().replace(" ", "")
#     if "publix" in name:
#         return "Publix"
#     elif "sedano" in name:
#         return "Sedanos"
#     elif "fresco" in name:
#         return "Fresco y Mas"
#     else:
#         return "Other"

# # Abbreviate completed store names to match df_sheet["Name"]
# def abbreviate_completed_id(store_id):
#     store_id = store_id.strip().lower()
#     if store_id.startswith("publix"):
#         return "P" + store_id.replace("publix", "").strip().title().replace(" ", "")
#     elif store_id.startswith("sedano") or store_id.startswith("sedano's"):
#         return "S" + store_id.replace("sedano's", "").replace("sedanos", "").strip().title().replace(" ", "")
#     elif store_id.startswith("fresco"):
#         return "F" + store_id.replace("fresco y mas", "").strip().title().replace(" ", "")
#     else:
#         return store_id.title().replace(" ", "")

# # Helper to calculate bucket
# def get_bucket_date(visit_date):
#     if pd.isna(visit_date):
#         return None
#     visit_date = pd.to_datetime(visit_date)
#     day = visit_date.day
#     bucket_day = (day // 5) * 5
#     if bucket_day == 0:
#         bucket_day = 5
#     try:
#         return visit_date.replace(day=bucket_day)
#     except ValueError:
#         next_month = (visit_date + pd.DateOffset(months=1)).replace(day=1)
#         last_day = (next_month - pd.Timedelta(days=1)).day
#         return visit_date.replace(day=last_day)

# # --- Define cross-out function ---
# def cross_out_stores(cell_value, completed_ids):
#     if pd.isna(cell_value) or not isinstance(cell_value, str):
#         return cell_value

#     parts = cell_value.replace("<br>", ", ").split(",")
#     crossed_parts = []
#     for name in parts:
#         name = name.strip()
#         if any(store_id.strip().lower() in name.lower() for store_id in completed_ids):
#             crossed_parts.append(f"<span style='text-decoration: line-through; color: #999;'>❌ {name}</span>")
#         else:
#             crossed_parts.append(name)

#     # Wrap every 8 entries with line breaks
#     wrapped = []
#     for i in range(0, len(crossed_parts), 8):
#         wrapped.append(", ".join(crossed_parts[i:i+8]))
#     return "<br>".join(wrapped)

# def abbreviate_store_name(name):
#     if pd.isna(name):
#         return name
#     name = name.strip().lower()
#     if "publix" in name:
#         return "P" + name.replace("publix", "").strip().title().replace(" ", "")
#     elif "sedano" in name:
#         return "S" + name.replace("sedano's", "").replace("sedanos", "").strip().title().replace(" ", "")
#     elif "fresco" in name:
#         return "F" + name.replace("fresco y mas", "").strip().title().replace(" ", "")
#     else:
#         return name.title().replace(" ", "")


# def wrap_text_after_n_commas(text, limit=8):
#     if pd.isna(text) or not isinstance(text, str):
#         return text
#     items = [item.strip() for item in text.split(",")]
#     wrapped = []
#     for i in range(0, len(items), limit):
#         wrapped.append(", ".join(items[i:i+limit]))
#     return "<br>".join(wrapped)

# def apply_unicode_strikethrough(text):
#     return ''.join(char + '\u0336' for char in text)

# def draw_calendar(delivery_df):
#     st.subheader("🗓️ Delivery Calendar")

#     # Make sure Date is datetime
#     delivery_df["Date"] = pd.to_datetime(delivery_df["Date"], errors="coerce")

#     # User selects month and year
#     today = date.today()
#     selected_year = st.selectbox("Select Year", sorted(delivery_df["Date"].dt.year.dropna().unique()), index=0)
#     selected_month = st.selectbox("Select Month", list(calendar.month_name)[1:], index=today.month - 1)

#     month_number = list(calendar.month_name).index(selected_month)
#     filtered_df = delivery_df[
#         (delivery_df["Date"].dt.year == selected_year) &
#         (delivery_df["Date"].dt.month == month_number)
#     ]

#     # Build day-to-store map
#     day_to_stores = filtered_df.groupby(delivery_df["Date"].dt.day)["Name"].apply(list).to_dict()

#     # Draw the calendar
#     st.markdown(f"### {selected_month} {selected_year}")
#     cal = calendar.monthcalendar(selected_year, month_number)

#     for week in cal:
#         cols = st.columns(7)
#         for i, day in enumerate(week):
#             if day == 0:
#                 cols[i].empty()
#             else:
#                 label = f"{day}"
#                 if day in day_to_stores:
#                     stores = "\n".join(day_to_stores[day])
#                     cols[i].markdown(f"**{label}** 🟢")
#                     with cols[i].expander("Details"):
#                         for store in day_to_stores[day]:
#                             st.write(f"- {store}")
#                 else:
#                     cols[i].markdown(f"{label}")
                    

# # --- Function to Calculate Dates ---
# def calculate_delivery_dates(df):
#     df['last_delivery_date'] = pd.to_datetime(df['last_delivery_date'], errors='coerce')
#     df['expected_empty_date'] = df['last_delivery_date'] + pd.to_timedelta(df['depletion_days_estimate'], unit='D')
#     df['days_until_empty'] = (df['expected_empty_date'] - datetime.today()).dt.days
#     return df

# # Define custom 5-day bucket function
# def get_5day_bucket(date):
#     # Calculate the starting day for the bucket (in groups of 5)
#     start_day = ((date.day - 1) // 5) * 5 + 1
#     # Calculate the last day of the bucket ensuring we don't exceed the month's days
#     end_day = min(start_day + 4, pd.Period(date, freq='M').days_in_month)
#     start_date = date.replace(day=start_day)
#     end_date = date.replace(day=end_day)
#     label = f"{start_date.strftime('%b %d')}–{end_date.strftime('%d')}"
#     return f"{label} ({date.strftime('%Y')})"

# def get_5day_bucket2(date_val):
#     """
#     Takes a datetime and returns a tuple (bucket_start_date, bucket_label)
#     bucket_start_date = datetime.date used for sorting
#     bucket_label = string like 'Jun 15 – Jun 19'
#     """
#     if pd.isnull(date_val):
#         return (None, "Unknown")

#     # Force date only
#     date_val = pd.to_datetime(date_val).date()

#     # Start buckets from June 15, 2025 (adjust if you want dynamic start)
#     start = date.today()  # Use today's date as rolling start
#     days_since_start = (date_val - start).days
#     if days_since_start < 0:
#         # If date is before today, just assign to today's bucket
#         bucket_start = start
#     else:
#         bucket_start = start + timedelta(days=(days_since_start // 5) * 5)

#     bucket_end = bucket_start + timedelta(days=4)
#     bucket_label = f"{bucket_start.strftime('%b %d')} – {bucket_end.strftime('%b %d')}"

#     return (bucket_start, bucket_label)


# # --- Google Sheet Setup ---
# # Define scope and authenticate
# scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
# creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
# client = gspread.authorize(creds)
# spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
# sheet = spreadsheet.worksheet("Sheet1")

# # Create a second worksheet to track completed store numbers
# try:
#     sheet_completed = spreadsheet.worksheet("Completed")
# except gspread.exceptions.WorksheetNotFound:
#     sheet_completed = spreadsheet.add_worksheet(title="Completed", rows="100", cols="20")


# st.set_page_config(layout="wide")

# st.title("🥚 Quail Egg Delivery Manager")


# # Load completed store numbers
# try:
#     completed_vals = sheet_completed.get_all_values()
#     completed_set = set()
#     if completed_vals:
#         for row in completed_vals:
#             for item in row:
#                 if item.strip():
#                     completed_set.add(item.strip())
#     else:
#         completed_set = set()
# except Exception as e:
#     st.error(f"Error loading completed stores: {e}")
#     completed_set = set()

# # Open and read the file
# with open("store_list.txt", "r") as file:
#     raw_store_list = file.read()




# with st.expander("📤 Upload Excel File", expanded=False):
#     uploaded_file = st.file_uploader("Upload your Excel File", type=["xlsx"])
    
#     if uploaded_file:
#         try:
#             sheet_completed.clear()
            
#             # --- Load and slice raw data ---
#             raw_df = pd.read_excel(uploaded_file, sheet_name="Sheet1", header=None)
    
#             start_row = raw_df[2][raw_df[2] == "QUAIL EGGS X 10 (QUAIL EGGS X 10)"].index[0] + 1
#             end_row = raw_df[2][raw_df[2] == "Total QUAIL EGGS X 10 (QUAIL EGGS X 10)"].index[0] - 1
#             target_cols = [5, 7, 9, 11, 13, 15, 17, 19, 21]
#             df_hist = raw_df.loc[start_row:end_row, target_cols].copy()
    
#             df_hist.columns = [
#                 "Type", "Date", "Num", "Memo", "Name",
#                 "Qty", "Sales Price", "Amount", "Balance"
#             ]

    
#             store_days = []
#             for line in raw_store_list.strip().splitlines():
#                 cleaned = line.lstrip("- ").strip()
#                 if " - " in cleaned:
#                     store_name, days = cleaned.rsplit(" - ", 1)
#                     store_days.append((store_name.strip(), int(days.strip())))
#             days_df = pd.DataFrame(store_days, columns=["Name", "depletion_days_estimate"])
    
#             # --- Merge and Upload ---
#             df_hist = df_hist.merge(days_df, on="Name", how="left")
#             sheet.clear()
#             set_with_dataframe(sheet, df_hist)
    
#             st.success("✅ Data cleaned and saved to Google Sheets successfully!")
#         except Exception as e:
#             st.error(f"❌ Error: {e}")

# # --- View Google Sheet Section ---
# with st.expander("📄 View Current Google Sheet Data", expanded=False):
#     try:
#         df_sheet = get_as_dataframe(sheet).dropna(how="all")
#         if not df_sheet.empty:
#             st.dataframe(df_sheet, use_container_width=True)
#         else:
#             st.info("ℹ️ Google Sheet is currently empty.")
#     except Exception as e:
#         st.error(f"❌ Error loading Google Sheet: {e}")




# # --- Visit Date & 5-Day Bucket Agenda ---

# # --- Compute Visit Date ---
# df_sheet["Date"] = pd.to_datetime(df_sheet["Date"], errors="coerce")
# df_sheet["Visit Date"] = df_sheet["Date"] + pd.to_timedelta(df_sheet["depletion_days_estimate"], unit="D")

# with st.expander("Agenda Data", expanded = False):
#     st.dataframe(df_sheet, use_container_width=True)



# completed_input = st.text_input("✅ Enter completed store numbers (comma-separated):")

# if st.button("💾 Save Completed Stores"):
#     new_ids = [x.strip() for x in completed_input.split(",") if x.strip()]
#     try:
#         # Access or create "Completed" sheet
#         try:
#             completed_sheet = spreadsheet.worksheet("Completed")
#         except gspread.exceptions.WorksheetNotFound:
#             completed_sheet = spreadsheet.add_worksheet(title="Completed", rows="100", cols="1")
        
#         # Load existing completed IDs from sheet
#         existing_df = get_as_dataframe(completed_sheet).dropna(how="all")
#         existing_ids = set()
#         if not existing_df.empty and "store_id" in existing_df.columns:
#             existing_ids = set(existing_df["store_id"].astype(str).str.strip())
        
#         # Combine existing and new IDs, avoiding duplicates
#         combined_ids = sorted(existing_ids.union(new_ids))
        
#         # Save combined list back to sheet
#         completed_sheet.clear()
#         combined_df = pd.DataFrame({"store_id": combined_ids})
#         set_with_dataframe(completed_sheet, combined_df)

                                                           
#         st.success("✅ Completed stores saved!")
#     except Exception as e:
#         st.error(f"❌ Failed to save completed stores: {e}")


# # --- Load completed stores from "Completed" sheet ---
# try:
#     completed_sheet = spreadsheet.worksheet("Completed")
#     completed_df = get_as_dataframe(completed_sheet).dropna(how="all")
#     completed_ids = completed_df["store_id"].astype(str).str.strip().tolist()
# except Exception:
#     completed_ids = []


# # Normalize all completed IDs
# completed_ids = [abbreviate_completed_id(x) for x in completed_ids]

    
# df_sheet["bucket_date"] = df_sheet["Visit Date"].apply(get_bucket_date)

# # --- Filter future or current buckets only ---
# today = pd.Timestamp(datetime.today().date())
# today_day = today.day
# today_bucket_day = (today_day // 5) * 5
# if today_bucket_day == 0:
#     today_bucket_day = 5
# today_bucket_date = today.replace(day=today_bucket_day)

# df_sheet = df_sheet[df_sheet["bucket_date"] >= today_bucket_date]

# df_sheet["store_group"] = df_sheet["Name"].apply(normalize_store)

# df_sheet["Name"] = df_sheet["Name"].apply(abbreviate_store_name)


# # --- Build 5-day agenda DataFrame ---
# agenda_data = []
# for bucket_date, group in df_sheet.groupby("bucket_date"):
#     row = {
#         "5-day-bucket-date": bucket_date.strftime("%-m/%-d"),  # e.g. 6/15
#         "Publix": ", ".join(group[group["store_group"] == "Publix"]["Name"].unique()),
#         "Sedanos": ", ".join(group[group["store_group"] == "Sedanos"]["Name"].unique()),
#         "Fresco y Mas": ", ".join(group[group["store_group"] == "Fresco y Mas"]["Name"].unique()),
#     }
#     agenda_data.append(row)

# agenda_df = pd.DataFrame(agenda_data)




# # --- Apply wrapping and crossing out ---
# for col in ["Publix", "Sedanos", "Fresco y Mas"]:
#     if col in agenda_df.columns:
#         agenda_df[col] = agenda_df[col].apply(lambda x: cross_out_stores(x, completed_ids))
#         agenda_df[col] = agenda_df[col].apply(lambda x: wrap_text_after_n_commas(x, limit=8))



# # Convert DataFrame to HTML
# agenda_html = agenda_df.to_html(escape=False, index=False)

# # Display as HTML in Streamlit
# st.markdown("### 📅 5-Day Delivery Agenda")
# st.markdown(agenda_html, unsafe_allow_html=True)
