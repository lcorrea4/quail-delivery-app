import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import json
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
# --- Google Sheet Setup ---
# Define scope and authenticate
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key("1Rej0GZl5Td6nSQiPyrmvHDerH9LhISE0eFWRO8Rl6ZY")
sheet = spreadsheet.worksheet("Sheet1")

import calendar
from datetime import date
import streamlit as st

def draw_calendar(delivery_df):
    st.subheader("🗓️ Delivery Calendar")

    # Make sure Date is datetime
    delivery_df["Date"] = pd.to_datetime(delivery_df["Date"], errors="coerce")

    # User selects month and year
    today = date.today()
    selected_year = st.selectbox("Select Year", sorted(delivery_df["Date"].dt.year.dropna().unique()), index=0)
    selected_month = st.selectbox("Select Month", list(calendar.month_name)[1:], index=today.month - 1)

    month_number = list(calendar.month_name).index(selected_month)
    filtered_df = delivery_df[
        (delivery_df["Date"].dt.year == selected_year) &
        (delivery_df["Date"].dt.month == month_number)
    ]

    # Build day-to-store map
    day_to_stores = filtered_df.groupby(delivery_df["Date"].dt.day)["Name"].apply(list).to_dict()

    # Draw the calendar
    st.markdown(f"### {selected_month} {selected_year}")
    cal = calendar.monthcalendar(selected_year, month_number)

    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].empty()
            else:
                label = f"{day}"
                if day in day_to_stores:
                    stores = "\n".join(day_to_stores[day])
                    cols[i].markdown(f"**{label}** 🟢")
                    with cols[i].expander("Details"):
                        for store in day_to_stores[day]:
                            st.write(f"- {store}")
                else:
                    cols[i].markdown(f"{label}")

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

st.set_page_config(layout="wide")
st.title("📦 Quality Quail Eggs")
st.subheader("📅 Upcoming Deliveries:")

uploaded_file = st.file_uploader("Upload Excel File with Historical Deliveries", type=["xlsx"])
    

if uploaded_file:
    # sheet_name = st.text_input("Enter the sheet name", value="")

    try:
        # Read the full Excel file with no headers to find boundaries
        raw_df = pd.read_excel(uploaded_file, sheet_name="Sheet1", header=None)

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
        # Raw input as a multiline string (paste your actual list here)
        raw_store_list = """
        - Fresco y Mas 1717 - 30
        - Fresco y Mas 201 - 20
        - Fresco y Mas 231 - 10
        - Fresco y Mas 235 - 25
        - Fresco y Mas 237 - 30
        - Fresco y Mas 239 - 30
        - Fresco y Mas 242 - 20
        - Fresco y Mas 243 - 15
        - Fresco y Mas 2450 - 40
        - Fresco y Mas 252 - 20
        - Fresco y Mas 270 - 15
        - Fresco y Mas 286 - 25
        - Fresco y Mas 287 - 20
        - Fresco y Mas 292 - 10
        - Fresco y Mas 304 - 60
        - Fresco y Mas 353 - 20
        - Fresco y Mas 359 - 20
        - Fresco y Mas 361 - 20
        - Fresco y Mas 366 - 15
        - Fresco y Mas 384 - 20
        - Fresco y Mas 385 - 15
        - Fresco y Mas 387 - 15
        - Fresco y Mas 388 - 20
        - Fresco y Mas 697 - 50
        - Fresco y Mas 745 - 60
        - Fresco y mas 283 - 20
        - Publix 10 - 15
        - Publix 1009 - 20
        - Publix 1017 - 20
        - Publix 1036 - 40
        - Publix 1062 - 25
        - Publix 1072 - 15
        - Publix 1094 - 30
        - Publix 1097 - 20
        - Publix 1124 - 40
        - Publix 1129 - 15
        - Publix 1151 - 15
        - Publix 1209 - 30
        - Publix 1230 - 25
        - Publix 1236 - 15
        - Publix 1264 - 10
        - Publix 127 - 25
        - Publix 1273 - 30
        - Publix 1288 - 30
        - Publix 1297 - 35
        - Publix 1382 - 15
        - Publix 1384 - 30
        - Publix 1386 - 30
        - Publix 1389 - 35
        - Publix 1397 - 15
        - Publix 1405 - 40
        - Publix 1423 - 25
        - Publix 1467 - 20
        - Publix 1469 - 20
        - Publix 1491 - 50
        - Publix 1492 - 15
        - Publix 1494 - 15
        - Publix 1526 - 40
        - Publix 1536 - 15
        - Publix 1561 - 30
        - Publix 1571 - 15
        - Publix 1614 - 25
        - Publix 1699 - 40
        - Publix 1715 - 30
        - Publix 1748 - 20
        - Publix 1776 - 50
        - Publix 1803 - 30
        - Publix 1804 - 20
        - Publix 21 - 30
        - Publix 222 - 20
        - Publix 223 - 30
        - Publix 238 - 20
        - Publix 24 - 10
        - Publix 242 - 60
        - Publix 246 - 40
        - Publix 262 - 20
        - Publix 293 - 15
        - Publix 302 - 50
        - Publix 31 - 15
        - Publix 327 - 20
        - Publix 343 - 15
        - Publix 375 - 20
        - Publix 402 - 15
        - Publix 406 - 30
        - Publix 421 - 25
        - Publix 44 - 20
        - Publix 454 - 20
        - Publix 50 - 20
        - Publix 509 - 40
        - Publix 51 - 15
        - Publix 510 - 25
        - Publix 529 - 20
        - Publix 54 - 20
        - Publix 550 - 40
        - Publix 56 - 40
        - Publix 581 - 20
        - Publix 583 - 20
        - Publix 586 - 20
        - Publix 588 - 30
        - Publix 600 - 30
        - Publix 621 - 30
        - Publix 655 - 25
        - Publix 657 - 40
        - Publix 658 - 20
        - Publix 669 - 20
        - Publix 674 - 30
        - Publix 70 - 25
        - Publix 714 - 20
        - Publix 715 - 40
        - Publix 747 - 30
        - Publix 750 - 50
        - Publix 759 - 30
        - Publix 794 - 30
        - Publix 832 - 15
        - Publix 835 - 30
        - Publix 84 - 30
        - Publix 848 - 50
        - Publix 861 - 50
        - Publix 889 - 25
        - Sedano's 04 - 20
        - Sedano's 05 - 30
        - Sedano's 08 - 20
        - Sedano's 09 - 25
        - Sedano's 10 - 25
        - Sedano's 11 - 15
        - Sedano's 14 - 20
        - Sedano's 16 - 30
        - Sedano's 17 - 20
        - Sedano's 18 - 30
        - Sedano's 20 - 25
        - Sedano's 21 - 30
        - Sedano's 22 - 30
        - Sedano's 23 - 25
        - Sedano's 24 - 25
        - Sedano's 26 - 25
        - Sedano's 27 - 50
        - Sedano's 28 - 20
        - Sedano's 29 - 40
        - Sedano's 31 - 30
        - Sedano's 32 - 40
        - Sedano's 33 - 20
        - Sedano's 34 - 40
        - Sedano's 36 - 25
        - Sedano's 37 - 40
        - Sedano's 38 - 15
        - Sedano's 41 - 40
        - Sedano's 42 - 25
        - Sedano's 43 - 30
        - Sedano's 7 - 30
        - sedanos 1 - 40
        """
        
        # Step 1: Clean and parse
        store_days = []
        for line in raw_store_list.strip().splitlines():
            cleaned = line.lstrip("- ").strip()
            if " - " in cleaned:
                store_name, days = cleaned.rsplit(" - ", 1)
                store_days.append((store_name.strip(), int(days.strip())))
        
        # Step 2: Convert to DataFrame
        days_df = pd.DataFrame(store_days, columns=["Name", "depletion_days_estimate"])
        
        # Step 3: Merge into your existing df_hist
        df_hist = df_hist.merge(days_df, on="Name", how="left")

        st.success("✅ Historical delivery data loaded successfully!")

        # st.dataframe(df_hist)
        # draw_calendar(df_hist)
        # st.dataframe(df_hist)

        # # Extract and sort unique store names
        # unique_stores = (
        #     df_hist[["Name"]]
        #     .dropna()
        #     .drop_duplicates()
        #     .sort_values("Name")
        # )
        
        # # Format for WhatsApp
        # store_list_text = "\n".join(f"- {row['Name']} -" for _, row in unique_stores.iterrows())
        
        # # Display in Streamlit
        # st.subheader("📋 Copy This List and Send via WhatsApp")
        # st.text_area("Store List", store_list_text, height=400)


    
        # 1. Filter historical data to only get the last delivery per store
        last_deliveries = df_hist.sort_values("Date").groupby("Name", as_index=False).last()
        
        # 2. Set up a DataFrame to hold future visits
        calendar_rows = []
        
        # 3. Simulate future delivery dates based on depletion estimate
        for _, row in last_deliveries.iterrows():
            store = row["Name"]
            last_date = pd.to_datetime(row["Date"])
            days_est = row.get("depletion_days_estimate")
        
            # Skip if depletion estimate is missing
            if pd.isna(days_est):
                continue
        
            visit_date = last_date + timedelta(days=days_est)
            while visit_date <= pd.Timestamp("2025-07-31"):
                if visit_date >= pd.Timestamp("2025-06-01"):
                    calendar_rows.append({
                        "Store": store,
                        "Visit Date": visit_date.date()
                    })
                visit_date += timedelta(days=days_est)
        
        # 4. Create the calendar DataFrame
        calendar_df = pd.DataFrame(calendar_rows).sort_values("Visit Date")
        
        # Optional: Group by date to see who should be visited each day
        grouped_calendar = calendar_df.groupby("Visit Date")["Store"].apply(list).reset_index()
        
        # Show result
        st.subheader("📅 Projected Delivery Calendar (June & July)")
        # Build grid options to enable horizontal scroll and column resizing
        # Build options
        gb = GridOptionsBuilder.from_dataframe(grouped_calendar)
        
        # ✅ Make columns resizable and wrap text
        gb.configure_default_column(
            resizable=True,
            wrapText=True,
            autoHeight=True,
            sortable=True,
            filter=True
        )
        
        # ✅ Adjust "Visit Date" column width and alignment
        gb.configure_column(
            "Visit Date",
            header_name="📅 Visit Date",
            width=150,
            cellStyle={"textAlign": "center", "fontWeight": "bold"}
        )
        
        # ✅ Style "Stores" column
        gb.configure_column(
            "Stores",
            #header_name="🏪 Stores to Deliver",
            autoHeight=True,
            wrapText=True,
            cellStyle={"whiteSpace": "normal"}
        )
        
        # ✅ Optional: Add zebra striping (row styles)
        gb.configure_grid_options(
            domLayout='normal',
            rowStyle={"background": "#f9f9f9"},
            getRowStyle=JsCode("""
                function(params) {
                    if (params.node.rowIndex % 2 === 0) {
                        return { 'background': '#ffffff' };
                    }
                    return { 'background': '#f1f3f6' };
                }
            """)
        )
        
        # Build final options
        grid_options = gb.build()

        grouped_calendar["Visit Date"] = pd.to_datetime(grouped_calendar["Visit Date"], errors='coerce')
        grouped_calendar["Visit Date"] = grouped_calendar["Visit Date"].dt.strftime("%m/%d/%Y")

        # Define today's date and the range end
        today = date.today()
        end_date = today + timedelta(days=4)
        
        # Filter the calendar to only show a 5-day rolling window
        agenda_calendar = grouped_calendar[
            (grouped_calendar["Visit Date"] >= today) &
            (grouped_calendar["Visit Date"] <= end_date)
        ]
        
        # Display the table
        with st.container():
            AgGrid(
                grouped_calendar,
                gridOptions=grid_options,
                fit_columns_on_grid_load=False,
                height=600,
                theme="material",
                enable_enterprise_modules=False,
                allow_unsafe_jscode=True,
                reload_data=True
            )



    except Exception as e:
        st.error(f"⚠️ Error loading file: {e}")

# --- UI ---
with st.expander("🔧 Show Experimental or Less Important Tools", expanded=False):
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
    







