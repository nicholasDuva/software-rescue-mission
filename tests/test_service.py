"""Added tests for Campus Supply Desk, grouped by testing category.

Expected values come from System Understanding Note.md, not from the current
implementation. A failing test points at a suspected defect; it must not be
"fixed" by changing the expected value.
"""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from supplydesk import cli
from supplydesk.menu import run_menu
from supplydesk.service import OrderService


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


class ServiceTestCase(unittest.TestCase):
    """Gives every test its own temporary save file."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def stock(self, product_id):
        for product in self.service.catalog():
            if product["product_id"] == product_id:
                return product["stock"]
        raise AssertionError("product not in catalog: " + product_id)

    def file_bytes(self):
        return self.path.read_bytes() if self.path.exists() else None


# ---------------------------------------------------------------------------
# Category 1: normal behaviour with valid inputs
# ---------------------------------------------------------------------------
class NormalBehaviourTests(ServiceTestCase):

    def test_quote_returns_full_line_details_for_multiple_items(self):
        quote = self.service.quote("regular", [item("notebook", 2), item("mug", 1)])
        self.assertEqual(quote["items"], [
            {"product_id": "notebook", "name": "Notebook", "unit_price_cents": 500,
             "quantity": 2, "line_total_cents": 1000},
            {"product_id": "mug", "name": "Campus mug", "unit_price_cents": 1500,
             "quantity": 1, "line_total_cents": 1500},
        ])
        self.assertEqual(quote["subtotal_cents"], 2500)
        self.assertEqual(quote["total_cents"], 2500)

    def test_place_order_deducts_stock_and_records_order(self):
        first = self.service.place_order("student", [item("hoodie", 2)], "delivery")
        second = self.service.place_order("regular", [item("hoodie", 1)])
        self.assertEqual((first["order_id"], first["status"], first["total_cents"]),
                         ("ORD-0001", "placed", 7800))
        self.assertEqual(second["order_id"], "ORD-0002")
        self.assertEqual(self.stock("hoodie"), 2)
        self.assertEqual(self.service.list_orders(), [first, second])


# ---------------------------------------------------------------------------
# Category 2: boundary behaviour
# ---------------------------------------------------------------------------
class BoundaryTests(ServiceTestCase):

    def test_student_discount_applies_at_exactly_5000_cents(self):
        # Spec: 10% discount when the subtotal is AT LEAST 5,000 cents.
        quote = self.service.quote("student", [item("bag", 2)])
        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    def test_delivery_threshold_at_10000_cents_after_discount(self):
        # Exactly 10,000 -> free delivery.
        at_limit = self.service.quote("regular", [item("bag", 4)], "delivery")
        self.assertEqual(at_limit["delivery_cents"], 0)
        # Subtotal 11,000 but only 9,900 after the student discount -> delivery charged.
        below = self.service.quote(
            "student", [item("hoodie", 2), item("bag", 1), item("notebook", 1)], "delivery")
        self.assertEqual(below["discount_cents"], 1100)
        self.assertEqual(below["delivery_cents"], 600)
        self.assertEqual(below["total_cents"], 10500)

    def test_quantity_limits(self):
        self.assertEqual(self.service.quote("regular", [item("notebook", 1)])["total_cents"], 500)
        for quantity in (0, -1, 100):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    self.service.quote("regular", [item("notebook", quantity)])

    def test_ordering_all_remaining_stock_then_one_more(self):
        self.service.place_order("regular", [item("hoodie", 5)])
        self.assertEqual(self.stock("hoodie"), 0)
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("hoodie", 1)])
        self.assertEqual(self.stock("hoodie"), 0)

    def test_duplicate_lines_combined_over_stock_are_rejected(self):
        # Spec: combined quantity for a product must not exceed its stock (bag stock = 4).
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("bag", 3), item("bag", 3)])
        self.assertEqual(self.stock("bag"), 4)


# ---------------------------------------------------------------------------
# Category 3: invalid or exceptional behaviour
# ---------------------------------------------------------------------------
class InvalidInputTests(ServiceTestCase):

    def test_non_integer_quantities_are_rejected(self):
        # Spec: booleans, fractional numbers and numeric strings are not valid quantities.
        for quantity in (True, 2.0, "2", None):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    self.service.quote("regular", [item("notebook", quantity)])

    def test_cancelling_a_cancelled_order_changes_nothing(self):
        # Spec: returns the existing cancelled order without changing stock again.
        order = self.service.place_order("regular", [item("mug", 1)])
        self.service.cancel_order(order["order_id"])
        again = self.service.cancel_order(order["order_id"])
        self.assertEqual(again["status"], "cancelled")
        self.assertEqual(self.stock("mug"), 8)

    def test_malformed_save_file_raises_instead_of_resetting(self):
        self.path.write_text("{ this is not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("notebook", 1)])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{ this is not json")


# ---------------------------------------------------------------------------
# Category 4: behaviour to preserve during refactoring
# (planned refactoring: remove the duplicated validation/pricing code in
#  quote() and place_order(), and the repeated catalog-lookup loops)
# ---------------------------------------------------------------------------
class PreservedBehaviourTests(ServiceTestCase):

    def test_quote_and_placed_order_have_identical_pricing(self):
        requests = [
            ("regular", [item("notebook", 2)], "pickup"),
            ("student", [item("hoodie", 2)], "delivery"),
            ("student", [item("pen-pack", 3), item("mug", 1), item("pen-pack", 1)], "delivery"),
        ]
        for number, (customer, items, fulfillment) in enumerate(requests):
            with self.subTest(customer=customer, items=items, fulfillment=fulfillment):
                service = OrderService(Path(self.directory.name) / f"s{number}.json")
                quote = service.quote(customer, items, fulfillment)
                order = service.place_order(customer, items, fulfillment)
                for key in ("items", "subtotal_cents", "discount_cents",
                            "delivery_cents", "total_cents"):
                    self.assertEqual(order[key], quote[key], key)

    def test_quote_does_not_save_or_use_an_order_id(self):
        quote = self.service.quote("regular", [item("notebook", 1)])
        self.assertNotIn("order_id", quote)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.place_order("regular", [item("notebook", 1)])["order_id"],
                         "ORD-0001")

    def test_invalid_requests_leave_saved_data_unchanged(self):
        self.service.place_order("regular", [item("notebook", 2)])
        snapshot = self.file_bytes()
        bad_requests = [
            ("regular", [item("widget", 1)], "pickup"),
            ("staff", [item("notebook", 1)], "pickup"),
            ("regular", [item("notebook", 1)], "courier"),
            ("regular", [item("notebook", 1), item("bag", 50)], "pickup"),
        ]
        for request in bad_requests:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    self.service.place_order(*request)
                self.assertEqual(self.file_bytes(), snapshot)
        self.assertEqual(self.service.place_order("regular", [item("mug", 1)])["order_id"],
                         "ORD-0002")

    def test_cli_json_output_and_exit_statuses(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ok = cli.main(["--data", str(self.path), "place", "--item", "mug:1"])
            rejected = cli.main(["--data", str(self.path), "place", "--item", "widget:1"])
        self.assertEqual(ok, 0)
        self.assertEqual(json.loads(out.getvalue())["total_cents"], 1500)
        self.assertEqual(rejected, 2)
        self.assertTrue(err.getvalue().startswith("Error: "))

    def test_menu_declined_placement_saves_nothing(self):
        answers = ["3", "student", "hoodie", "2", "", "delivery", "n", "0"]
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(out):
            status = run_menu(self.service)
        self.assertEqual(status, 0)
        self.assertIn("Total: $78.00", out.getvalue())
        self.assertIn("Order not placed.", out.getvalue())
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
