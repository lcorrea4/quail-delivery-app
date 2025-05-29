
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

# --- Group Stores by Custom 5-Day Week Buckets ---
st.subheader("📅 Upcoming Deliveries Grouped by 5-Day Intervals")

# Make sure dates are datetime
df['expected_empty_date'] = pd.to_datetime(df['expected_empty_date'], errors='coerce')

# Drop rows with invalid dates
df = df.dropna(subset=['expected_empty_date'])

# Create custom 5-day bucket labels
def get_5day_bucket(date):
    day = date.day
    month = date.strftime('%b')
    year = date.year

    start_day = ((day - 1) // 5) * 5 + 1
    end_day = start_day + 4

    # Adjust for end-of-month
    last_day = (date + pd.offsets.MonthEnd(0)).day
    if end_day > last_day:
        end_day = last_day

    return f"{month} {start_day}-{end_day}, {year}"

df['delivery_window'] = df['expected_empty_date'].apply(get_5day_bucket)

# Group by window
grouped = df.groupby('delivery_window')

# Display grouped agenda
for window, group in grouped:
    st.markdown(f"### 📆 {window}")
    for _, row in group.iterrows():
        st.markdown(f"- **{row['store_name']}** – {row['address']} (🗓️ {row['expected_empty_date'].date()}, {row['days_until_empty']} days left)")

# Optional: Add a bar chart by delivery window
st.subheader("📊 Delivery Volume by 5-Day Window")
count_by_window = df['delivery_window'].value_counts().sort_index()
st.bar_chart(count_by_window)



        

