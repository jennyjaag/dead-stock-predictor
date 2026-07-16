"""
shopify_connect.py -- pull a Shopify store's products + sales straight from the
Admin API (no CSV export), in the exact shape shopify_join.compute() expects.

    prod, sales = fetch(shop_domain, admin_api_token, months=12)
    r = shopify_join.compute(prod, sales)

Auth: an Admin API access token ("shpat_…") from a custom app on the store, with
read_products, read_inventory and read_orders scopes. Uses only the standard
library (urllib) so there's no extra dependency to deploy.
"""

import json
import urllib.error
import urllib.request
from datetime import date, timedelta

import shopify_join as SJ

API_VERSION = "2024-10"


def _clean_domain(d):
    d = (d or "").strip().replace("https://", "").replace("http://", "").strip("/")
    if d and "." not in d:
        d = d + ".myshopify.com"
    return d


def _graphql(shop, token, query, variables=None):
    url = "https://{}/admin/api/{}/graphql.json".format(shop, API_VERSION)
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": token,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Shopify rejected the token (check the store domain, the token, "
                               "and that the app has read_products / read_orders scopes).")
        raise RuntimeError("Shopify API error {}: {}".format(e.code, e.reason))
    except urllib.error.URLError as e:
        raise RuntimeError("Couldn't reach the store — check the domain. ({})".format(e.reason))
    if data.get("errors"):
        raise RuntimeError("Shopify API: {}".format(str(data["errors"])[:300]))
    return data["data"]


_PRODUCTS_Q = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      handle title vendor productType status isGiftCard createdAt publishedAt
      variants(first: 100) {
        nodes {
          sku inventoryQuantity price
          selectedOptions { name value }
          inventoryItem { unitCost { amount } }
        }
      }
    }
  }
}
"""


def _fetch_products(shop, token):
    prod, cursor = {}, None
    while True:
        conn = _graphql(shop, token, _PRODUCTS_Q, {"cursor": cursor})["products"]
        for n in conn["nodes"]:
            # product age: when it became available (published), else when created
            added = None
            for fld in ("publishedAt", "createdAt"):
                v = n.get(fld)
                if v:
                    try:
                        added = date.fromisoformat(v[:10])
                        break
                    except ValueError:
                        pass
            p = {"title": n["title"], "vendor": n.get("vendor") or "",
                 "type": n.get("productType") or "", "status": (n.get("status") or "").lower(),
                 "giftcard": bool(n.get("isGiftCard")), "stock": 0, "added": added,
                 "costs": [], "prices": [], "variants": []}
            for v in n["variants"]["nodes"]:
                qty = v.get("inventoryQuantity") or 0
                p["stock"] += qty
                cost = None
                uc = (v.get("inventoryItem") or {}).get("unitCost")
                if uc and uc.get("amount") is not None:
                    try:
                        cost = float(uc["amount"])
                        p["costs"].append(cost)
                    except (TypeError, ValueError):
                        cost = None
                if v.get("price") not in (None, ""):
                    try:
                        p["prices"].append(float(v["price"]))
                    except (TypeError, ValueError):
                        pass
                opts = {o["name"]: o["value"] for o in (v.get("selectedOptions") or [])
                        if o.get("value") and o["value"] != "Default Title"}
                p["variants"].append({"label": " / ".join(opts.values()) or "(single)",
                                      "sku": v.get("sku") or "", "stock": qty,
                                      "cost": cost, "options": opts})
            prod[n["handle"]] = p
        if conn["pageInfo"]["hasNextPage"]:
            cursor = conn["pageInfo"]["endCursor"]
        else:
            return prod


_ORDERS_Q = """
query($cursor: String, $q: String) {
  orders(first: 50, after: $cursor, query: $q) {
    pageInfo { hasNextPage endCursor }
    nodes {
      lineItems(first: 100) { nodes { quantity title product { title } } }
    }
  }
}
"""


def _fetch_sales(shop, token, months):
    since = (date.today() - timedelta(days=int(months * 30.44))).isoformat()
    q = "created_at:>={}".format(since)
    sales, cursor = {}, None
    while True:
        conn = _graphql(shop, token, _ORDERS_Q, {"cursor": cursor, "q": q})["orders"]
        for o in conn["nodes"]:
            for li in o["lineItems"]["nodes"]:
                title = (li.get("product") or {}).get("title") or li.get("title")
                if not title:
                    continue
                key = SJ.norm(title)
                sales[key] = sales.get(key, 0) + (li.get("quantity") or 0)
        if conn["pageInfo"]["hasNextPage"]:
            cursor = conn["pageInfo"]["endCursor"]
        else:
            return sales


def fetch(shop_domain, token, months=12):
    """Return (prod, sales) ready for shopify_join.compute(). Raises on bad auth/domain."""
    shop = _clean_domain(shop_domain)
    if not shop or not token:
        raise ValueError("Store domain and access token are both required.")
    prod = _fetch_products(shop, token)
    sales = _fetch_sales(shop, token, months)
    return prod, sales
