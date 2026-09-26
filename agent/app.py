#!/usr/bin/env python3
"""Мини-интерфейс агента расходов (Ф7): http://127.0.0.1:5002

Одна страница: поле ввода (как сообщение боту), ответ агента в виде карточек
и последние записи из таблицы. Запуск:  .venv/bin/python agent/app.py
"""
import json
import os
import sys

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(AGENT_DIR)
for _p in (PROJECT, AGENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJECT, ".env"))
load_dotenv(os.path.join(AGENT_DIR, ".env"))  # локальные переопределения движка

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import engine as engine_mod  # noqa: E402
import harness  # noqa: E402

app = Flask(__name__)
app.json.ensure_ascii = False


@app.route("/")
def index():
    return send_from_directory(AGENT_DIR, "index.html")


@app.route("/api/engine")
def api_engine():
    return jsonify({"mode": engine_mod.engine_mode()})


@app.route("/api/message", methods=["POST"])
def api_message():
    text = (request.get_json(silent=True) or {}).get("text") or ""
    if not text.strip():
        return jsonify({"error": u"пустое сообщение"}), 400
    try:
        result = harness.validate(engine_mod.parse_message(text))
    except harness.ValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    if result["action"] == "expense":
        written = harness.write_expense(result)
        return jsonify({"result": result, "written": written})
    if result["action"] == "correct":
        fixed = harness.apply_correction(result)
        return jsonify({"result": result, "corrected": fixed})
    return jsonify({"result": result})


@app.route("/api/recent")
def api_recent():
    try:
        return jsonify({"rows": harness.recent_rows()})
    except Exception as exc:
        return jsonify({"rows": [], "error": exc.__class__.__name__})


if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT") or 5002)
    print(u"Агент расходов (движок: %s) -> http://127.0.0.1:%d" % (engine_mod.engine_mode(), port))
    app.run(host="127.0.0.1", port=port, debug=False)
