"""Точка входа каркаса: Flask отдаёт статику из app/static и JSON API.

Запуск:  .venv/bin/python app/server.py   ->  http://127.0.0.1:5000
Порт берётся из .env (PORT, по умолчанию 5000), источник данных — DATA_SOURCE.
Python 3.9: без match, без X | Y в аннотациях.
"""
import math
import os
import sys
import traceback
from typing import Any, Dict, List

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)
for _p in (BASE_DIR, APP_DIR):  # чтобы работало и `python app/server.py`, и `python -m app.server`
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BASE_DIR, ".env"))

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import db  # noqa: E402
from services.sources import (  # noqa: E402
    PERIODS,
    PERIOD_LABELS,
    SourceError,
    available_sources,
    get_source,
)

APP_NAME = u"Сервис отчётности «Вектор» — каркас (Ф3)"


class ApiError(Exception):
    """Ошибка API: наружу уходит {"error": "..."} + HTTP-код."""

    def __init__(self, message: str, code: int = 400) -> None:
        super(ApiError, self).__init__(message)
        self.message = message
        self.code = code


app = Flask(__name__, static_folder="static", static_url_path="")
app.json.ensure_ascii = False   # кириллица в ответах — как есть, UTF-8
app.json.sort_keys = False
app.config["APP_NAME"] = APP_NAME

SOURCE = None  # type: Any  # инициализируется в init_app()


# --------------------------------------------------------------------------- #
# инфраструктура
# --------------------------------------------------------------------------- #
def get_active_source() -> Any:
    global SOURCE
    if SOURCE is None:
        SOURCE = get_source()
    return SOURCE


def data(period: str) -> Dict[str, Any]:
    """Единая точка получения данных от активного источника."""
    return get_active_source().fetch(period)


def parse_period() -> str:
    period = (request.args.get("period") or "all").strip().lower()
    if period not in PERIODS:
        raise ApiError(u"неизвестный период: «%s» (доступно: %s)" % (period, ", ".join(PERIODS)))
    return period


@app.errorhandler(ApiError)
def handle_api_error(exc):
    return jsonify({"error": exc.message}), exc.code


@app.errorhandler(SourceError)
def handle_source_error(exc):
    return jsonify({"error": str(exc)}), 503


@app.errorhandler(404)
def handle_404(exc):
    if request.path.startswith("/api/"):
        return jsonify({"error": u"нет такого метода API: %s" % request.path}), 404
    return jsonify({"error": u"не найдено: %s" % request.path}), 404


@app.errorhandler(Exception)
def handle_unexpected(exc):
    # ApiError/SourceError перехватываются своими обработчиками выше
    traceback.print_exc()
    if request.path.startswith("/api/"):
        return jsonify({"error": u"внутренняя ошибка сервера: %s" % exc.__class__.__name__}), 500
    return jsonify({"error": u"внутренняя ошибка сервера"}), 500


# --------------------------------------------------------------------------- #
# статика
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.route("/api/meta")
def api_meta():
    d = data("all")
    meta = d["meta"]
    norms = db.get_norms()
    defs = []
    for m in d.get("metric_defs", []):
        norm = norms.get(m.get("key"), {})
        defs.append({
            "key": m.get("key"),
            "name": m.get("name"),
            "unit": norm.get("unit") or m.get("unit", ""),
            "good_is_higher": norm.get("good_is_higher", bool(m.get("good_is_higher"))),
            "norm": norm.get("value", m.get("norm")),
        })
    return jsonify({
        "company": meta.get("company"),
        "currency": meta.get("currency"),
        "vat_rate": meta.get("vat_rate"),
        "months": meta.get("months"),
        "partial_last_month": meta.get("partial_last_month"),
        "periods": [{"value": p, "label": _period_label(p)} for p in PERIODS],
        "metrics": defs,
        "data_source": meta.get("data_source"),
        "sources": available_sources(),
        "dataset_updated_at": meta.get("dataset_updated_at"),
        "app": APP_NAME,
    })


@app.route("/api/overview")
def api_overview():
    period = parse_period()
    d = data(period)
    dds = d["dds"]
    meta = d["meta"]
    return jsonify({
        "period": period,
        "period_label": meta.get("period_label"),
        "is_partial": meta.get("is_partial"),
        "partial_last_month": meta.get("partial_last_month"),
        "vat_rate": meta.get("vat_rate"),
        "currency": meta.get("currency"),
        "months": dds.get("months"),
        "income": dds.get("income"),
        "expense": dds.get("expense"),
        "income_total": dds.get("income_total"),
        "expense_total": dds.get("expense_total"),
        "cash_result": dds.get("cash_result"),
        "balance": dds.get("balance"),
        "expense_by_article": dds.get("expense_by_article"),
        "expense_by_article_total": dds.get("expense_by_article_total"),
        "expense_full_total": dds.get("expense_full_total"),
        "operations": dds.get("operations"),
    })


@app.route("/api/marketing")
def api_marketing():
    period = parse_period()
    d = data(period)
    mkt = d["marketing"]
    meta = d["meta"]
    return jsonify({
        "period": period,
        "period_label": meta.get("period_label"),
        "is_partial": meta.get("is_partial"),
        "partial_last_month": meta.get("partial_last_month"),
        "vat_rate": meta.get("vat_rate"),
        "months": mkt.get("months"),
        "plan": mkt.get("plan"),
        "fact": mkt.get("fact"),
        "plan_total": mkt.get("plan_total"),
        "fact_total": mkt.get("fact_total"),
        "osvoenie_pct": mkt.get("osvoenie_pct"),
        "deviation_pct": mkt.get("deviation_pct"),
        "channels": mkt.get("channels"),
    })


@app.route("/api/sales")
def api_sales():
    # период к CRM-данным в датасете не применяется (нет разбивки сделок по месяцам)
    d = data("all")
    sales = d["sales"]
    meta = d["meta"]
    return jsonify({
        "period": "all",
        "basis": sales.get("basis", "full"),
        "currency": meta.get("currency"),
        "vat_rate": meta.get("vat_rate"),
        "funnel": sales.get("funnel"),
        "directions": sales.get("directions"),
        "leads": sales.get("leads"),
        "paid_deals": sales.get("paid_deals"),
        "revenue_total": sales.get("revenue_total"),
        "deals_total": sales.get("deals_total"),
        "avg_check": sales.get("avg_check"),
        "conversion_pct": sales.get("conversion_pct"),
    })


def build_metrics(period: str, d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """4 метрики: значение, норматив из SQLite, отклонение, формула, база расчёта."""
    basis = d["basis"]
    per, full = basis["period"], basis["full"]
    norms = db.get_norms()
    # (ключ, числитель, знаменатель, база: period — пересчёт от периода, full — янв–сен)
    calc = [
        ("roas", per["income_net"], per["budget_fact_net"], "period"),
        ("cac", full["budget_fact_net"], basis["paid_deals"], "full"),
        ("gp_per_lead", full["gross_profit"], basis["leads"], "full"),
        ("cash_conv", per["income_net"], per["revenue_accrued_net"], "period"),
    ]
    defs = {m.get("key"): m for m in d.get("metric_defs", [])}

    out = []
    for key, num, den, base in calc:
        meta = defs.get(key, {})
        norm = norms.get(key, {})
        value = num / den if den else 0.0
        norm_value = norm.get("value")
        if norm_value is None:
            norm_value = meta.get("norm", 0.0)
        unit = norm.get("unit") or meta.get("unit", "")
        value = _round_by_unit(value, unit)
        norm_value = _round_by_unit(float(norm_value), unit)
        dev = _deviation(value, norm_value)
        good_is_higher = bool(norm.get("good_is_higher", meta.get("good_is_higher", True)))
        out.append({
            "key": key,
            "name": meta.get("name", key),
            "formula": meta.get("formula", ""),
            "value": value,
            "norm": norm_value,
            "unit": unit,
            "good_is_higher": good_is_higher,
            "basis": base,
            "deviation_pct": dev,
            "is_ok": dev >= 0 if good_is_higher else dev <= 0,
        })
    return out


@app.route("/api/metrics")
def api_metrics():
    period = parse_period()
    d = data(period)
    meta = d["meta"]
    return jsonify({
        "period": period,
        "period_label": meta.get("period_label"),
        "is_partial": meta.get("is_partial"),
        "vat_rate": meta.get("vat_rate"),
        "currency": meta.get("currency"),
        "metrics": build_metrics(period, d),
        "note": (u"CAC и валовая прибыль на лида считаются за весь период датасета "
                 u"(в данных нет разбивки сделок по месяцам), ROAS и Cash Conversion — "
                 u"за выбранный период. Нормативы задаются в Настройках."),
    })


@app.route("/api/settings", methods=["GET", "PUT"])
def api_settings():
    if request.method == "GET":
        return jsonify(_settings_payload())

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(u"ожидается JSON-объект с ключами settings и/или norms")

    settings_in = payload.get("settings") or {}
    norms_in = payload.get("norms") or {}
    if not isinstance(settings_in, dict) or not isinstance(norms_in, dict):
        raise ApiError(u"settings и norms должны быть объектами")

    unknown = [k for k in settings_in if k not in db.SETTING_KEYS]
    if unknown:
        raise ApiError(u"неизвестные настройки: %s" % ", ".join(sorted(unknown)))

    known_metrics = {m.get("key") for m in data("all").get("metric_defs", [])}
    norms = {}
    for key, value in norms_in.items():
        if key not in known_metrics:
            raise ApiError(u"неизвестный норматив: %s" % key)
        try:
            num = float(str(value).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            raise ApiError(u"норматив «%s» должен быть числом" % key)
        if num < 0:
            raise ApiError(u"норматив «%s» не может быть отрицательным" % key)
        norms[key] = num

    if settings_in:
        db.save_settings(settings_in)
    if norms:
        db.save_norms(norms)

    body = _settings_payload()
    body["saved"] = True
    body["saved_at"] = db.now()
    body["changed"] = {"settings": sorted(settings_in.keys()), "norms": sorted(norms.keys())}
    return jsonify(body)


def _settings_payload() -> Dict[str, Any]:
    return {
        "settings": db.public_settings(),
        "norms": db.get_norms(),
        "data_source": get_active_source().name,
        "sources": available_sources(),
        "updated_at": max([v.get("updated_at", "") for v in db.get_settings().values()] or [""]),
    }


# --------------------------------------------------------------------------- #
# утилиты
# --------------------------------------------------------------------------- #
def _period_label(period: str) -> str:
    return PERIOD_LABELS.get(period, period)


def _round_half_up(value: float, digits: int = 1) -> float:
    """Округление как в JS Math.round — чтобы API и интерфейс не расходились."""
    mult = 10 ** digits
    return math.floor(value * mult + 0.5) / mult


def _round_by_unit(value: float, unit: str) -> float:
    if unit == u"×":
        return round(value, 2)
    if unit == u"%":
        return round(value, 3)
    return round(value)


def _deviation(value: float, norm: float) -> float:
    if not norm:
        return 0.0
    return _round_half_up((value / norm - 1) * 100)


def init_app() -> str:
    """Создаёт БД, засеивает нормативы, пишет в журнал импортов факт загрузки."""
    path = db.init_db()
    src = get_active_source()
    try:
        rows = src.rows_count()
        db.log_import(src.name, rows, "ok", os.path.basename(getattr(src, "data_file", "mock")))
        print(u"[db] %s · источник: %s · строк: %s" % (path, src.name, rows))
    except SourceError as exc:
        db.log_import(src.name, 0, "error", str(exc))
        print(u"[db] источник недоступен: %s" % exc)
    return path


def main() -> None:
    init_app()
    port = int(os.environ.get("PORT") or 5000)
    debug = (os.environ.get("FLASK_DEBUG") or "1") not in ("0", "false", "False", "")
    print(u"%s -> http://127.0.0.1:%d" % (APP_NAME, port))
    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    main()
