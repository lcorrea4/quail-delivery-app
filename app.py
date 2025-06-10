import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import json

# --- Google Sheet Setup ---
# Define scope and authenticate
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
sheet = spreadsheet.worksheet("Sheet1")

# --- Function to Calculate Dates ---
def calculate_delivery_dates(df):
    df['last_delivery_date'] = pd.to_datetime(df['last_delivery_date'], errors='coerce')
    df['expected_empty_date'] = df['last_delivery_date'] + pd.to_timedelta(df['depletion_days_estimate'], unit='D')
    df['days_until_empty'] = (df['expected_empty_date'] - datetime.today()).dt.days
    return df

# Define custom 5-day bucket function
def get_5day_bucket(date):
    # Calculate the starting day for the bucket (in groups of 5)
    start_day = ((date.day - 1) // 5) * 5 + 1
    # Calculate the last day of the bucket ensuring we don't exceed the month's days
    end_day = min(start_day + 4, pd.Period(date, freq='M').days_in_month)
    start_date = date.replace(day=start_day)
    end_date = date.replace(day=end_day)
    label = f"{start_date.strftime('%b %d')}–{end_date.strftime('%d')}"
    return f"{label} ({date.strftime('%Y')})"



# --- UI ---
st.title("📦 Quail Egg Delivery Tracker")
st.subheader("📅 Upcoming Deliveries: 5-Day Agenda View")

# Use the updated session state DataFrame
# Load dataframe from Google Sheet and store in session state
if "df" not in st.session_state:
    df = get_as_dataframe(sheet).dropna(how='all')
    df = calculate_delivery_dates(df)
    st.session_state.df = df.copy()
else:
    df = st.session_state.df.copy()



df = calculate_delivery_dates(df)
df = df.dropna(subset=["expected_empty_date"])




# Create a new column with the 5-day bucket
df["delivery_week"] = df["expected_empty_date"].apply(get_5day_bucket)


# Group by the 5-day bucket
grouped = df.groupby("delivery_week")
if grouped.ngroups == 0:
    st.write("No groups found. Check that 'expected_empty_date' values exist in your data.")
else:
    for group, items in grouped:
        st.markdown(f"### 📌 {group}")
        agenda_table = items[["store_name", "address", "expected_empty_date", "days_until_empty"]].copy()
        agenda_table["expected_empty_date"] = agenda_table["expected_empty_date"].dt.strftime("%b %d")
        st.dataframe(agenda_table)



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
        st.session_state.df = df.copy()
        set_with_dataframe(sheet, df.fillna(""))
        st.success(f"✅ Delivery logged for {store}")

# --- Historical Delivery Calendar from Excel ---
st.subheader("📊 Historical Delivery Calendar")

uploaded_file = st.file_uploader("Upload Excel File with Historical Deliveries", type=["xlsx"])

#import xlrd  # just in case
import os

# Upload and parse Excel history
#uploaded_file = st.file_uploader("📤 Upload historical delivery .xlsm file", type=["xlsm"])

if uploaded_file:
    sheet_name = st.text_input("Enter the sheet name", value="Sheet1")

    try:
        # Read the full Excel file with no headers to find boundaries
        raw_df = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

        # Find the row where the string starts and ends in column C (index 2)
        start_row = raw_df[2][raw_df[2] == "QUAIL EGGS X 10 (QUAIL EGGS X 10)"].index[0] + 1
        end_row = raw_df[2][raw_df[2] == "Total QUAIL EGGS X 10 (QUAIL EGGS X 10)"].index[0] - 1

        # Define Excel columns to keep: F,H,J,L,N,P,R,T,V = indices 5,7,...,21
        target_cols = [5, 7, 9, 11, 13, 15, 17, 19, 21]

        # Slice the relevant data
        df_hist = raw_df.loc[start_row:end_row, target_cols].copy()

        # Rename columns for readability (adjust as needed)
        df_hist.columns = [
            "Type", "Date", "Num", "Memo", "Name",
            "Qty", "Sales Price", "Amount", "Balance"
        ]

        # Safely assign column names if the number of columns matches
        expected_columns = [
            "Type", "Date", "Num", "Memo", "Name",
            "Qty", "Sales Price", "Amount", "Balance"
        ]
        
        if len(df_hist.columns) == len(expected_columns):
            df_hist.columns = expected_columns
        else:
            st.warning(f"⚠️ Expected {len(expected_columns)} columns but got {len(df_hist.columns)}. Showing raw data for review.")
            st.dataframe(df_hist.head())
            
        st.success("✅ Historical delivery data loaded successfully!")
        st.dataframe(df_hist)

    except Exception as e:
        st.error(f"⚠️ Error loading file: {e}")

    # --- Calendar-Style Timeline Plot ---
    import plotly.express as px
    fig = px.timeline(
        df_hist,
        x_start="Date",
        x_end="Date",
        y="Store",
        color="Store",
        title="📅 Delivery History Timeline",
    )
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_layout(height=800)
    st.plotly_chart(fig, use_container_width=True)

