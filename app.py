"""
Hostel management app — entry point.

For now this is a connection test. We'll replace it with the real login
screen in the next step.
"""
import streamlit as st
from services.supabase_client import get_supabase

st.set_page_config(
    page_title="Hostel Ops",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("🏛️ Hostel Ops — Connection Test")
st.caption("If you see a green box below, your Supabase connection is working.")

try:
    supabase = get_supabase()
    res = supabase.table("app_settings").select("key").execute()
    st.success(
        f"✅ Supabase reachable. Anon query returned {len(res.data)} rows "
        "(0 is expected and correct — RLS is blocking anonymous reads)."
    )
    st.json({"rows_returned": len(res.data), "data": res.data})
except Exception as e:
    st.error(f"❌ Connection failed: {type(e).__name__}")
    st.exception(e)

st.info(
    "Next step: we'll build the login page here. This test page will be "
    "replaced, not kept."
)
