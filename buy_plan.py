"""
buy_plan.py -- AI Buy-Plan (Module 2: the reorder brain)
========================================================

A SEPARATE report from the dead-stock predictor. Where the predictor tells you
what's ALREADY going dead, the buy-plan looks forward: based on sell-through
velocity and recent demand momentum, it says
    * what to REORDER, and how many units, and
    * what to STOP buying
so you prevent dead stock before it happens.

It reads the same joined Shopify report (the "Reorder & Margin" .xlsx) and
writes buy_plan.html in the same simple style. The predictor is untouched.

Run:  python3 buy_plan.py "CASA_EQUESTRE_Reorder_Margin_Report (2).xlsx"

A NOTE ON SEASONALITY (read the report's methodology too):
True calendar seasonality needs 2-3 years of month-by-month history. The
current exports don't contain that (only a single month of order-level detail),
so 'seasonality' here is a MOMENTUM signal: recent run-rate (30/90-day,
annualised) vs the trailing-12-month rate. Heating up -> buy ahead; cooling ->
ease off. Swap in monthly history later and this sharpens into real seasonality.
"""

import math
import os
import sys

import casa_report as C   # reuse column indexes + money/esc/fmt_cover/colour + load()

# ---- TUNING KNOBS ----------------------------------------------------------
TARGET_COVER_M = 4.0     # after reordering, aim to hold ~4 months of forward demand
MIN_ANNUAL_UNITS = 3     # only reorder products selling at least this many/year...
MIN_RECENT_UNITS_90 = 2  # ...or with at least this many sold in the last 90 days
STOP_COVER_M = 24        # stock but >24 months cover + declining = stop buying
SEASON_HOT = 1.20        # recent rate >= 1.2x annual rate  -> "heating up"
SEASON_COLD = 0.80       # recent rate <= 0.8x annual rate  -> "cooling"
CURRENCY = "$"
ASOF = "2026-07-14"


def n(x):
    return x if isinstance(x, (int, float)) else 0.0


def money(v):
    return "—" if v is None else "{}{:,.0f}".format(CURRENCY, v)


def annualise(units, days):
    return units * (365.0 / days)


def analyse(rows):
    items = []
    for r in rows:
        u30, u90, u12, uprior = n(r[C.C_U30]), n(r[C.C_U90]), n(r[C.C_U12]), n(r[C.C_UPRIOR])
        stock = n(r[C.C_STOCK])
        cover = n(r[C.C_COVER_M])
        cost = n(r[C.C_UNITCOST])
        price = n(r[C.C_AVGPRICE])
        margin = n(r[C.C_ACT_MARGIN])

        annual_rate = u12                      # units / year
        # recent run-rate, annualised, blended (90d stabilises, 30d catches spikes)
        recent = 0.6 * annualise(u90, 90) + 0.4 * annualise(u30, 30)
        momentum = recent / annual_rate if annual_rate > 0 else (2.0 if recent > 0 else 0.0)

        # forward monthly demand = blend of trailing-year base and recent momentum
        fwd_monthly = 0.5 * (annual_rate / 12.0) + 0.5 * (recent / 12.0)
        target_stock = fwd_monthly * TARGET_COVER_M
        reorder_qty = max(0, int(math.ceil(target_stock - stock)))

        # cost/price may be missing (one of the 87 no-cost products) -> None, not 0
        buy_cost = reorder_qty * cost if cost > 0 else None
        rev_potential = reorder_qty * price if price > 0 else None

        items.append({
            "name": r[C.C_NAME], "vendor": r[C.C_VENDOR] or "", "type": r[C.C_TYPE] or "Uncategorised",
            "status": r[C.C_STATUS] or "", "u12": u12, "uprior": uprior, "u90": u90, "u30": u30,
            "stock": stock, "cover": cover, "cost": cost, "price": price, "margin": margin,
            "momentum": momentum, "reorder_qty": reorder_qty,
            "buy_cost": buy_cost, "rev_potential": rev_potential,
            "invval": n(r[C.C_INVVAL]),
        })
    return items


def classify(items):
    reorder, stop = [], []
    for x in items:
        selling = x["u12"] >= MIN_ANNUAL_UNITS or x["u90"] >= MIN_RECENT_UNITS_90
        # STOP: has stock but not moving (dead) or badly overstocked & fading
        if x["stock"] > 0 and (
                x["u12"] == 0 or
                (x["cover"] and x["cover"] > STOP_COVER_M and x["u12"] < x["uprior"])):
            reason = ("no sales in 12 months" if x["u12"] == 0
                      else "{:.0f}mo of cover & sales falling".format(x["cover"]))
            stop.append({**x, "reason": reason})
            continue
        # REORDER: selling, and current stock won't cover forward demand
        if selling and x["reorder_qty"] >= 1 and x["status"] != "archived":
            reorder.append(x)

    reorder.sort(key=lambda x: (x["rev_potential"] or 0), reverse=True)
    stop.sort(key=lambda x: x["invval"], reverse=True)
    return reorder, stop


def seasonality(items):
    """Category-level momentum: recent annualised rate vs trailing-year rate."""
    cats = {}
    for x in items:
        c = cats.setdefault(x["type"], {"annual": 0.0, "recent": 0.0})
        c["annual"] += x["u12"]
        c["recent"] += 0.6 * annualise(x["u90"], 90) + 0.4 * annualise(x["u30"], 30)
    out = []
    for name, c in cats.items():
        if c["annual"] < 4:            # ignore tiny categories (noise)
            continue
        m = c["recent"] / c["annual"] if c["annual"] > 0 else 1.0
        label = "Heating up" if m >= SEASON_HOT else "Cooling" if m <= SEASON_COLD else "Steady"
        out.append((name, m, label, c["annual"]))
    out.sort(key=lambda t: t[1], reverse=True)
    return out


def trend_arrow(x):
    if x["momentum"] >= SEASON_HOT:
        return "&#9650;"      # up
    if x["momentum"] <= SEASON_COLD:
        return "&#9660;"      # down
    return "&#9644;"          # flat


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/jennypersson/Downloads/CASA_EQUESTRE_Reorder_Margin_Report (2).xlsx"
    rows = C.load(path)
    items = analyse(rows)
    reorder, stop = classify(items)
    seasons = seasonality(items)

    total_buy = sum((x["buy_cost"] or 0) for x in reorder)
    total_rev = sum((x["rev_potential"] or 0) for x in reorder)
    stop_cash = sum(x["invval"] for x in stop)

    # ---- reorder table ----
    ro_rows = ""
    for x in reorder:
        ro_rows += (
            "<tr><td class='name'>{n}<span class='sku'>{v} &middot; {t}</span></td>"
            "<td>{u12:.0f}/yr <span class='tr'>{ar}</span></td>"
            "<td>{stock:.0f}</td><td>{cov}</td>"
            "<td class='qty'>+{q}</td>"
            "<td class='num'>{buy}</td><td>{m:.0%}</td>"
            "<td class='num rev'>{rev}</td></tr>").format(
            n=C.esc(x["name"]), v=C.esc(x["vendor"]), t=C.esc(x["type"]),
            u12=x["u12"], ar=trend_arrow(x), stock=x["stock"], cov=C.fmt_cover(x["cover"] or 0),
            q=x["reorder_qty"], buy=money(x["buy_cost"]), m=x["margin"], rev=money(x["rev_potential"]))

    # ---- stop table ----
    st_rows = ""
    for x in stop:
        st_rows += (
            "<tr><td class='name'>{n}<span class='sku'>{v} &middot; {t}</span></td>"
            "<td>{stock:.0f}</td><td>{cov}</td><td>{u12:.0f}/yr</td>"
            "<td class='num'>{cash}</td><td class='reason'>{why}</td></tr>").format(
            n=C.esc(x["name"]), v=C.esc(x["vendor"]), t=C.esc(x["type"]),
            stock=x["stock"], cov=C.fmt_cover(x["cover"] or float("inf") if x["u12"] == 0 else x["cover"]),
            u12=x["u12"], cash=money(x["invval"]), why=C.esc(x["reason"]))

    # ---- seasonality panel ----
    se_rows = ""
    for name, m, label, annual in seasons:
        cls = "hot" if label == "Heating up" else "cold" if label == "Cooling" else "mid"
        pct = (m - 1) * 100
        se_rows += ("<div class='searow'><div class='sename'>{n}</div>"
                    "<div class='sebar'><div class='sefill {cls}' style='width:{w:.0f}%'></div></div>"
                    "<div class='seval {cls}'>{lab} {sign}{pct:.0f}%</div></div>").format(
            n=C.esc(name), cls=cls, w=min(100, abs(pct)), lab=label,
            sign="+" if pct >= 0 else "", pct=pct)

    html = TEMPLATE.format(
        asof=ASOF, total_buy=money(total_buy), reorder_count=len(reorder),
        total_rev=money(total_rev), stop_count=len(stop), stop_cash=money(stop_cash),
        target_cover=int(TARGET_COVER_M), seasons=se_rows, ro_rows=ro_rows, st_rows=st_rows)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buy_plan.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print("CASA EQUESTRE — AI BUY-PLAN (as of {})".format(ASOF))
    print("=" * 60)
    print("REORDER: {} products, {} to invest -> {} sell-through potential".format(
        len(reorder), money(total_buy), money(total_rev)))
    print("STOP buying: {} products ({} of cash to stop feeding)".format(len(stop), money(stop_cash)))
    print("=" * 60)
    print("Top reorders:")
    for x in reorder[:8]:
        print("  {:<38} +{:<3} units  (buy {}, {:.0f}/yr)".format(
            str(x["name"])[:38], x["reorder_qty"], money(x["buy_cost"]), x["u12"]))
    print("\nWrote -> {}".format(out))


TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Casa Equestre — AI Buy-Plan</title>
<style>
  *{{box-sizing:border-box}} body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f5f6f8;color:#1b1f24}}
  .wrap{{max-width:1000px;margin:0 auto;padding:28px 20px 60px}}
  h1{{font-size:22px;margin:0 0 2px}} .sub{{color:#6b7280;font-size:12.5px;margin-bottom:22px}}
  .hero{{background:#123a2b;color:#fff;border-radius:14px;padding:24px 26px;display:flex;flex-wrap:wrap;gap:26px;align-items:center}}
  .hero .big{{font-size:34px;font-weight:800;line-height:1}} .hero .stat{{font-size:22px;font-weight:600}}
  .hero .label{{font-size:11.5px;opacity:.85;margin-top:5px}} .hero .divider{{width:1px;align-self:stretch;background:rgba(255,255,255,.22)}}
  .card{{background:#fff;border-radius:14px;padding:20px 22px;margin-top:20px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  h2{{font-size:15px;margin:0 0 4px}} .h2sub{{color:#6b7280;font-size:12px;margin-bottom:14px}}
  .note{{background:#fbf7ec;border:1px solid #ece0c3;border-radius:10px;padding:12px 14px;margin-top:16px;font-size:12px;line-height:1.55;color:#6a5b33}}
  .scroll{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;font-size:12.5px}}
  th,td{{text-align:left;padding:8px;border-bottom:1px solid #eef0f2;white-space:nowrap}}
  th{{color:#6b7280;font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em}}
  td.num{{text-align:right;font-variant-numeric:tabular-nums}} td.name{{font-weight:600;white-space:normal}}
  .sku{{display:block;font-weight:400;color:#9aa0a6;font-size:11px}}
  td.qty{{font-weight:800;color:#1c6b28;font-size:14px}} td.rev{{color:#1c6b28;font-weight:600}}
  .tr{{color:#9aa0a6;font-size:11px}} td.reason{{color:#8a6100;white-space:normal}}
  /* seasonality */
  .searow{{display:grid;grid-template-columns:150px 1fr 150px;align-items:center;gap:12px;margin-bottom:7px;font-size:12.5px}}
  .sename{{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .sebar{{background:#eef0f2;border-radius:8px;height:14px;overflow:hidden}}
  .sefill{{height:100%}} .sefill.hot{{background:#1c9d54}} .sefill.cold{{background:#c98a2b}} .sefill.mid{{background:#9aa0a6}}
  .seval{{text-align:right;font-weight:600;font-size:11.5px}} .seval.hot{{color:#1c6b28}} .seval.cold{{color:#8a6100}} .seval.mid{{color:#6b7280}}
</style></head><body><div class="wrap">
  <h1>Casa Equestre — AI Buy-Plan</h1>
  <div class="sub">The reorder brain: what to buy, how much, and what to stop &mdash; before it becomes dead stock &middot; as of {asof} &middot; targets ~{target_cover} months of forward cover</div>

  <div class="hero">
    <div><div class="big">{total_buy}</div><div class="label">to reinvest across {reorder_count} products to reorder</div></div>
    <div class="divider"></div>
    <div><div class="stat">{total_rev}</div><div class="label">projected sell-through from those reorders</div></div>
    <div class="divider"></div>
    <div><div class="stat">{stop_count}</div><div class="label">products to STOP buying ({stop_cash} already frozen)</div></div>
  </div>

  <div class="card">
    <h2>Demand momentum by category</h2>
    <div class="h2sub">Recent run-rate (30/90-day, annualised) vs the trailing-year rate. Heating &rarr; buy ahead; cooling &rarr; ease off.</div>
    {seasons}
    <div class="note"><b>On seasonality &mdash; read this:</b> true calendar seasonality (which month each line peaks) needs 2&ndash;3 years of month-by-month sales. The current exports only carry a single month of order-level detail, so this plan uses <b>demand momentum</b> instead &mdash; how fast something is selling now vs its yearly average. It's a solid proxy for &ldquo;lean in / ease off,&rdquo; and it upgrades to real seasonality the moment monthly history is available.</div>
  </div>

  <div class="card">
    <h2>Reorder now &mdash; proven sellers running low</h2>
    <div class="h2sub">Ranked by sell-through value at stake. Quantity buys back to ~{target_cover} months of forward cover, adjusted for momentum.</div>
    <div class="scroll"><table><thead><tr>
      <th>Product</th><th>Sold/yr</th><th>In stock</th><th>Cover</th><th>Reorder</th><th class="num">Buy cost</th><th>Margin</th><th class="num">Sell-thru value</th>
    </tr></thead><tbody>{ro_rows}</tbody></table></div>
  </div>

  <div class="card">
    <h2>Stop buying &mdash; don't feed the dead stock</h2>
    <div class="h2sub">Already in stock and not moving. Do not reorder; clear what's on hand. This is where future dead stock is prevented.</div>
    <div class="scroll"><table><thead><tr>
      <th>Product</th><th>In stock</th><th>Cover</th><th>Sold/yr</th><th class="num">Cash frozen</th><th>Why stop</th>
    </tr></thead><tbody>{st_rows}</tbody></table></div>
  </div>
</div></body></html>"""


if __name__ == "__main__":
    main()
