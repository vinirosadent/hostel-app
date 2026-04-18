# Hostel Ops

Hostel management system — Streamlit frontend + Supabase backend.

## Modules
- Shared calendar
- Fundraiser workflow (proposal -> execution -> reporting)
- Event budgeting (pre/post event)
- Expense reimbursements with receipt uploads
- Sanction alert tracking (ICF status only; documents live in Teams)
- Admin panel (users, roles, scoped permissions)

## Local setup
1. Clone this repository
2. Create a Python virtual environment: `py -m venv venv`
3. Activate it: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill with real values
6. Run the app: `streamlit run app.py`

## Status
In active development — bootstrap phase.
