# Task 3: Identify and Diagnose Code Problems

This document diagnoses five separate problems in the original implementation: three code smells, one testing/testability problem and one real software defect. Line numbers refer to the original `supplydesk/service.py`, `cli.py` and `menu.py`.

| # | Type | Problem | Main location |
|---|---|---|---|
| 1 | Code smell | Duplicated Code | `OrderService.quote()` / `place_order()` |
| 2 | Code smell | Magic Numbers and business rules scattered across files | `service.py`, `cli.py`, `menu.py` |
| 3 | Code smell | Primitive Obsession: raw dictionaries and hand-written search loops | `service.py` (all methods), `menu.py` |
| 4 | Testing / testability | Business rules can't be tested in isolation, and the supplied tests cover only the normal path | `OrderService.__init__`, `menu.py`, `tests/test_smoke.py` |
| 5 | Software defect | The stock check ignores repeated lines, so stock can go negative | `quote()` line 36 / `place_order()` line 86 |

---

## 1. Duplicated Code: `quote()` and `place_order()`

**Location:** `supplydesk/service.py`, `OrderService.quote()` (lines 13–61) and `OrderService.place_order()` (lines 63–102).

**Problem:** `place_order()` starts with a copy of almost the whole body of `quote()`, about 40 lines. Both methods do the same steps in the same order:

1. validate the customer type, the fulfillment option and the item list;
2. loop over the items, find each product and validate its quantity and stock;
3. build the line dictionaries and add up the subtotal;
4. calculate the discount and the delivery charge.

Only the last 20 lines of `place_order()` are different: building the order ID, deducting stock and saving.

**Evidence:** lines 14–52 and 64–102 are identical apart from their position in the file. For example, both methods contain these lines:

```python
if customer_type == "student" and subtotal > 5000:      # line 48 and line 98
    discount = (subtotal * 10 + 50) // 100
```

The Task 2 test `test_student_discount_applies_at_exactly_5000_cents` fails because `>` should be `>=`. That same wrong comparison exists in **both** copies.

**Consequence:**

- Every change to validation or pricing has to be made twice, in exactly the same way.
- The spec requires that a quote and the order placed from it have identical prices. Nothing in the code guarantees this: it is true only while two separate copies are kept in step. If a developer fixes the discount in `quote()` and forgets `place_order()`, customers would see one price and be charged another, and no error would appear.
- Anyone reading the code has to compare the two methods line by line to be sure they really are the same.

**Improvement:** apply *Extract Method*. Move the shared code into one private helper, for example `_build_priced_request(state, customer_type, items, fulfillment)`, which validates the request and returns the priced dictionary. `quote()` returns that result directly. `place_order()` calls the same helper and then adds the order ID, deducts stock and saves. After this, pricing exists in exactly one place, and a quote and its order match by design. The Task 2 test `test_quote_and_placed_order_have_identical_pricing` protects this change.

---

## 2. Magic Numbers and business rules scattered across files

**Location:** `service.py` lines 15–18, 34, 48–52 and 65–68, 84, 98–102. Also `cli.py` `build_parser()` lines 32–33, and the prompts in `menu.py` `read_request()` lines 28 and 41.

**Problem:** the store's business rules are written directly into the code as bare numbers and strings, with no names. The same rule is repeated in several places and in several files.

**Evidence:**

| Value | Meaning | Where it appears |
|---|---|---|
| `5000` | student discount threshold (cents) | `service.py` 48, 98 |
| `* 10 + 50) // 100` | a 10% discount, rounded half-up | `service.py` 49, 99 |
| `10000` | free-delivery threshold (cents) | `service.py` 51, 101 |
| `600` | delivery charge (cents) | `service.py` 52, 102 |
| `1`, `99` | allowed quantity range | `service.py` 34–35, 84–85 |
| `("regular", "student")` | valid customer types | `service.py` 15, 65; `cli.py` 32; `menu.py` 28 (prompt text) |
| `("pickup", "delivery")` | valid fulfillment options | `service.py` 17, 67; `cli.py` 33; `menu.py` 41 (prompt text) |

**Consequence:**

- The expression `(subtotal * 10 + 50) // 100` does not show that it means "10% rounded to the nearest cent, with half a cent rounded up". A reader has to work that out, and so has to work out whether it is correct.
- A rule change, such as a new delivery fee or a new customer type, needs edits in up to three files. If one file is missed, the interfaces disagree with the service. For example, `cli.py` would reject a customer type that the service accepts.
- With the comparison hidden inside a bare-number expression, an off-by-one mistake like `> 5000` is easy to miss in review.

**Improvement:** apply *Replace Magic Number with Symbolic Constant*. Define named constants once in `service.py`, for example:

- `STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000`
- `STUDENT_DISCOUNT_PERCENT = 10`
- `FREE_DELIVERY_THRESHOLD_CENTS = 10000`
- `DELIVERY_FEE_CENTS = 600`
- `MIN_QUANTITY, MAX_QUANTITY = 1, 99`
- `CUSTOMER_TYPES = ("regular", "student")`
- `FULFILLMENT_OPTIONS = ("pickup", "delivery")`

Put the rounding in a small, documented function such as `_discount_cents(subtotal)`. `cli.build_parser()` should use `choices=CUSTOMER_TYPES` and `choices=FULFILLMENT_OPTIONS`, and the menu prompts can be built from the same constants.

---

## 3. Primitive Obsession: raw dictionaries and hand-written search loops

**Location:** `supplydesk/service.py`: `quote()` lines 26–30, `place_order()` lines 76–80 and 114–117, `get_order()` lines 128–131 and `cancel_order()` lines 136–145. Also `menu.py`, `show_order()` line 16.

**Problem:** the whole application state is a nested dictionary of lists of dictionaries, read with string keys. There is no function to "find a product by ID" or "find an order by ID". Every method writes its own search loop over a list, sometimes nested inside another loop. This is a separate problem from #1: these loops also appear in `get_order()`, `cancel_order()` and the stock-update code, which are not part of the copied block.

**Evidence:**

- The same product search is written out four times: twice to validate items (lines 27–30, 77–80), once to deduct stock (lines 115–117) and once to restore stock (lines 143–145).
- The order search is written twice (lines 128–130, 136–139).
- The stock updates are nested loops:

  ```python
  for line in lines:                      # place_order, lines 114-117
      for product in state["catalog"]:
          if product["product_id"] == line["product_id"]:
              product["stock"] -= line["quantity"]
  ```

- String keys such as `"unit_price_cents"`, `"line_total_cents"` and `"next_order_number"` are typed by hand in `service.py`, `storage.py` and `menu.py`.
- `menu.show_order()` tells a quote and an order apart only by whether the key `"order_id"` is missing: `order.get("order_id", "Quote")`.

**Consequence:**

- The shape of the data is never written down anywhere. A reader has to piece it together from `JsonStore.load()` and the method bodies.
- A mistyped key fails only at run time, with a `KeyError`. The CLI and the menu catch `KeyError` and show it to the user as if they had made an input error (`cli.py` line 63, `menu.py` line 87). This hides real programming mistakes, which makes debugging harder.
- Each search loop is another place where a mistake can creep in. The nested loops are hard to follow and do unnecessary work (every line × every product).

**Improvement:**

- Add small helpers such as `_find_product(state, product_id)` and `_find_order(state, order_id)`, which raise `ValueError` when nothing is found. Use them everywhere instead of the hand-written loops.
- Alternatively, build a dictionary from product ID to product once per operation.
- As a further step, represent products and orders as `dataclasses` that are converted to and from dictionaries only in `JsonStore`. Then the data shape is written in one place, and editors can catch mistyped field names.

---

## 4. Testability: business rules can't be tested in isolation, and the existing tests cover only the normal path

**Location:** `OrderService.__init__` (`service.py` lines 7–8), the pricing code inside `quote()` and `place_order()`, `menu.read_request()` and `menu.run_menu()`, and `tests/test_smoke.py`.

**Problem:** the code is hard to unit-test, and the supplied tests don't make up for that.

- `OrderService.__init__` always creates its own `JsonStore(state_path)`. No other store or catalog can be passed in, so every service test needs a real file on disk.
- The pricing rules exist only inside `quote()` and `place_order()`. Testing a price means building a full request against the stored catalog.
- `menu.py` calls `input()` and `print()` directly, so the menu can only be tested by patching built-in functions.
- `tests/test_smoke.py` contains just four normal-path tests.

**Evidence:**

- The bundled catalog prices are all multiples of 50 cents, so the half-cent rounding rule in the spec can never happen through the service unless you first write your own save file to disk.
- To test the menu, Task 2 had to use `mock.patch("builtins.input", ...)` together with `redirect_stdout` (`test_menu_declined_placement_saves_nothing`).
- The four supplied tests all pass, but the Task 2 baseline shows **3 defects** that they don't catch: the $50 discount boundary, repeated lines over stock, and cancelling twice. They contain no boundary tests, no invalid-input tests, no CLI or menu tests, and no check that a quote matches its placed order.

**Consequence:** defects at the boundaries reached the delivered code without being caught. Developers get little protection when refactoring. A simple pricing rule can't be checked with a quick test that needs no files. Because tests are slow and awkward to write, fewer of them get written.

**Improvement:**

- Move the pricing into a pure function such as `price_request(catalog, customer_type, items, fulfillment)`. It takes plain data and returns the priced dictionary without touching disk, so it can be tested directly with any catalog.
- Let `OrderService` optionally receive a store (*dependency injection*: `OrderService(store=InMemoryStore())`).
- Let `run_menu()` optionally receive `input_fn` and `output_fn` arguments, so tests don't need to patch built-ins.
- Keep the Task 2 boundary, invalid-input and preserved-behaviour tests as the regression suite.

---

## 5. Defect: the stock check ignores repeated lines, so stock can go negative

**Location:** `supplydesk/service.py`: `OrderService.quote()` line 36, and `OrderService.place_order()` line 86 with the stock deduction at lines 114–117.

**Problem:** stock is checked one line at a time against the stock *before* the order:

```python
if quantity > product["stock"]:
    raise ValueError("Not enough stock for " + product["product_id"] + ".")
```

The spec says that when a product appears on several lines, "its combined quantity must not exceed its available stock". The code never adds those quantities together.

**Evidence:** with bag stock at 4, `place_order("regular", [bag × 3, bag × 3])` passes the check for each line (3 ≤ 4). The order is saved as `ORD-0001` with a total of 15,000 cents, and bag stock becomes **−2**. The Task 2 test `test_duplicate_lines_combined_over_stock_are_rejected` fails with `ValueError not raised`. `quote()` accepts the same request.

**Consequence:**

- The store sells stock it doesn't have.
- A negative stock level is saved to the file and shown in the catalog.
- Every later order for that product is rejected until enough cancellations bring the stock back above zero.
- This breaks a basic rule of the data (stock is never negative), and it is hard to trace afterwards because each line looked valid when it was checked.

**Improvement:**

- Before checking stock, add up the requested quantity for each product (for example with a `dict` or `collections.Counter` keyed by `product_id`).
- Then check each total against that product's stock, and raise `ValueError` before anything changes.
- Do this check once, in the shared validation helper proposed in #1, so that `quote()` and `place_order()` both get the fix.
- Keep the repeated lines separate in the result, since the spec allows that.

---

### Not counted separately

Task 2 also found two other defects: the discount comparison `> 5000` that should be `>=`, and `cancel_order()` adding stock back when an order is cancelled a second time. The first is used above as evidence for #1 and #2. Both will be fixed during refactoring, but they are not listed as extra problems, because this task asks for exactly five.
