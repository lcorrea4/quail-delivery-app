
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import json
from io import StringIO


# Define scope
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Use the secrets directly as a dict
creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

# Authorize and access the spreadsheet
client = gspread.authorize(creds)

spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")


sheet = spreadsheet.worksheet("Sheet1")


def calculate_delivery_dates(df):
    df['last_delivery_date'] = pd.to_datetime(df['last_delivery_date'], errors='coerce')
    df['expected_empty_date'] = df['last_delivery_date'] + pd.to_timedelta(df['depletion_days_estimate'], unit='D')
    df['days_until_empty'] = (df['expected_empty_date'] - datetime.today()).dt.days
    return df
    
df = get_as_dataframe(sheet).dropna(how='all')
df = calculate_delivery_dates(df)

# Load dataframe once on app start and save to session state
if "df" not in st.session_state:
    df = get_as_dataframe(sheet).dropna(how='all')
    df = calculate_delivery_dates(df)
    st.session_state.df = df
else:
    df = st.session_state.df


# --- UI ---
st.title("📦 Quail Egg Delivery Tracker")

# Priority list
st.subheader("🚨 Stores Needing Delivery Soon")
priority_df = df[df['days_until_empty'] <= 1].sort_values(by='days_until_empty')
st.dataframe(priority_df[['store_name', 'address', 'days_until_empty']])

# Log new delivery
st.subheader("📝 Log a New Delivery")
with st.form("log_form"):
    store = st.text_input("Store Name")
    address = st.text_input("Address")
    delivery_date = st.date_input("Delivery Date", value=datetime.today())
    cartons = st.number_input("Cartons Delivered", min_value=1)
    depletion_days = st.number_input("Estimated Days to Depletion", min_value=1)

    submitted = st.form_submit_button("Submit Delivery")
    if submitted:
        new_row = pd.DataFrame([{
            "store_name": store,
            "address": address,
            "last_delivery_date": pd.to_datetime(delivery_date),
            "cartons_delivered": cartons,
            "depletion_days_estimate": depletion_days
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df = calculate_delivery_dates(df)

        # Update session state
        st.session_state.df = df

        # Write updated data back to the sheet
        set_with_dataframe(sheet, df.fillna(""))

        st.success(f"✅ Delivery logged for {store}")
        
# --- Agenda by 5-Day Bucket ---
st.subheader("📅 Upcoming Deliveries: 5-Day Agenda View")

# Refresh dataframe in case of form submission
df = calculate_delivery_dates(df)
df = df.dropna(subset=["expected_empty_date"])

# Create custom 5-day buckets
def get_5day_bucket(date):
    start_day = ((date.day - 1) // 5) * 5 + 1
    end_day = min(start_day + 4, pd.Period(date, freq='M').days_in_month)
    start_date = date.replace(day=start_day)
    end_date = date.replace(day=end_day)
    label = f"{start_date.strftime('%b %d')}–{end_date.strftime('%d')}"
    return f"{label} ({date.strftime('%Y')})"

df["delivery_week"] = df["expected_empty_date"].apply(get_5day_bucket)

# Group by 5-day interval
grouped = df.groupby("delivery_week")

for group, items in grouped:
    st.markdown(f"### 📌 {group}")
    st.dataframe(items[["store_name", "address", "expected_empty_date", "days_until_empty"]])








        

