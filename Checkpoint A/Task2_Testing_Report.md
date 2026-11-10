# Task 2: Testing Safety Net

## 1. Existing tests

`tests/test_smoke.py` has four tests, and all of them pass:

- a regular pickup quote;
- a student delivery quote;
- reopening the save file and finding a placed order;
- cancelling an order and getting the stock back.

These tests cover only the main path. They test no limits (the $50 discount, the $100 free-delivery threshold, quantity limits, running out of stock) and no invalid input. They don't check that a quote matches the order placed from it, and they don't test the CLI or the menu. They pass even though the three defects in section 4 exist.

## 2. Added tests

I added **15 tests** in `tests/test_service.py`, grouped into one class per category. Each expected value comes from `System Understanding Note.md`, not from what the current code returns. Each test uses its own temporary save file, so none of them touches `.supplydesk/state.json`.

Run all tests with:

```sh
python -m unittest discover -s tests -v
```

## 3. Categories

### 3.1 Normal behaviour (`NormalBehaviourTests`, 2 tests)

- **What:**
  - `test_quote_returns_full_line_details_for_multiple_items` checks that a quote for 2 notebooks and 1 mug returns the correct product ID, name, unit price, quantity and line total for each line, and a total of 2,500 cents.
  - `test_place_order_deducts_stock_and_records_order` places two orders. It checks that they get `ORD-0001` and `ORD-0002`, that the status is `placed`, that the student delivery total is 7,800 cents, that hoodie stock goes from 5 to 2, and that both orders appear in the history in order.
- **Why:** quoting and placing orders are the main jobs of the application. Wrong prices or stock mean customers are charged wrongly or the inventory is wrong.
- **Expected and actual:** the results matched the spec. **Both tests pass.**

### 3.2 Boundary behaviour (`BoundaryTests`, 5 tests)

- **What:**
  - `test_student_discount_applies_at_exactly_5000_cents` checks that a student gets a 10% discount on a subtotal of exactly 5,000 cents.
  - `test_delivery_threshold_at_10000_cents_after_discount` checks that delivery is free at exactly 10,000 cents, and still charged when 11,000 drops to 9,900 after the discount.
  - `test_quantity_limits` checks that a quantity of 1 is accepted and that 0, −1 and 100 are rejected.
  - `test_ordering_all_remaining_stock_then_one_more` orders all 5 hoodies (stock becomes 0), then checks that ordering one more is rejected.
  - `test_duplicate_lines_combined_over_stock_are_rejected` checks that `bag:3` plus `bag:3` is rejected when only 4 bags are in stock.
- **Why:** mistakes are most likely at limits, for example `>` written instead of `>=`. A mistake here changes what a customer pays or lets stock go below zero.
- **Expected and actual:** 3 of these tests pass. **2 fail:** the discount test and the duplicate-lines test (see section 4).

### 3.3 Invalid or exceptional behaviour (`InvalidInputTests`, 3 tests)

- **What:**
  - `test_non_integer_quantities_are_rejected` checks that the quantities `True`, `2.0`, `"2"` and `None` raise `ValueError`.
  - `test_cancelling_a_cancelled_order_changes_nothing` cancels the same order twice and checks that stock is restored only once.
  - `test_malformed_save_file_raises_instead_of_resetting` checks that a corrupted save file raises an error and is left as it was.
- **Why:** the spec requires invalid requests to raise `ValueError`, and cancelling twice must not change anything. If a corrupted file were quietly reset, the whole order history would be lost.
- **Expected and actual:** 2 of these tests pass. **1 fails:** cancelling twice (see section 4).

### 3.4 Behaviour to preserve during refactoring (`PreservedBehaviourTests`, 5 tests)

The refactoring I plan merges the copied validation and pricing code in `OrderService.quote()` and `place_order()`. These tests guard what that change could break:

- **What:**
  - `test_quote_and_placed_order_have_identical_pricing` checks that a quote and the order then placed from it have the same items, subtotal, discount, delivery charge and total, for three different requests.
  - `test_quote_does_not_save_or_use_an_order_id` checks that a quote creates no save file and no order ID, so the next order is still `ORD-0001`.
  - `test_invalid_requests_leave_saved_data_unchanged` sends four invalid placements and checks that the save file stays identical byte for byte, and that the next order is still `ORD-0002`.
  - `test_cli_json_output_and_exit_statuses` checks that a successful `place` command prints JSON and exits with 0, and a rejected one prints `Error: …` and exits with 2.
  - `test_menu_declined_placement_saves_nothing` checks that the menu shows the quote ($78.00), and that answering `n` places no order and creates no save file.
- **Why:** after refactoring, these tests show that the code still behaves the same way for the user, apart from the defects that will be fixed on purpose.
- **Expected and actual:** the results matched the spec. **All 5 tests pass.**

## 4. Baseline results (before refactoring)

Tests were run on Python 3.13.2. The full output is in `docs/baseline_test_results.txt`.

```text
Ran 19 tests in 0.065s
FAILED (failures=3)
```

| Test class | Tests | Passed | Failed |
|---|---|---|---|
| `OrderSmokeTests` (existing) | 4 | 4 | 0 |
| `NormalBehaviourTests` | 2 | 2 | 0 |
| `BoundaryTests` | 5 | 3 | 2 |
| `InvalidInputTests` | 3 | 2 | 1 |
| `PreservedBehaviourTests` | 5 | 5 | 0 |
| **Total** | **19** | **16** | **3** |

### Failures and findings

I did not change any expected value to make a test pass. Each failure is a suspected defect in `supplydesk/service.py`.

| Failing test | Expected (spec) | Actual | Cause |
|---|---|---|---|
| `test_student_discount_applies_at_exactly_5000_cents` | Discount 500, total 4,500 | Discount 0, total 5,000 | `subtotal > 5000` (lines 48 and 98) should be `>=`, because the spec says "at least". The same mistake is in **both** copies of the pricing code. |
| `test_duplicate_lines_combined_over_stock_are_rejected` | `ValueError` raised and bag stock stays 4 | The order was placed and bag stock became **−2** | Stock is checked one line at a time (lines 36 and 86), so quantities of the same product are never added together. |
| `test_cancelling_a_cancelled_order_changes_nothing` | Mug stock stays 8 | Mug stock became **9** | `cancel_order()` (lines 133–148) never checks whether the order is already cancelled before adding stock back. |

The first two defects are in both `quote()` and `place_order()`, so each fix would have to be made twice. This supports the refactoring planned next. After refactoring, the 16 passing tests must still pass, and the 3 failing tests should pass once the defects are fixed.
