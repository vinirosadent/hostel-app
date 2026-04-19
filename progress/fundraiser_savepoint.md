# Fundraiser Module — Implementation Savepoint

Last updated: 2026-04-19

---

## VERIFIED DONE

### components/auth_ui.py
- Sidebar fully rewritten with emoji labels (🏠, 💰, ⚙️, 🔒, ↩)
- No `:material/` icon tokens remain
- No duplicated label text (homeHome-style bug fixed)
- No "arrow" artifact
- Role-based Admin button (master only)
- Proper user info block with name, role, assigned block
- "Navigation" section header
- Change Password + Sign out below divider

### services/fundraiser_service.py
- `list_registered_students` FK ambiguity fixed:
  `users!fundraiser_students_user_id_fkey(username, full_name)`
- This fixes PGRST201 crash affecting Committee, Items, Selling Options tabs

### pages/11_Fundraiser_Detail.py (1990 lines, all syntax OK)
- No `:material/` icons anywhere
- No `pip install fpdf2` message shown to users
- PDF expander moved to BOTTOM of page (after workflow action bar)
- PDF fallback: `st.caption("PDF export is not available on this deployment.")`
- "Proposal is locked — status: Draft" replaced with neutral read-only notice
- `can_edit_proposal` expanded: creator OR committee member can edit in draft/rejected
- Dynamic tabs: only 6 proposal tabs shown during Draft
- Stock Movement hidden until after Master approval (`_show_stock`)
- Report Confirmations hidden until reporting stage (`_show_report`)
- Purchaser List hidden for non-staff (`_show_purchaser`)
- Submit to RF action placed in Selling Options tab (spec G)
- Workflow action bar kept for RF/Master actions only (no student submit there)
- Timeline labels: "Drafting", "Submitted to RF", "Approved by RF", "Approved by The Master"
- Appendix Marketing and Appendix Artwork: gallery renderer + upload form
- Item linking for product_design type assets
- Compliance checkboxes on Proposal tab
- Auto-calculated flyer removal (delivery+7d) and report deadline (delivery+21d)
- Stock reconciliation + financial summary in Stock Movement tab
- RF closure checklist + sequential confirmation chain

### static/styles.css
- `.sh-pb-label` text-transform changed from `uppercase` to `none`
- Letter-spacing normalized
- Max-width slightly increased for longer labels like "Approved by The Master"

---

## PARTIALLY DONE / TO VERIFY AT RUNTIME

- `st.date_input` with string values from Supabase (Streamlit 1.56 should handle this)
- `register_student` does not pass `added_by` — may fail if column is NOT NULL
- Supabase Storage bucket `fundraiser-assets` must exist for appendix uploads
- `fpdf2` must be installed for PDF export to work

---

## NOT IMPLEMENTED / OUT OF SCOPE

- NUSync integration (payment channel)
- Real-time notifications
- Email notifications on status transitions
- File size validation on uploads (client-side)

---

## NEXT STEP IF RESUMING

1. Start the app: `streamlit run app.py`
2. Login as a student user
3. Open "Pineapple Tart Christmas Drive"
4. Verify: 6 proposal tabs visible, all editable, no crash
5. Check sidebar: emoji icons, no raw text
6. Submit to RF from Selling Options tab
7. Login as RF, verify review flow
8. Login as Master, verify approval flow
9. After Master approval: verify Stock Movement tab appears

---

## FILES CHANGED (this session)
- `services/fundraiser_service.py` — FK fix line 626
- `components/auth_ui.py` — emoji sidebar
- `pages/11_Fundraiser_Detail.py` — full rewrite (1990 lines)
- `static/styles.css` — `.sh-pb-label` text-transform fix
- `progress/fundraiser_savepoint.md` — this file
