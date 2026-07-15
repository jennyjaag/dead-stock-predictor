"""
generate_sample.py
-------------------
Creates a realistic, fictional tack-shop dataset so you can run and demo the
Dead-Stock Predictor before you have a real shop's export.

It writes TWO files (to show that stock levels can live in a separate file):
  1. sample_sales.csv  -> one row per sale (the transaction history)
  2. sample_stock.csv  -> one row per product (current stock on hand)

Run it with:   python3 generate_sample.py
Everything here is deterministic (fixed random seed) so you get the same
data every time -- handy for demos.
"""

import csv
import random
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
random.seed(42)                      # fixed seed = same data every run
END_DATE = date(2026, 7, 14)         # the "export date" -- data runs up to here
WEEKS_OF_HISTORY = 53                # ~12 months of sales
START_DATE = END_DATE - timedelta(weeks=WEEKS_OF_HISTORY)

# ---------------------------------------------------------------------------
# The product catalogue.
# Each product is a tuple:
#   sku, name, category, unit_cost, retail_price,
#   rate_start  = avg units sold/week at the START of the year
#   rate_end    = avg units sold/week at the END of the year (lets velocity
#                 accelerate or decay over time)
#   stock_on_hand = how many units are sitting on the shelf right now
#   dead_weeks_ago = if >0, the product simply stopped selling this many weeks
#                    ago (simulates true dead stock). 0 = still selling.
# ---------------------------------------------------------------------------
PRODUCTS = [
    # --- Fast movers: sell steadily, low stock, healthy -------------------
    ("FLY-001", "Fly Spray 1L",              "Fly Control", 6.50, 14.99, 18, 22,  40, 0),
    ("TRT-001", "Horse Treats Apple 1kg",    "Feed & Treats", 3.20, 7.99, 25, 24,  60, 0),
    ("HOF-001", "Hoof Oil 500ml",            "Hoof Care", 4.10, 9.99, 12, 13,  30, 0),
    ("PAD-001", "Everyday Saddle Pad Navy",  "Saddle Pads", 11.00, 24.99, 9, 10, 22, 0),
    ("GLV-001", "Riding Gloves Black M",     "Rider Apparel", 5.80, 14.99, 8, 9,  25, 0),

    # --- Seasonal: fly spray-style summer peak, now slowing ---------------
    ("FLY-002", "Fly Rug Mesh Cob",          "Fly Control", 22.00, 49.99, 6, 3,  35, 0),
    ("PAD-002", "Cooler Rug Fleece",         "Rugs", 18.00, 39.99, 4, 7,  28, 0),

    # --- Medium / watch: soft demand, a bit overstocked -------------------
    ("BRE-001", "Breeches Beige 28",         "Rider Apparel", 24.00, 59.99, 3, 2,  30, 0),
    ("BRE-002", "Breeches Navy 30",          "Rider Apparel", 24.00, 59.99, 3, 2,  26, 0),
    ("BOO-001", "Jodhpur Boots Brown 5",     "Footwear", 28.00, 64.99, 2, 2,  18, 0),
    ("PAD-003", "Dressage Pad White",        "Saddle Pads", 13.00, 29.99, 3, 2,  24, 0),
    ("BIT-001", "Loose Ring Snaffle 5in",    "Bits & Bridles", 16.00, 34.99, 2, 1, 20, 0),

    # --- Clear dead stock: high stock, stopped selling months ago ---------
    ("JKT-001", "Show Jacket Tweed 16",      "Rider Apparel", 55.00, 129.99, 1, 0, 14, 30),
    ("JKT-002", "Show Jacket Navy 8",        "Rider Apparel", 55.00, 129.99, 1, 0, 11, 26),
    ("BIT-002", "Kimblewick Bit 6in",        "Bits & Bridles", 19.00, 42.99, 1, 0, 16, 34),
    ("PAD-004", "Saddle Pad Neon Pink",      "Saddle Pads", 12.00, 27.99, 2, 0, 33, 22),
    ("BOO-002", "Long Riding Boots Black 7", "Footwear", 62.00, 149.99, 1, 0, 9, 40),
    ("RUG-001", "Turnout Rug 6ft3 200g",     "Rugs", 38.00, 89.99, 2, 0, 20, 18),

    # --- Very slow but not fully dead: occasional sale --------------------
    ("SPR-001", "Spurs Stainless",           "Accessories", 7.00, 16.99, 1, 1, 15, 0),
    ("BND-001", "Bandages Set of 4 Red",     "Accessories", 9.00, 19.99, 1, 1, 21, 0),
]


def weekly_rate(rate_start, rate_end, week_index, total_weeks):
    """Linearly interpolate the sales rate from start-of-year to end-of-year."""
    if total_weeks <= 1:
        return rate_end
    fraction = week_index / (total_weeks - 1)
    return rate_start + (rate_end - rate_start) * fraction


def draw_units(avg_per_week):
    """
    Turn an average weekly rate into a whole number of units for one week,
    with a bit of natural randomness. Never negative.
    """
    if avg_per_week <= 0:
        return 0
    # Simple noisy draw around the average (approximates real week-to-week wobble)
    noise = random.uniform(-0.6, 0.6) * avg_per_week
    return max(0, round(avg_per_week + noise))


def main():
    sales_rows = []

    for (sku, name, category, cost, retail,
         rate_start, rate_end, stock, dead_weeks_ago) in PRODUCTS:

        for week in range(WEEKS_OF_HISTORY):
            week_start = START_DATE + timedelta(weeks=week)
            weeks_from_end = WEEKS_OF_HISTORY - week

            # If this product "died", zero out sales in its final weeks
            if dead_weeks_ago > 0 and weeks_from_end <= dead_weeks_ago:
                continue

            rate = weekly_rate(rate_start, rate_end, week, WEEKS_OF_HISTORY)
            units = draw_units(rate)
            if units == 0:
                continue

            # Spread the week's units across 1-3 shopping days
            days = sorted(random.sample(range(7), min(3, max(1, units))))
            per_day = [0] * len(days)
            for u in range(units):
                per_day[u % len(days)] += 1

            for d, qty in zip(days, per_day):
                if qty == 0:
                    continue
                sale_date = week_start + timedelta(days=d)
                if sale_date > END_DATE:
                    continue
                sales_rows.append({
                    "date": sale_date.isoformat(),
                    "sku": sku,
                    "product_name": name,
                    "category": category,
                    "quantity": qty,
                    "unit_cost": f"{cost:.2f}",
                    "retail_price": f"{retail:.2f}",
                })

    # Sort by date so the file looks like a natural export
    sales_rows.sort(key=lambda r: (r["date"], r["sku"]))

    # --- Write the sales file ------------------------------------------------
    with open("sample_sales.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "sku", "product_name", "category",
            "quantity", "unit_cost", "retail_price",
        ])
        writer.writeheader()
        writer.writerows(sales_rows)

    # --- Write the stock file (one row per product) --------------------------
    with open("sample_stock.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sku", "product_name", "stock_on_hand"])
        writer.writeheader()
        for (sku, name, category, cost, retail,
             rate_start, rate_end, stock, dead_weeks_ago) in PRODUCTS:
            writer.writerow({"sku": sku, "product_name": name, "stock_on_hand": stock})

    print("Created sample_sales.csv  ({} sale rows)".format(len(sales_rows)))
    print("Created sample_stock.csv  ({} products)".format(len(PRODUCTS)))
    print("Data runs {} -> {}".format(START_DATE.isoformat(), END_DATE.isoformat()))


if __name__ == "__main__":
    main()
