"""Regression checks against the running CI app and its demo catalog (no AI)."""
import json
from urllib.request import Request, urlopen

for query, size, count in [("sneakers bianche", "42", 2), ("sneakers bianche", "4", 0), ("felpa", "m", 1)]:
    body = json.dumps({"query": query, "history": [], "manualFilters": {"size": size}}).encode()
    request = Request("http://localhost:3000/api/search", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        products = json.load(response)["products"]
    assert len(products) == count, (query, size, products)
    assert all(size.lower() in [part.strip().lower() for part in p["size"].split(",")] for p in products)
print("Exact size API regression: 3 cases passed")
