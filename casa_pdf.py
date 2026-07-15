"""
casa_pdf.py -- build a print-ready PDF dead-stock report for Casa Equestre.

Reuses the scoring in casa_report.py, lays it out as a paginated A4 document
with a "How to read this report" guide, and renders it to PDF via headless
Chrome (faithful CSS, no extra Python deps).

Run:  python3 casa_pdf.py "CASA_EQUESTRE_Reorder_Margin_Report (1).xlsx"
"""

import os
import subprocess
import sys

import casa_report as C   # reuse load() + score() + helpers


def money(v):
    return "—" if v is None else "{}{:,.0f}".format(C.CURRENCY, v)


def pill(risk):
    if risk >= C.MARKDOWN_SCORE:
        return "r"
    if risk >= C.WATCH_SCORE:
        return "a"
    return "g"


def build_html(path):
    raw = C.load(path)
    max_inv = max(C.num(r[C.C_INVVAL]) for r in raw) or 1.0
    items = [C.score(r, max_inv) for r in raw]
    items.sort(key=lambda x: x["risk"], reverse=True)

    total_inv = sum(x["invval"] for x in items)
    at_risk = [x for x in items if x["risk"] >= C.AT_RISK_SCORE]
    cash_at_risk = sum(x["invval"] for x in at_risk)
    dead12 = [x for x in items if x["stock"] > 0 and x["u12"] == 0]
    dead_cash = sum(x["invval"] for x in dead12)
    free_half = cash_at_risk * 0.5
    reorder = [x for x in items if x["action"] == "Reorder"]

    in_stock = [x for x in items if x["stock"] > 0]          # ranked by risk (already sorted)
    no_stock = sorted([x for x in items if x["stock"] <= 0],
                      key=lambda x: x["u12"], reverse=True)   # reorder candidates first

    # by-brand concentration (merge case variants like Animo/animo)
    vend = {}
    for x in at_risk:
        key = (x["vendor"] or "—").strip().title()
        vend[key] = vend.get(key, 0) + x["invval"]
    vend_sorted = sorted(vend.items(), key=lambda kv: kv[1], reverse=True)[:8]
    vmax = vend_sorted[0][1] if vend_sorted else 1

    # ---- in-stock table rows (ALL in-stock products, ranked by risk) ----
    ar_rows = ""
    for i, x in enumerate(in_stock, 1):
        arrow = "&#9650;" if x["u12"] > x["uprior"] else "&#9660;" if x["u12"] < x["uprior"] else "&#9644;"
        ar_rows += (
            "<tr><td class='rk'>{i}</td>"
            "<td class='nm'>{n}<span class='sub'>{v} &middot; {t}</span></td>"
            "<td><span class='p {pc}'>{r}</span></td>"
            "<td>{stock:.0f}</td><td>{cov}</td>"
            "<td>{u12:.0f}/yr <span class='tr'>{ar}</span></td>"
            "<td>{m:.0%}</td><td class='num'>{cash}</td>"
            "<td class='act'>{a}</td></tr>"
        ).format(i=i, n=C.esc(x["name"]), v=C.esc(x["vendor"]), t=C.esc(x["type"]),
                 pc=pill(x["risk"]), r=x["risk"], stock=x["stock"], cov=C.fmt_cover(x["cover"]),
                 u12=x["u12"], ar=arrow, m=x["margin"], cash=money(x["invval"]),
                 a=C.esc(x["action"]))

    # ---- not-in-stock table rows (compact: reorder candidates + sold out) ----
    ns_rows = ""
    for i, x in enumerate(no_stock, 1):
        arrow = "&#9650;" if x["u12"] > x["uprior"] else "&#9660;" if x["u12"] < x["uprior"] else "&#9644;"
        ns_rows += (
            "<tr><td class='rk'>{i}</td>"
            "<td class='nm'>{n}<span class='sub'>{v} &middot; {t}</span></td>"
            "<td>{u12:.0f}/yr <span class='tr'>{ar}</span></td>"
            "<td>{uprior:.0f}</td><td>{m:.0%}</td>"
            "<td class='act'>{a}</td></tr>"
        ).format(i=i, n=C.esc(x["name"]), v=C.esc(x["vendor"]), t=C.esc(x["type"]),
                 u12=x["u12"], ar=arrow, uprior=x["uprior"], m=x["margin"], a=C.esc(x["action"]))

    # ---- to-do ----
    todo = [x for x in at_risk if x["action"] in ("Mark down / clear", "Watch")][:6]
    todo_rows = ""
    for x in todo:
        todo_rows += ("<li><b>{a}</b> &mdash; {n} <span class='dim'>(risk {r}, {c} tied up, "
                      "{u:.0f} sold last year, {cov} cover, {m:.0%} margin)</span></li>").format(
            a=C.esc(x["action"]), n=C.esc(x["name"]), r=x["risk"], c=money(x["invval"]),
            u=x["u12"], cov=C.fmt_cover(x["cover"]), m=x["margin"])

    # ---- brand bars ----
    vend_rows = ""
    for name, val in vend_sorted:
        vend_rows += ("<div class='bar'><div class='bn'>{n}</div>"
                      "<div class='bt'><div class='bf' style='width:{p:.0f}%'></div></div>"
                      "<div class='bv'>{v}</div></div>").format(
            n=C.esc(name), p=val / vmax * 100, v=money(val))

    return TEMPLATE.format(
        asof=C.ASOF, total_inv=money(total_inv), product_count=len(items),
        instock=len(in_stock), nostock=len(no_stock),
        cash_at_risk=money(cash_at_risk), at_risk_count=len(at_risk),
        pct_risk=round(cash_at_risk / total_inv * 100) if total_inv else 0,
        dead_count=len(dead12), dead_cash=money(dead_cash),
        free_half=money(free_half), reorder_count=len(reorder),
        todo=todo_rows, vendors=vend_rows, ar_rows=ar_rows, ns_rows=ns_rows,
        cover_low=C.COVER_LOW_M, cover_high=C.COVER_HIGH_M)


TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 14mm 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1b1f24;
         font-size: 10.5px; line-height: 1.45; margin: 0; }}
  h1 {{ font-size: 22px; margin: 0 0 2px; }}
  h2 {{ font-size: 14px; margin: 20px 0 9px; padding-bottom: 4px; border-bottom: 2px solid #12263a; }}
  .muted {{ color: #6b7280; }}
  .sub-h {{ color: #6b7280; font-size: 10px; margin-bottom: 4px; }}
  .page-break {{ page-break-before: always; }}
  .avoid-break {{ page-break-inside: avoid; }}

  /* hero */
  .hero {{ display: flex; gap: 0; background: #12263a; color: #fff; border-radius: 10px;
          overflow: hidden; margin-top: 12px; }}
  .hero .cell {{ padding: 14px 16px; flex: 1; border-right: 1px solid rgba(255,255,255,.15); }}
  .hero .cell:last-child {{ border-right: 0; }}
  .hero .big {{ font-size: 25px; font-weight: 800; line-height: 1.05; }}
  .hero .lbl {{ font-size: 9px; opacity: .82; margin-top: 4px; }}

  .callout {{ background: #eef6ff; border: 1px solid #cfe3fb; border-radius: 8px;
             padding: 11px 13px; margin-top: 12px; font-size: 10.5px; }}
  .callout b {{ color: #0b57d0; }}

  /* guide box */
  .guide {{ background: #f7f8fa; border: 1px solid #e6e8ec; border-radius: 8px; padding: 4px 16px 12px; }}
  .guide h3 {{ font-size: 11.5px; margin: 13px 0 4px; }}
  .guide p {{ margin: 4px 0; }}
  .gl {{ margin: 4px 0 0; padding-left: 16px; }}
  .gl li {{ margin-bottom: 3px; }}
  .chip {{ display: inline-block; padding: 1px 7px; border-radius: 10px; font-weight: 700; font-size: 9.5px; }}
  .chip.r {{ background: #fde2e1; color: #a11a12; }}
  .chip.a {{ background: #fdf3d8; color: #8a6100; }}
  .chip.g {{ background: #e3f6e5; color: #1c6b28; }}

  ol.todo {{ margin: 0; padding-left: 18px; }} ol.todo li {{ margin-bottom: 5px; }}
  .dim {{ color: #6b7280; }}

  /* brand bars */
  .bar {{ display: grid; grid-template-columns: 90px 1fr 60px; align-items: center; gap: 9px; margin-bottom: 5px; }}
  .bn {{ font-weight: 600; }} .bt {{ background: #eceef1; border-radius: 6px; height: 12px; overflow: hidden; }}
  .bf {{ background: #d0433a; height: 100%; }} .bv {{ text-align: right; color: #4b5563; font-variant-numeric: tabular-nums; }}

  /* table */
  table {{ width: 100%; border-collapse: collapse; font-size: 9.3px; }}
  thead {{ display: table-header-group; }}
  th, td {{ text-align: left; padding: 4px 5px; border-bottom: 0.5px solid #e6e8ec; }}
  th {{ color: #6b7280; font-size: 8px; text-transform: uppercase; letter-spacing: .03em;
        border-bottom: 1px solid #c9ccd1; }}
  tr {{ page-break-inside: avoid; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.nm {{ font-weight: 600; max-width: 230px; }}
  td.rk {{ color: #9aa0a6; }} td.act {{ white-space: nowrap; }}
  .sub {{ display: block; font-weight: 400; color: #9aa0a6; font-size: 8px; }}
  .tr {{ color: #9aa0a6; }}
  .p {{ display: inline-block; min-width: 26px; text-align: center; padding: 1px 6px; border-radius: 10px; font-weight: 700; }}
  .p.r {{ background: #fde2e1; color: #a11a12; }} .p.a {{ background: #fdf3d8; color: #8a6100; }} .p.g {{ background: #e3f6e5; color: #1c6b28; }}
  .foot {{ margin-top: 8px; font-size: 8.5px; color: #9aa0a6; }}
</style></head><body>

  <h1>Casa Equestre &mdash; Dead-Stock Report</h1>
  <div class="sub-h">Source: Shopify sales &plus; Products export (cost &amp; inventory) &nbsp;&middot;&nbsp; as of {asof} &nbsp;&middot;&nbsp; velocity measured over the trailing 12 months</div>

  <div class="hero avoid-break">
    <div class="cell"><div class="big">{cash_at_risk}</div><div class="lbl">CASH TIED UP IN AT-RISK STOCK<br>{at_risk_count} products &middot; {pct_risk}% of inventory</div></div>
    <div class="cell"><div class="big">{dead_cash}</div><div class="lbl">STONE-DEAD STOCK<br>{dead_count} products, 0 sales in 12 months</div></div>
    <div class="cell"><div class="big">{total_inv}</div><div class="lbl">TOTAL INVENTORY AT COST<br>{product_count} products ({instock} in stock)</div></div>
  </div>

  <div class="callout avoid-break">&#128176; <b>Cash you could free up:</b> clearing just half of your at-risk stock puts <b>{free_half}</b> back into working capital &mdash; to reinvest in the {reorder_count} fast movers flagged &ldquo;Reorder&rdquo;.</div>

  <h2>How to read this report</h2>
  <div class="guide avoid-break">
    <h3>What this is</h3>
    <p>A ranking of every product you stock by how likely it is to become <b>dead stock</b> &mdash; cash frozen on the shelf. It reads your real Shopify sales and current inventory, and tells you where money is stuck and what to do about it. Work from the top of the table down; the highest-risk, highest-cash items are worth your attention first.</p>

    <h3>The Risk Score (0&ndash;100)</h3>
    <p>Each product gets one number blending four signals. A product scores <b>high</b> when it is: overstocked for its demand (<b>months of cover</b>, 35%), hasn't sold recently (<b>staleness</b>, 35%), ties up a lot of <b>cash</b> (20%), and has <b>declining</b> year-on-year sales (10%). Colour bands:</p>
    <p>
      <span class="chip r">70&ndash;100 &nbsp;Mark down / clear</span> &nbsp;
      <span class="chip a">45&ndash;69 &nbsp;Watch</span> &nbsp;
      <span class="chip g">0&ndash;44 &nbsp;Healthy</span>
    </p>

    <h3>The columns</h3>
    <ul class="gl">
      <li><b>Stock</b> &mdash; units on hand right now (summed across all variants/sizes).</li>
      <li><b>Cover</b> &mdash; how many <b>months</b> your current stock would last at the last 12 months' pace. Under {cover_low} months is healthy; over {cover_high} is badly overstocked. <b>&infin;</b> means it hasn't sold at all in a year &mdash; it will never clear at the current pace.</li>
      <li><b>Sold/yr</b> &mdash; units sold in the last 12 months. The arrow shows the trend vs. the prior 12 months (&#9650; up, &#9660; down, &#9644; flat).</li>
      <li><b>Margin</b> &mdash; your actual gross margin on this product. High margin = more room to discount and still come out ahead.</li>
      <li><b>Cash @cost</b> &mdash; the money tied up in this item (units on hand &times; unit cost). This is what you free up by clearing it.</li>
      <li><b>Action</b> &mdash; the recommended move (see below).</li>
    </ul>

    <h3>What the actions mean</h3>
    <ul class="gl">
      <li><b>Mark down / clear</b> &mdash; high risk. Discount, bundle, or return-to-vendor to release the cash. Use the Margin column to set how deep you can go.</li>
      <li><b>Watch</b> &mdash; moderate risk. Not urgent, but don't reorder without a reason; revisit next month.</li>
      <li><b>Reorder</b> &mdash; selling well and about to run out. The opposite problem &mdash; make sure you don't go short on a winner.</li>
      <li><b>Healthy / Sold out</b> &mdash; nothing to do.</li>
    </ul>

    <h3>Two things to keep in mind</h3>
    <ul class="gl">
      <li>This file has no exact &ldquo;last sale date,&rdquo; so recency is measured from your 30/90/365-day sales windows rather than a single date &mdash; steadier, but it won't pinpoint the exact last sale.</li>
      <li>A few flagged items are <b>slow by nature, not mistakes</b> &mdash; e.g. custom or one-off consignment pieces. The report surfaces them; your judgement decides. It points, you choose.</li>
    </ul>
  </div>

  <h2 class="page-break">What to do this week</h2>
  <ol class="todo avoid-break">{todo}</ol>

  <h2>Where the frozen cash sits &mdash; by brand</h2>
  <div class="avoid-break">{vendors}</div>

  <h2 class="page-break">All in-stock products &mdash; ranked by dead-stock risk</h2>
  <div class="sub-h">{instock} products currently in stock, most at-risk first. Colour = risk band (red/amber/green).</div>
  <table>
    <thead><tr>
      <th>#</th><th>Product</th><th>Risk</th><th>Stock</th><th>Cover</th><th>Sold/yr</th><th>Margin</th><th class="num">Cash&nbsp;@cost</th><th>Action</th>
    </tr></thead>
    <tbody>{ar_rows}</tbody>
  </table>

  <h2 class="page-break">Not currently in stock &mdash; reorder candidates &amp; sold-out lines</h2>
  <div class="sub-h">{nostock} products with no stock on hand (no cash tied up). Sorted by last-12-month sales &mdash; the top of this list are your proven sellers to consider reordering.</div>
  <table>
    <thead><tr>
      <th>#</th><th>Product</th><th>Sold/yr</th><th>Prior&nbsp;yr</th><th>Margin</th><th>Action</th>
    </tr></thead>
    <tbody>{ns_rows}</tbody>
  </table>

  <div class="foot">Generated by the Dead-Stock Predictor (Equine Edge Consulting) from a standard Shopify export. Risk weights &amp; thresholds are tunable. Shows all {product_count} products that have sold: {instock} in stock (ranked by risk) and {nostock} not currently stocked.</div>

</body></html>"""


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "CASA_EQUESTRE_Reorder_Margin_Report (1).xlsx"
    html = build_html(path)
    html_path = os.path.abspath("casa_equestre_report_print.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    pdf_path = os.path.abspath("Casa_Equestre_Dead-Stock_Report.pdf")
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    cmd = [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           "--run-all-compositor-stages-before-draw", "--virtual-time-budget=4000",
           "--print-to-pdf=" + pdf_path, "file://" + html_path.replace(" ", "%20")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(pdf_path):
        # older Chrome flag fallback
        cmd2 = [chrome, "--headless=new", "--disable-gpu", "--print-to-pdf=" + pdf_path,
                "file://" + html_path.replace(" ", "%20")]
        subprocess.run(cmd2, capture_output=True, text=True)
    if os.path.exists(pdf_path):
        size = os.path.getsize(pdf_path)
        print("Wrote PDF -> {} ({:,} bytes)".format(pdf_path, size))
    else:
        print("PDF generation failed.\nSTDERR:", res.stderr[:500])


if __name__ == "__main__":
    main()
