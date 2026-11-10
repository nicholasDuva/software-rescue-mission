# Task 5: Client Change Request CR-01 (Express Delivery)

CR-01 adds a third fulfillment option, `express`, which always costs 1,200 cents and is never waived. The starting point was commit `6bbf807` (Task 4), where all 19 tests pass.

## Part A: Prediction (written before implementation)

**1. Behaviour that will change**

- Fulfillment can be `pickup`, `delivery` or `express`. Every other value is still invalid.
- Express adds a flat 1,200 cents to `delivery_cents`. The student discount still applies to merchandise only.
- Pickup and standard delivery are unchanged.
- The error message, the menu prompt and the CLI choices will list `express`. The defaults stay `regular` and `pickup`.

**2. Files and methods I expect to modify**

| File | Expected change |
|---|---|
| `service.py` | Add `EXPRESS` and `EXPRESS_FEE_CENTS`, and extend `FULFILLMENT_OPTIONS`. Extract the delivery charge out of `_price_request()`. Reword the error message, because `' or '.join` would give "pickup or delivery or express". |
| `cli.py` | Help text only. The choices already come from `FULFILLMENT_OPTIONS`. |
| `menu.py` | No change. The prompt is already built from the constants. |
| `README.md` | Add a usage note. |

I do not expect to change `quote()`, `place_order()`, `get_order()`, `cancel_order()` or `storage.py`.

**3. Tests needed**

- The 19 existing tests, unedited, as the regression check.
- A new `tests/test_express.py` covering:
  - the CR-01 examples;
  - a fee that is never waived;
  - an unchanged discount and rounding;
  - a quote that agrees with the placed order;
  - an express order that keeps its details when retrieved, reopened and cancelled;
  - other fulfillment values still rejected;
  - the CLI and menu support.

## Part B: Implementation and testing

### Code changes

```python
# service.py
PICKUP, DELIVERY, EXPRESS = "pickup", "delivery", "express"
FULFILLMENT_OPTIONS = (PICKUP, DELIVERY, EXPRESS)
EXPRESS_FEE_CENTS = 1200  # flat fee, never waived (CR-01)

def _delivery_charge_cents(fulfillment, discounted_subtotal_cents):
    if fulfillment == EXPRESS:
        return EXPRESS_FEE_CENTS
    if fulfillment == DELIVERY and discounted_subtotal_cents < FREE_DELIVERY_THRESHOLD_CENTS:
        return DELIVERY_FEE_CENTS
    return 0
```

```diff
# service.py, _price_request()
-        delivery = 0
-        if fulfillment == DELIVERY and subtotal - discount < FREE_DELIVERY_THRESHOLD_CENTS:
-            delivery = DELIVERY_FEE_CENTS
+        delivery = _delivery_charge_cents(fulfillment, subtotal - discount)
```

Other changes:

- **`service.py`:** a new `_list_choices()` builds both validation messages, for example `Fulfillment must be pickup, delivery or express.`
- **`cli.py`:** adds `--fulfillment` help text built from the fee constants.
- **`menu.py`:** unchanged. Its prompt now reads `Fulfillment [pickup/delivery/express] (Enter = pickup): ` on its own.
- **`README.md`:** a new usage section.

| File | Added | Removed |
|---|---|---|
| `service.py` | 26 | 7 |
| `cli.py` | 10 | 3 |
| `menu.py` | 0 | 0 |
| `README.md` | 21 | 1 |

### Tests

I added 18 tests in `tests/test_express.py`. Expected values come from CR-01 and the spec, not from the code.

| Class | Tests | Covers |
|---|---|---|
| `ExpressPricingTests` | 7 | The CR-01 examples ($22, $84, and $120 vs $132), a fee never waived, the discount at the 5,000-cent boundary and never applied to the fee, rounding, pickup and delivery unchanged |
| `ExpressOrderTests` | 3 | Quote and order agree; the order is kept when retrieved, reopened and cancelled; numbering, stock and history work across all options |
| `ExpressValidationTests` | 3 | `Express`, `courier`, `""` and `None` are rejected with the save file unchanged; the default is still `pickup` |
| `ExpressInterfaceTests` | 5 | The CR-01 command gives 8400; CLI place, show and `--help`; an invalid choice exits with 2; the menu prompt and an express order placed through the menu |

### Results

The full output is in `test_results_after_cr01.txt`.

| Test file | Before CR-01 | After CR-01 |
|---|---|---|
| `test_smoke.py` + `test_service.py` | 19 pass | 19 pass |
| `test_express.py` (new) | — | 18 pass |
| **Total** | **19 pass** | **37 pass** |

On the first run, one new test failed because my test basket came to 5,250 cents instead of 4,750. The code was right. I fixed the basket, not the expected values.

### Unrelated behaviour

`compare_cr01.py` re-runs the Task 4 behaviour comparison against `6bbf807`: 10,000 service calls plus CLI and menu runs, none of which use express. It turns the intended new wording back into the old text before comparing. The output is in `cr01_comparison_output.txt`:

```text
Task 4 commit 6bbf807 vs working tree: 358 differences, all of them CR-01 wording only
```

To confirm the checks can catch mistakes, I made two deliberate breakages and then restored the code:

- Changing the standard delivery fee gave 8,195 differences not explained by CR-01.
- Removing the express fee made 10 new tests fail. The comparison did not see it, because it never uses express.

## Part C: Review

**1. What actually changed.** In `service.py`:

- the constants;
- the new functions `_delivery_charge_cents()` and `_list_choices()`;
- one line in `_price_request()`.

In `cli.py`, the help text. In `README.md`, the usage section. `menu.py` did not change, and neither did any public service method or `storage.py`.

**2. Was the prediction correct?** Mostly. Every predicted file and method was right, and so was every unchanged one. Things I did not foresee:

- The customer-type message used the same `' or '.join` pattern, so it moved to `_list_choices()` too. Its text is unchanged.
- The CLI help needed three extra constant imports.
- The Task 4 comparison script could not be reused as it was, because CR-01 changes wording on purpose. I needed `compare_cr01.py` to separate intended changes from regressions.
- That comparison cannot see the new feature at all, so the new tests are essential.

**3. Tests added or updated.** I added 18 tests in `tests/test_express.py`. No existing test was edited.

**4. Effect of the earlier refactoring: much easier.**

- **Extract Method:** the fee rule was changed once, in `_price_request()`. Before the refactoring it was in two copies, and quotes and orders could have disagreed, which would break CR-01 requirement 5.
- **Named constants:** one new tuple entry updated the validation, the CLI choices, the usage text and the menu prompt. Before the refactoring the options were typed in four places across three files.
- **Lookup helpers:** little effect. Express orders reuse the same lookups.

The one small cost: building messages from the constants exposed the awkward "or" wording, which needed `_list_choices()`.
