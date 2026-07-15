"""
master_pdf.py -- print-ready PDF dead-stock report from the single master .xlsx.

Reuses master_load.load_master() for all the analysis, lays it out as a paginated
A4 document (print-safe colours), and renders to PDF via headless Chrome.

Run:  python3 master_pdf.py "casa_equestre_deadstock_master.xlsx"
"""

import os
import subprocess
import sys
from datetime import date, timedelta

import master_load as ML
import casa_report as C

TODAY = date.today()
CUR = "$"


def money(v):
    return "—" if v is None else "{}{:,.0f}".format(CUR, v)


def cover_txt(c):
    return "∞" if c == float("inf") else "{:.0f} mo".format(c)


def pill(risk):
    return "r" if risk >= C.MARKDOWN_SCORE else "a" if risk >= C.WATCH_SCORE else "g"


def recommend(x):
    if x["action"] == "New — too early to tell":
        return "New — too early to tell", "watch"
    if x["action"] == "Reorder":
        return "Reorder — selling fast", "now"
    if x["risk"] >= C.MARKDOWN_SCORE:
        if x["u12"] == 0:
            act = "Stop reordering · mark down 30%"
        elif x["risk"] >= 85:
            act = "Mark down 40% now"
        else:
            act = "Mark down 25% now"
        return act, TODAY.strftime("%d %b %Y")
    if x["risk"] >= C.WATCH_SCORE:
        return "Watch — recheck in 3 weeks", (TODAY + timedelta(weeks=3)).strftime("%d %b %Y")
    return "Healthy", "—"


def why(x):
    cash = money(x["cash"]) if x["cash"] is not None else "cost unknown"
    lead = "0 sales in 12 months" if x["u12"] == 0 else "{:.0f} sold last year".format(x["u12"])
    return "{} · {} of cover · {} tied up".format(lead, cover_txt(x["cover"]), cash)


def build_html(r):
    in_stock = r["in_stock"]
    at_risk = r["at_risk"]
    top_by_cash = sorted([x for x in at_risk if x["cash"]], key=lambda x: x["cash"], reverse=True)
    free10 = sum(x["cash"] for x in top_by_cash[:10])

    # action list (top at-risk)
    todo = ""
    for x in at_risk[:20]:
        act, when = recommend(x)
        todo += ("<tr><td class='nm'>{n}<span class='sub'>{w}</span></td>"
                 "<td><span class='p {pc}'>{r}</span></td><td class='num'>{cash}</td>"
                 "<td class='act'>{a}<span class='dt'>{d}</span></td></tr>").format(
            n=C.esc(x["title"]), w=C.esc(why(x)), pc=pill(x["risk"]), r=x["risk"],
            cash=money(x["cash"]), a=C.esc(act), d=when)

    # cash at risk by brand
    vmax = r["vend_sorted"][0][1] if r["vend_sorted"] else 1
    brands = ""
    for name, val in r["vend_sorted"]:
        brands += ("<div class='bar'><div class='bn'>{n}</div><div class='bt'>"
                   "<div class='bf' style='width:{p:.0f}%'></div></div><div class='bv'>{v}</div></div>").format(
            n=C.esc(name), p=val / vmax * 100, v=money(val))

    # full in-stock ranked table
    allrows = ""
    for i, x in enumerate(in_stock, 1):
        act, _ = recommend(x)
        vt = " · ".join([p for p in (x["vendor"], x["type"]) if p and p != "Uncategorised"])
        allrows += ("<tr><td class='rk'>{i}</td><td class='nm'>{n}<span class='sub'>{vt}</span></td>"
                    "<td><span class='p {pc}'>{r}</span></td><td>{stock:.0f}</td><td>{cov}</td>"
                    "<td>{u:.0f}/yr</td><td class='num'>{cash}</td><td class='act'>{a}</td></tr>").format(
            i=i, n=C.esc(x["title"]), vt=C.esc(vt), pc=pill(x["risk"]), r=x["risk"], stock=x["stock"],
            cov=cover_txt(x["cover"]), u=x["u12"], cash=money(x["cash"]) if x["cash"] is not None else "—",
            a=C.esc(act))

    return TEMPLATE.format(
        asof=TODAY.strftime("%d %b %Y"),
        cash_at_risk=money(r["cash_at_risk"]), at_risk_count=r["at_risk_count"],
        dead_cash=money(r["dead_cash"]), dead_count=r["dead_count"],
        total_inv=money(r["total_inv"]), instock=r["instock_count"],
        new_count=len(r.get("new_arrivals", [])), free10=money(free10),
        brands=brands, todo=todo, allrows=allrows)


TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  @page {{ size:A4; margin:14mm 12mm; }}
  * {{ box-sizing:border-box; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  body {{ font-family:-apple-system,"Helvetica Neue",Arial,sans-serif; color:#1b1f24; font-size:10.5px; line-height:1.45; margin:0; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  h2 {{ font-size:14px; margin:20px 0 9px; padding-bottom:4px; border-bottom:2px solid #1F5A43; }}
  .sub-h {{ color:#6b7280; font-size:10px; margin-bottom:4px; }}
  .page-break {{ page-break-before:always; }} tr {{ page-break-inside:avoid; }}
  .hero {{ display:flex; background:#1F5A43; color:#fff; border-radius:10px; overflow:hidden; margin-top:12px; }}
  .hero .cell {{ padding:14px 16px; flex:1; border-right:1px solid rgba(255,255,255,.15); }}
  .hero .cell:last-child {{ border-right:0; }}
  .hero .big {{ font-size:23px; font-weight:800; line-height:1.05; }}
  .hero .lbl {{ font-size:9px; opacity:.82; margin-top:4px; }}
  .callout {{ background:#eef6ff; border:1px solid #cfe3fb; border-radius:8px; padding:11px 13px; margin-top:12px; }}
  .callout b {{ color:#0b57d0; }}
  .guide {{ background:#f7f8fa; border:1px solid #e6e8ec; border-radius:8px; padding:6px 16px 12px; font-size:10px; }}
  .guide h3 {{ font-size:11px; margin:11px 0 3px; }} .guide ul {{ margin:3px 0; padding-left:15px; }} .guide li {{ margin-bottom:2px; }}
  .chip {{ display:inline-block; padding:1px 7px; border-radius:10px; font-weight:700; font-size:9.5px; }}
  .chip.r {{ background:#f6e1dd; color:#b23a2e; }} .chip.a {{ background:#fbf0d8; color:#94661a; }} .chip.g {{ background:#e9e7df; color:#6b7268; }}
  table {{ width:100%; border-collapse:collapse; font-size:9.3px; }}
  thead {{ display:table-header-group; }}
  th,td {{ text-align:left; padding:4px 5px; border-bottom:0.5px solid #e6e8ec; }}
  th {{ color:#6b7280; font-size:8px; text-transform:uppercase; letter-spacing:.03em; border-bottom:1px solid #c9ccd1; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  td.nm {{ font-weight:600; max-width:320px; }} td.rk {{ color:#9aa0a6; }} td.act {{ white-space:nowrap; }}
  td.act .dt {{ display:block; color:#98a2b3; font-weight:400; font-size:8px; }}
  .nm .sub {{ display:block; font-weight:400; color:#98a2b3; font-size:8.5px; }}
  .p {{ display:inline-block; min-width:24px; text-align:center; padding:1px 6px; border-radius:10px; font-weight:700; }}
  .p.r {{ background:#f6e1dd; color:#b23a2e; }} .p.a {{ background:#fbf0d8; color:#94661a; }} .p.g {{ background:#e9e7df; color:#6b7268; }}
  .foot {{ margin-top:8px; font-size:8.5px; color:#9aa0a6; }}
  .bar {{ display:grid; grid-template-columns:110px 1fr 66px; align-items:center; gap:9px; margin-bottom:5px; font-size:10px; }}
  .bn {{ font-weight:600; }} .bt {{ background:#eceef1; border-radius:6px; height:12px; overflow:hidden; }}
  .bf {{ background:#D1483B; height:100%; }} .bv {{ text-align:right; color:#4b5563; font-variant-numeric:tabular-nums; }}
</style></head><body>
  <h1>Casa Equestre — Dead-Stock Report</h1>
  <div class="sub-h">Source: single master export (stock, cost, 30/90/12-month + prior-year sales, date added) · as of {asof}</div>

  <div class="hero">
    <div class="cell"><div class="big">{cash_at_risk}</div><div class="lbl">CASH TIED UP IN AT-RISK STOCK<br>{at_risk_count} products</div></div>
    <div class="cell"><div class="big">{dead_cash}</div><div class="lbl">GENUINELY DEAD<br>{dead_count} products, 0 sales in 12mo</div></div>
    <div class="cell"><div class="big">{total_inv}</div><div class="lbl">ACTIVE INVENTORY AT COST<br>{instock} in stock</div></div>
    <div class="cell"><div class="big">{new_count}</div><div class="lbl">NEW ARRIVALS<br>kept out of dead stock</div></div>
  </div>

  <div class="callout">&#128176; <b>Cash you could free up:</b> clearing half of your at-risk stock puts <b>{free10}</b>
  back into working capital. New arrivals (added in the last 90 days, no sales yet) are flagged &ldquo;too early to tell,&rdquo; not dead.</div>

  <h2>How to read this report</h2>
  <div class="guide">
    <p>Every in-stock product is ranked by <b>dead-stock risk (0&ndash;100)</b>, blending months of cover, how recently it sold,
    cash tied up, and a real year-on-year trend. Colour bands:
    <span class="chip r">70&ndash;100 Mark down</span> <span class="chip a">45&ndash;69 Watch</span> <span class="chip g">0&ndash;44 Healthy</span></p>
    <h3>Columns</h3>
    <ul>
      <li><b>Cover</b> = months your stock lasts at the last year's pace. <b>&infin;</b> = no sales in 12 months.</li>
      <li><b>Sold/yr</b> = units sold in the last 12 months. <b>Cash</b> = money tied up (— = no cost recorded).</li>
      <li><b>Action</b> = the move: mark down / stop reordering / watch / reorder / healthy.</li>
    </ul>
  </div>

  <h2>Where the frozen cash sits — by brand</h2>
  <div>{brands}</div>

  <h2 class="page-break">Do this first — your action list</h2>
  <table><thead><tr><th>Product &amp; why</th><th>Risk</th><th class="num">Cash</th><th>Recommended action</th></tr></thead>
    <tbody>{todo}</tbody></table>

  <h2 class="page-break">All in-stock products — ranked by dead-stock risk</h2>
  <table><thead><tr><th>#</th><th>Product</th><th>Risk</th><th>Stock</th><th>Cover</th><th>Sold/yr</th><th class="num">Cash</th><th>Action</th></tr></thead>
    <tbody>{allrows}</tbody></table>
  <div class="foot">Generated by the Dead-Stock Predictor (Equine Edge Consulting) from the master Shopify export. New arrivals (added &le;90 days, no sales) are excluded from the dead-stock counts.</div>
</body></html>"""


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/jennypersson/Downloads/casa_equestre_deadstock_master.xlsx"
    r = ML.load_master(src)
    html = build_html(r)
    html_path = os.path.abspath("casa_master_report_print.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    pdf_path = os.path.abspath("Casa_Equestre_DeadStock_Master_Report.pdf")
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=4000",
                    "--print-to-pdf=" + pdf_path, "file://" + html_path.replace(" ", "%20")],
                   capture_output=True, text=True)
    if os.path.exists(pdf_path):
        print("Wrote PDF -> {} ({:,} bytes)".format(pdf_path, os.path.getsize(pdf_path)))
    else:
        print("PDF generation failed.")


if __name__ == "__main__":
    main()
