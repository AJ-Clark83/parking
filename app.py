# -*- coding: utf-8 -*-
"""
Created on Mon Feb 10 13:53:50 2025

@author: andrew.clark
"""

import streamlit as st
from supabase import create_client, Client
import datetime
import pytz
import time
import requests
from dateutil import parser
import streamlit.components.v1 as components

# --------------------------------------------------
# Inject Tracking
# --------------------------------------------------

# Define the Clarity tracking script
CLARITY_SCRIPT = """
<script type="text/javascript">
    (function(c,l,a,r,i,t,y){
        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
    })(window, document, "clarity", "script", "vbtqd6ciqh");
</script>
"""

# 2. Inject the script into the app
components.html(CLARITY_SCRIPT, height=0, width=0)

# --------------------------------------------------
# BLOCK COPY SEARCH
# --------------------------------------------------
st.markdown("""
<style>
/* Disable text selection for the entire body of the app */
.stApp {
  -webkit-user-select: none; /* Safari */
  -moz-user-select: none; /* Firefox */
  -ms-user-select: none; /* IE10+ and Edge */
  user-select: none; /* Standard syntax */
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# Supabase Setup
# --------------------------------------------------
# Retrieve secrets from .streamlit/secrets.toml
SUPABASE_URL = st.secrets["supabase"]["SUPABASE_URL"]
SC = st.secrets["supabase"]["SC"]
SUPABASE_KEY = st.secrets["supabase"]["SUPABASE_KEY"]
TEAMS_WEBHOOK_URL = st.secrets["teams_webhook"]["TEAMS_WEBHOOK_URL"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------------------------------
# Configuration
# --------------------------------------------------
TOTAL_BAYS = 6
TIMEZONE = pytz.timezone("Asia/Shanghai")  # Adjust as needed
LOCK_DURATION = 60  # 1 minute to complete form

# Booking windows:
# Opens at 16:00 (4 PM), closes at 08:30 next morning
BOOKING_START_HOUR = 16  # 4:00 PM in 24-hour format
BOOKING_END_HOUR = 8  # 8:30 AM
BOOKING_END_MINUTE = 30

# --------------------------------------------------
# Initialize session state variables
# --------------------------------------------------
if "availability_checked" not in st.session_state:
    st.session_state["availability_checked"] = False
if "locked" not in st.session_state:
    st.session_state["locked"] = False
if "temp_record_id" not in st.session_state:
    st.session_state["temp_record_id"] = None
if "lock_time" not in st.session_state:
    st.session_state["timeout_reached"] = False
    st.session_state["lock_time"] = None


# --------------------------------------------------
# Helper functions
# --------------------------------------------------
def is_booking_open():
    """
    Returns True if the current local time is within the booking window
    and the next day's booking date is NOT Monday.
    """
    now_local = datetime.datetime.now(pytz.UTC).astimezone(TIMEZONE)
    booking_date = get_booking_date()

    # If the calculated booking date is Monday, prevent booking
    if booking_date.weekday() == 0:  # 0 = Monday
        return False

    current_hour = now_local.hour
    current_minute = now_local.minute

    # Booking is open between 16:00 (4 PM) - 08:30 the next day
    if current_hour >= BOOKING_START_HOUR:
        return True
    elif current_hour < BOOKING_END_HOUR or (current_hour == BOOKING_END_HOUR and current_minute <= BOOKING_END_MINUTE):
        return True

    return False


def get_booking_date():
    """
    Determines the booking date based on the current time.
    - If it's after 16:00, the booking is for tomorrow.
    - If tomorrow is Monday, booking is not allowed.
    """
    now_local = datetime.datetime.now(pytz.UTC).astimezone(TIMEZONE)

    # Determine the next day's booking date
    if now_local.hour >= BOOKING_START_HOUR:
        booking_date = now_local.date() + datetime.timedelta(days=1)
    else:
        booking_date = now_local.date()

    return booking_date


def cleanup_old_temporary_reservations():
    """
    Removes 'TEMP' records older than LOCK_DURATION.
    """
    expiration_time = datetime.datetime.now(pytz.UTC) - datetime.timedelta(seconds=LOCK_DURATION)
    response = supabase.table("maca_parking").select("id", "created_at").eq("first_name", "TEMP").execute()
    if response.data:
        for record in response.data:
            try:
                record_time = parser.isoparse(record["created_at"])
                # Ensure UTC timezone
                if record_time.tzinfo is None:
                    record_time = record_time.replace(tzinfo=pytz.UTC)
                if record_time <= expiration_time:
                    supabase.table("maca_parking").delete().eq("id", record["id"]).execute()
            except ValueError as e:
                st.error(f"Error parsing timestamp: {e}")


# --------------------------------------------------
# Teams channel integration
# --------------------------------------------------

def send_teams_notification(webhook_url: str, message: str):
    """
    Sends a notification to a Microsoft Teams channel
    via an Incoming Webhook.

    :param webhook_url: The full Teams webhook URL.
    :param message:     The text to display in Teams.
    """
    payload = {
        "text": message
    }

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()  # Raise an error if request failed
    except Exception as e:
        print(f"Error sending Teams notification: {e}")


# --------------------------------------------------
# Main UI
# --------------------------------------------------
st.title("88 Colin Street Visitor Car Bay Booking")

# Check if bookings are open
booking_open = is_booking_open()
booking_date = get_booking_date()

if not booking_open:
    if booking_date.weekday() == 0:  # If the next day's booking date is Monday
        st.warning("Bookings are not allowed for Mondays. Please return after 4:00 PM on Monday to book for Tuesday.")
    else:
        st.warning(
            "Booking opens at 4:00 PM and closes at 8:30 AM. Please return during this time to make your booking.")

    st.stop()  # Stop the app execution here to prevent form display

booking_date = get_booking_date()

# --------------------------------------------------
# Question Challenge From Supabase
# --------------------------------------------------
if "question_verified" not in st.session_state:
    st.session_state["question_verified"] = False

if "current_question" not in st.session_state:
    # Fetch a random question from Supabase
    response = supabase.table("questions").select("Question", "Answer").execute()
    if not response.data:
        st.error("No questions available. Please try again later.")
        st.stop()

    import random
    selected = random.choice(response.data)
    st.session_state["current_question"] = selected

if not st.session_state["question_verified"]:
    question = st.session_state["current_question"]["Question"]
    correct_answer = st.session_state["current_question"]["Answer"]

    st.write("Please answer the question to proceed:")
    user_answer = st.text_input(question, key="question_input")

    if st.button("Verify Answer"):
        normalized_user = user_answer.strip().lower()
        normalized_correct = correct_answer.strip().lower()

        if normalized_user == normalized_correct or user_answer == SC:
            st.success("✅ Correct! You can now check parking availability.")
            st.session_state["question_verified"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect. Please try again.")
else:
    # Show the Check Available Bays button if verified
    if st.button("Check Available Bays"):
        cleanup_old_temporary_reservations()
        response = supabase.table("maca_parking").select("id").eq("date", str(booking_date)).execute()
        booked_count = len(response.data)
        available_bays = TOTAL_BAYS - booked_count

        st.session_state["availability_checked"] = True
        st.session_state["available_bays"] = available_bays
        st.rerun()



# --------------------------------------------------
# If availability checked and not locked, show availability
# --------------------------------------------------
if st.session_state.get("availability_checked") and not st.session_state.get("locked"):
    available_bays = st.session_state.get("available_bays", 0)
    if available_bays > 0:
        st.success(f"{available_bays} bay(s) available for {booking_date}")

        if st.button("Request a Bay"):
            cleanup_old_temporary_reservations()

            # Get updated bookings count INCLUDING 'TEMP' records
            response = supabase.table("maca_parking").select("id").eq("date", str(booking_date)).execute()
            current_count = len(response.data)

            if current_count >= TOTAL_BAYS:
                st.error("All available bays have now been allocated.")
                st.stop()
            else:
                # Now insert 'TEMP' lock
                temp_entry = supabase.table("maca_parking").insert({
                    "date": str(booking_date),
                    "first_name": "TEMP",
                    "surname": "TEMP",
                    "email": "TEMP",
                    "mobile": "TEMP",
                    "registration": "TEMP"
                }).execute()

                if not temp_entry.data:
                    st.error("Failed to reserve your bay. Please try again.")
                    st.stop()

                st.session_state["temp_record_id"] = temp_entry.data[0]['id']
                st.session_state["lock_time"] = time.time()
                st.session_state["locked"] = True
                st.rerun()


    else:
        st.error("Sorry, there are no visitor bays currently available.")

# --------------------------------------------------
# Booking Form
# --------------------------------------------------
# Ensure a session state flag exists
if "booking_confirmed" not in st.session_state:
    st.session_state["booking_confirmed"] = False

if st.session_state.get("locked") and not st.session_state.get("timeout_reached"):
    st.warning("You have 60 seconds to complete the form before your temporary reservation is released.")
    elapsed_time = time.time() - st.session_state["lock_time"]
    remaining_time = max(0, LOCK_DURATION - int(elapsed_time))

    # If time is up, release the lock
    if remaining_time <= 0:
        cleanup_old_temporary_reservations()
        st.session_state["timeout_reached"] = True
        st.session_state["locked"] = False
        st.error("Time expired! Please re-check available bays and try again.")
        st.stop()

    st.subheader("Complete Your Booking")
    first_name = st.text_input("First Name")
    surname = st.text_input("Surname")
    email = st.text_input("Email")
    mobile = st.text_input("Mobile")
    registration = st.text_input("Vehicle Registration")

    # The Confirm Booking button is disabled if booking_confirmed is True
    if st.button("Confirm Booking", disabled=st.session_state["booking_confirmed"]):
        # Only process if not already confirmed
        if not st.session_state["booking_confirmed"]:

            # Additional validation: first or last name too short
            if len(first_name.strip()) <= 1 or len(surname.strip()) <= 1:
                st.error("Invalid Entry, Please add a real name and try again.")
                time.sleep(3)  # Show message for 3 seconds
                st.rerun()
           
            # Validate form fields
            if (not first_name or not surname or not email or not mobile or not registration
                    or ('thiess' not in email.lower() and 'maca' not in email.lower())):
                st.error("All fields are required, and you must use a MACA or Thiess email address to book.")
            else:
                # Update the temporary record to finalize
                supabase.table("maca_parking").update({
                    "first_name": first_name,
                    "surname": surname,
                    "email": email,
                    "mobile": mobile,
                    "registration": registration
                }).eq("id", st.session_state["temp_record_id"]).execute()

                st.success("Booking Confirmed!")
                st.balloons()

                # Construct a message for Teams
                message_text = (
                    f"**New Booking Confirmed**\n\n"
                    f"**Name**: {first_name} {surname}\n"
                    f"**Date**: {booking_date}\n"
                    f"**Email**: {email}\n"
                    f"**Registration**: {registration}"
                )

                # Send Teams notification
                send_teams_notification(TEAMS_WEBHOOK_URL, message_text)

                st.info("Notification sent to the Microsoft Teams channel.")

                # Set the flag to prevent further clicks
                st.session_state["booking_confirmed"] = True


