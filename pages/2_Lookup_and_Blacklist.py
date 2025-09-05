# pages/3_🔎_Lookup_and_Blacklist.py

import streamlit as st
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# Supabase client
from supabase import create_client, Client

# ---------- Page setup ----------
st.set_page_config(page_title="Lookup & Blacklist", page_icon="🔎", layout="centered")

st.title("Registration Lookup & Blacklist")

# ---------- Utilities ----------
@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets["supabase"]["SUPABASE_URL"]
    key = st.secrets["supabase"]["SUPABASE_KEY"]
    return create_client(url, key)

def iso_date_from_ddmmyyyy(s: str) -> str:
    """
    Parse DD/MM/YYYY string to ISO 'YYYY-MM-DD'.
    Raises ValueError if invalid.
    """
    dt = datetime.strptime(s.strip(), "%d/%m/%Y").date()
    return dt.isoformat()

def ddmmyyyy_from_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")

def normalize_rego(rego: str) -> str:
    # Keep it simple per requirements: lower-case only (no other transforms)
    return (rego or "").strip().lower()

supabase = get_supabase()

# ---------- Password Gate ----------
if "lookup_blacklist_authed" not in st.session_state:
    st.session_state.lookup_blacklist_authed = False

if not st.session_state.lookup_blacklist_authed:
    with st.form("password_form", clear_on_submit=True):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
        if submitted:
            expected = st.secrets.get("Password")
            if expected is None:
                st.error("No 'Password' found in secrets. Please add it.")
            elif pw == expected:
                st.session_state.lookup_blacklist_authed = True
                st.success("Access granted.")
                st.rerun()  # <-- this triggers the immediate reload
            else:
                st.error("Incorrect password.")
    st.stop()




# ---------- Lookup Form ----------
st.subheader("Find Registration in Approved List")

with st.form("lookup_form"):
    lookup_rego = st.text_input(
        "Registration number",
        placeholder="e.g. 1ABC123"
    )
    exact_match = st.checkbox("Exact match (case-insensitive)", value=True,
                              help="If unchecked, uses 'contains' search (case-insensitive).")
    do_lookup = st.form_submit_button("Search")

if do_lookup:
    if not lookup_rego.strip():
        st.warning("Please enter a registration to search.")
    else:
        # Case-insensitive search. If exact -> ilike 'value' ; else -> ilike '%value%'
        pattern = lookup_rego.strip()
        if exact_match:
            # Use ILIKE with exact string
            query = supabase.table("approved_registrations").select("*").ilike("registration", pattern)
        else:
            query = supabase.table("approved_registrations").select("*").ilike("registration", f"%{pattern}%")

        with st.spinner("Searching…"):
            resp = query.execute()

        rows = resp.data or []
        if len(rows) == 0:
            st.info("No matching registration found in **approved_registrations**.")
        else:
            st.success(f"Found {len(rows)} matching row(s).")
            for i, row in enumerate(rows, start=1):
                with st.expander(f"Result {i}: {row.get('registration','(no reg shown)')}"):
                    # Pretty render key-value pairs
                    for k in sorted(row.keys()):
                        st.write(f"**{k}**: {row[k]}")

# ---------- Divider ----------
st.divider()

# ---------- Blacklist Form ----------
st.subheader("Add Vehicle to Blacklist")

default_end = date.today() + relativedelta(months=1)
default_end_str = ddmmyyyy_from_date(default_end)

with st.form("blacklist_form", clear_on_submit=False):
    bl_rego_raw = st.text_input(
        "registration",
        placeholder="e.g. 1abc123",
        help="Will be saved as lower-case."
    )
    bl_end_str = st.text_input(
        "suspension_end (DD/MM/YYYY)",
        value=default_end_str,
        help="Defaults to today + 1 month. Must be in DD/MM/YYYY."
    )

    submit_blacklist = st.form_submit_button("Add to blacklist")

if submit_blacklist:
    # Validate and transform
    bl_rego = normalize_rego(bl_rego_raw)
    if not bl_rego:
        st.error("Please enter a registration.")
    else:
        try:
            iso_end = iso_date_from_ddmmyyyy(bl_end_str)
        except ValueError:
            st.error("Invalid date format. Please use DD/MM/YYYY.")
            st.stop()

        payload = {
            "registration": bl_rego,
            "suspension_end": iso_end,  # stored as 'date' type in Supabase
        }

        with st.spinner("Saving to blacklist…"):
            try:
                resp = supabase.table("blacklist").insert(payload).execute()
            except Exception as e:
                st.error(f"Failed to insert into blacklist: {e}")
            else:
                st.success(f"Registration **{bl_rego}** blacklisted until **{bl_end_str}**.")

# ---------- Helpful Notes ----------
with st.expander("Notes"):
    st.markdown(
        """
- **Lookup** uses case-insensitive search (`ILIKE`). Toggle *Exact match* for strict equality; otherwise it finds rows that *contain* your input.
- **Blacklist** saves `registration` as lower-case (per your request).
- `suspension_end` accepts **DD/MM/YYYY** input for convenience but is saved to Supabase as an ISO `date` (`YYYY-MM-DD`).
        """
    )
