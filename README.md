# Dead-Stock Predictor (v1 prototype)

Reads a tack shop's sales history from a CSV and tells you which products are
turning into **dead stock** — cash frozen on the shelf — so you can mark them
down, stop reordering, or clear them out. Produces a single `report.html` you
open in your browser.

**No accounts, no internet, no database.** It runs entirely on your machine
using only Python's built-in tools — **nothing to install.**

---

## 1. What you need

- A Mac (or PC) with **Python 3** installed. To check, open Terminal and run:
  ```
  python3 --version
  ```
  If you see a version number (e.g. `Python 3.9.6`), you're ready. If not,
  install it from https://www.python.org/downloads/ .

That's it. There are **no other dependencies to install** — no `pip install`
step, no pandas.

---

## 2. Run it on the sample data (try this first)

The project ships with a fictional tack shop's data so you can see it work
before you have a real shop's export.

In Terminal, go to this folder and run:

```
cd "dead-stock-predictor"
python3 generate_sample.py      # (already done once — recreates the sample CSVs)
python3 predictor.py sample_sales.csv
```

You'll see a summary printed in the Terminal, and a file called
**`report.html`** will appear in the folder. **Double-click it** to open the
full report in your browser.

What you should see: a headline showing the cash tied up in at-risk stock, a
"what to do this week" list, and a table of all products ranked from most to
least risky (red = mark down, amber = watch, green = healthy).

---

## 3. Run it on a real shop's CSV

When you have a real export, just point the tool at it:

```
python3 predictor.py "path/to/their_sales.csv"
```

The tool **auto-detects** which columns are which (date, quantity, product,
cost, etc.), and prints what it found so you can check it. It understands
common naming variations (`qty`, `units_sold`, `Sale Date`, `RRP`, and so on).

**If stock levels are in a separate file:**
```
python3 predictor.py their_sales.csv --stock their_stock.csv
```

**If it guesses a column wrong,** override it (repeat `--map` as needed):
```
python3 predictor.py their_sales.csv --map quantity=UnitsSold --map date=OrderDate
```
Valid field names for `--map`: `date`, `quantity`, `sku`, `product_name`,
`unit_cost`, `retail_price`, `stock_on_hand`, `category`.

**Other options:**
```
--out my_report.html      # name the output file
--asof 2026-06-30         # measure "today" from a specific date
                          # (default: the most recent sale in the file)
```

### What it can and can't compute if data is missing
- **No stock-on-hand column?** It still scores risk from sales velocity and
  staleness, but can't show "weeks of cover" or "cash at risk." The report
  says so at the bottom.
- **No unit-cost column?** Everything works except the cash figures.

---

## 4. The columns it looks for

| Field | Needed? | Example column names it recognises |
|-------|---------|-----------------------------------|
| Product name | one of these two | `product`, `name`, `item`, `description` |
| SKU / code | one of these two | `sku`, `item_id`, `code`, `barcode` |
| Sale date | **required** | `date`, `sale_date`, `order_date` |
| Quantity sold | **required** | `qty`, `units_sold`, `quantity` |
| Unit cost | optional | `cost`, `cost_price`, `wholesale` |
| Retail price | optional | `price`, `retail`, `rrp` |
| Stock on hand | optional | `stock`, `on_hand`, `inventory`, `soh` |
| Category | optional | `category`, `department`, `type` |

---

## 5. How the risk score works (and how to tune it)

Every product gets a **Dead-Stock Risk Score from 0 (healthy) to 100 (frozen
cash)**. It blends four things — a product scores high when it is:

1. **Selling slowly or not at all** — few/zero units per week (weight 30%)
2. **Massively overstocked** — many weeks of stock for its demand (weight 30%)
3. **Stale** — hasn't sold in a long time (weight 25%)
4. **Tying up a lot of cash** — high stock value at risk (weight 15%)

Each of the four is scored 0–100 on its own, then blended using those weights.

**To tune it, open `predictor.py` and edit the `TUNING KNOBS` section near the
top.** It's all plain-English constants — for example:

```python
RECENT_WEEKS = 12        # how many weeks counts as "recent" sales
HEALTHY_VELOCITY = 2.0   # units/week that counts as healthy demand
HIGH_COVER = 52          # weeks of stock = maximum overstock risk
STALE_DAYS = 90          # days without a sale = maximum staleness
WEIGHT_VELOCITY = 0.30   # how much each factor counts (must total 1.0)
MARKDOWN_SCORE = 70      # score at/above this = "Mark down now"
CURRENCY = "£"           # change to "$", "€", etc.
```

Change a number, save the file, and re-run — the report updates instantly.

**Recommended actions** come from the score plus context:
- **Reorder** — selling well and about to run out
- **Mark down now** — high risk (score ≥ 70); a suggested markdown date is shown
- **Watch** — moderate risk (score ≥ 45); revisit in a few weeks
- **Healthy** — nothing to do

---

## 6. The files in this folder

| File | What it is |
|------|-----------|
| `predictor.py` | The analysis engine + report generator (the main program) |
| `generate_sample.py` | Creates the fictional sample data |
| `sample_sales.csv` | Fictional 12-month sales history (created by the generator) |
| `sample_stock.csv` | Fictional current stock levels (created by the generator) |
| `report.html` | The output report (created when you run `predictor.py`) |
| `README.md` | This file |

---

*This is a v1 proof-of-concept for demoing to shop owners. It's intentionally
simple and self-contained so it "just runs."*
