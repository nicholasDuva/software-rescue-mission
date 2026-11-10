# software-rescue-mission
You have joined a software development team and inherited an existing application called Campus Supply Desk. The application has an existing implementation, but its code may contain problems that make it difficult to understand, test, debug, and maintain.

## Usage

```sh
python -m supplydesk                      # interactive menu
python -m supplydesk catalog
python -m supplydesk quote --customer student --fulfillment express --item hoodie:2
python -m supplydesk place --item notebook:2 --item mug:1
python -m supplydesk orders | show ORD-0001 | cancel ORD-0001
```

Options for `quote` and `place`: `--customer regular|student` (default `regular`) and `--fulfillment pickup|delivery|express` (default `pickup`).

| Fulfillment | Charge |
|---|---|
| `pickup` | free |
| `delivery` | $6.00, free when the subtotal after any student discount is at least $100.00 |
| `express` | $12.00 always, never waived |

Students get 10% off merchandise when the subtotal is at least $50.00. The discount never applies to delivery or express charges.
