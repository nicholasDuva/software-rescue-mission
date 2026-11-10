"""Task 4 evidence: compare the refactored code with the Checkpoint A baseline.

Run from the repository root:

    python "Checkpoint B/compare_behaviour.py"

Requests that trigger one of the three known defects are left out of the main
comparison and run separately in the "defects" section, where a change is
expected. Exit status 0 means no difference was found anywhere else.
"""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "7714d90"  # "initial commit: Post Checkpoint A"
SEEDS = range(40)
OPERATIONS_PER_SEED = 250

# Mostly valid values, so that many requests succeed, mixed with invalid ones.
CUSTOMER_TYPES = ["regular"] * 8 + ["student"] * 10 + ["staff", "", None]
FULFILLMENTS = ["pickup"] * 7 + ["delivery"] * 10 + ["courier", None]
PRODUCT_IDS = ["notebook", "pen-pack", "hoodie", "mug", "bag"] * 5 + ["widget", None]
QUANTITIES = [1, 2, 3, 4] * 5 + [5, 10, 99, 0, -1, 100, True, 2.0, "2", None]
ODD_ITEM_LISTS = [[], None, "notebook:1", ("notebook", 1), ["notebook"], [None],
                  [{}], [{"product_id": "mug"}], [{"quantity": 1}]]

# A catalog whose prices are not multiples of 50 cents, so the discount
# rounding (half a cent rounds up) is exercised.
ODD_PRICE_CATALOG = [
    {"product_id": "a", "name": "A", "unit_price_cents": 5005, "stock": 99},
    {"product_id": "b", "name": "B", "unit_price_cents": 333, "stock": 99},
    {"product_id": "c", "name": "C", "unit_price_cents": 4999, "stock": 99},
    {"product_id": "d", "name": "D", "unit_price_cents": 1, "stock": 99},
]

CLI_COMMANDS = [
    ["--help"],
    ["quote", "--help"],
    ["place", "--help"],
    ["catalog"],
    ["quote", "--item", "notebook:2"],
    ["quote", "--customer", "student", "--fulfillment", "delivery", "--item", "hoodie:2"],
    ["quote", "--customer", "staff", "--item", "notebook:2"],
    ["quote", "--fulfillment", "courier", "--item", "notebook:2"],
    ["quote", "--item", "notebook"],
    ["quote", "--item", "notebook:two"],
    ["quote"],
    ["place", "--customer", "student", "--item", "bag:2", "--item", "mug:1"],
    ["place", "--fulfillment", "delivery", "--item", "hoodie:3"],
    ["place", "--item", "widget:1"],
    ["orders"],
    ["show", "ORD-0001"],
    ["show", "ORD-0042"],
    ["cancel", "ORD-0001"],
    ["cancel", "ORD-0042"],
    ["catalog"],
]

MENU_SESSIONS = [
    ["1", "0"],
    ["2", "", "notebook", "2", "", "", "0"],
    ["2", "student", "hoodie", "two", "hoodie", "2", "", "delivery", "0"],
    ["3", "student", "hoodie", "2", "", "delivery", "n", "0"],
    ["3", "student", "hoodie", "2", "bag", "1", "", "delivery", "y", "4", "5", "ORD-0001",
     "6", "ORD-0001", "n", "6", "ORD-0001", "y", "1", "0"],
    ["2", "staff", "notebook", "1", "", "", "2", "", "widget", "1", "", "",
     "2", "", "", "", "2", "", "notebook", "1", "", "courier", "5", "ORD-0009", "9", "4", "0"],
    ["3", "", "mug", "8", "", "", "y", "3", "", "mug", "1", "", "", "y"],  # ends at EOF
]


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def attempt(function, *args):
    """Return what a call produced: its result, or its exception type and message."""
    try:
        return {"result": function(*args)}
    except Exception as error:  # the transcript records every kind of failure
        return {"error": type(error).__name__, "message": str(error)}


def random_items(rng):
    if rng.random() < 0.08:
        return rng.choice(ODD_ITEM_LISTS)
    return [{"product_id": rng.choice(PRODUCT_IDS), "quantity": rng.choice(QUANTITIES)}
            for _ in range(rng.randint(1, 4))]


def random_order_id(rng, service):
    known = [order["order_id"] for order in service.list_orders()]
    if known and rng.random() < 0.85:
        return rng.choice(known)
    return rng.choice(["ORD-9999", "", "ord-0001"])


def known_defect(service, name, args):
    """Name the known defect this call would trigger, or return None.

    The test is deliberately broad: it may also leave out a few requests that
    are invalid for another reason, but it never lets a defect case through.
    """
    if name == "cancel_order":
        cancelled = [order["order_id"] for order in service.list_orders()
                     if order["status"] == "cancelled"]
        return "cancel twice" if args[0] in cancelled else None
    if name not in ("quote", "place_order") or not isinstance(args[1], list):
        return None
    products = {product["product_id"]: product for product in service.catalog()}
    units, line_count, subtotal = {}, {}, 0
    for item in args[1]:
        if not isinstance(item, dict) or item.get("product_id") not in products:
            continue
        quantity = item.get("quantity")
        if type(quantity) is not int or not 1 <= quantity <= 99:
            continue
        product_id = item["product_id"]
        units[product_id] = units.get(product_id, 0) + quantity
        line_count[product_id] = line_count.get(product_id, 0) + 1
        subtotal += products[product_id]["unit_price_cents"] * quantity
    if any(line_count[product_id] > 1 and units[product_id] > products[product_id]["stock"]
           for product_id in units):
        return "repeated lines over stock"
    if args[0] == "student" and subtotal == 5000:
        return "discount at exactly 5000"
    return None


def service_transcript(OrderService, directory):
    records = []
    for seed in SEEDS:
        rng = random.Random(seed)
        path = directory / f"service-{seed}.json"
        service = OrderService(path)
        for _ in range(OPERATIONS_PER_SEED):
            name = rng.choice(["quote", "quote", "place_order", "place_order", "place_order",
                               "cancel_order", "get_order", "list_orders", "catalog"])
            if name in ("quote", "place_order"):
                args = [rng.choice(CUSTOMER_TYPES), random_items(rng)]
                if rng.random() < 0.8:  # otherwise rely on the default fulfillment
                    args.append(rng.choice(FULFILLMENTS))
            elif name in ("cancel_order", "get_order"):
                args = [random_order_id(rng, service)]
            else:
                args = []
            defect = known_defect(service, name, args)
            if defect:
                outcome = {"left out": defect}
            else:
                outcome = attempt(getattr(service, name), *args)
            records.append({"seed": seed, "call": name, "args": repr(args),
                            "outcome": outcome, "file": file_digest(path)})
    return records


def rounding_transcript(OrderService, directory):
    path = directory / "odd-prices.json"
    state = {"schema_version": 1, "next_order_number": 1,
             "catalog": ODD_PRICE_CATALOG, "orders": []}
    path.write_text(json.dumps(state), encoding="utf-8")
    service = OrderService(path)
    records = []
    for customer in ("regular", "student"):
        for fulfillment in ("pickup", "delivery"):
            for product in ODD_PRICE_CATALOG:
                for quantity in (1, 2, 3, 7, 15, 16, 20, 21, 30, 31, 99):
                    other = "b" if product["product_id"] == "d" else "d"  # never a repeated line
                    items = [{"product_id": product["product_id"], "quantity": quantity},
                             {"product_id": other, "quantity": quantity % 5 + 1}]
                    records.append({"args": repr((customer, items, fulfillment)),
                                    "outcome": attempt(service.quote, customer, items,
                                                       fulfillment)})
    return records


def defect_transcript(OrderService, directory):
    """Trigger each known defect once and record what a user would see."""
    def stock(service, product_id):
        return next(product["stock"] for product in service.catalog()
                    if product["product_id"] == product_id)

    bag = {"product_id": "bag", "quantity": 3}
    records = []

    service = OrderService(directory / "defect-discount.json")
    quote = attempt(service.quote, "student", [{"product_id": "bag", "quantity": 2}])
    records.append({"defect": "student discount at a subtotal of exactly 5,000 cents",
                    "seen": {key: quote["result"][key] for key in
                             ("subtotal_cents", "discount_cents", "total_cents")}})

    service = OrderService(directory / "defect-stock.json")
    quoted = attempt(service.quote, "regular", [bag, bag])
    placed = attempt(service.place_order, "regular", [bag, bag])
    records.append({"defect": "bag x 3 on two lines when 4 bags are in stock",
                    "seen": {"quote": quoted.get("message", "accepted"),
                             "place_order": placed.get("message", "accepted"),
                             "bag_stock_afterwards": stock(service, "bag")}})

    service = OrderService(directory / "defect-cancel.json")
    order = service.place_order("regular", [{"product_id": "mug", "quantity": 1}])
    service.cancel_order(order["order_id"])
    again = attempt(service.cancel_order, order["order_id"])
    records.append({"defect": "cancelling the same order twice (mug stock starts at 8)",
                    "seen": {"second_cancel_status": again["result"]["status"],
                             "mug_stock_afterwards": stock(service, "mug")}})
    return records


def cli_transcript(cli, directory):
    path = directory / "cli.json"
    records = []
    for command in CLI_COMMANDS:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                status = cli.main(["--data", str(path)] + command)
            except SystemExit as stop:  # argparse exits on --help and bad arguments
                status = "SystemExit " + str(stop.code)
        records.append({"command": command, "status": status, "stdout": out.getvalue(),
                        "stderr": err.getvalue(), "file": file_digest(path)})
    return records


def menu_transcript(OrderService, run_menu, directory):
    records = []
    for number, answers in enumerate(MENU_SESSIONS):
        path = directory / f"menu-{number}.json"
        remaining = list(answers)
        out = io.StringIO()

        def fake_input(prompt=""):
            print("<prompt>" + prompt)
            if not remaining:
                raise EOFError
            return remaining.pop(0)

        with mock.patch("builtins.input", side_effect=fake_input), \
                contextlib.redirect_stdout(out):
            status = run_menu(OrderService(path))
        records.append({"session": number, "status": status, "screen": out.getvalue(),
                        "file": file_digest(path)})
    return records


def write_transcript(package_root):
    """Import `supplydesk` from package_root and print everything it does."""
    sys.path.insert(0, str(package_root))
    from supplydesk import cli
    from supplydesk.menu import run_menu
    from supplydesk.service import OrderService
    sys.argv[0] = "supplydesk"  # keeps argparse usage text independent of this script
    with tempfile.TemporaryDirectory() as name:
        directory = Path(name)
        transcript = {
            "service": service_transcript(OrderService, directory),
            "rounding": rounding_transcript(OrderService, directory),
            "cli": cli_transcript(cli, directory),
            "menu": menu_transcript(OrderService, run_menu, directory),
            "defects": defect_transcript(OrderService, directory),
        }
    json.dump(transcript, sys.stdout)


def extract_baseline(commit, destination):
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "supplydesk"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True).stdout.split("\n")
    for name in filter(None, listing):
        content = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=REPO_ROOT,
                                 check=True, capture_output=True).stdout
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def read_transcript(package_root):
    output = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--transcript", str(package_root)],
        check=True, capture_output=True, text=True, cwd=package_root).stdout
    return json.loads(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--baseline", default=BASELINE_COMMIT,
                        help="git commit holding the original code (default: %(default)s)")
    parser.add_argument("--transcript", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.transcript:
        write_transcript(args.transcript)
        return 0

    with tempfile.TemporaryDirectory() as name:
        extract_baseline(args.baseline, Path(name))
        before = read_transcript(Path(name))
    after = read_transcript(REPO_ROOT)

    differences = 0
    for section in before:
        if section == "defects":
            continue
        old, new = before[section], after[section]
        errors = sum(1 for record in old if "error" in record.get("outcome", {}))
        left_out = sum(1 for record in old if "left out" in record.get("outcome", {}))
        changed = [index for index, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
        if len(old) != len(new):
            changed.append(min(len(old), len(new)))
        differences += len(changed)
        detail = f" ({errors} raised an error, {left_out} defect cases left out)" \
            if errors else ""
        print(f"{section:<9} {len(old):>6} records compared{detail}: "
              f"{len(changed)} differences")
        for index in changed[:3]:
            print("  baseline:  ", json.dumps(old[index])[:600] if index < len(old) else None)
            print("  refactored:", json.dumps(new[index])[:600] if index < len(new) else None)
    print(f"Baseline commit {args.baseline} vs working tree, outside the known defects: "
          + ("IDENTICAL behaviour" if not differences else f"{differences} DIFFERENCES"))

    print("\nKnown defects (a change here is expected once the defect is fixed):")
    for old, new in zip(before["defects"], after["defects"]):
        print(f"- {old['defect']}: " + ("CHANGED" if old != new else "unchanged"))
        print("    baseline:    ", json.dumps(old["seen"]))
        print("    working tree:", json.dumps(new["seen"]))
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
