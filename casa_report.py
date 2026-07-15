"""
casa_report.py  --  Dead-Stock report for a real Shopify store (Casa Equestre)
==============================================================================

This is a variant of predictor.py adapted to the *joined* Shopify export
(the "Reorder & Margin Report" .xlsx), which already contains stock on hand,
unit cost, and sales split into 30d / 90d / 12mo / prior-12mo windows.

Because that file has no per-transaction dates, we measure staleness from the
velocity windows instead of "days since last sale", and we work in MONTHS of
cover (right for a boutique, high-ticket store) rather than weeks.

Run:  python3 casa_report.py "CASA_EQUESTRE_Reorder_Margin_Report (1).xlsx"
Needs: openpyxl  (pip3 install openpyxl)
"""

import sys
import os
import openpyxl

# ---- TUNING KNOBS (calibrated for a boutique, high-value store) -----------
COVER_LOW_M   = 6      # months of cover at/under which overstock risk ~ 0
COVER_HIGH_M  = 36     # months of cover at/over which overstock risk maxes
WEIGHT_COVER    = 0.35
WEIGHT_RECENCY  = 0.35
WEIGHT_CASH     = 0.20
WEIGHT_TREND    = 0.10
AT_RISK_SCORE = 60     # counted in the "cash at risk" headline
MARKDOWN_SCORE = 70
WATCH_SCORE    = 45
REORDER_COVER_M = 3    # selling and <=3 months cover -> reorder
CURRENCY = "$"
ASOF = "2026-07-14"    # the through-date printed in the source file

# Column indexes in the "Reorder & Margin Report" sheet (0-based, data rows)
C_NAME, C_VENDOR, C_TYPE, C_STATUS = 0, 1, 2, 3
C_U_LIFE, C_U30, C_U90, C_U12, C_UPRIOR, C_YOY = 4, 5, 6, 7, 8, 9
C_NETSALES, C_TOTSALES = 10, 11
C_UNITCOST, C_AVGPRICE = 12, 13
C_ACT_MARGIN = 17
C_STOCK, C_COVER_M, C_INVVAL, C_NVAR = 21, 22, 23, 24


def num(x):
    return x if isinstance(x, (int, float)) else 0.0


def band(v, lo, hi):
    if v <= lo:
        return 0.0
    if v >= hi:
        return 100.0
    return (v - lo) / (hi - lo) * 100.0


def load(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Reorder & Margin Report"]
    rows = list(ws.iter_rows(values_only=True))[4:]   # skip title + header
    return [r for r in rows if r and r[C_NAME]]


def score(r, max_inv):
    stock = num(r[C_STOCK])
    u30, u90, u12, uprior = num(r[C_U30]), num(r[C_U90]), num(r[C_U12]), num(r[C_UPRIOR])
    cover = num(r[C_COVER_M])           # months; 0 in file can mean "no 12mo sales"
    invval = num(r[C_INVVAL])

    # If there's stock but nothing sold in 12 months, cover is effectively infinite.
    infinite_cover = stock > 0 and u12 == 0
    cover_display = float("inf") if infinite_cover else cover

    # 1) Overstock: months of cover.
    if infinite_cover:
        cover_sub = 100.0
    else:
        cover_sub = band(cover, COVER_LOW_M, COVER_HIGH_M)

    # 2) Staleness, from the velocity windows (proxy for days-since-last-sale).
    if stock <= 0:
        recency_sub = 0.0                # not dead stock if there's nothing on the shelf
    elif u12 == 0:
        recency_sub = 100.0              # in stock, nothing sold in a year
    elif u90 == 0:
        recency_sub = 70.0               # nothing in 90 days
    elif u30 == 0:
        recency_sub = 35.0               # nothing in 30 days
    else:
        recency_sub = 0.0

    # 3) Cash tied up, scaled against the biggest inventory pile.
    cash_sub = min(100.0, 100.0 * invval / max_inv) if max_inv > 0 else 0.0

    # 4) Trend: only *declining* year-on-year adds risk (YoY is a fraction).
    yoy = r[C_YOY]
    if not isinstance(yoy, (int, float)):
        trend_sub = 40.0 if (stock > 0 and u12 <= 1) else 20.0   # unknown/new-ish
    elif yoy <= -0.5:
        trend_sub = 100.0
    elif yoy >= 0:
        trend_sub = 0.0
    else:
        trend_sub = (-yoy) / 0.5 * 100.0

    risk = round(WEIGHT_COVER * cover_sub + WEIGHT_RECENCY * recency_sub +
                 WEIGHT_CASH * cash_sub + WEIGHT_TREND * trend_sub)

    # Recommended action.
    if stock <= 0:
        action, md = ("Reorder", "") if u90 > 0 else ("Sold out", "")
    elif u12 > 0 and 0 < cover <= REORDER_COVER_M:
        action, md = "Reorder", ""
    elif risk >= MARKDOWN_SCORE:
        action, md = "Mark down / clear", ASOF
    elif risk >= WATCH_SCORE:
        action, md = "Watch", ""
    else:
        action, md = "Healthy", ""

    return {
        "name": r[C_NAME], "vendor": r[C_VENDOR] or "", "type": r[C_TYPE] or "Uncategorised",
        "stock": stock, "u12": u12, "uprior": uprior, "cover": cover_display,
        "margin": num(r[C_ACT_MARGIN]), "invval": invval,
        "risk": risk, "action": action, "md": md,
    }


def money(v):
    return "—" if v is None else "{}{:,.0f}".format(CURRENCY, v)


def fmt_cover(c):
    if c == float("inf"):
        return "∞"
    return "{:.0f} mo".format(c)


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def colour(s):
    if s >= MARKDOWN_SCORE:
        return "#fde2e1", "#a11a12"
    if s >= WATCH_SCORE:
        return "#fdf3d8", "#8a6100"
    return "#e3f6e5", "#1c6b28"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "CASA_EQUESTRE_Reorder_Margin_Report (1).xlsx"
    raw = load(path)
    max_inv = max(num(r[C_INVVAL]) for r in raw) or 1.0
    items = [score(r, max_inv) for r in raw]
    items.sort(key=lambda x: x["risk"], reverse=True)

    total_inv = sum(x["invval"] for x in items)
    at_risk = [x for x in items if x["risk"] >= AT_RISK_SCORE]
    cash_at_risk = sum(x["invval"] for x in at_risk)
    dead12 = [x for x in items if x["stock"] > 0 and x["u12"] == 0]
    dead_cash = sum(x["invval"] for x in dead12)
    free_half = cash_at_risk * 0.5

    # Cash at risk by vendor (where the overstock concentrates).
    vend = {}
    for x in at_risk:
        vend[x["vendor"]] = vend.get(x["vendor"], 0) + x["invval"]
    vend_sorted = sorted(vend.items(), key=lambda kv: kv[1], reverse=True)[:6]
    vmax = vend_sorted[0][1] if vend_sorted else 1

    # Top-5 to-do (highest risk, actionable, weighted toward cash).
    todo = [x for x in at_risk if x["action"] in ("Mark down / clear", "Watch")][:5]

    # ---- build HTML --------------------------------------------------------
    rows_html = ""
    for x in items:
        bg, fg = colour(x["risk"])
        arrow = "▲" if x["u12"] > x["uprior"] else "▼" if x["u12"] < x["uprior"] else "▬"
        rows_html += """
        <tr>
          <td class="name">{name}<span class="sku">{vendor} · {type}</span></td>
          <td><span class="pill" style="background:{bg};color:{fg}">{risk}</span></td>
          <td>{stock:.0f}</td>
          <td>{cover}</td>
          <td>{u12:.0f}/yr <span class="trend">{arrow}</span></td>
          <td>{margin:.0%}</td>
          <td class="num">{cash}</td>
          <td>{action}{md}</td>
        </tr>""".format(
            name=esc(x["name"]), vendor=esc(x["vendor"]), type=esc(x["type"]),
            bg=bg, fg=fg, risk=x["risk"], stock=x["stock"], cover=fmt_cover(x["cover"]),
            u12=x["u12"], arrow=arrow, margin=x["margin"], cash=money(x["invval"]),
            action=esc(x["action"]),
            md=('<span class="md">by {}</span>'.format(x["md"]) if x["md"] else ""))

    todo_html = ""
    for x in todo:
        todo_html += ('<li><strong>{a}</strong> — {n} '
                      '<span class="dim">(risk {r}, {c} tied up, {u:.0f} sold last year, '
                      '{cov} cover, {m:.0%} margin)</span></li>').format(
            a=esc(x["action"]), n=esc(x["name"]), r=x["risk"], c=money(x["invval"]),
            u=x["u12"], cov=fmt_cover(x["cover"]), m=x["margin"])

    vend_html = ""
    for name, val in vend_sorted:
        pct = val / vmax * 100
        vend_html += ('<div class="catrow"><div class="catname">{n}</div>'
                      '<div class="cattrack"><div class="catfill" style="width:{p:.0f}%"></div></div>'
                      '<div class="catval">{v}</div></div>').format(
            n=esc(name), p=pct, v=money(val))

    html = TEMPLATE.format(
        asof=ASOF, cash_at_risk=money(cash_at_risk), at_risk_count=len(at_risk),
        total_inv=money(total_inv), product_count=len(items),
        dead_count=len(dead12), dead_cash=money(dead_cash),
        free_half=money(free_half), vendors=vend_html, todo=todo_html, rows=rows_html)

    out = "casa_equestre_report.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    # ---- console summary ---------------------------------------------------
    print("CASA EQUESTRE — dead-stock analysis (as of {})".format(ASOF))
    print("=" * 64)
    print("Inventory at cost: {}   across {} products".format(money(total_inv), len(items)))
    print("At risk (score>={}): {} products, {} of cash tied up".format(
        AT_RISK_SCORE, len(at_risk), money(cash_at_risk)))
    print("Hard dead (in stock, 0 sales in 12mo): {} products, {}".format(
        len(dead12), money(dead_cash)))
    print("=" * 64)
    print("{:<40} {:>4} {:>6} {:>7} {}".format("TOP AT-RISK", "RISK", "STOCK", "COVER", "ACTION"))
    for x in items[:12]:
        print("{:<40} {:>4} {:>6.0f} {:>7} {}".format(
            str(x["name"])[:40], x["risk"], x["stock"], fmt_cover(x["cover"]), x["action"]))
    print("\nWrote -> {}".format(os.path.abspath(out)))


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casa Equestre — Dead-Stock Report</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f5f6f8;color:#1b1f24}}
  .wrap{{max-width:1040px;margin:0 auto;padding:28px 20px 60px}}
  h1{{font-size:22px;margin:0 0 2px}}
  .sub{{color:#6b7280;font-size:13px;margin-bottom:24px}}
  .hero{{background:#12263a;color:#fff;border-radius:14px;padding:26px 28px;display:flex;flex-wrap:wrap;gap:30px;align-items:center}}
  .hero .big{{font-size:40px;font-weight:700;line-height:1}}
  .hero .stat{{font-size:24px;font-weight:600}}
  .hero .label{{font-size:12px;opacity:.8;margin-top:6px}}
  .hero .divider{{width:1px;align-self:stretch;background:rgba(255,255,255,.2)}}
  .roi{{display:flex;gap:12px;align-items:flex-start;background:#eef6ff;border:1px solid #cfe3fb;border-radius:14px;padding:16px 18px;margin-top:16px;font-size:13.5px;line-height:1.5;color:#1b2a3a}}
  .roi b{{color:#0b57d0}}
  .card{{background:#fff;border-radius:14px;padding:22px 24px;margin-top:22px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  h2{{font-size:16px;margin:0 0 14px}}
  ol.todo{{margin:0;padding-left:20px}} ol.todo li{{margin-bottom:8px;line-height:1.45}}
  .dim{{color:#6b7280;font-size:12px}}
  table{{width:100%;border-collapse:collapse;font-size:12.5px}}
  th,td{{text-align:left;padding:9px 8px;border-bottom:1px solid #eef0f2;white-space:nowrap}}
  th{{color:#6b7280;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
  td.num{{text-align:right;font-variant-numeric:tabular-nums}} td.name{{font-weight:600;white-space:normal}}
  .sku{{display:block;font-weight:400;color:#9aa0a6;font-size:11px}}
  .pill{{display:inline-block;min-width:34px;text-align:center;padding:3px 8px;border-radius:20px;font-weight:700}}
  .trend{{color:#9aa0a6;font-size:11px}} .md{{display:block;color:#9aa0a6;font-size:11px}}
  .catrow{{display:grid;grid-template-columns:120px 1fr 70px;align-items:center;gap:10px;margin-bottom:8px;font-size:12.5px}}
  .catname{{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .cattrack{{background:#f0f1f3;border-radius:8px;height:14px;overflow:hidden}}
  .catfill{{background:#d0433a;height:100%;border-radius:8px}}
  .catval{{text-align:right;font-variant-numeric:tabular-nums;color:#4b5563}}
  .legend{{font-size:11px;color:#6b7280;margin-top:10px}}
  .legend span{{display:inline-block;padding:2px 8px;border-radius:10px;margin-right:6px}}
  .scroll{{overflow-x:auto}}
</style></head><body><div class="wrap">
  <h1>Casa Equestre — Dead-Stock Report</h1>
  <div class="sub">Source: Shopify sales + Products export (cost &amp; inventory) · as of {asof} · velocity over the trailing 12 months</div>

  <div class="hero">
    <div><div class="big">{cash_at_risk}</div><div class="label">cash tied up in at-risk stock ({at_risk_count} products)</div></div>
    <div class="divider"></div>
    <div><div class="stat">{total_inv}</div><div class="label">total inventory at cost ({product_count} products)</div></div>
    <div class="divider"></div>
    <div><div class="stat">{dead_cash}</div><div class="label">stone-dead: {dead_count} products, 0 sales in 12 months</div></div>
  </div>

  <div class="roi"><span>&#128176;</span><div><strong>Cash you could free up:</strong> clearing just half of your at-risk stock puts <b>{free_half}</b> back into working capital — to reinvest in the fast movers flagged &ldquo;Reorder&rdquo; below.</div></div>

  <div class="card"><h2>What to do this week</h2><ol class="todo">{todo}</ol></div>

  <div class="card"><h2>Where the frozen cash sits — by brand</h2>{vendors}</div>

  <div class="card"><h2>All products — ranked by dead-stock risk</h2>
    <div class="scroll"><table><thead><tr>
      <th>Product</th><th>Risk</th><th>Stock</th><th>Cover</th><th>Sold/yr</th><th>Margin</th><th class="num">Cash @cost</th><th>Action</th>
    </tr></thead><tbody>{rows}</tbody></table></div>
    <div class="legend">
      <span style="background:#fde2e1;color:#a11a12">70–100 Mark down</span>
      <span style="background:#fdf3d8;color:#8a6100">45–69 Watch</span>
      <span style="background:#e3f6e5;color:#1c6b28">0–44 Healthy</span>
    </div>
  </div>
</div></body></html>"""


if __name__ == "__main__":
    main()
