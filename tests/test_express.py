"""Tests for CR-01: express delivery.

Expected values come from CR-01.md and System Understanding Note.md, not from
the implementation.
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


class ExpressTestCase(unittest.TestCase):
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

    def amounts(self, priced):
        return (priced["subtotal_cents"], priced["discount_cents"],
                priced["delivery_cents"], priced["total_cents"])


class ExpressPricingTests(ExpressTestCase):

    def test_cr01_example_regular_two_notebooks(self):
        # $10 merchandise + $12 express = $22.
        quote = self.service.quote("regular", [item("notebook", 2)], "express")
        self.assertEqual(quote["fulfillment"], "express")
        self.assertEqual(self.amounts(quote), (1000, 0, 1200, 2200))

    def test_cr01_example_student_two_hoodies(self):
        # $80 merchandise - $8 discount + $12 express = $84.
        quote = self.service.quote("student", [item("hoodie", 2)], "express")
        self.assertEqual(self.amounts(quote), (8000, 800, 1200, 8400))

    def test_cr01_example_three_hoodies_standard_versus_express(self):
        standard = self.service.quote("regular", [item("hoodie", 3)], "delivery")
        express = self.service.quote("regular", [item("hoodie", 3)], "express")
        self.assertEqual(self.amounts(standard), (12000, 0, 0, 12000))
        self.assertEqual(self.amounts(express), (12000, 0, 1200, 13200))

    def test_express_fee_is_never_waived(self):
        # Far above the 10,000-cent free-delivery threshold, and exactly at it.
        large = self.service.quote(
            "regular", [item("hoodie", 5), item("bag", 4), item("mug", 8)], "express")
        self.assertEqual(large["delivery_cents"], 1200)
        self.assertEqual(large["total_cents"], large["subtotal_cents"] + 1200)
        at_limit = self.service.quote("regular", [item("bag", 4)], "express")
        self.assertEqual(self.amounts(at_limit), (10000, 0, 1200, 11200))

    def test_student_discount_is_unchanged_and_excludes_the_fee(self):
        # At exactly 5,000 cents the discount applies, to merchandise only.
        at_threshold = self.service.quote("student", [item("bag", 2)], "express")
        self.assertEqual(self.amounts(at_threshold), (5000, 500, 1200, 5700))
        # Just below the threshold: no discount, even though the fee lifts the total above it.
        below = self.service.quote(
            "student", [item("bag", 1), item("mug", 1), item("pen-pack", 1)], "express")
        self.assertEqual(self.amounts(below), (4750, 0, 1200, 5950))

    def test_discount_rounding_is_unchanged_with_express(self):
        # Half a cent rounds up: 10% of 50,050 cents is 5,005; of 5,005 cents is 500.5 -> 501.
        self.path.write_text(json.dumps({
            "schema_version": 1, "next_order_number": 1, "orders": [],
            "catalog": [{"product_id": "odd", "name": "Odd", "unit_price_cents": 5005,
                         "stock": 50}],
        }), encoding="utf-8")
        quote = self.service.quote("student", [item("odd", 1)], "express")
        self.assertEqual(self.amounts(quote), (5005, 501, 1200, 5704))

    def test_pickup_and_standard_delivery_are_unchanged(self):
        cases = [
            ("regular", [item("notebook", 2)], "pickup", (1000, 0, 0, 1000)),
            ("student", [item("hoodie", 2)], "delivery", (8000, 800, 600, 7800)),
            ("regular", [item("bag", 4)], "delivery", (10000, 0, 0, 10000)),
            ("regular", [item("hoodie", 3)], "delivery", (12000, 0, 0, 12000)),
        ]
        for customer, items, fulfillment, expected in cases:
            with self.subTest(customer=customer, fulfillment=fulfillment):
                quote = self.service.quote(customer, items, fulfillment)
                self.assertEqual(self.amounts(quote), expected)


class ExpressOrderTests(ExpressTestCase):

    def test_quote_and_placed_express_order_agree(self):
        items = [item("pen-pack", 3), item("mug", 1), item("pen-pack", 1)]
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")
        for key in ("customer_type", "fulfillment", "items", "subtotal_cents",
                    "discount_cents", "delivery_cents", "total_cents"):
            self.assertEqual(order[key], quote[key], key)

    def test_express_order_is_retained_when_retrieved_reopened_and_cancelled(self):
        order = self.service.place_order("student", [item("hoodie", 2)], "express")
        self.assertEqual((order["order_id"], order["status"]), ("ORD-0001", "placed"))
        self.assertEqual(self.stock("hoodie"), 3)

        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order("ORD-0001"), order)
        self.assertEqual(reopened.list_orders(), [order])

        cancelled = reopened.cancel_order("ORD-0001")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.stock("hoodie"), 5)
        kept = {key: value for key, value in order.items() if key != "status"}
        after = OrderService(self.path).get_order("ORD-0001")
        self.assertEqual({key: value for key, value in after.items() if key != "status"}, kept)
        self.assertEqual(after["fulfillment"], "express")
        self.assertEqual(self.amounts(after), (8000, 800, 1200, 8400))

    def test_numbering_stock_and_history_work_across_fulfillment_options(self):
        first = self.service.place_order("regular", [item("bag", 1)], "pickup")
        second = self.service.place_order("regular", [item("bag", 1)], "express")
        third = self.service.place_order("regular", [item("bag", 1)], "delivery")
        self.assertEqual([o["order_id"] for o in (first, second, third)],
                         ["ORD-0001", "ORD-0002", "ORD-0003"])
        self.assertEqual(self.stock("bag"), 1)
        with self.assertRaises(ValueError):  # stock rules apply to express as well
            self.service.place_order("regular", [item("bag", 2)], "express")
        self.assertEqual([o["fulfillment"] for o in self.service.list_orders()],
                         ["pickup", "express", "delivery"])


class ExpressValidationTests(ExpressTestCase):

    def test_other_fulfillment_values_remain_invalid(self):
        self.service.place_order("regular", [item("notebook", 1)])
        snapshot = self.path.read_bytes()
        for fulfillment in ("Express", "EXPRESS", " express", "courier", "", None):
            with self.subTest(fulfillment=fulfillment):
                with self.assertRaises(ValueError):
                    self.service.quote("regular", [item("notebook", 1)], fulfillment)
                with self.assertRaises(ValueError):
                    self.service.place_order("regular", [item("notebook", 1)], fulfillment)
                self.assertEqual(self.path.read_bytes(), snapshot)

    def test_invalid_express_request_changes_nothing(self):
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("hoodie", 6)], "express")
        self.assertFalse(self.path.exists())

    def test_default_fulfillment_is_still_pickup(self):
        quote = self.service.quote("regular", [item("notebook", 2)])
        self.assertEqual((quote["fulfillment"], quote["delivery_cents"]), ("pickup", 0))


class ExpressInterfaceTests(ExpressTestCase):

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                status = cli.main(["--data", str(self.path), *args])
            except SystemExit as stop:  # argparse exits on --help and invalid choices
                status = stop.code
        return status, out.getvalue(), err.getvalue()

    def test_cli_example_command_from_cr01(self):
        status, out, _ = self.run_cli(
            "quote", "--customer", "student", "--fulfillment", "express", "--item", "hoodie:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 8400)

    def test_cli_place_express_and_show_it(self):
        status, out, _ = self.run_cli("place", "--fulfillment", "express", "--item", "notebook:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 2200)
        status, out, _ = self.run_cli("show", "ORD-0001")
        self.assertEqual((status, json.loads(out)["fulfillment"]), (0, "express"))

    def test_cli_help_lists_express_and_invalid_values_are_rejected(self):
        for command in ("quote", "place"):
            with self.subTest(command=command):
                status, out, _ = self.run_cli(command, "--help")
                self.assertEqual(status, 0)
                self.assertIn("{pickup,delivery,express}", out)
                self.assertIn("1200", out)
        status, _, err = self.run_cli("quote", "--fulfillment", "courier", "--item", "mug:1")
        self.assertEqual(status, 2)
        self.assertIn("invalid choice", err)

    def test_menu_prompt_lists_express_and_places_an_express_order(self):
        answers = ["3", "student", "hoodie", "2", "", "express", "y", "0"]
        prompts = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return answers.pop(0)

        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=fake_input), \
                contextlib.redirect_stdout(out):
            status = run_menu(self.service)
        self.assertEqual(status, 0)
        self.assertIn("Fulfillment [pickup/delivery/express] (Enter = pickup): ", prompts)
        self.assertIn("Fulfillment: express", out.getvalue())
        self.assertIn("Delivery: $12.00", out.getvalue())
        self.assertIn("Total: $84.00", out.getvalue())
        self.assertEqual(self.service.get_order("ORD-0001")["fulfillment"], "express")

    def test_menu_blank_fulfillment_still_defaults_to_pickup(self):
        answers = ["2", "", "notebook", "2", "", "", "0"]
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(out):
            run_menu(self.service)
        self.assertIn("Fulfillment: pickup", out.getvalue())
        self.assertIn("Total: $10.00", out.getvalue())


if __name__ == "__main__":
    unittest.main()
