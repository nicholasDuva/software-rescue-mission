# System Understanding Note: Campus Supply Desk

## 1. Main purpose

Campus Supply Desk is a small offline Python (3.10+) command-line application for a campus store. Staff can view products and stock, get a price **quote**, **place** an order (which deducts stock and gets an ID like `ORD-0001`), browse or look up order history, and **cancel** an order (which puts the stock back). All data lives in a local JSON save file (`.supplydesk/state.json` by default, or another file chosen with `--data`). Money is stored and calculated as integer Canadian cents. Only the interactive menu converts it to dollars for display.

## 2. Major components

The design has three layers: two user interfaces call one service, and the service calls one storage class.

| File / class | Responsibility |
|---|---|
| `supplydesk/__main__.py` | Runs when you type `python -m supplydesk`. It calls `cli.main()` and passes the result to `SystemExit`, so that result becomes the process exit status. |
| `supplydesk/cli.py` | `build_parser()` sets up the argparse sub-commands (`catalog`, `quote`, `place`, `orders`, `show`, `cancel`) and the global `--data` option. `parse_item()` turns text like `notebook:2` into `{"product_id": "notebook", "quantity": 2}`. `main()` creates the `OrderService`. With no sub-command it opens the menu. Otherwise it runs the chosen operation, prints the result as JSON and returns `0`, or prints an error and returns `2`. |
| `supplydesk/menu.py` | The interactive interface. `run_menu()` loops over options 0–6. `read_request()` asks for the customer type, the items and the fulfillment option, filling in the defaults `regular` and `pickup`. `show_catalog()`, `show_order()` and `money()` format the output. It exits on `EOFError` or `KeyboardInterrupt`. On `ValueError`, `OSError`, `KeyError` or `TypeError` it prints the error and shows the menu again. |
| `supplydesk/service.py`: `OrderService` | Holds all the business rules: `catalog()`, `quote()`, `place_order()`, `list_orders()`, `get_order()` and `cancel_order()`. This covers validation, pricing (student discount, delivery charge), changing stock, creating order IDs and recording status. It keeps nothing in memory between calls: each method loads the state fresh from the store. |
| `supplydesk/storage.py`: `JsonStore` | `load()` reads the save file. If the file does not exist, it builds a new state from `catalog.json` (`schema_version: 1`, `next_order_number: 1`, `orders: []`). `save()` creates the folder if needed and overwrites the whole file. |
| `supplydesk/catalog.json` | The starting data: five products, each with a price and stock level. |
| `tests/test_smoke.py` | Four `unittest` smoke tests that call `OrderService` directly, using a temporary save file. |

The saved state is a plain dictionary: `{schema_version, next_order_number, catalog: [product…], orders: [order…]}`.

## 3. Key execution flow: placing an order through the menu

1. `python -m supplydesk` starts `__main__.py`, which calls `cli.main()`. `parse_args()` finds no sub-command, so `main()` creates `OrderService(args.data)` (which wraps a `JsonStore`) and calls `menu.run_menu(service)`.
2. The user picks **3**. `run_menu()` calls `read_request(service)`. That function shows the catalog (`service.catalog()` → `JsonStore.load()`) and then asks for the customer type and for product/quantity pairs until the product ID is left blank. Each quantity is converted with `int()`, and the user is asked to re-enter the item if that fails. Finally it asks for the fulfillment option and returns `(customer, items, fulfillment)`.
3. `run_menu()` calls `service.quote(*request)` and shows the result with `show_order()`. This is only a preview: nothing is saved.
4. If the user answers `y`, `run_menu()` calls `service.place_order(*request)`. That method:
   - loads fresh state;
   - checks the customer type, the fulfillment option and that the item list is not empty;
   - for each item, finds the product in `state["catalog"]` by checking each product in turn, checks that the quantity is an `int` from 1 to 99 and is no more than the stock, and builds a line with `line_total_cents`;
   - calculates the discount as `(subtotal * 10 + 50) // 100`, which is integer rounding with half a cent rounded up, and the 600-cent delivery charge;
   - builds the order with `order_id = "ORD-" + str(next_order_number).zfill(4)` and `status: "placed"`;
   - only then deducts stock, increases `next_order_number`, appends the order and calls `self.store.save(state)` once.
5. `show_order()` prints the returned order. If any check raises `ValueError`, this happens before `save()`, so the file is unchanged, and the `except` block in `run_menu()` reports the error and shows the menu again.

The CLI `place` command follows the same path from step 4. The difference is that argparse and `parse_item()` build the items, there is no confirmation prompt, and the result is printed with `json.dumps`.

## 4. Hardest part to understand and maintain

The hardest part is **`OrderService.quote()` and `OrderService.place_order()`** (`service.py` lines 13–61 and 63–121). `place_order()` copies about 40 lines of `quote()` word for word: the validation, the product lookup, the line building and the pricing. There is no shared helper. As a result:

- **Every rule change has to be made twice.** The spec requires that a quote and the order placed after it show the same prices. If the two copies ever differ, that requirement breaks without any error.
- **Each method does too many jobs in one long function:** validating input, looking up products, calculating money, creating IDs and saving. The same nested "search the catalog" loop also appears in stock deduction and in `cancel_order()`. This makes it hard to test or reuse the pricing rules on their own.
- **Fixed values are written directly into the code and repeated:** the numbers `5000`, `10000`, `600` and `99`, and the tuples `("regular", "student")` and `("pickup", "delivery")`. The same choices are repeated again in `cli.build_parser()`.
- **The data is untyped nested dictionaries** (`state["catalog"]`, `order["items"]`). The only way to learn their shape is to read `JsonStore.load()` and the method bodies.

This structure makes mistakes easy to miss when reading the code against `FUNCTIONAL_SPEC.md`. For example, the discount condition is `subtotal > 5000`, but the spec says the discount applies when the subtotal is "at least" $50.00. The stock check also looks at each line separately instead of adding up repeated lines of the same product.
