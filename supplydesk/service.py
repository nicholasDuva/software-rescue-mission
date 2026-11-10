"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore

# Business rules of the store. All money amounts are integer Canadian cents.
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

STATUS_PLACED = "placed"
STATUS_CANCELLED = "cancelled"


def _percentage_of(amount_cents, percent):
    """Return percent% of an amount, rounded to the nearest cent (half a cent rounds up).

    Integer arithmetic only: adding 50 before the floor division by 100 turns
    "round down" into "round to nearest".
    """
    return (amount_cents * percent + 50) // 100


def _find_product(state, product_id):
    """Return the catalog product with this ID, or None if there is none."""
    for product in state["catalog"]:
        if product["product_id"] == product_id:
            return product
    return None


def _find_order(state, order_id):
    """Return the saved order with this ID; raise ValueError if there is none."""
    for order in state["orders"]:
        if order["order_id"] == order_id:
            return order
    raise ValueError("Unknown order: " + order_id)


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def quote(self, customer_type, items, fulfillment=DEFAULT_FULFILLMENT):
        state = self.store.load()
        return self._price_request(state, customer_type, items, fulfillment)

    def place_order(self, customer_type, items, fulfillment=DEFAULT_FULFILLMENT):
        state = self.store.load()
        priced = self._price_request(state, customer_type, items, fulfillment)
        order = {
            "order_id": "ORD-" + str(state["next_order_number"]).zfill(4),
            "status": STATUS_PLACED,
            **priced,
        }
        for line in order["items"]:
            _find_product(state, line["product_id"])["stock"] -= line["quantity"]
        state["next_order_number"] += 1
        state["orders"].append(order)
        self.store.save(state)
        return order

    def _price_request(self, state, customer_type, items, fulfillment):
        """Validate a request against the loaded state and return its priced lines and totals.

        Shared by quote() and place_order(), so both always apply the same rules.
        Raises ValueError for an invalid request; never changes state.
        """
        if customer_type not in CUSTOMER_TYPES:
            raise ValueError(f"Customer type must be {' or '.join(CUSTOMER_TYPES)}.")
        if fulfillment not in FULFILLMENT_OPTIONS:
            raise ValueError(f"Fulfillment must be {' or '.join(FULFILLMENT_OPTIONS)}.")
        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")
        lines = []
        subtotal = 0
        requested = {}  # product ID -> units requested so far, across repeated lines
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each item must contain a product_id and quantity.")
            product = _find_product(state, item.get("product_id"))
            if product is None:
                raise ValueError("Unknown product.")
            quantity = item.get("quantity")
            if type(quantity) is not int or not MIN_QUANTITY <= quantity <= MAX_QUANTITY:
                raise ValueError(
                    f"Quantity must be an integer from {MIN_QUANTITY} to {MAX_QUANTITY}.")
            product_id = product["product_id"]
            requested[product_id] = requested.get(product_id, 0) + quantity
            if requested[product_id] > product["stock"]:
                raise ValueError("Not enough stock for " + product_id + ".")
            line_total = product["unit_price_cents"] * quantity
            subtotal += line_total
            lines.append({
                "product_id": product["product_id"],
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],
                "quantity": quantity,
                "line_total_cents": line_total,
            })
        discount = 0
        if customer_type == STUDENT and subtotal >= STUDENT_DISCOUNT_THRESHOLD_CENTS:
            discount = _percentage_of(subtotal, STUDENT_DISCOUNT_PERCENT)
        delivery = 0
        if fulfillment == DELIVERY and subtotal - discount < FREE_DELIVERY_THRESHOLD_CENTS:
            delivery = DELIVERY_FEE_CENTS
        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": lines,
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "delivery_cents": delivery,
            "total_cents": subtotal - discount + delivery,
        }

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        return _find_order(self.store.load(), order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = _find_order(state, order_id)
        if order["status"] == STATUS_CANCELLED:
            return order  # its stock was already restored by the first cancellation
        for line in order["items"]:
            product = _find_product(state, line["product_id"])
            if product is not None:  # as before, a product no longer in the catalog is skipped
                product["stock"] += line["quantity"]
        order["status"] = STATUS_CANCELLED
        self.store.save(state)
        return order
