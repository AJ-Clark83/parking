from pathlib import Path
import streamlit as st
import base64

_here = Path(__file__).parent

st.set_page_config(layout="wide")

def img_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

parking_src = f"data:image/png;base64,{img_to_base64(_here / 'static' / 'parking.png')}"

col1, col2, col3 = st.columns(3)

with col2:
    # 1. Added 'f' before the triple quotes
    st.markdown(f"""
    <style>
    .custom-img {{
        border: 1px solid #000000;
        border-radius: 5px;
        max-width: 100%;
    }}
    </style>
    <div>
    <h1 style='text-align: center;'>Aus-West Parking</h1>
    </div>
    <p>
    <img src="{parking_src}" style="height:768px; width:auto" class="custom-img">
    </p>
    <p style='text-align: center;'>
    Available Parking at West Perth has expired. Please find alternate parking arrangements.
    </p>
    """,
    unsafe_allow_html=True,
)