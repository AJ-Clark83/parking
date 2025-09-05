# pages/1_Vehicle_Management.py
import re
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Vehicle management", page_icon="🚗", layout="centered")

# --------------------------------------------------
# Supabase Setup (mirrors your existing app)
# --------------------------------------------------
SUPABASE_URL = st.secrets["supabase"]["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["supabase"]["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLE_NAME = "approved_registrations"

st.title("Vehicle management")
st.caption("Add a vehicle to the register.")

with st.form("vehicle_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        first_name = st.text_input("First name", autocomplete="given-name")
        last_name  = st.text_input("Last name", autocomplete="family-name")
        email      = st.text_input("Email", autocomplete="email")
        phone      = st.text_input("Phone", autocomplete="tel")
    with col2:
        registration = st.text_input("Vehicle registration")
        make         = st.text_input("Vehicle make")
        model        = st.text_input("Vehicle model")
        colour       = st.text_input("Vehicle colour")

    submitted = st.form_submit_button("Save vehicle", use_container_width=True)

if submitted:
    # --------- Validation ----------
    errs = []

    def req(name, val):
        if not val or not str(val).strip():
            errs.append(f"• {name} is required")

    req("First name", first_name)
    req("Last name", last_name)
    req("Email", email)
    req("Phone", phone)
    req("Vehicle registration", registration)
    req("Vehicle make", make)
    req("Vehicle model", model)
    req("Vehicle colour", colour)

    # Simple email + phone sanity checks (not strict)
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errs.append("• Please enter a valid email")
    if phone and not re.match(r"^[0-9+\-\s()]{6,}$", phone):
        errs.append("• Please enter a valid phone number")

    # Normalise values
    clean = {
        "first_name": first_name.strip().title() if first_name else "",
        "last_name":  last_name.strip().title() if last_name else "",
        "email":      email.strip(),
        "phone":      phone.strip(),
        "registration": re.sub(r"\s+", "", registration).upper() if registration else "",
        "make":       make.strip().title() if make else "",
        "model":      model.strip().title() if model else "",
        "colour":     colour.strip().title() if colour else "",
    }

    if errs:
        st.error("Please fix the following:\n" + "\n".join(errs))
        st.stop()

    # --------- Optional: Prevent obvious duplicates by (email, registration) ----------
    try:
        exists = supabase.table(TABLE_NAME)\
            .select("id")\
            .eq("email", clean["email"])\
            .eq("registration", clean["registration"])\
            .limit(1).execute()
        if exists.data:
            st.warning("This vehicle is already on the approved list for that email.")
            st.stop()
    except Exception as e:
        st.error(f"Lookup failed: {e}")
        st.stop()

    # --------- Insert ----------
    try:
        res = supabase.table(TABLE_NAME).insert(clean).execute()
        if res.data:
            st.success("✅ Vehicle saved to approved list.")
            st.balloons()
        else:
            st.error("Insert returned no data; please try again.")
    except Exception as e:
        st.error(f"Insert failed: {e}")

