import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# Normalize completed store IDs (example, adapt if needed)
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

# 5-day bucket date function
def get_bucket_date(visit_date):
    if pd.isna(visit_date):
        return pd.NaT
    visit_date = pd.to_datetime(visit_date).date()
    anchor = datetime(2025, 5, 31).date()
    delta_days = (visit_date - anchor).days
    bucket_offset = (delta_days // 5) * 5
    bucket_date = anchor + timedelta(days=bucket_offset)
    return pd.Timestamp(bucket_date)

# Setup Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
sheet = spreadsheet.worksheet("Sheet1")

try:
    sheet_completed = spreadsheet.worksheet("Completed")
except gspread.exceptions.WorksheetNotFound:
    sheet_completed = spreadsheet.add_worksheet(title="Completed", rows="100", cols="20")

st.set_page_config(layout="wide")
st.title("🥚 Quail Egg Delivery Manager")

# Load df_sheet
df_sheet = get_as_dataframe(sheet).dropna(how="all")
if df_sheet.empty:
    st.warning("⚠️ No delivery data available in Google Sheet yet.")
else:
    df_sheet["Date"] = pd.to_datetime(df_sheet["Date"], errors="coerce")
    df_sheet["Visit Date"] = pd.to_datetime(df_sheet["Visit Date"], errors="coerce")
    df_sheet["bucket_date"] = df_sheet["Visit Date"].apply(get_bucket_date)
    df_sheet["store_group"] = df_sheet["Name"].apply(normalize_store)
    df_sheet["Name"] = df_sheet["Name"].apply(abbreviate_store_name)

completed_input = st.text_input("✅ Enter completed store numbers (comma-separated):")
defer_toggle = st.checkbox("🔁 Defer store(s) to next 5-day bucket?")

if st.button("💾 Save Completed Stores"):
    new_ids = [x.strip() for x in completed_input.split(",") if x.strip()]
    try:
        today = pd.Timestamp(datetime.today().date())
        today_bucket = get_bucket_date(today)

        if defer_toggle:
            error_stores = []
            for store_id in new_ids:
                store_id = store_id.strip()
                match_idx = df_sheet[
                    (df_sheet["Name"] == abbreviate_completed_id(store_id)) &
                    (df_sheet["bucket_date"] == today_bucket)
                ].index

                if not match_idx.empty:
                    current_visit = df_sheet.loc[match_idx[0], "Visit Date"]
                    if pd.notna(current_visit):
                        new_visit = current_visit + timedelta(days=5)
                        df_sheet.at[match_idx[0], "Visit Date"] = new_visit
                        df_sheet.at[match_idx[0], "bucket_date"] = get_bucket_date(new_visit)
                else:
                    error_stores.append(store_id)

            if error_stores:
                st.error(f"❌ These stores were not found in the current 5-day bucket ({today_bucket.strftime('%-m/%-d')}): {', '.join(error_stores)}")
            else:
                sheet.clear()
                set_with_dataframe(sheet, df_sheet)
                st.success("✅ Store(s) deferred to next 5-day bucket.")

                # Reload df_sheet
                df_sheet = get_as_dataframe(sheet).dropna(how="all")
                df_sheet["Date"] = pd.to_datetime(df_sheet["Date"], errors="coerce")
                df_sheet["Visit Date"] = pd.to_datetime(df_sheet["Visit Date"], errors="coerce")
                df_sheet["bucket_date"] = df_sheet["Visit Date"].apply(get_bucket_date)
                df_sheet["store_group"] = df_sheet["Name"].apply(normalize_store)
                df_sheet["Name"] = df_sheet["Name"].apply(abbreviate_store_name)
        else:
            # Save completed stores normally
            try:
                completed_sheet = spreadsheet.worksheet("Completed")
            except gspread.exceptions.WorksheetNotFound:
                completed_sheet = spreadsheet.add_worksheet(title="Completed", rows="100", cols="1")

            existing_df = get_as_dataframe(completed_sheet).dropna(how="all")
            existing_ids = set()
            if not existing_df.empty and "store_id" in existing_df.columns:
                existing_ids = set(existing_df["store_id"].astype(str).str.strip())

            combined_ids = sorted(existing_ids.union(new_ids))
            completed_sheet.clear()
            combined_df = pd.DataFrame({"store_id": combined_ids})
            set_with_dataframe(completed_sheet, combined_df)

            st.success("✅ Completed stores saved!")

        # Refresh df_sheet after changes
        df_sheet = get_as_dataframe(sheet).dropna(how="all")
        df_sheet["Date"] = pd.to_datetime(df_sheet["Date"], errors="coerce")
        df_sheet["Visit Date"] = pd.to_datetime(df_sheet["Visit Date"], errors="coerce")
        df_sheet["bucket_date"] = df_sheet["Visit Date"].apply(get_bucket_date)
        df_sheet["store_group"] = df_sheet["Name"].apply(normalize_store)
        df_sheet["Name"] = df_sheet["Name"].apply(abbreviate_store_name)

    except Exception as e:
        st.error(f"❌ Failed to save: {e}")

# DEBUG output - bucket dates after reload
st.write("### Bucket Dates after reload")
st.write(df_sheet[["Name", "Visit Date", "bucket_date"]])

# Filter df_sheet for current and next bucket (to include deferred stores)
today = pd.Timestamp(datetime.today().date())
current_bucket = get_bucket_date(today)
next_bucket = current_bucket + timedelta(days=5)

st.write("Current bucket:", current_bucket)
st.write("Next bucket:", next_bucket)
st.write("All bucket_dates in df_sheet:")
st.write(df_sheet["bucket_date"].drop_duplicates().sort_values())

mask = df_sheet["bucket_date"].isin([current_bucket, next_bucket])
filtered_df = df_sheet[mask]

st.write("Filtered df for agenda:")
st.write(filtered_df)

if filtered_df.empty:
    st.warning("⚠️ No delivery data available for current or next bucket.")
else:
    agenda_data = []
    for bucket_date, group in filtered_df.groupby("bucket_date"):
        row = {
            "5-day-bucket-date": bucket_date.strftime("%-m/%-d"),
            "Publix": ", ".join(group[group["store_group"] == "Publix"]["Name"].unique()),
            "Sedanos": ", ".join(group[group["store_group"] == "Sedanos"]["Name"].unique()),
            "Fresco y Mas": ", ".join(group[group["store_group"] == "Fresco y Mas"]["Name"].unique()),
        }
        agenda_data.append(row)

    agenda_df = pd.DataFrame(agenda_data)
    agenda_html = agenda_df.to_html(escape=False, index=False)
    st.markdown("### 📅 5-Day Delivery Agenda")
    st.markdown(agenda_html, unsafe_allow_html=True)
