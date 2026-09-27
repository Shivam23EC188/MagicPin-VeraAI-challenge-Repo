"""
Pushes the full local dataset into the running app.py server, then calls
/v1/tick with every available trigger and prints each action's body so you
can manually check specificity / merchant fit / category fit / WHY-NOW /
hallucination for every trigger kind.

Run this AFTER uvicorn is already running (Terminal 1), from a second
terminal, in the project root:

    python check_quality.py
"""
import json
import requests
from pathlib import Path

BASE = "http://127.0.0.1:8000"
DATASET_DIR = Path("dataset")


def push(scope, context_id, payload):
    r = requests.post(f"{BASE}/v1/context", json={
        "scope": scope,
        "context_id": context_id,
        "version": 1,
        "payload": payload,
        "delivered_at": "2026-09-27T00:00:00Z"
    })
    ok = r.status_code == 200 and r.json().get("accepted")
    print(f"  [{'OK' if ok else 'FAIL'}] {scope}/{context_id}  (status {r.status_code})")
    return ok


def main():
    # 1. Push categories
    print("Pushing categories...")
    cat_dir = DATASET_DIR / "categories"
    if cat_dir.exists():
        for f in cat_dir.glob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            slug = data.get("slug", f.stem)
            push("category", slug, data)

    # 2. Push merchants
    print("Pushing merchants...")
    m_path = DATASET_DIR / "merchants_seed.json"
    merchants = {}
    if m_path.exists():
        data = json.load(open(m_path, encoding="utf-8"))
        items = data.get("merchants", [])
        for item in items:
            mid = item.get("merchant_id")
            merchants[mid] = item
            push("merchant", mid, item)

    # 3. Push customers
    print("Pushing customers...")
    c_path = DATASET_DIR / "customers_seed.json"
    if c_path.exists():
        data = json.load(open(c_path, encoding="utf-8"))
        items = data.get("customers", [])
        for item in items:
            cid = item.get("customer_id")
            push("customer", cid, item)

    # 4. Push triggers
    print("Pushing triggers...")
    t_path = DATASET_DIR / "triggers_seed.json"
    trigger_ids = []
    triggers_by_id = {}
    if t_path.exists():
        data = json.load(open(t_path, encoding="utf-8"))
        items = data.get("triggers", [])
        for item in items:
            tid = item.get("id")
            trigger_ids.append(tid)
            triggers_by_id[tid] = item
            push("trigger", tid, item)

    print(f"\nTotal triggers loaded: {len(trigger_ids)}")

    # 5. Call /v1/tick with ALL trigger ids at once
    print("\nCalling /v1/tick with all triggers...\n")
    r = requests.post(f"{BASE}/v1/tick", json={
        "now": "2026-09-27T00:00:00Z",
        "available_triggers": trigger_ids
    })
    if r.status_code != 200:
        print(f"[ERROR] tick failed: {r.status_code} {r.text}")
        return

    actions = r.json().get("actions", [])
    print(f"Bot returned {len(actions)} action(s)\n")
    print("=" * 100)

    for a in actions:
        kind = a.get("template_name")
        mid = a.get("merchant_id")
        m_name = merchants.get(mid, {}).get("identity", {}).get("name", mid)
        category = merchants.get(mid, {}).get("category_slug", "?")
        print(f"KIND: {kind}")
        print(f"MERCHANT: {m_name}  (category: {category})")
        print(f"BODY: {a.get('body')}")
        print(f"CTA: {a.get('cta')}")
        print("-" * 100)


if __name__ == "__main__":
    main()