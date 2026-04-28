"""
webhook.py — Flask app to receive inbound WhatsApp commands via CallMeBot webhook.
Deploy to Render.com free tier.
"""

import os
from flask import Flask, request, jsonify

from config_manager import get_config
from whatsapp import handle_incoming_command

app = Flask(__name__)


def _verify_secret(req) -> bool:
    """Check WEBHOOK_SECRET in header or query param."""
    expected = os.environ.get("WEBHOOK_SECRET", "")
    if not expected:
        # If no secret is set, allow all (not recommended for production)
        return True
    provided = (
        req.headers.get("X-Webhook-Secret")
        or req.args.get("secret")
        or (req.json or {}).get("secret", "")
        if req.is_json else req.form.get("secret", "")
    )
    return provided == expected


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive inbound WhatsApp command from CallMeBot."""
    if not _verify_secret(request):
        return jsonify({"error": "Unauthorized"}), 401

    # Extract message text from JSON body or form data
    text = ""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "") or data.get("message", "")
    else:
        text = request.form.get("text", "") or request.form.get("message", "")

    if not text:
        return jsonify({"error": "No text field found in request"}), 400

    print(f"[webhook] Received command: {text!r}")
    reply = handle_incoming_command(text)
    return jsonify({"status": "ok", "reply": reply}), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check — returns current config."""
    try:
        config = get_config()
        return jsonify({"status": "ok", "config": config}), 200
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 500


@app.route("/", methods=["GET"])
def index():
    return jsonify({"service": "Stock Agent Webhook", "status": "running"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
