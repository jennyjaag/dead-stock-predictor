"""
predictor.py  --  Dead-Stock Predictor (v1 prototype)
=====================================================

WHAT IT DOES
------------
Reads a shop's sales history from a CSV and works out, for every product:
  * how fast it sells (sell-through velocity, units/week)
  * how long the current stock will last (weeks of cover)
  * how stale it is (days since the last sale)
  * whether demand is accelerating or decaying (trend)
  * a Dead-Stock Risk Score from 0 (healthy) to 100 (frozen cash)
  * a recommended action + suggested markdown date
  * the cash tied up in it (units on hand x unit cost)

Then it writes a single, self-contained report.html you can open in a browser.

HOW TO RUN
----------
  python3 predictor.py sample_sales.csv

  # if stock levels are in a separate file:
  python3 predictor.py sample_sales.csv --stock sample_stock.csv

  # override a column guess if the auto-detector gets one wrong:
  python3 predictor.py my_sales.csv --map quantity=UnitsSold --map date=OrderDate

WHERE TO TUNE THE RISK FORMULA
------------------------------
See the "TUNING KNOBS" section just below. Every threshold and weight that
drives the score lives there in plain English -- change a number, re-run.

No internet, no accounts, no database. Standard-library Python only.
"""

import argparse
import csv
import os
import sys
from datetime import date, datetime, timedelta


# ===========================================================================
# TUNING KNOBS  --  everything that shapes the risk score lives here.
# Change a number, re-run the script, and the report updates. No other edits
# needed. Each knob is explained in plain English.
# ===========================================================================

# How many recent weeks count as "recent" when measuring how fast something
# sells. 12 weeks (~3 months) is a good default for seasonal retail.
RECENT_WEEKS = 12

# --- Velocity (how fast it sells) ------------------------------------------
# At or above this many units/week we treat demand as healthy (0 risk from
# velocity). At 0 units/week the velocity risk is maxed out.
HEALTHY_VELOCITY = 2.0        # units per week

# --- Weeks of cover (how long the stock will last) -------------------------
# Below LOW_COVER weeks = practically no risk from overstock.
# Above HIGH_COVER weeks = maximum overstock risk (a year+ of stock sitting).
LOW_COVER = 8                 # weeks
HIGH_COVER = 52               # weeks

# --- Staleness (days since the last sale) ----------------------------------
# Up to FRESH_DAYS = fine. At/after STALE_DAYS = maximum staleness risk.
FRESH_DAYS = 14
STALE_DAYS = 90

# --- How the four ingredients are weighted into the 0-100 score ------------
# These must add up to 1.0. Raise the one you care about most.
WEIGHT_VELOCITY  = 0.30       # slow / zero sales
WEIGHT_COVER     = 0.30       # too much stock for the demand
WEIGHT_STALENESS = 0.25       # hasn't sold in a long time
WEIGHT_CASH      = 0.15       # how much money is tied up (bigger = more urgent)

# --- Action thresholds ------------------------------------------------------
# A product is counted in the "cash at risk" headline at/above this score.
AT_RISK_SCORE = 60
# Score bands that decide the recommended action.
MARKDOWN_SCORE = 70           # >= this -> "Mark down now"
WATCH_SCORE    = 45           # >= this (but < MARKDOWN) -> "Watch"
# If something is selling and will run out within this many weeks -> "Reorder".
REORDER_COVER  = 6            # weeks

# --- Cosmetic ---------------------------------------------------------------
CURRENCY = "£"                # change to "$", "€", etc.


# ===========================================================================
# COLUMN MAPPING
# Real exports name their columns all sorts of ways. We map the shop's column
# headers onto the fields we need by matching against a list of common names.
# ===========================================================================

# For each field we need, a list of header names we'll recognise. Matching is
# case-insensitive and ignores spaces/underscores/punctuation.
COLUMN_SYNONYMS = {
    "sku":           ["sku", "productid", "itemid", "itemcode", "code", "style", "stylecode", "barcode"],
    "product_name":  ["productname", "product", "name", "item", "itemname", "description", "title"],
    "date":          ["date", "saledate", "orderdate", "transactiondate", "invoicedate", "soldon", "day"],
    "quantity":      ["quantity", "qty", "units", "unitssold", "qtysold", "count", "sold", "quantitysold"],
    "unit_cost":     ["unitcost", "cost", "costprice", "buyprice", "wholesale", "wholesaleprice", "costeach"],
    "retail_price":  ["retailprice", "price", "retail", "sellprice", "unitprice", "rrp", "saleprice"],
    "stock_on_hand": ["stockonhand", "stock", "onhand", "qtyonhand", "inventory", "instock",
                      "quantityonhand", "soh", "stocklevel", "available"],
    "category":      ["category", "dept", "department", "type", "group", "productgroup", "class"],
}

# Which fields we absolutely need vs. can live without.
REQUIRED_FIELDS = ["date", "quantity"]           # plus at least one of sku/product_name
OPTIONAL_FIELDS = ["unit_cost", "retail_price", "stock_on_hand", "category"]


def _normalise(text):
    """Lower-case and strip anything that isn't a letter or number."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def auto_map_columns(headers, overrides):
    """
    Given the CSV's header row, decide which real column feeds each field.
    `overrides` is a dict like {"quantity": "UnitsSold"} from the --map flag.
    Returns (mapping, notes) where mapping is field -> actual header (or None).
    """
    normalised = {_normalise(h): h for h in headers}
    mapping = {}

    for field, synonyms in COLUMN_SYNONYMS.items():
        # 1) explicit override from the command line always wins
        if field in overrides:
            chosen = overrides[field]
            if chosen not in headers:
                sys.exit("ERROR: --map {}={} but there is no column named '{}'.\n"
                         "Columns in the file: {}".format(field, chosen, chosen, ", ".join(headers)))
            mapping[field] = chosen
            continue
        # 2) otherwise look for a header whose normalised form matches a synonym
        found = None
        for syn in synonyms:
            if syn in normalised:
                found = normalised[syn]
                break
        mapping[field] = found

    return mapping


def prompt_for_missing(mapping, headers, field):
    """
    If a needed field couldn't be auto-detected and we're running in a real
    terminal, ask the user which column to use. Otherwise fail with guidance.
    """
    if not sys.stdin.isatty():
        return None
    print("\nCouldn't auto-detect the '{}' column.".format(field))
    print("Available columns:")
    for i, h in enumerate(headers, 1):
        print("  {}. {}".format(i, h))
    answer = input("Enter the number for '{}' (or press Enter to skip): ".format(field)).strip()
    if answer.isdigit() and 1 <= int(answer) <= len(headers):
        return headers[int(answer) - 1]
    return None


# ===========================================================================
# LOADING THE DATA
# ===========================================================================

def parse_date(value):
    """Accept the date formats real exports commonly use."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def to_number(value):
    """Turn '1,234.50', '£9.99', '  12 ' etc. into a float. Blank -> None."""
    if value is None:
        return None
    cleaned = value.strip().replace(",", "")
    for symbol in ("£", "$", "€", "%"):
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()
    if cleaned == "":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_sales(path, overrides):
    """Read the sales CSV and return (list_of_rows, mapping)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = auto_map_columns(headers, overrides)

        # We need a product identifier: sku OR product_name.
        if not mapping.get("sku") and not mapping.get("product_name"):
            picked = prompt_for_missing(mapping, headers, "product_name")
            if picked:
                mapping["product_name"] = picked

        # We need date and quantity.
        for field in REQUIRED_FIELDS:
            if not mapping.get(field):
                picked = prompt_for_missing(mapping, headers, field)
                if picked:
                    mapping[field] = picked

        missing_required = [f for f in REQUIRED_FIELDS if not mapping.get(f)]
        if missing_required or (not mapping.get("sku") and not mapping.get("product_name")):
            sys.exit(
                "ERROR: couldn't find the columns needed to analyse this file.\n"
                "  Need a date column, a quantity column, and a product name or SKU.\n"
                "  Detected mapping: {}\n"
                "  Columns in file : {}\n"
                "  Fix with, e.g.: --map date=YourDateCol --map quantity=YourQtyCol".format(
                    {k: v for k, v in mapping.items() if v}, ", ".join(headers))
            )

        rows = []
        for raw in reader:
            d = parse_date(raw.get(mapping["date"], ""))
            qty = to_number(raw.get(mapping["quantity"], ""))
            if d is None or qty is None:
                continue  # skip unreadable rows quietly
            sku = raw.get(mapping["sku"], "").strip() if mapping.get("sku") else ""
            name = raw.get(mapping["product_name"], "").strip() if mapping.get("product_name") else ""
            key = sku or name
            if not key:
                continue
            rows.append({
                "key": key,
                "sku": sku,
                "name": name or sku,
                "category": raw.get(mapping["category"], "").strip() if mapping.get("category") else "",
                "date": d,
                "qty": qty,
                "unit_cost": to_number(raw.get(mapping["unit_cost"], "")) if mapping.get("unit_cost") else None,
                "retail_price": to_number(raw.get(mapping["retail_price"], "")) if mapping.get("retail_price") else None,
                "stock_on_hand": to_number(raw.get(mapping["stock_on_hand"], "")) if mapping.get("stock_on_hand") else None,
            })
    return rows, mapping


def load_stock(path, overrides):
    """Read an optional stock-on-hand file: returns {product_key: stock}."""
    stock = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = auto_map_columns(headers, overrides)
        key_col = mapping.get("sku") or mapping.get("product_name")
        soh_col = mapping.get("stock_on_hand")
        if not key_col or not soh_col:
            sys.exit("ERROR: stock file '{}' needs a SKU/product column and a stock column. "
                     "Found: {}".format(path, ", ".join(headers)))
        for raw in reader:
            key = raw.get(key_col, "").strip()
            soh = to_number(raw.get(soh_col, ""))
            if key and soh is not None:
                stock[key] = soh
    return stock


# ===========================================================================
# THE ANALYSIS
# ===========================================================================

def analyse(rows, stock_lookup, as_of):
    """
    Crunch the per-product metrics. `as_of` is the date we measure 'today'
    from (defaults to the most recent sale in the file).
    Returns a list of per-product dictionaries.
    """
    recent_start = as_of - timedelta(weeks=RECENT_WEEKS)
    prior_start = as_of - timedelta(weeks=2 * RECENT_WEEKS)

    # Group sale rows by product.
    products = {}
    for r in rows:
        p = products.setdefault(r["key"], {
            "key": r["key"], "sku": r["sku"], "name": r["name"],
            "category": r["category"], "sales": [],
            "unit_cost": None, "retail_price": None, "stock_in_sales": None,
        })
        p["sales"].append((r["date"], r["qty"]))
        # Keep the most recent non-empty cost/price/stock we see for the product.
        if r["unit_cost"] is not None:
            p["unit_cost"] = r["unit_cost"]
        if r["retail_price"] is not None:
            p["retail_price"] = r["retail_price"]
        if r["stock_on_hand"] is not None:
            p["stock_in_sales"] = r["stock_on_hand"]
        if not p["category"] and r["category"]:
            p["category"] = r["category"]

    results = []
    max_cash = 0.0

    for p in products.values():
        recent_units = sum(q for d, q in p["sales"] if recent_start < d <= as_of)
        prior_units = sum(q for d, q in p["sales"] if prior_start < d <= recent_start)
        last_sale = max(d for d, q in p["sales"])
        days_since = (as_of - last_sale).days

        velocity_recent = recent_units / RECENT_WEEKS      # units/week
        velocity_prior = prior_units / RECENT_WEEKS

        # Stock on hand: prefer the dedicated stock file, then a stock column
        # inside the sales file. May be None if we have neither.
        stock = stock_lookup.get(p["key"])
        if stock is None:
            stock = stock_lookup.get(p["sku"]) or stock_lookup.get(p["name"])
        if stock is None:
            stock = p["stock_in_sales"]

        # Weeks of cover = how long current stock lasts at the recent pace.
        if stock is None:
            weeks_cover = None
        elif velocity_recent > 0:
            weeks_cover = stock / velocity_recent
        else:
            weeks_cover = float("inf")     # stock but no sales = never clears

        # Trend vs. the previous comparable period.
        if velocity_prior > 0:
            trend_pct = (velocity_recent - velocity_prior) / velocity_prior * 100
        elif velocity_recent > 0:
            trend_pct = 100.0              # was zero, now selling
        else:
            trend_pct = 0.0
        if trend_pct > 15:
            trend_label = "Accelerating"
        elif trend_pct < -15:
            trend_label = "Decaying"
        else:
            trend_label = "Steady"

        # Cash tied up = units on hand x what they cost us.
        unit_cost = p["unit_cost"]
        if stock is not None and unit_cost is not None:
            cash_at_risk = stock * unit_cost
        else:
            cash_at_risk = None
        if cash_at_risk:
            max_cash = max(max_cash, cash_at_risk)

        results.append({
            "sku": p["sku"], "name": p["name"], "category": p["category"],
            "velocity_recent": velocity_recent, "velocity_prior": velocity_prior,
            "weeks_cover": weeks_cover, "days_since": days_since,
            "trend_pct": trend_pct, "trend_label": trend_label,
            "stock": stock, "unit_cost": unit_cost,
            "cash_at_risk": cash_at_risk,
        })

    # Now that we know the biggest cash exposure, compute the 0-100 score.
    for r in results:
        r["risk"], r["parts"] = risk_score(r, max_cash)
        r["action"], r["markdown_date"] = recommend(r, as_of)

    results.sort(key=lambda r: r["risk"], reverse=True)
    return results


def _band(value, low, high):
    """Scale `value` to 0-100 as it moves from `low` to `high` (clamped)."""
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    return (value - low) / (high - low) * 100.0


def risk_score(r, max_cash):
    """
    Combine four 0-100 sub-scores into the overall Dead-Stock Risk Score.

    In plain English -- a product scores HIGH (risky) when it is:
      1. Selling slowly or not at all        (velocity sub-score)
      2. Massively overstocked for its demand (weeks-of-cover sub-score)
      3. Not sold in a long time              (staleness sub-score)
      4. Holding a lot of our cash            (cash-at-risk sub-score)

    Each sub-score is 0-100, then blended using the WEIGHT_* knobs above.
    """
    # 1. Velocity: fast sales -> low risk. HEALTHY_VELOCITY or more -> 0.
    v = r["velocity_recent"]
    velocity_sub = max(0.0, 100.0 * (1 - v / HEALTHY_VELOCITY)) if HEALTHY_VELOCITY > 0 else 0.0
    velocity_sub = min(100.0, velocity_sub)

    # 2. Weeks of cover: more cover -> more risk. Unknown stock -> neutral 0.
    wc = r["weeks_cover"]
    if wc is None:
        cover_sub = 0.0
    elif wc == float("inf"):
        cover_sub = 100.0
    else:
        cover_sub = _band(wc, LOW_COVER, HIGH_COVER)

    # 3. Staleness: longer since last sale -> more risk.
    stale_sub = _band(r["days_since"], FRESH_DAYS, STALE_DAYS)

    # 4. Cash at risk: bigger dollar exposure -> more urgent. Scaled against
    #    the largest cash pile in the catalogue so it's always 0-100.
    if r["cash_at_risk"] and max_cash > 0:
        cash_sub = min(100.0, 100.0 * r["cash_at_risk"] / max_cash)
    else:
        cash_sub = 0.0

    score = (WEIGHT_VELOCITY * velocity_sub +
             WEIGHT_COVER * cover_sub +
             WEIGHT_STALENESS * stale_sub +
             WEIGHT_CASH * cash_sub)

    parts = {
        "velocity": round(velocity_sub), "cover": round(cover_sub),
        "staleness": round(stale_sub), "cash": round(cash_sub),
    }
    return round(score), parts


def recommend(r, as_of):
    """Turn the score + context into an action and a suggested markdown date."""
    v = r["velocity_recent"]
    wc = r["weeks_cover"]
    score = r["risk"]

    # Selling well and about to run out -> reorder, not mark down.
    if v > 0 and wc is not None and wc != float("inf") and wc <= REORDER_COVER:
        return "Reorder", ""

    if score >= MARKDOWN_SCORE:
        # Act now: suggest today's date.
        return "Mark down now", as_of.isoformat()
    if score >= WATCH_SCORE:
        # Give it a few weeks, then revisit.
        return "Watch", (as_of + timedelta(weeks=3)).isoformat()
    return "Healthy", ""


# ===========================================================================
# THE HTML REPORT
# ===========================================================================

def money(value):
    if value is None:
        return "—"
    return "{}{:,.0f}".format(CURRENCY, value)


def fmt_cover(wc):
    if wc is None:
        return "—"
    if wc == float("inf"):
        return "∞"
    return "{:.0f} wk".format(wc)


def risk_colour(score):
    """Return (row background, text colour) for a risk band."""
    if score >= MARKDOWN_SCORE:
        return "#fde2e1", "#a11a12"      # red-ish
    if score >= WATCH_SCORE:
        return "#fdf3d8", "#8a6100"      # amber
    return "#e3f6e5", "#1c6b28"          # green


def build_report(results, as_of, notes, source_name):
    at_risk = [r for r in results if r["risk"] >= AT_RISK_SCORE]
    total_cash_risk = sum(r["cash_at_risk"] for r in at_risk if r["cash_at_risk"])
    total_inventory = sum(r["cash_at_risk"] for r in results if r["cash_at_risk"])

    # --- ROI framing: "cash you could free up" -----------------------------
    # Make the headline number concrete: clearing even part of the at-risk
    # stock frees cash to reinvest in the fast movers flagged "Reorder".
    roi_html = ""
    if total_cash_risk > 0:
        free_half = total_cash_risk * 0.5
        roi_html = (
            '<div class="roi"><span class="roi-ico">&#128176;</span>'
            '<div><strong>Cash you could free up:</strong> clearing just half of your '
            'at-risk stock this quarter puts <b>{}</b> back in the till — cash to '
            'reinvest in the fast movers flagged &ldquo;Reorder&rdquo; below.</div></div>'
        ).format(money(free_half))

    # --- Category breakdown: where the frozen cash actually sits -----------
    cat_totals = {}
    for r in at_risk:
        if r["cash_at_risk"]:
            cat = r["category"] or "Uncategorised"
            cat_totals[cat] = cat_totals.get(cat, 0) + r["cash_at_risk"]
    categories_html = ""
    if cat_totals:
        cat_sorted = sorted(cat_totals.items(), key=lambda kv: kv[1], reverse=True)
        cat_max = cat_sorted[0][1]
        bars = []
        for name, val in cat_sorted:
            pct = (val / cat_max * 100) if cat_max else 0
            bars.append(
                '<div class="catrow"><div class="catname">{name}</div>'
                '<div class="cattrack"><div class="catfill" style="width:{pct:.0f}%"></div></div>'
                '<div class="catval">{val}</div></div>'.format(
                    name=escape(name), pct=pct, val=money(val))
            )
        categories_html = ('<div class="card"><h2>Where the frozen cash sits — by category</h2>'
                           + "".join(bars) + '</div>')

    # "What to do this week": the 5 highest scores that need an action.
    actionable = [r for r in results if r["action"] in ("Mark down now", "Watch")]
    todo = actionable[:5]

    rows_html = []
    for r in results:
        bg, fg = risk_colour(r["risk"])
        trend_arrow = ("▲" if r["trend_label"] == "Accelerating"
                       else "▼" if r["trend_label"] == "Decaying" else "▬")
        rows_html.append("""
        <tr>
          <td class="name">{name}<span class="sku">{sku}</span></td>
          <td><span class="pill" style="background:{bg};color:{fg}">{risk}</span></td>
          <td>{cover}</td>
          <td>{days}</td>
          <td>{vel:.1f}/wk <span class="trend">{arrow}</span></td>
          <td class="num">{cash}</td>
          <td>{action}{md}</td>
        </tr>""".format(
            name=escape(r["name"]),
            sku=(" · " + escape(r["sku"])) if r["sku"] and r["sku"] != r["name"] else "",
            bg=bg, fg=fg, risk=r["risk"],
            cover=fmt_cover(r["weeks_cover"]),
            days=r["days_since"],
            vel=r["velocity_recent"], arrow=trend_arrow,
            cash=money(r["cash_at_risk"]),
            action=escape(r["action"]),
            md=('<span class="md">by {}</span>'.format(r["markdown_date"]) if r["markdown_date"] else ""),
        ))

    todo_html = []
    for i, r in enumerate(todo, 1):
        todo_html.append(
            '<li><strong>{action}</strong> — {name} '
            '(risk {risk}, {cash} tied up, last sold {days} days ago)</li>'.format(
                action=escape(r["action"]), name=escape(r["name"]), risk=r["risk"],
                cash=money(r["cash_at_risk"]), days=r["days_since"]))
    if not todo_html:
        todo_html.append("<li>Nothing urgent — inventory looks healthy. 🎉</li>")

    notes_html = ""
    if notes:
        notes_html = ('<div class="notes"><strong>Note:</strong> '
                      + " ".join(escape(n) for n in notes) + "</div>")

    return TEMPLATE.format(
        source=escape(source_name),
        as_of=as_of.isoformat(),
        total_cash_risk=money(total_cash_risk),
        at_risk_count=len(at_risk),
        product_count=len(results),
        total_inventory=money(total_inventory),
        todo="".join(todo_html),
        rows="".join(rows_html),
        notes=notes_html,
        currency=CURRENCY,
        recent_weeks=RECENT_WEEKS,
        roi=roi_html,
        categories=categories_html,
    )


def escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dead-Stock Report</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; background: #f5f6f8; color: #1b1f24; }}
  .wrap {{ max-width: 1000px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 22px; margin: 0 0 2px; }}
  .sub {{ color: #6b7280; font-size: 13px; margin-bottom: 24px; }}
  .hero {{ background: #12263a; color: #fff; border-radius: 14px; padding: 26px 28px;
          display: flex; flex-wrap: wrap; gap: 30px; align-items: center; }}
  .hero .big {{ font-size: 42px; font-weight: 700; line-height: 1; }}
  .hero .label {{ font-size: 13px; opacity: .8; margin-top: 6px; }}
  .hero .divider {{ width: 1px; align-self: stretch; background: rgba(255,255,255,.2); }}
  .hero .stat {{ font-size: 26px; font-weight: 600; }}
  .card {{ background: #fff; border-radius: 14px; padding: 22px 24px; margin-top: 22px;
          box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  h2 {{ font-size: 16px; margin: 0 0 14px; }}
  ol.todo {{ margin: 0; padding-left: 20px; }}
  ol.todo li {{ margin-bottom: 8px; line-height: 1.45; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid #eef0f2; }}
  th {{ color: #6b7280; font-weight: 600; font-size: 11px; text-transform: uppercase;
        letter-spacing: .04em; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.name {{ font-weight: 600; }}
  .sku {{ display: block; font-weight: 400; color: #9aa0a6; font-size: 11px; }}
  .pill {{ display: inline-block; min-width: 34px; text-align: center; padding: 3px 8px;
          border-radius: 20px; font-weight: 700; }}
  .trend {{ color: #9aa0a6; font-size: 11px; }}
  .md {{ display: block; color: #9aa0a6; font-size: 11px; }}
  .notes {{ font-size: 12px; color: #6b7280; margin-top: 18px; line-height: 1.5; }}
  .legend {{ font-size: 11px; color: #6b7280; margin-top: 10px; }}
  .legend span {{ display: inline-block; padding: 2px 8px; border-radius: 10px; margin-right: 6px; }}
  .roi {{ display: flex; gap: 12px; align-items: flex-start; background: #eef6ff;
         border: 1px solid #cfe3fb; border-radius: 14px; padding: 16px 18px; margin-top: 16px;
         font-size: 13.5px; line-height: 1.5; color: #1b2a3a; }}
  .roi-ico {{ font-size: 20px; line-height: 1.2; }}
  .roi b {{ color: #0b57d0; }}
  .catrow {{ display: grid; grid-template-columns: 130px 1fr 70px; align-items: center;
            gap: 10px; margin-bottom: 8px; font-size: 12.5px; }}
  .catname {{ font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .cattrack {{ background: #f0f1f3; border-radius: 8px; height: 14px; overflow: hidden; }}
  .catfill {{ background: #d0433a; height: 100%; border-radius: 8px; }}
  .catval {{ text-align: right; font-variant-numeric: tabular-nums; color: #4b5563; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Dead-Stock Report</h1>
  <div class="sub">Source: {source} · Measured as of {as_of} · Velocity over the trailing {recent_weeks} weeks</div>

  <div class="hero">
    <div>
      <div class="big">{total_cash_risk}</div>
      <div class="label">cash tied up in at-risk stock ({at_risk_count} products)</div>
    </div>
    <div class="divider"></div>
    <div>
      <div class="stat">{total_inventory}</div>
      <div class="label">total inventory value ({product_count} products)</div>
    </div>
  </div>

  {roi}

  <div class="card">
    <h2>What to do this week</h2>
    <ol class="todo">{todo}</ol>
  </div>

  {categories}

  <div class="card">
    <h2>All products — ranked by dead-stock risk</h2>
    <table>
      <thead>
        <tr>
          <th>Product</th><th>Risk</th><th>Cover</th><th>Days since sale</th>
          <th>Velocity</th><th class="num">Cash at risk</th><th>Action</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="legend">
      <span style="background:#fde2e1;color:#a11a12">70–100 Mark down</span>
      <span style="background:#fdf3d8;color:#8a6100">45–69 Watch</span>
      <span style="background:#e3f6e5;color:#1c6b28">0–44 Healthy</span>
    </div>
    {notes}
  </div>
</div>
</body>
</html>"""


# ===========================================================================
# COMMAND-LINE ENTRY POINT
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Predict dead stock from a sales CSV and write report.html")
    parser.add_argument("sales_csv", help="Path to the sales history CSV")
    parser.add_argument("--stock", help="Optional separate CSV of current stock on hand")
    parser.add_argument("--out", default="report.html", help="Output HTML file (default report.html)")
    parser.add_argument("--asof", help="Measure 'today' from this date (YYYY-MM-DD). "
                                       "Default: the most recent sale in the file.")
    parser.add_argument("--map", action="append", default=[], metavar="field=Column",
                        help="Override a column guess, e.g. --map quantity=UnitsSold. Repeatable.")
    args = parser.parse_args()

    # Parse --map overrides into a dict.
    overrides = {}
    for item in args.map:
        if "=" not in item:
            sys.exit("ERROR: --map expects field=Column, got '{}'".format(item))
        field, col = item.split("=", 1)
        field = field.strip()
        if field not in COLUMN_SYNONYMS:
            sys.exit("ERROR: unknown field '{}'. Valid fields: {}".format(
                field, ", ".join(COLUMN_SYNONYMS)))
        overrides[field] = col.strip()

    if not os.path.exists(args.sales_csv):
        sys.exit("ERROR: can't find sales file '{}'".format(args.sales_csv))

    rows, mapping = load_sales(args.sales_csv, overrides)
    if not rows:
        sys.exit("ERROR: no usable sales rows found in '{}'.".format(args.sales_csv))

    # Report what got mapped, so the user can sanity-check the auto-detection.
    print("Column mapping (field -> your column):")
    for field in ["date", "quantity", "sku", "product_name", "unit_cost",
                  "retail_price", "stock_on_hand", "category"]:
        print("  {:<14} {}".format(field, mapping.get(field) or "(not found)"))

    # Load stock: explicit --stock file, else auto-look for a sibling stock file.
    stock_lookup = {}
    stock_path = args.stock
    if not stock_path:
        guess = os.path.join(os.path.dirname(args.sales_csv) or ".", "sample_stock.csv")
        if os.path.exists(guess) and os.path.abspath(guess) != os.path.abspath(args.sales_csv):
            stock_path = guess
            print("\nFound a stock file next to your sales file: {}".format(stock_path))
    if stock_path:
        if not os.path.exists(stock_path):
            sys.exit("ERROR: can't find stock file '{}'".format(stock_path))
        stock_lookup = load_stock(stock_path, overrides)

    # Decide the "as of" date.
    if args.asof:
        as_of = parse_date(args.asof)
        if as_of is None:
            sys.exit("ERROR: couldn't read --asof date '{}'. Use YYYY-MM-DD.".format(args.asof))
    else:
        as_of = max(r["date"] for r in rows)

    results = analyse(rows, stock_lookup, as_of)

    # Work out which metrics we couldn't compute, and say so honestly.
    notes = []
    have_stock = any(r["stock"] is not None for r in results)
    have_cost = any(r["unit_cost"] is not None for r in results)
    if not have_stock:
        notes.append("No stock-on-hand data was found, so 'weeks of cover' and 'cash at risk' "
                     "could not be calculated — risk is based on velocity and staleness only. "
                     "Provide a stock file with --stock to unlock those figures.")
    if not have_cost:
        notes.append("No unit-cost column was found, so 'cash at risk' is not shown.")

    html = build_report(results, as_of, notes, os.path.basename(args.sales_csv))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    # Console summary.
    at_risk = [r for r in results if r["risk"] >= AT_RISK_SCORE]
    total_cash_risk = sum(r["cash_at_risk"] for r in at_risk if r["cash_at_risk"])
    print("\n" + "=" * 60)
    print("ANALYSED {} products as of {}".format(len(results), as_of.isoformat()))
    print("{} at risk (score >= {}) — {} of cash tied up".format(
        len(at_risk), AT_RISK_SCORE, money(total_cash_risk)))
    print("=" * 60)
    print("{:<28} {:>4}  {:>7}  {:>9}  {}".format("TOP AT-RISK", "RISK", "COVER", "LASTSOLD", "ACTION"))
    for r in results[:8]:
        print("{:<28} {:>4}  {:>7}  {:>6}d   {}".format(
            r["name"][:28], r["risk"], fmt_cover(r["weeks_cover"]),
            r["days_since"], r["action"]))
    print("\nWrote report -> {}".format(os.path.abspath(args.out)))
    print("Open it in your browser to see the full picture.")


if __name__ == "__main__":
    main()
