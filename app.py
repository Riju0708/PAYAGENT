import os, json, sqlite3, requests
from flask import Flask, request, jsonify, redirect
from dotenv import load_dotenv

load_dotenv()
PP = "https://api-m.sandbox.paypal.com"  # sandbox only, no real money
BASE = os.getenv("BASE_URL", "http://localhost:5000")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
app = Flask(__name__, static_folder="static")


def db():
    c = sqlite3.connect("invoices.db")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS invoices(
        id INTEGER PRIMARY KEY, client TEXT, amount REAL, currency TEXT,
        description TEXT, order_id TEXT, link TEXT, status TEXT DEFAULT 'PENDING',
        created TEXT DEFAULT CURRENT_TIMESTAMP, paid_at TEXT)""")
    return c


def pp(method, path, **kw):
    t = requests.post(f"{PP}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                      auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"]), timeout=20)
    t.raise_for_status()
    r = requests.request(method, PP + path, timeout=20,
                         headers={"Authorization": "Bearer " + t.json()["access_token"]}, **kw)
    if not r.ok:
        raise RuntimeError(f"PayPal error {r.status_code}: {r.text[:300]}")
    return r.json()


def ask(system, user, max_tokens=600):
    """Call Google Gemini (free tier) and return the reply text."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    r = requests.post(
        url,
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            # extra room because some Gemini models spend tokens on internal thinking
            "generationConfig": {"maxOutputTokens": max_tokens * 4},
        },
        timeout=40,
    )
    if not r.ok:
        raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


PARSE = ("You turn a freelancer's request into an invoice. Reply with ONLY JSON: "
         '{"client": str, "amount": number, "currency": "USD", "description": str}. '
         'If the client or amount is missing, reply {"error": "<what is missing, one short sentence>"}.')


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.post("/api/chat")
def chat():
    raw = ask(PARSE, request.json["message"]).replace("```json", "").replace("```", "").strip()
    d = json.loads(raw)
    if "error" in d:
        return jsonify(error=d["error"])
    amt, cur = float(d["amount"]), d.get("currency", "USD")
    order = pp("POST", "/v2/checkout/orders", json={
        "intent": "CAPTURE",
        "purchase_units": [{"description": d["description"][:120],
                            "amount": {"currency_code": cur, "value": f"{amt:.2f}"}}],
        "payment_source": {"paypal": {"experience_context": {
            "return_url": f"{BASE}/return", "cancel_url": f"{BASE}/", "user_action": "PAY_NOW"}}}})
    link = next(l["href"] for l in order["links"] if l["rel"] in ("payer-action", "approve"))
    with db() as c:
        c.execute("INSERT INTO invoices(client,amount,currency,description,order_id,link) VALUES(?,?,?,?,?,?)",
                  (d["client"], amt, cur, d["description"], order["id"], link))
    return jsonify(client=d["client"], link=link)


@app.get("/return")  # PayPal sends the buyer back here after approving
def back():
    oid = request.args.get("token")
    try:
        pp("POST", f"/v2/checkout/orders/{oid}/capture", json={})
        with db() as c:
            c.execute("UPDATE invoices SET status='PAID', paid_at=CURRENT_TIMESTAMP WHERE order_id=?", (oid,))
    except Exception as e:
        print("capture failed:", e)
    return redirect("/")


@app.post("/api/webhook")  # optional: needs a public URL (e.g. ngrok/Render). Signature check skipped in sandbox.
def webhook():
    ev = request.json or {}
    if ev.get("event_type") == "PAYMENT.CAPTURE.COMPLETED":
        oid = ev["resource"].get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        with db() as c:
            c.execute("UPDATE invoices SET status='PAID', paid_at=CURRENT_TIMESTAMP WHERE order_id=?", (oid,))
    return "", 200


@app.get("/api/invoices")
def invoices():
    return jsonify([dict(r) for r in db().execute("SELECT * FROM invoices ORDER BY id DESC")])


@app.get("/api/insights")
def insights():
    rows = [dict(r) for r in db().execute("SELECT client,amount,status,created,paid_at FROM invoices")]
    if not rows:
        return jsonify(text="Create a few invoices first, then I can spot patterns.")
    return jsonify(text=ask("You are a sharp, friendly finance assistant for a freelancer. Given their invoices, "
                            "give 3 short, specific, actionable insights (late payers, cash flow, what to do next). No fluff.",
                            json.dumps(rows)))


@app.post("/api/reminder/<int:i>")
def reminder(i):
    row = db().execute("SELECT * FROM invoices WHERE id=?", (i,)).fetchone()
    if row is None:
        return jsonify(error="Invoice not found"), 404
    r = dict(row)
    return jsonify(text=ask("Write a short, polite payment reminder message the freelancer can send. "
                            "Include the amount and the payment link. Under 60 words.", json.dumps(r)))


@app.errorhandler(Exception)
def oops(e):
    return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
