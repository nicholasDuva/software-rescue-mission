# Task 4: Refactor with Evidence

This report covers the three code smells diagnosed in Task 3, the refactoring applied to each one, and the three defects that were fixed afterwards in the refactored code.

| # | Code smell (Task 3) | Refactoring technique | Files changed |
|---|---|---|---|
| 1 | Duplicated Code in `quote()` / `place_order()` | Extract Method | `service.py` |
| 2 | Magic Numbers and scattered business rules | Replace Magic Number with Named Constant | `service.py`, `cli.py`, `menu.py` |
| 3 | Primitive Obsession: hand-written search loops | Extract Method (lookup helpers), Remove Duplicated Code | `service.py` |

**How the work was done.** The work had two stages, and each stage was verified on its own.

1. **Refactoring (sections 1–3).** I applied the three refactorings one at a time. A refactoring changes the structure of the code and not what the code does, so after each one the tests had to give exactly the Task 2 baseline: 16 passing and the same 3 failing.
2. **Defect fixes (section 5).** Task 2 found three defects, and Task 3 said they would be fixed as part of this work. I fixed them after the refactoring was finished and verified. A defect fix changes behaviour on purpose, so it is reported separately and is not presented as a refactoring. All 19 tests now pass.

Line numbers marked *before* refer to the Checkpoint A code (commit `7714d90`). Line numbers marked *after* refer to the final code.

---

## 1. Duplicated Code: `quote()` and `place_order()`

### Before

`place_order()` began with a copy of almost the whole body of `quote()`. Lines 15–52 of `quote()` and lines 65–102 of `place_order()` were the same 38 lines: validating the request, finding each product, building the lines and calculating the discount and delivery charge. I confirmed this with a script that compared the two blocks, and they matched character for character.

```python
def quote(self, customer_type, items, fulfillment="pickup"):        # before, lines 13-61
    state = self.store.load()
    ...38 lines of validation and pricing...
    return {"customer_type": customer_type, ...}

def place_order(self, customer_type, items, fulfillment="pickup"):  # before, lines 63-121
    state = self.store.load()
    ...the same 38 lines again...
    order = {"order_id": ..., "status": "placed", "customer_type": customer_type, ...}
    ...deduct stock, save...
```

Every rule existed twice, so every change had to be made twice. The spec requires a quote and the order placed from it to have the same prices, but nothing in the code made that true.

### Refactoring

*Extract Method.* I moved the shared block, unchanged, into one private method, `OrderService._price_request(state, customer_type, items, fulfillment)`. It validates the request and returns the priced dictionary. The two public methods now call it:

```python
def quote(self, customer_type, items, fulfillment=DEFAULT_FULFILLMENT):        # after, lines 59-61
    state = self.store.load()
    return self._price_request(state, customer_type, items, fulfillment)

def place_order(self, customer_type, items, fulfillment=DEFAULT_FULFILLMENT):  # after, lines 63-76
    state = self.store.load()
    priced = self._price_request(state, customer_type, items, fulfillment)
    order = {
        "order_id": "ORD-" + str(state["next_order_number"]).zfill(4),
        "status": STATUS_PLACED,
        **priced,
    }
    ...deduct stock, save...
```

`**priced` copies the priced fields into the order in their original order, so the saved file and the JSON output keep the same key order as before.

### Reason

The two copies were not just similar: they were the same code with the same purpose. Extract Method is the standard answer to that, because it leaves one copy and gives it a name. It also keeps the order of the steps the same (load, validate, price, then change state), so the rule "validate the complete request before changing saved data" still holds.

### After

- Validation and pricing exist in **one** place. A quote and its order now agree because they run the same code, not because two copies happen to match.
- `quote()` is 3 lines and `place_order()` is 14 lines. `place_order()` now shows only what is special about placing an order: the ID, the status, the stock and the save.
- A rule change is made once. This paid off straight away: two of the three defect fixes in section 5 were single edits that corrected quotes and orders together. The change request CR-01 (express delivery) will also need one edit instead of two.
- `_price_request()` never changes the state, so it can be tested with a plain dictionary and no file.

### Verification

- After this refactoring, all 19 tests gave the same result as the baseline (16 pass, 3 fail).
- `test_quote_and_placed_order_have_identical_pricing` passes. It compares a quote with the order placed from it for three requests.
- `test_quote_does_not_save_or_use_an_order_id` and `test_invalid_requests_leave_saved_data_unchanged` pass, so a quote still saves nothing and a rejected order still leaves the file identical byte for byte.
- The behaviour comparison in section 4.2 found 0 differences, including the key order of saved orders (it compares the bytes of the save file).

---

## 2. Magic Numbers and scattered business rules

### Before

The business rules were bare numbers and strings inside the logic:

```python
if customer_type not in ("regular", "student"):                 # before, lines 15, 65
if type(quantity) is not int or quantity < 1 or quantity > 99:  # before, lines 34, 84
if customer_type == "student" and subtotal > 5000:              # before, lines 48, 98
    discount = (subtotal * 10 + 50) // 100
if fulfillment == "delivery" and subtotal - discount < 10000:   # before, lines 51, 101
    delivery = 600
```

The valid customer types and fulfillment options were also typed again in `cli.py` (`choices=("regular", "student")`, before lines 32–33) and in the prompt text and defaults in `menu.py` (before lines 28 and 41). A reader had to work out what `(subtotal * 10 + 50) // 100` means, and a rule change needed edits in three files.

### Refactoring

*Replace Magic Number with Named Constant.* The rules are now defined once at the top of `service.py` (after, lines 5–21):

```python
REGULAR, STUDENT = "regular", "student"
CUSTOMER_TYPES = (REGULAR, STUDENT)
DEFAULT_CUSTOMER_TYPE = REGULAR

PICKUP, DELIVERY = "pickup", "delivery"
FULFILLMENT_OPTIONS = (PICKUP, DELIVERY)
DEFAULT_FULFILLMENT = PICKUP

MIN_QUANTITY = 1
MAX_QUANTITY = 99

STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000
STUDENT_DISCOUNT_PERCENT = 10

DELIVERY_FEE_CENTS = 600
FREE_DELIVERY_THRESHOLD_CENTS = 10000
```

The rounding expression became a small documented function, `_percentage_of(amount_cents, percent)` (after, lines 27–33). At the end of this refactoring the pricing code read:

```python
if customer_type == STUDENT and subtotal > STUDENT_DISCOUNT_THRESHOLD_CENTS:
    discount = _percentage_of(subtotal, STUDENT_DISCOUNT_PERCENT)
if fulfillment == DELIVERY and subtotal - discount < FREE_DELIVERY_THRESHOLD_CENTS:
    delivery = DELIVERY_FEE_CENTS
```

The comparison was still `>` at this point, because a refactoring must not change it. It became `>=` in the defect fix (section 5.1).

`cli.build_parser()` uses `choices=CUSTOMER_TYPES` and `choices=FULFILLMENT_OPTIONS` with the default constants. The two menu prompts and the three error messages that name the rules are built from the same constants. The text they produce is unchanged, for example `Customer type [regular/student] (Enter = regular): ` and `Quantity must be an integer from 1 to 99.`

### Reason

The problem was that the values had no names and no single home. A named constant fixes both: the name says what the number means, and every user of the rule reads the same definition. This technique does not change any value, so it is safe to check by comparing output.

### After

- The rules of the store can be read in one 17-line block, without reading any logic.
- The two interfaces can no longer disagree with the service about which customer types and fulfillment options exist. Adding `express` for CR-01 starts with one edit to `FULFILLMENT_OPTIONS`, and the CLI choices, the menu prompt and the error message follow.
- The comparison `subtotal > STUDENT_DISCOUNT_THRESHOLD_CENTS` is easy to check against the spec ("at least 5,000 cents"), where `> 5000` was easy to miss. Naming the threshold made the defect obvious.
- `_percentage_of()` explains the rounding once and can be tested directly.

### Verification

- After this refactoring, all 19 tests gave the same result as the baseline (16 pass, 3 fail).
- `test_delivery_threshold_at_10000_cents_after_discount`, `test_quantity_limits` and `test_non_integer_quantities_are_rejected` pass. They cover the 10,000-cent threshold, the 600-cent fee, the 1–99 range and the rejection of `True`, `2.0`, `"2"` and `None`.
- `test_cli_json_output_and_exit_statuses` and `test_menu_declined_placement_saves_nothing` pass, so the CLI and the menu still work through the shared constants.
- The behaviour comparison found 0 differences. It records every menu prompt, the `--help` text of the commands, argparse's "invalid choice" errors and every error message, so the rebuilt strings are shown to be identical. It also checks the discount rounding with prices such as 333 and 5,005 cents, which the bundled catalog cannot reach.

---

## 3. Primitive Obsession: hand-written search loops

### Before

The state is a dictionary of lists of dictionaries, and there was no function to find a product or an order. Each method wrote its own loop. After refactoring 1 removed one copy, the product search was still written three times and the order search twice:

```python
product = None                                         # validation (before, lines 26-32)
for candidate in state["catalog"]:
    if candidate["product_id"] == item.get("product_id"):
        product = candidate
        break

for line in lines:                                     # deduct stock (before, lines 114-117)
    for product in state["catalog"]:
        if product["product_id"] == line["product_id"]:
            product["stock"] -= line["quantity"]

for line in order["items"]:                            # restore stock (before, lines 142-145)
    for product in state["catalog"]:
        if product["product_id"] == line["product_id"]:
            product["stock"] += line["quantity"]

for order in state["orders"]:                          # get_order (before, lines 128-131)
    if order["order_id"] == order_id:
        return order
raise ValueError("Unknown order: " + order_id)
# ...and the same search again in cancel_order (before, lines 135-141)
```

The nested loops hid a simple idea ("change this product's stock") inside three levels of indentation.

### Refactoring

*Extract Method*, applied to the lookups. Two small module-level functions now hold the only search loops (after, lines 36–49):

```python
def _find_product(state, product_id):
    """Return the catalog product with this ID, or None if there is none."""

def _find_order(state, order_id):
    """Return the saved order with this ID; raise ValueError if there is none."""
```

All five hand-written loops were replaced by calls. At the end of this refactoring the code read:

```python
product = _find_product(state, item.get("product_id"))                     # validation

for line in order["items"]:                                                # deduct stock
    _find_product(state, line["product_id"])["stock"] -= line["quantity"]

def get_order(self, order_id):
    return _find_order(self.store.load(), order_id)

def cancel_order(self, order_id):
    state = self.store.load()
    order = _find_order(state, order_id)
    for line in order["items"]:
        product = _find_product(state, line["product_id"])
        if product is not None:
            product["stock"] += line["quantity"]
    ...
```

`_find_product()` returns `None` and `_find_order()` raises, because that is what the callers did before: validation needs its own message (`Unknown product.`), while both order searches raised the same `Unknown order: …` error. The `is not None` check in `cancel_order()` keeps the old behaviour of skipping a product that is no longer in the catalog.

### Reason

Task 3 listed two possible steps for this smell: lookup helpers, and later `dataclasses` for products and orders. I chose the helpers. They remove the repeated loops, which was the evidence given in Task 3, and they are small enough to verify fully. Introducing dataclasses would change how every method and both interfaces read the data. That is a rewrite, and it would be much harder to show that behaviour was preserved.

### After

- "How to find a product" and "how to find an order" are each written once and have a name.
- No method contains a nested loop any more. `get_order()` is one line, and `cancel_order()` went from 16 lines to 10 (12 after the defect fix in section 5.3).
- The helpers take plain data and can be tested without a file.
- If the lookup needs to change later (for example to a dictionary keyed by product ID), only the helper changes.

### Verification

- After this refactoring, all 19 tests gave the same result as the baseline (16 pass, 3 fail).
- `test_place_order_deducts_stock_and_records_order`, `test_ordering_all_remaining_stock_then_one_more`, `test_cancel_order_restores_stock` and `test_order_can_be_reopened` pass. They cover stock deduction, stock restoration and order lookup.
- The behaviour comparison found 0 differences. Its final run covers 577 successful placements, 385 successful cancellations, 869 successful lookups and 443 unknown-order errors, and it compares the save file after every call, so every stock change is checked.

---

## 4. Verification summary

### 4.1 Test suite compared with the Task 2 baseline

```sh
python -m unittest discover -s tests -v
```

All runs used Python 3.13.2. Before starting, I re-ran the baseline on the unchanged code, and it matched the stored file.

| Stage | Output file | Result |
|---|---|---|
| Baseline (Task 2) | `Checkpoint A/baseline_test_results.txt` | 16 pass, 3 fail |
| After the three refactorings | `Checkpoint B/test_results_after_refactoring.txt` | 16 pass, 3 fail |
| After the defect fixes | `Checkpoint B/test_results_after_defect_fixes.txt` | **19 pass, 0 fail** |

| Test class | Tests | Baseline | After refactoring | After defect fixes |
|---|---|---|---|---|
| `OrderSmokeTests` | 4 | 4 pass | 4 pass | 4 pass |
| `NormalBehaviourTests` | 2 | 2 pass | 2 pass | 2 pass |
| `BoundaryTests` | 5 | 3 pass, 2 fail | 3 pass, 2 fail | 5 pass |
| `InvalidInputTests` | 3 | 2 pass, 1 fail | 2 pass, 1 fail | 3 pass |
| `PreservedBehaviourTests` | 5 | 5 pass | 5 pass | 5 pass |
| **Total** | **19** | **16 pass, 3 fail** | **16 pass, 3 fail** | **19 pass** |

**After refactoring.** I compared the output with the baseline test by test: every one of the 19 tests had the same result. The 3 failing tests were the same ones and failed with the same messages (`ValueError not raised`, `0 != 500`, `9 != 8`). I ran this comparison after each of the three refactorings, and the result was the same each time. This shows that the refactoring preserved behaviour, including the defective behaviour.

**After the defect fixes.** The 16 tests that passed before still pass, and the 3 tests that recorded the defects now pass.

No test was added, removed or edited in this task. In particular, no expected value was changed to make a test pass.

### 4.2 Behaviour comparison against the original code

The test suite has 19 tests, so I added a second check. `Checkpoint B/compare_behaviour.py` takes the original `supplydesk` package from commit `7714d90`, runs the original code and the current code through the same scripted operations, and compares everything a user or caller can observe: return values, exception types and messages, printed output, prompts, exit statuses and the bytes of the save file after each step.

| Section | What it runs |
|---|---|
| `service` | 10,000 random calls to `quote`, `place_order`, `cancel_order`, `get_order`, `list_orders` and `catalog`, with valid and invalid arguments (unknown products, bad quantities such as `0`, `100`, `True`, `"2"`, bad customer types, items that are not lists or dictionaries) |
| `rounding` | 176 quotes against a catalog with prices such as 333 and 5,005 cents, to exercise the half-cent rounding |
| `cli` | Individual commands, including `--help`, rejected arguments, placing, showing and cancelling |
| `menu` | 7 scripted menu sessions, recording every prompt and every printed line |
| `defects` | One scenario for each of the three known defects |

**After the three refactorings (before the defect fixes).** The script ran every request, including the ones that trigger the defects, and found **0 differences** in all sections: the refactored code behaved exactly like the original, defects included.

**After the defect fixes.** The behaviour is now meant to differ in the three defect cases, so the script leaves out the requests that trigger a defect and runs those cases in their own section. The output is saved in `Checkpoint B/behaviour_comparison_output.txt`:

```sh
python "Checkpoint B/compare_behaviour.py"
```

```text
service    10000 records compared (4364 raised an error, 1168 defect cases left out): 0 differences
rounding     176 records compared: 0 differences
cli           20 records compared: 0 differences
menu           7 records compared: 0 differences
Baseline commit 7714d90 vs working tree, outside the known defects: IDENTICAL behaviour

Known defects (a change here is expected once the defect is fixed):
- student discount at a subtotal of exactly 5,000 cents: CHANGED
    baseline:     {"subtotal_cents": 5000, "discount_cents": 0, "total_cents": 5000}
    working tree: {"subtotal_cents": 5000, "discount_cents": 500, "total_cents": 4500}
- bag x 3 on two lines when 4 bags are in stock: CHANGED
    baseline:     {"quote": "accepted", "place_order": "accepted", "bag_stock_afterwards": -2}
    working tree: {"quote": "Not enough stock for bag.", "place_order": "Not enough stock for bag.", "bag_stock_afterwards": 4}
- cancelling the same order twice (mug stock starts at 8): CHANGED
    baseline:     {"second_cancel_status": "cancelled", "mug_stock_afterwards": 9}
    working tree: {"second_cancel_status": "cancelled", "mug_stock_afterwards": 8}
```

So the final code differs from the original in the three defect cases and nowhere else that the script exercises.

To check that the script can detect an unintended change, I temporarily made four small changes to the final code, one at a time: the delivery fee from 600 to 601, the rounding `+ 50` to `+ 49`, stock not restored on cancel, and the maximum quantity from 99 to 98. The script reported differences for all four (8,195, 4, 9,191 and 1,439). I then restored the file and confirmed that the result was identical again and that all 19 tests passed.

### 4.3 Limits of this evidence

- The comparison shows the same behaviour for the inputs it ran, which is strong evidence but not a proof for all inputs.
- The 1,168 calls left out of the final run are 515 repeat cancellations, 596 requests with repeated lines over stock and 57 student requests with a subtotal of exactly 5,000 cents. The filter is broad on purpose, so it also leaves out some requests that are invalid for another reason.
- The fixes are in the same files as the refactoring, so the "0 differences with the defects included" run cannot be repeated on the final code. `test_results_after_refactoring.txt` is the saved record of that stage.
- One difference is known and is outside the spec. If a save file is edited by hand so that two catalog products share a product ID, the original code changed the stock of both, and the refactored code changes the first one only. Product IDs are unique in the spec, and manual edits to the save file are out of scope, so no supported use is affected.

---

## 5. Defect fixes (documented separately)

These three changes are **not** refactorings: each one changes what the program does, to match the spec. They were made after the refactoring in sections 1–3 was complete and verified, and they are small because of that refactoring.

### 5.1 Student discount not applied at exactly 5,000 cents

- **Defect.** The spec gives the discount when the subtotal is "at least 5,000 cents". The code used `>`, so a student with a subtotal of exactly $50.00 got no discount.
- **Fix.** One character, in `_price_request()` (after, line 117):

  ```python
  if customer_type == STUDENT and subtotal >= STUDENT_DISCOUNT_THRESHOLD_CENTS:
  ```

- **Effect of the refactoring.** The same mistake was in two places before (lines 48 and 98). After refactoring 1 it was in one place, so one edit corrected both quotes and orders.
- **Evidence.** `test_student_discount_applies_at_exactly_5000_cents` now passes. Two bags for a student: discount 0 and total 5,000 before; discount 500 and total 4,500 now.

### 5.2 Repeated lines could take stock below zero

- **Defect.** The spec says that when a product appears on several lines, its combined quantity must not exceed its stock. The code checked each line on its own, so `bag × 3` twice was accepted with 4 bags in stock, and stock became −2.
- **Fix.** `_price_request()` now keeps a running total for each product and checks the total (after, lines 92 and 103–106):

  ```python
  requested = {}  # product ID -> units requested so far, across repeated lines
  ...
  product_id = product["product_id"]
  requested[product_id] = requested.get(product_id, 0) + quantity
  if requested[product_id] > product["stock"]:
      raise ValueError("Not enough stock for " + product_id + ".")
  ```

  The error message is the existing one. The check still runs before anything is changed or saved. Repeated lines that fit within stock are still accepted and still kept as separate lines, as the spec allows.
- **Effect of the refactoring.** The check was in two places before (lines 36 and 86). It is now in one, so quotes and orders both get the fix.
- **Evidence.** `test_duplicate_lines_combined_over_stock_are_rejected` now passes: the order is rejected and bag stock stays at 4. `test_quote_and_placed_order_have_identical_pricing` still passes with a request that repeats a product within stock (`pen-pack × 3` and `pen-pack × 1`).

### 5.3 Cancelling a cancelled order restored stock again

- **Defect.** The spec says that cancelling an already cancelled order returns the existing order without changing stock, prices or history. The code added the stock back every time.
- **Fix.** `cancel_order()` returns early when the order is already cancelled (after, lines 141–142):

  ```python
  order = _find_order(state, order_id)
  if order["status"] == STATUS_CANCELLED:
      return order  # its stock was already restored by the first cancellation
  ```

  Nothing is saved in that case, so the save file is untouched. The status strings `"placed"` and `"cancelled"` are now the named constants `STATUS_PLACED` and `STATUS_CANCELLED` (after, lines 23–24), because the second one is now used in two places.
- **Evidence.** `test_cancelling_a_cancelled_order_changes_nothing` now passes: after two cancellations, mug stock is 8 and not 9. `test_cancel_order_restores_stock` still passes, so a first cancellation still restores stock.

### Summary of the defect fixes

| Defect | Test that recorded it | Baseline | After refactoring | After fix |
|---|---|---|---|---|
| Discount at exactly 5,000 cents | `test_student_discount_applies_at_exactly_5000_cents` | fail | fail | pass |
| Repeated lines over stock | `test_duplicate_lines_combined_over_stock_are_rejected` | fail | fail | pass |
| Cancelling twice | `test_cancelling_a_cancelled_order_changes_nothing` | fail | fail | pass |
