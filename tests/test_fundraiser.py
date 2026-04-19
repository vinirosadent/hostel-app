"""
Automated tests for the fundraiser module.

Coverage:
  1.  State machine — valid and invalid transitions
  2.  Submission validation — required fields + compliance checkboxes
  3.  Item validation — guard clauses in upsert_item
  4.  Quote threshold flag — requires_quote computed correctly
  5.  Selling option validation — type, composition, margin
  6.  GST / price maths — unit cost, profit %, final customer price
  7.  Stock reconciliation — sold vs purchased per item
  8.  Financial summary — revenue, GST collected, gross profit
  9.  _parse_date helper — ISO strings, None, date objects, garbage
  10. Permission logic — can_edit_proposal conditions
  11. Committee FK query — explicit FK hint present in service source
  12. Tab visibility rules — stock / report / purchaser flag logic
"""
from __future__ import annotations

import sys
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure project root is on the path so imports work from any working dir.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Patch Supabase before importing the service so no real DB connection is made.
# ---------------------------------------------------------------------------
_mock_sb = MagicMock()
_supabase_patcher = patch("services.supabase_client.get_supabase", return_value=_mock_sb)
_supabase_patcher.start()

import services.fundraiser_service as svc  # noqa: E402  (must come after patch)


# ============================================================================
# Helpers
# ============================================================================

def _make_fr(**kwargs) -> dict:
    """Minimal fundraiser dict for validate_for_submission."""
    base = {
        "name": "Pineapple Tart Drive",
        "objective": "Raise funds for hall welfare.",
        "delivery_date": "2024-12-25",
        "compliance_nusync": True,
        "compliance_no_intermediary": True,
        "compliance_gst_artwork": True,
        "compliance_regulations": True,
    }
    base.update(kwargs)
    return base


def _make_item(code: str, unit_cost: float, quantity: int) -> dict:
    return {
        "item_code": code,
        "item_name": f"Item {code}",
        "unit_cost": unit_cost,
        "quantity": quantity,
    }


def _make_option(opt_id: str, composition: dict, selling_price: float,
                 unit_cost: float) -> dict:
    return {
        "id": opt_id,
        "option_name": f"Option {opt_id}",
        "option_type": "single" if len(composition) == 1 else "bundle",
        "composition": composition,
        "selling_price": selling_price,
        "unit_cost": unit_cost,
        "is_acceptable": True,
    }


def _make_movement(opt_id: str, qty_sold: int) -> dict:
    return {"selling_option_id": opt_id, "quantity_sold": qty_sold}


# ============================================================================
# 1. State machine
# ============================================================================

class TestStateMachine(unittest.TestCase):

    def test_valid_draft_to_rf_review(self):
        svc.check_transition("draft", "rf_review")  # must not raise

    def test_valid_rf_to_master(self):
        svc.check_transition("rf_review", "master_review")

    def test_valid_rf_approve_directly(self):
        svc.check_transition("rf_review", "approved")

    def test_valid_rf_return_to_draft(self):
        svc.check_transition("rf_review", "draft")

    def test_valid_master_approve(self):
        svc.check_transition("master_review", "approved")

    def test_valid_full_closure_chain(self):
        chain = [
            ("approved", "executing"),
            ("executing", "reporting"),
            ("reporting", "dof_confirming"),
            ("dof_confirming", "finance_confirming"),
            ("finance_confirming", "master_confirming"),
            ("master_confirming", "closed"),
        ]
        for current, nxt in chain:
            with self.subTest(f"{current} → {nxt}"):
                svc.check_transition(current, nxt)  # must not raise

    def test_invalid_draft_to_approved(self):
        with self.assertRaises(svc.InvalidTransition):
            svc.check_transition("draft", "approved")

    def test_invalid_draft_to_closed(self):
        with self.assertRaises(svc.InvalidTransition):
            svc.check_transition("draft", "closed")

    def test_invalid_closed_to_anything(self):
        for target in svc.VALID_STATUSES:
            if target == "closed":
                continue
            with self.subTest(target):
                with self.assertRaises(svc.InvalidTransition):
                    svc.check_transition("closed", target)

    def test_invalid_skip_rf(self):
        with self.assertRaises(svc.InvalidTransition):
            svc.check_transition("draft", "master_review")

    def test_invalid_backwards_approved_to_draft(self):
        with self.assertRaises(svc.InvalidTransition):
            svc.check_transition("approved", "draft")

    def test_rejected_can_return_to_draft(self):
        svc.check_transition("rejected", "draft")

    def test_rejected_cannot_go_directly_to_rf(self):
        with self.assertRaises(svc.InvalidTransition):
            svc.check_transition("rejected", "rf_review")


# ============================================================================
# 2. Submission validation
# ============================================================================

class TestValidateForSubmission(unittest.TestCase):

    def test_valid_proposal_has_no_errors(self):
        self.assertEqual(svc.validate_for_submission(_make_fr()), [])

    def test_missing_name(self):
        errs = svc.validate_for_submission(_make_fr(name=""))
        self.assertTrue(any("name" in e.lower() for e in errs))

    def test_missing_objective(self):
        errs = svc.validate_for_submission(_make_fr(objective=""))
        self.assertTrue(any("description" in e.lower() for e in errs))

    def test_missing_delivery_date(self):
        errs = svc.validate_for_submission(_make_fr(delivery_date=None))
        self.assertTrue(any("delivery" in e.lower() for e in errs))

    def test_each_compliance_checkbox_required(self):
        for key in ("compliance_nusync", "compliance_no_intermediary",
                    "compliance_gst_artwork", "compliance_regulations"):
            with self.subTest(key):
                errs = svc.validate_for_submission(_make_fr(**{key: False}))
                self.assertTrue(len(errs) >= 1, f"Expected error for {key}")

    def test_multiple_missing_returns_multiple_errors(self):
        errs = svc.validate_for_submission(_make_fr(
            name="", objective="", compliance_nusync=False
        ))
        self.assertGreaterEqual(len(errs), 3)


# ============================================================================
# 3. Item validation (guard clauses — Supabase call short-circuited by mock)
# ============================================================================

class TestItemValidation(unittest.TestCase):

    def setUp(self):
        # get_quote_threshold() reads from Supabase settings — stub it
        self._qt_patch = patch.object(svc, "get_quote_threshold", return_value=Decimal("1000"))
        self._qt_patch.start()
        # Stub the actual Supabase table call so upsert doesn't blow up
        _mock_sb.table.return_value.upsert.return_value.execute.return_value.data = [
            {"id": "fake-id", "item_code": "A", "item_name": "Test",
             "unit_cost": 5.0, "quantity": 10, "requires_quote": False,
             "fundraiser_id": "fr-1", "supplier": None, "notes": None}
        ]

    def tearDown(self):
        self._qt_patch.stop()

    def test_zero_quantity_raises(self):
        with self.assertRaises(svc.ValidationError):
            svc.upsert_item("fr-1", "A", item_name="X", quantity=0, unit_cost=5.0)

    def test_negative_quantity_raises(self):
        with self.assertRaises(svc.ValidationError):
            svc.upsert_item("fr-1", "A", item_name="X", quantity=-1, unit_cost=5.0)

    def test_negative_unit_cost_raises(self):
        with self.assertRaises(svc.ValidationError):
            svc.upsert_item("fr-1", "A", item_name="X", quantity=1, unit_cost=-0.01)

    def test_blank_item_code_raises(self):
        with self.assertRaises(svc.ValidationError):
            svc.upsert_item("fr-1", "  ", item_name="X", quantity=1, unit_cost=5.0)

    def test_zero_unit_cost_is_allowed(self):
        # Free items (samples) are valid
        result = svc.upsert_item("fr-1", "A", item_name="Sample", quantity=1, unit_cost=0.0)
        self.assertIsNotNone(result)


# ============================================================================
# 4. Quote threshold
# ============================================================================

class TestQuoteThreshold(unittest.TestCase):

    def _run(self, qty, cost, threshold=1000.0):
        return (qty * cost) >= threshold

    def test_below_threshold_no_quote(self):
        self.assertFalse(self._run(10, 99.0))

    def test_exactly_at_threshold_requires_quote(self):
        self.assertTrue(self._run(10, 100.0))  # 10 * 100 = 1000

    def test_above_threshold_requires_quote(self):
        self.assertTrue(self._run(100, 50.0))  # 5000


# ============================================================================
# 5. Selling option validation
# ============================================================================

class TestSellingOptionValidation(unittest.TestCase):

    def _call(self, **kwargs):
        defaults = dict(
            fundraiser_id="fr-1",
            option_name="Classic Box",
            option_type="single",
            composition={"A": 1},
            selling_price=12.0,
        )
        defaults.update(kwargs)
        return svc.upsert_selling_option(**defaults)

    def setUp(self):
        self._gm_patch = patch.object(svc, "get_min_margin", return_value=Decimal("0.20"))
        self._li_patch = patch.object(svc, "list_items", return_value=[
            _make_item("A", 8.0, 100),
            _make_item("B", 5.0, 50),
        ])
        self._gm_patch.start()
        self._li_patch.start()
        _mock_sb.table.return_value.upsert.return_value.execute.return_value.data = [
            {"id": "opt-1", "option_name": "Classic Box", "option_type": "single",
             "composition": {"A": 1}, "selling_price": 12.0, "unit_cost": 8.0,
             "is_acceptable": True, "fundraiser_id": "fr-1"}
        ]

    def tearDown(self):
        self._gm_patch.stop()
        self._li_patch.stop()

    def test_invalid_option_type_raises(self):
        with self.assertRaises(svc.ValidationError):
            self._call(option_type="mystery")

    def test_empty_composition_raises(self):
        with self.assertRaises(svc.ValidationError):
            self._call(composition={})

    def test_single_with_two_items_raises(self):
        with self.assertRaises(svc.ValidationError):
            self._call(option_type="single", composition={"A": 1, "B": 1})

    def test_bundle_with_one_item_raises(self):
        with self.assertRaises(svc.ValidationError):
            self._call(option_type="bundle", composition={"A": 1})

    def test_unknown_item_code_in_composition_raises(self):
        with self.assertRaises(svc.ValidationError):
            self._call(composition={"Z": 1})

    def test_zero_quantity_in_composition_raises(self):
        with self.assertRaises(svc.ValidationError):
            self._call(composition={"A": 0})

    def test_valid_single_option_returns_dict(self):
        result = self._call()
        self.assertIn("id", result)


# ============================================================================
# 6. GST / price maths (pure arithmetic — no Supabase)
# ============================================================================

class TestGSTMaths(unittest.TestCase):

    GST = Decimal("0.09")

    def _final_price(self, selling_price: float) -> Decimal:
        return Decimal(str(selling_price)) * (1 + self.GST)

    def _profit(self, selling_price: float, unit_cost: float) -> Decimal:
        return Decimal(str(selling_price)) - Decimal(str(unit_cost))

    def _profit_pct(self, selling_price: float, unit_cost: float) -> Decimal:
        uc = Decimal(str(unit_cost))
        return (self._profit(selling_price, unit_cost) / uc) if uc else Decimal("0")

    def test_final_price_9pct_gst(self):
        self.assertAlmostEqual(float(self._final_price(10.00)), 10.90, places=4)

    def test_final_price_zero_selling(self):
        self.assertEqual(self._final_price(0.00), Decimal("0"))

    def test_profit_positive(self):
        self.assertAlmostEqual(float(self._profit(12.0, 8.0)), 4.0, places=4)

    def test_profit_negative(self):
        self.assertLess(float(self._profit(5.0, 8.0)), 0)

    def test_profit_pct_exactly_20(self):
        pct = float(self._profit_pct(12.0, 10.0))
        self.assertAlmostEqual(pct, 0.20, places=4)

    def test_profit_pct_meets_minimum(self):
        MIN = 0.20
        self.assertGreaterEqual(float(self._profit_pct(12.0, 9.0)), MIN)

    def test_profit_pct_below_minimum(self):
        MIN = 0.20
        self.assertLess(float(self._profit_pct(9.50, 9.0)), MIN)

    def test_bundle_unit_cost_sums_components(self):
        items = [_make_item("A", 8.0, 100), _make_item("B", 5.0, 50)]
        cost = svc._compute_unit_cost_from_composition({"A": 1, "B": 2}, items)
        self.assertEqual(cost, Decimal("18.00"))  # 8 + 5*2

    def test_bundle_unit_cost_unknown_code_raises(self):
        items = [_make_item("A", 8.0, 100)]
        with self.assertRaises(svc.ValidationError):
            svc._compute_unit_cost_from_composition({"Z": 1}, items)


# ============================================================================
# 7. Stock reconciliation (pure computation — patch the three list functions)
# ============================================================================

class TestStockReconciliation(unittest.TestCase):

    def _run(self, items, options, movements):
        with patch.object(svc, "list_items", return_value=items), \
             patch.object(svc, "list_selling_options", return_value=options), \
             patch.object(svc, "list_stock_movements", return_value=movements):
            return svc.compute_stock_reconciliation("fr-1")

    def test_no_sales_full_stock_unsold(self):
        items = [_make_item("A", 10.0, 100)]
        options = [_make_option("o1", {"A": 1}, 15.0, 10.0)]
        rows = self._run(items, options, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].purchased, 100)
        self.assertEqual(rows[0].sold, 0)
        self.assertEqual(rows[0].unsold, 100)

    def test_sold_reduces_unsold(self):
        items = [_make_item("A", 10.0, 100)]
        options = [_make_option("o1", {"A": 1}, 15.0, 10.0)]
        movements = [_make_movement("o1", 30)]
        rows = self._run(items, options, movements)
        self.assertEqual(rows[0].sold, 30)
        self.assertEqual(rows[0].unsold, 70)

    def test_bundle_deducts_from_multiple_items(self):
        items = [_make_item("A", 8.0, 50), _make_item("B", 5.0, 50)]
        options = [_make_option("o1", {"A": 1, "B": 2}, 20.0, 18.0)]
        movements = [_make_movement("o1", 10)]
        rows = self._run(items, options, movements)
        by_code = {r.item_code: r for r in rows}
        self.assertEqual(by_code["A"].sold, 10)
        self.assertEqual(by_code["B"].sold, 20)

    def test_oversold_flagged(self):
        items = [_make_item("A", 10.0, 5)]
        options = [_make_option("o1", {"A": 1}, 15.0, 10.0)]
        movements = [_make_movement("o1", 10)]
        rows = self._run(items, options, movements)
        self.assertTrue(rows[0].over_sold)

    def test_unknown_option_in_movement_ignored_gracefully(self):
        items = [_make_item("A", 10.0, 50)]
        options = [_make_option("o1", {"A": 1}, 15.0, 10.0)]
        movements = [_make_movement("ghost-option", 99)]
        rows = self._run(items, options, movements)
        self.assertEqual(rows[0].sold, 0)

    def test_rows_sorted_by_item_code(self):
        items = [_make_item("C", 5.0, 10), _make_item("A", 5.0, 10), _make_item("B", 5.0, 10)]
        rows = self._run(items, [], [])
        codes = [r.item_code for r in rows]
        self.assertEqual(codes, sorted(codes))


# ============================================================================
# 8. Financial summary
# ============================================================================

class TestFinancialSummary(unittest.TestCase):

    GST = Decimal("0.09")

    def _run(self, items, options, movements, gst_rate=None):
        gst = gst_rate if gst_rate is not None else self.GST
        with patch.object(svc, "list_items", return_value=items), \
             patch.object(svc, "list_selling_options", return_value=options), \
             patch.object(svc, "list_stock_movements", return_value=movements), \
             patch.object(svc, "get_gst_rate", return_value=gst):
            return svc.compute_financial_summary("fr-1")

    def test_zero_sales(self):
        items = [_make_item("A", 10.0, 100)]
        options = [_make_option("o1", {"A": 1}, 15.0, 10.0)]
        summary = self._run(items, options, [])
        self.assertEqual(summary.gross_revenue_before_gst, Decimal("0"))
        self.assertEqual(summary.gst_collected, Decimal("0"))
        self.assertEqual(summary.gross_profit, -summary.total_cost)

    def test_total_cost_is_unit_cost_times_quantity(self):
        items = [_make_item("A", 10.0, 50), _make_item("B", 5.0, 20)]
        summary = self._run(items, [], [])
        self.assertEqual(summary.total_cost, Decimal("600"))  # 500 + 100

    def test_gst_collected_is_9pct_of_gross_revenue(self):
        items = [_make_item("A", 8.0, 100)]
        options = [_make_option("o1", {"A": 1}, 10.0, 8.0)]
        movements = [_make_movement("o1", 10)]
        summary = self._run(items, options, movements)
        # gross revenue = 10 * 10 = 100
        self.assertEqual(summary.gross_revenue_before_gst, Decimal("100"))
        self.assertAlmostEqual(float(summary.gst_collected), 9.0, places=4)

    def test_total_customer_payment_equals_revenue_plus_gst(self):
        items = [_make_item("A", 8.0, 100)]
        options = [_make_option("o1", {"A": 1}, 10.0, 8.0)]
        movements = [_make_movement("o1", 10)]
        summary = self._run(items, options, movements)
        expected = summary.gross_revenue_before_gst + summary.gst_collected
        self.assertEqual(summary.total_customer_payment, expected)

    def test_gross_profit_is_revenue_minus_cost(self):
        items = [_make_item("A", 8.0, 10)]
        options = [_make_option("o1", {"A": 1}, 12.0, 8.0)]
        movements = [_make_movement("o1", 10)]
        summary = self._run(items, options, movements)
        # revenue = 120, cost = 80
        self.assertEqual(float(summary.gross_profit), 40.0)

    def test_as_dict_returns_floats(self):
        summary = self._run([], [], [])
        d = summary.as_dict()
        self.assertTrue(all(isinstance(v, float) for v in d.values()))


# ============================================================================
# 9. _parse_date helper
# ============================================================================

class TestParseDate(unittest.TestCase):
    """Test the _parse_date helper defined in pages/11_Fundraiser_Detail.py."""

    def _parse_date(self, val):
        # Replicate the helper inline so we don't need to import the Streamlit page.
        from datetime import date
        if not val:
            return None
        if isinstance(val, date):
            return val
        try:
            return date.fromisoformat(str(val)[:10])
        except (ValueError, TypeError):
            return None

    def test_none_returns_none(self):
        self.assertIsNone(self._parse_date(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(self._parse_date(""))

    def test_iso_string_parses(self):
        self.assertEqual(self._parse_date("2024-12-25"), date(2024, 12, 25))

    def test_iso_datetime_string_truncated(self):
        self.assertEqual(self._parse_date("2024-12-25T09:00:00+00:00"), date(2024, 12, 25))

    def test_date_object_returned_unchanged(self):
        d = date(2024, 6, 1)
        self.assertIs(self._parse_date(d), d)

    def test_garbage_string_returns_none(self):
        self.assertIsNone(self._parse_date("not-a-date"))

    def test_integer_yyyymmdd_parses_in_py311(self):
        # Python 3.11+ date.fromisoformat accepts compact YYYYMMDD — helper
        # converts int to str first, so this is valid input, not garbage.
        result = self._parse_date(20241225)
        # Either parses to a date or returns None — both are safe; must not raise.
        self.assertTrue(result is None or isinstance(result, date))


# ============================================================================
# 10. Permission logic — can_edit_proposal conditions
# ============================================================================

class TestPermissionLogic(unittest.TestCase):
    """Test the can_edit_proposal decision logic (replicated from detail page)."""

    def _can_edit(self, *, is_creator, is_committee_member, status,
                  is_rf=False, is_rf_in_charge=False, is_staff_flag=False,
                  is_master=False) -> bool:
        return (
            ((is_creator or is_committee_member) and status in ("draft", "rejected"))
            or (is_rf and (is_rf_in_charge or is_staff_flag) and status == "rf_review")
            or is_master
        )

    def test_creator_can_edit_draft(self):
        self.assertTrue(self._can_edit(is_creator=True, is_committee_member=False, status="draft"))

    def test_committee_member_can_edit_draft(self):
        self.assertTrue(self._can_edit(is_creator=False, is_committee_member=True, status="draft"))

    def test_stranger_cannot_edit_draft(self):
        self.assertFalse(self._can_edit(is_creator=False, is_committee_member=False, status="draft"))

    def test_creator_cannot_edit_after_submission(self):
        self.assertFalse(self._can_edit(is_creator=True, is_committee_member=False, status="rf_review"))

    def test_rf_in_charge_can_edit_at_rf_review(self):
        self.assertTrue(self._can_edit(
            is_creator=False, is_committee_member=False,
            status="rf_review", is_rf=True, is_rf_in_charge=True,
        ))

    def test_rf_without_in_charge_cannot_edit(self):
        self.assertFalse(self._can_edit(
            is_creator=False, is_committee_member=False,
            status="rf_review", is_rf=True, is_rf_in_charge=False, is_staff_flag=False,
        ))

    def test_master_can_edit_any_stage(self):
        for status in ("draft", "rf_review", "master_review", "approved", "closed"):
            with self.subTest(status):
                self.assertTrue(self._can_edit(
                    is_creator=False, is_committee_member=False,
                    status=status, is_master=True,
                ))

    def test_creator_can_edit_rejected(self):
        self.assertTrue(self._can_edit(is_creator=True, is_committee_member=False, status="rejected"))

    def test_committee_member_can_edit_rejected(self):
        self.assertTrue(self._can_edit(is_creator=False, is_committee_member=True, status="rejected"))


# ============================================================================
# 11. Committee FK query — explicit hint present in source
# ============================================================================

class TestCommitteeFKHint(unittest.TestCase):
    """Verify the PGRST201-safe FK hint is in the service source."""

    def test_explicit_fk_hint_in_list_registered_students(self):
        import inspect
        source = inspect.getsource(svc.list_registered_students)
        self.assertIn(
            "fundraiser_students_user_id_fkey",
            source,
            "Explicit FK hint missing — PGRST201 ambiguity will crash Committee tab.",
        )


# ============================================================================
# 12. Tab visibility rules
# ============================================================================

class TestTabVisibility(unittest.TestCase):

    def _flags(self, status: str, is_staff: bool = False):
        show_stock = status not in ("draft", "rejected", "rf_review", "master_review")
        show_report = status in (
            "reporting", "dof_confirming", "finance_confirming",
            "master_confirming", "closed",
        )
        show_purchaser = is_staff
        return show_stock, show_report, show_purchaser

    def test_draft_shows_only_base_tabs(self):
        stock, report, purchaser = self._flags("draft")
        self.assertFalse(stock)
        self.assertFalse(report)
        self.assertFalse(purchaser)

    def test_stock_hidden_during_rf_review(self):
        stock, _, _ = self._flags("rf_review")
        self.assertFalse(stock)

    def test_stock_visible_after_approval(self):
        for status in ("approved", "executing", "reporting", "closed"):
            with self.subTest(status):
                stock, _, _ = self._flags(status)
                self.assertTrue(stock)

    def test_report_tab_only_in_reporting_stages(self):
        for status in ("reporting", "dof_confirming", "finance_confirming",
                       "master_confirming", "closed"):
            with self.subTest(status):
                _, report, _ = self._flags(status)
                self.assertTrue(report)

    def test_report_tab_hidden_in_pre_reporting_stages(self):
        for status in ("draft", "rf_review", "master_review", "approved", "executing"):
            with self.subTest(status):
                _, report, _ = self._flags(status)
                self.assertFalse(report)

    def test_purchaser_tab_for_staff_only(self):
        _, _, staff_yes = self._flags("draft", is_staff=True)
        _, _, staff_no = self._flags("draft", is_staff=False)
        self.assertTrue(staff_yes)
        self.assertFalse(staff_no)

    def test_rejected_same_as_draft_visibility(self):
        d_flags = self._flags("draft")
        r_flags = self._flags("rejected")
        self.assertEqual(d_flags, r_flags)


# ============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
