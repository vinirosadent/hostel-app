"""
Supabase client singleton.

Two clients:
- `get_supabase()`: uses the anon key. All user-driven operations go here.
  RLS enforces access. This is what 99% of the app uses.
- `get_supabase_admin()`: uses the service_role key. Bypasses RLS.
  Used ONLY for admin user creation. Never expose its output to the UI
  without filtering.
"""
import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase() -> Client:
    """Anon client — respects RLS. Default client."""
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)


@st.cache_resource
def get_supabase_admin() -> Client:
    """Service-role client — bypasses RLS. Admin operations only."""
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_role_key"]
    return create_client(url, key)


def get_username_email(username: str) -> str:
    """
    Supabase Auth requires an email. We synthesize one from the username
    using a domain the user never sees. E.g. 'alice' -> 'alice@hostel.local'
    """
    domain = st.secrets["app"]["username_email_domain"]
    return f"{username.lower().strip()}@{domain}"
