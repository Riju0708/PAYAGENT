# PayAgent: an AI CFO for freelancers

Type "Bill Ravi $20 for logo design". PayAgent uses Claude to turn that into a structured invoice,
creates a PayPal order (sandbox) and gives you a payment link. When the client pays, the order is
captured, the invoice flips to Paid, and the dashboard updates. Claude also spots payment patterns
and drafts reminder messages.

## Features
- Plain-English invoice creation (Claude parses it, PayPal Orders v2 API creates it)
- Payment tracking via PayPal return flow capture, plus an optional webhook endpoint
- Dashboard: billed, collected, still owed
- AI insights on late payers and cash flow, and one-click reminder drafts

## Tools used
- **PayPal Developer Platform** (sandbox): OAuth token, Orders v2 create and capture, webhooks
- **Claude API (Anthropic)**: invoice parsing, insights, reminder drafting

## Run it
1. Python 3.10+. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill in your PayPal sandbox client ID and secret and your Anthropic API key
3. `python app.py`, then open http://localhost:5000
4. Create an invoice, open the Pay link, log in with a PayPal **sandbox personal** test account, approve.
   You land back on the dashboard with the invoice marked Paid.

Optional webhook: expose the app with a public URL, set `BASE_URL`, and add `POST /api/webhook`
for the `PAYMENT.CAPTURE.COMPLETED` event in your PayPal sandbox app.

Sandbox only, no real money moves.

## License
MIT
