"""
Fires the Phase D edge cases at /v1/reply that the judge's script doesn't
properly exercise (it uses a different conversation_id per auto-reply turn,
so it never tests same-conversation repeat behavior).

Run AFTER uvicorn is running, from a second terminal:
    python edge_case_test.py
"""
import requests

BASE = "http://127.0.0.1:8000"
MERCHANT = "m_001_drmeera_dentist_delhi"


def send(conv_id, message, turn):
    r = requests.post(f"{BASE}/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": MERCHANT,
        "customer_id": None,
        "from_role": "merchant",
        "message": message,
        "received_at": "2026-09-27T00:00:00Z",
        "turn_number": turn
    })
    data = r.json()
    print(f"  Turn {turn} | msg: \"{message}\"")
    print(f"    -> action: {data.get('action')}  body: {str(data.get('body'))[:80]}")
    return data


print("=" * 90)
print("TEST 1: Same auto-reply x4, SAME conversation_id")
print("=" * 90)
cid = "conv_edge_autoreply_1"
for i in range(1, 5):
    send(cid, "Thank you for contacting us, our team will get back to you as soon as possible.", i)

print()
print("=" * 90)
print("TEST 2: Three unclear turns -> graceful end")
print("=" * 90)
cid = "conv_edge_unclear_1"
for i, msg in enumerate(["hmm maybe", "not sure what you mean", "can you explain again"], start=1):
    send(cid, msg, i)

print()
print("=" * 90)
print("TEST 3: Same response body sent twice in one conversation (manual check)")
print("=" * 90)
cid = "conv_edge_repeat_1"
r1 = send(cid, "hmm ok", 1)
r2 = send(cid, "hmm ok", 2)
if r1.get("body") and r1.get("body") == r2.get("body"):
    print("  [WARNING] Same body sent twice verbatim in one conversation!")
else:
    print("  [OK] Bodies differ or are not both 'send' actions.")

print()
print("=" * 90)
print("TEST 4: 'give me time' -> wait 1800")
print("=" * 90)
send("conv_edge_wait_1", "give me time", 1)

print()
print("=" * 90)
print("TEST 5: 'not interested' -> end")
print("=" * 90)
send("conv_edge_neg_1", "not interested", 1)

print()
print("=" * 90)
print("TEST 6: Hostile + unrelated GST question")
print("=" * 90)
send("conv_edge_hostile_gst_1", "You are useless. Can you file my GST?", 1)

print()
print("=" * 90)
print("TEST 7: Hinglish positive intent")
print("=" * 90)
send("conv_edge_hinglish_1", "haan theek hai kar do", 1)