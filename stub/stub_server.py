#!/usr/bin/env python3
"""Локальный стаб внешних систем для каркаса (Ф4).

Имитирует два сервиса на тестовых данных stub/stub_data.json:

1. FinTablo API (REST + Bearer-токен):
     GET /v1/balance        -> {"balance": 11750512, "currency": "RUB"}
     GET /v1/operations     -> {"items": [...207 операций...]}
   Ошибка токена -> 401 {"error": "unauthorized"}.

2. Битрикс24 входящий вебхук (POST /rest/1/<secret>/Метод.json):
     crm.deal.list.json     -> {"result": [...486 сделок...], "total": N}
   Неверный секрет -> 403 {"error": "ACCESS_DENIED"}.

Запуск:  .venv/bin/python stub/stub_server.py   -> http://127.0.0.1:5001
Токен и секрет задаются переменными STUB_FINTABLO_TOKEN и STUB_BITRIX_SECRET
(значения по умолчанию согласованы с .env каркаса). Данные перечитываются
по mtime — правка stub_data.json видна без перезапуска.
"""
import json
import os
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "stub_data.json")

TOKEN = os.environ.get("STUB_FINTABLO_TOKEN", "stub-fintablo-token-9f2c")
SECRET = os.environ.get("STUB_BITRIX_SECRET", "stub-secret-bitrix-4e7a")
PORT = int(os.environ.get("STUB_PORT") or 5001)

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False
_cache: Optional[Dict[str, Any]] = None
_cache_key: Optional[float] = None


def dataset() -> Dict[str, Any]:
    global _cache, _cache_key
    try:
        key = os.path.getmtime(DATA)
    except OSError:
        return {"error": "stub data missing"}
    if _cache is None or _cache_key != key:
        with open(DATA, encoding="utf-8") as f:
            _cache = json.load(f)
        _cache_key = key
    return _cache


def authed() -> bool:
    return request.headers.get("Authorization", "").endswith(TOKEN)


# --------------------------------------------------------------- FinTablo --
@app.get("/v1/balance")
def balance():
    if not authed():
        return jsonify({"error": "unauthorized"}), 401
    ops = dataset().get("operations", [])
    bal = sum(o["amount"] for o in ops if o["type"] == "income") - \
          sum(o["amount"] for o in ops if o["type"] == "expense")
    return jsonify({"balance": bal + 12_400_000, "currency": "RUB", "as_of": "2026-09-23"})


@app.get("/v1/operations")
def operations():
    if not authed():
        return jsonify({"error": "unauthorized"}), 401
    items = dataset().get("operations", [])
    return jsonify({"items": items, "total": len(items)})


# -------------------------------------------------------------- Битрикс24 --
@app.post("/rest/1/<secret>/<method>.json")
def bitrix(secret: str, method: str):
    if secret != SECRET:
        return jsonify({"error": "ACCESS_DENIED", "error_description": "wrong webhook secret"}), 403
    if method != "crm.deal.list":
        return jsonify({"error": "METHOD_NOT_FOUND", "error_description": method}), 404
    deals = dataset().get("deals", [])
    return jsonify({"result": deals, "total": len(deals)})


if __name__ == "__main__":
    print(f"Stub FinTablo+Bitrix24 -> http://127.0.0.1:{PORT} "
          f"(token …{TOKEN[-4:]}, secret …{SECRET[-4:]})")
    app.run(host="127.0.0.1", port=PORT, debug=False)
