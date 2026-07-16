"""
shopify_api.py -- LIVE Shopify Admin API data source for EquiSphere.

Pulls products + variants (stock, cost, price, options) and trailing-window unit
sales straight from the Shopify Admin GraphQL API, and returns the SAME structures
that shopify_join.load_products / load_sales produce from CSV exports — so the
existing compute() and every view work unchanged, just on live data.

Auth uses the Shopify "client credentials" grant (a custom app in the SAME
organisation as the store). Credentials live in st.secrets, never in the repo:

    [shopify]
    store_domain  = "your-store.myshopify.com"
    client_id     = "xxxxxxxx"
    client_secret = "shpss_xxxxxxxx"
    api_version   = "2026-07"

Note: the access token from this grant is short-lived (~24h); we fetch a fresh
one at runtime and cache it for an hour.
"""

from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

import shopify_join as SJ  # reuse norm()


# ---------------------------------------------------------------------------
# config / auth
# ---------------------------------------------------------------------------
def _cfg():
    return st.secrets["shopify"]


def configured():
    """True when a [shopify] secrets block with the needed keys is present."""
    try:
        c = st.secrets["shopify"]
        return bool(c.get("store_domain") and c.get("client_id") and c.get("client_secret"))
    except Exception:
        return False


def store_label():
    try:
        return st.secrets["shopify"].get("store_domain", "Shopify")
    except Exception:
        return "Shopify"


@st.cache_data(ttl=3600, show_spinner=False)
def _token():
    c = _cfg()
    r = requests.post(
        "https://{}/admin/oauth/access_token".format(c["store_domain"]),
        json={"client_id": c["client_id"], "client_secret": c["client_secret"],
              "grant_type": "client_credentials"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _gql(query, variables=None):
    c = _cfg()
    ver = c.get("api_version", "2026-07")
    r = requests.post(
        "https://{}/admin/api/{}/graphql.json".format(c["store_domain"], ver),
        headers={"X-Shopify-Access-Token": _token(), "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=60,
    )
    r.raise_for_status()
    d = r.json()
    if "errors" in d:
        raise RuntimeError(d["errors"])
    return d["data"]


# ---------------------------------------------------------------------------
# products  ->  same shape as shopify_join.load_products()
# ---------------------------------------------------------------------------
_PRODUCTS_Q = """
query($cursor: String) {
  products(first: 40, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges { node {
      handle title vendor productType status
      variants(first: 100) { edges { node {
        sku title price inventoryQuantity
        selectedOptions { name value }
        inventoryItem { unitCost { amount } }
      } } }
    } }
  }
}
"""


def load_products_api():
    prod = {}
    cursor = None
    while True:
        conn = _gql(_PRODUCTS_Q, {"cursor": cursor})["products"]
        for e in conn["edges"]:
            n = e["node"]
            h = n.get("handle")
            if not h:
                continue
            p = prod.setdefault(h, {
                "title": n.get("title", "") or "", "vendor": n.get("vendor", "") or "",
                "type": n.get("productType", "") or "", "status": (n.get("status") or "").lower(),
                "giftcard": False, "stock": 0, "costs": [], "prices": [], "variants": [],
            })
            for ve in n["variants"]["edges"]:
                v = ve["node"]
                qty = v.get("inventoryQuantity") or 0
                p["stock"] += qty
                cost = None
                ii = v.get("inventoryItem") or {}
                uc = (ii.get("unitCost") or {}) if ii else {}
                if uc.get("amount") not in (None, ""):
                    try:
                        cost = float(uc["amount"]); p["costs"].append(cost)
                    except (ValueError, TypeError):
                        cost = None
                if v.get("price") not in (None, ""):
                    try:
                        p["prices"].append(float(v["price"]))
                    except (ValueError, TypeError):
                        pass
                options = {(o.get("name") or "Option").strip(): (o.get("value") or "").strip()
                           for o in (v.get("selectedOptions") or [])
                           if o.get("value") and o["value"] != "Default Title"}
                label = " / ".join(options.values()) or "(single)"
                p["variants"].append({"label": label, "sku": (v.get("sku") or "").strip(),
                                      "stock": qty, "cost": cost, "options": options})
        if conn["pageInfo"]["hasNextPage"]:
            cursor = conn["pageInfo"]["endCursor"]
        else:
            break
    return prod


# ---------------------------------------------------------------------------
# sales  ->  same shape as shopify_join.load_sales()  {norm(title): units}
# ---------------------------------------------------------------------------
_ORDERS_Q = """
query($cursor: String, $q: String!) {
  orders(first: 40, after: $cursor, query: $q, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    edges { node {
      lineItems(first: 100) { edges { node {
        quantity
        product { title }
      } } }
    } }
  }
}
"""


def load_sales_api(days=365):
    """Sum units sold per product title over the trailing `days`.

    Note: the `read_orders` scope covers the trailing 60 days; a full 12-month
    history needs Shopify's protected `read_all_orders` scope. Whatever the
    scope allows is what's summed here.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    q = "created_at:>={}".format(since)
    units = {}
    cursor = None
    while True:
        conn = _gql(_ORDERS_Q, {"cursor": cursor, "q": q})["orders"]
        for e in conn["edges"]:
            for le in e["node"]["lineItems"]["edges"]:
                li = le["node"]
                prodobj = li.get("product") or {}
                t = prodobj.get("title") if prodobj else None
                if t:
                    k = SJ.norm(t)
                    units[k] = units.get(k, 0) + (li.get("quantity") or 0)
        if conn["pageInfo"]["hasNextPage"]:
            cursor = conn["pageInfo"]["endCursor"]
        else:
            break
    return units


def fetch():
    """Return (prod, sales) ready for shopify_join.compute()."""
    prod = load_products_api()
    sales = load_sales_api()
    return prod, sales
