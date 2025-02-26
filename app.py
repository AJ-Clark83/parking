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

# --------------------------------------------------
# Supabase Setup
# --------------------------------------------------
# Retrieve secrets from .streamlit/secrets.toml
SUPABASE_URL = st.secrets["supabase"]["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["supabase"]["SUPABASE_KEY"]
TEAMS_WEBHOOK_URL = st.secrets["teams_webhook"]["TEAMS_WEBHOOK_URL"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --------------------------------------------------
# Configuration
# --------------------------------------------------
TOTAL_BAYS = 5
TIMEZONE = pytz.timezone("Asia/Shanghai")  # Adjust as needed
LOCK_DURATION = 60  # 1 minute to complete form

# Booking windows:
# Opens at 14:00 (2 PM), closes at 08:30 next morning
BOOKING_START_HOUR = 16  # 4:00 PM in 24-hour format
BOOKING_END_HOUR = 8     # 8:30 AM
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
    Returns True if current local time (TIMEZONE-based)
    is between 16:00 and 08:30 next day.
    i.e. open from 16:00 (4 PM) -> 23:59:59
         and from 00:00 -> 08:30
    Closed only 08:31 -> 15:59
    """
    now_local = datetime.datetime.now(pytz.UTC).astimezone(TIMEZONE)
    current_hour = now_local.hour
    current_minute = now_local.minute
    
    # If time is >= 16:00, booking is open
    # OR if time is < 08:30
    if current_hour >= BOOKING_START_HOUR:
        return True
    elif current_hour < BOOKING_END_HOUR or (current_hour == BOOKING_END_HOUR and current_minute <= BOOKING_END_MINUTE):
        return True
    return False

def get_booking_date():
    """
    If it's >= 16:00 local time, the booking date is tomorrow.
    Otherwise, it's today.
    """
    now_local = datetime.datetime.now(pytz.UTC).astimezone(TIMEZONE)
    if now_local.hour >= BOOKING_START_HOUR:
        return (now_local + datetime.timedelta(days=1)).date()
    else:
        return now_local.date()

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

booking_open = is_booking_open()
if not booking_open:
    st.warning("Booking opens at 4:00 PM and closes at 8:30 AM. Please return during this time to make your booking.")
    st.stop()

booking_date = get_booking_date()

# --------------------------------------------------
# Check Available Bays
# --------------------------------------------------
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
            response = supabase.table("maca_parking").select("id").eq("date", str(booking_date)).execute()
            booked_count = len(response.data)
            updated_available_bays = TOTAL_BAYS - booked_count
            
            if updated_available_bays <= 0:
                st.error("All available bays have now been allocated. Please try again during .")
                st.stop()
                
            # Lock the booking
            st.session_state["lock_time"] = time.time()
            st.session_state["locked"] = True
            
            # Insert temporary record
            temp_entry = supabase.table("maca_parking").insert({
                "date": str(booking_date),
                "first_name": "TEMP",
                "surname": "TEMP",
                "email": "TEMP",
                "mobile": "TEMP",
                "registration": "TEMP"
            }).execute()
            
            st.session_state["temp_record_id"] = temp_entry.data[0]['id']
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

