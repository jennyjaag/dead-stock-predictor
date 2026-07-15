"""
generate_demo.py -- create a synthetic tack-shop dataset in the SAME format as
real Shopify exports, so the app's "Try demo data" button runs the exact same
code path as a real upload. Writes:

    demo_data/demo_sales.csv     (Shopify 'Sales by product': Product title, Net items sold)
    demo_data/demo_products.csv  (Shopify products export: variant rows w/ inventory + cost)

Deterministic (no randomness) so the demo looks the same every time.
Run once:  python3 generate_demo.py
"""

import csv
import os

os.makedirs("demo_data", exist_ok=True)

# Each product: (title, vendor, type, status, [ (variant_qty, cost, price) ... ], units_sold_12mo)
# Designed to tell a clear story: fast movers, healthy, watch, and obvious dead stock.
PRODUCTS = [
    # --- fast movers: sell well, low stock -> Reorder / Healthy ------------
    ("Meadowbrook Fly Spray 1L", "Meadowbrook", "Fly Control", "active",
     [(18, 6.5, 14.99)], 210),
    ("Oakfield Horse Treats 1kg", "Oakfield", "Feed & Treats", "active",
     [(24, 3.2, 7.99)], 180),
    ("Everyday Saddle Pad Navy", "StablePro", "Saddle Pads", "active",
     [(9, 11.0, 24.99), (7, 11.0, 24.99)], 96),
    ("Riding Gloves Black", "StablePro", "Rider Apparel", "active",
     [(6, 5.8, 14.99), (6, 5.8, 14.99), (5, 5.8, 14.99)], 88),
    ("Hoof Oil 500ml", "Oakfield", "Hoof Care", "active", [(14, 4.1, 9.99)], 130),

    # --- healthy / watch --------------------------------------------------
    ("Competition Breeches Beige", "Elstead", "Breeches", "active",
     [(4, 24.0, 59.99), (5, 24.0, 59.99), (3, 24.0, 59.99)], 28),
    ("Dressage Pad White", "StablePro", "Saddle Pads", "active",
     [(12, 13.0, 29.99)], 22),
    ("Show Shirt Long Sleeve", "Elstead", "Show Shirts", "active",
     [(8, 12.0, 34.99), (6, 12.0, 34.99)], 26),
    ("Cooler Rug Fleece", "WarmwellRugs", "Rugs", "active",
     [(10, 18.0, 39.99)], 40),

    # --- overstocked, slow -> Watch / Mark down ---------------------------
    ("Leather Half Chaps Brown", "Parforce", "Footwear", "active",
     [(9, 28.0, 64.99), (8, 28.0, 64.99)], 6),
    ("Quilted Riding Gilet", "Elstead", "Rider Apparel", "active",
     [(11, 22.0, 49.99), (9, 22.0, 49.99)], 5),
    ("Snaffle Bridle Cob", "Parforce", "Bits & Bridles", "active",
     [(14, 26.0, 59.99)], 4),

    # --- clear dead stock: high stock, ZERO sales in 12mo -----------------
    ("Tweed Show Jacket 16", "Elstead", "Show Coats", "active",
     [(6, 55.0, 129.99), (5, 55.0, 129.99), (3, 55.0, 129.99)], 0),
    ("Neon Pink Saddle Pad", "StablePro", "Saddle Pads", "active",
     [(20, 12.0, 27.99), (13, 12.0, 27.99)], 0),
    ("Long Riding Boots Black 7", "Parforce", "Footwear", "active",
     [(9, 62.0, 149.99)], 0),
    ("Kimblewick Bit 6in", "Parforce", "Bits & Bridles", "active",
     [(16, 19.0, 42.99)], 0),
    ("Turnout Rug 200g 6ft3", "WarmwellRugs", "Rugs", "active",
     [(11, 38.0, 89.99), (9, 38.0, 89.99)], 1),
    ("Diamante Browband Full", "Parforce", "Bits & Bridles", "active",
     [(22, 9.0, 21.99)], 1),

    # --- missing-cost item (exercises the 'no cost' flag) -----------------
    ("Embroidered Stable Bandages", "Oakfield", "Accessories", "active",
     [(15, "", 19.99)], 0),

    # --- a draft product holding stock (exercises the draft flag) ---------
    ("Prototype Winter Jacket", "Elstead", "Rider Apparel", "draft",
     [(8, 40.0, 99.99)], 0),

    # --- an archived product still holding stock --------------------------
    ("Discontinued Fleece Cooler", "WarmwellRugs", "Rugs", "archived",
     [(4, 16.0, 34.99)], 0),
]


def handle(title):
    return title.lower().replace(" ", "-").replace("'", "")


def main():
    # products export (one row per variant)
    pcols = ["Handle", "Title", "Vendor", "Product Category", "Type", "Tags", "Published",
             "Option1 Name", "Option1 Value", "Variant SKU", "Variant Inventory Qty",
             "Variant Price", "Cost per item", "Gift Card", "Status"]
    with open("demo_data/demo_products.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pcols)
        w.writeheader()
        for title, vendor, ptype, status, variants, _ in PRODUCTS:
            h = handle(title)
            for i, (qty, cost, price) in enumerate(variants, 1):
                w.writerow({
                    "Handle": h, "Title": title if i == 1 else "",
                    "Vendor": vendor if i == 1 else "", "Type": ptype if i == 1 else "",
                    "Published": "TRUE", "Option1 Name": "Size", "Option1 Value": "Size {}".format(i),
                    "Variant SKU": "{}-{}".format(h[:12], i), "Variant Inventory Qty": qty,
                    "Variant Price": price, "Cost per item": cost, "Gift Card": "false",
                    "Status": status if i == 1 else "",
                })

    # sales by product (one row per product)
    with open("demo_data/demo_sales.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Product title", "Net items sold"])
        w.writeheader()
        for title, _, _, _, _, sold in PRODUCTS:
            if sold > 0:
                w.writerow({"Product title": title, "Net items sold": sold})

    print("Wrote demo_data/demo_products.csv and demo_data/demo_sales.csv "
          "({} products)".format(len(PRODUCTS)))


if __name__ == "__main__":
    main()
