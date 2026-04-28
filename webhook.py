"""
webhook.py — Flask app to receive Telegram bot updates via webhook.
Deploy to Render.com free tier. After deploying, register the webhook URL once:

    python webhook.py --set-webhook https://your-render-url.onrender.com/webhook

Or call the /register endpoint manually.
"""

import os
import sys
import requests
from flask import Flask, request, jsonify

from config_manager import get_config
from telegram_notifier import handle_incoming_command, set_webhook

app = Flask(__name__)


# ── Telegram webhook receiver ─────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive Telegram update (message from user to bot)."""
    data = request.get_json(silent=True) or {}

    # Extract message text and chat_id from Telegram update format
    message = data.get("message") or data.get("edited_message", {})
    if not message:
        return jsonify({"status": "ignored", "reason": "no message"}), 200

    text    = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not text or not chat_id:
        return jsonify({"status": "ignored", "reason": "empty text or chat_id"}), 200

    print(f"[webhook] Received from {chat_id}: {text!r}")
    reply = handle_incoming_command(text, chat_id=chat_id)
    return jsonify({"status": "ok", "reply": reply}), 200


# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Health check — returns current config."""
    try:
        config = get_config()
        return jsonify({"status": "ok", "config": config}), 200
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 500


# ── One-time webhook registration ─────────────────────────────────────────────

@app.route("/register", methods=["GET"])
def register():
    """
    Call this once after deploying to Render to register the Telegram webhook.
    e.g. https://your-app.onrender.com/register?url=https://your-app.onrender.com/webhook
    """
    webhook_url = request.args.get("url", "")
    if not webhook_url:
        host = request.host_url.rstrip("/")
        webhook_url = f"{host}/webhook"
    ok = set_webhook(webhook_url)
    return jsonify({"registered": ok, "webhook_url": webhook_url}), 200 if ok else 500


@app.route("/", methods=["GET"])
def index():
    return jsonify({"service": "Stock Agent Telegram Webhook", "status": "running"}), 200


# ── CLI webhook registration ──────────────────────────────────────────────────

if __name__ == "__main__":
    if "--set-webhook" in sys.argv:
        idx = sys.argv.index("--set-webhook")
        url = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        if not url:
            print("Usage: python webhook.py --set-webhook https://your-app.onrender.com/webhook")
            sys.exit(1)
        success = set_webhook(url)
        sys.exit(0 if success else 1)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
