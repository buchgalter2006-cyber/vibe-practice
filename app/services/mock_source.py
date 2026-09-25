"""Рабочий источник данных каркаса: тестовый датасет data/mock_data.json.

Читает файл, фильтрует месячные ряды по периоду (all=0..8, q3=6..8, sep=8)
и отдаёт секции dds / marketing / sales + basis (суммы без НДС для метрик).
Реальные источники (Google Sheets, Excel, FinTablo, Битрикс) — Ф4, см. sources.py.
"""
import json
import math
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .sources import PERIOD_INDEXES, PERIOD_LABELS, PERIODS, DataSource, SourceError

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(APP_DIR))
DEFAULT_DATA = os.path.join("data", "mock_data.json")


def _pick(seq: List[Any], idx: List[int]) -> List[Any]:
    return [seq[i] for i in idx if i < len(seq)]


def _money(value: float) -> int:
    return int(round(value))


class MockSource(DataSource):
    """Тестовый датасет. Ничего внешнего не читает, только локальный JSON."""

    name = "mock"
    title = u"Тестовый датасет (mock)"

    def __init__(self, data_file: Optional[str] = None) -> None:
        raw = data_file or os.environ.get("MOCK_DATA") or DEFAULT_DATA
        self.data_file = raw if os.path.isabs(raw) else os.path.join(BASE_DIR, raw)
        self._cache = None  # type: Optional[Dict[str, Any]]
        self._cache_key = None  # type: Optional[Any]

    # ---------------------------------------------------------------- данные --
    def _dataset(self) -> Dict[str, Any]:
        """Чтение датасета с кэшем по mtime (правка файла подхватывается)."""
        try:
            key = os.path.getmtime(self.data_file)
        except OSError:
            raise SourceError(u"датасет не найден: %s" % self.data_file)
        if self._cache is None or self._cache_key != key:
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except ValueError as exc:
                raise SourceError(u"датасет повреждён (%s): %s" % (self.data_file, exc))
            self._cache_key = key
        return self._cache

    def rows_count(self) -> int:
        d = self._dataset()
        rows = len(d.get("months", [])) + len(d.get("dds", {}).get("income", []))
        rows += len(d.get("operations", [])) + len(d.get("funnel", [])) + len(d.get("directions", []))
        for ch in d.get("marketing", {}).get("channels", []):
            rows += len(ch.get("plan", [])) + len(ch.get("fact", []))
        return rows

    # ------------------------------------------------------------------ API --
    def fetch(self, period: str) -> Dict[str, Any]:
        if period not in PERIODS:
            raise SourceError(u"неизвестный период: %s (доступно: %s)" % (period, ", ".join(PERIODS)))
        d = self._dataset()
        idx = PERIOD_INDEXES[period]
        months = d.get("months", [])
        labels = _pick(months, idx)

        marketing_plan_total = sum(sum(ch["plan"]) for ch in d["marketing"]["channels"])
        marketing_fact_total = sum(sum(ch["fact"]) for ch in d["marketing"]["channels"])

        return {
            "meta": self._meta(d, period, labels),
            "dds": self._dds(d, idx, labels),
            "marketing": self._marketing(d, idx, labels),
            "sales": self._sales(d),
            "basis": self._basis(d, idx, marketing_plan_total, marketing_fact_total),
            # определения метрик (название, формула, единица) — нормативы берутся из SQLite
            "metric_defs": d.get("metrics", []),
        }

    # --------------------------------------------------------------- секции --
    def _meta(self, d: Dict[str, Any], period: str, labels: List[str]) -> Dict[str, Any]:
        try:
            updated = datetime.fromtimestamp(os.path.getmtime(self.data_file)).isoformat(timespec="seconds")
        except OSError:
            updated = ""
        return {
            "company": d.get("company", ""),
            "currency": d.get("currency", u"₽"),
            "vat_rate": d.get("vat_rate", 0.0),
            "months": d.get("months", []),
            "partial_last_month": d.get("partial_last_month", {}),
            "period": period,
            "period_label": PERIOD_LABELS.get(period, period),
            "period_months": labels,
            # «сен — неполный месяц» показываем, только если период его задевает
            "is_partial": 8 in PERIOD_INDEXES[period],
            "data_source": self.name,
            "dataset_updated_at": updated,
        }

    def _dds(self, d: Dict[str, Any], idx: List[int], labels: List[str]) -> Dict[str, Any]:
        dds = d.get("dds", {})
        income = _pick(dds.get("income", []), idx)
        expense = _pick(dds.get("expense", []), idx)
        full_expense = sum(dds.get("expense", []))
        articles = d.get("expense_by_article", [])
        s_inc, s_exp = sum(income), sum(expense)
        return {
            "months": labels,
            "income": income,
            "expense": expense,
            "income_total": _money(s_inc),
            "expense_total": _money(s_exp),
            "cash_result": _money(s_inc - s_exp),
            "balance": _money(dds.get("balance", 0)),
            # структура расходов — за весь датасет (янв–сен), как в макете
            "expense_by_article": articles,
            "expense_by_article_total": _money(sum(a.get("amount", 0) for a in articles)),
            "expense_full_total": _money(full_expense),
            "operations": d.get("operations", []),
        }

    def _marketing(self, d: Dict[str, Any], idx: List[int], labels: List[str]) -> Dict[str, Any]:
        channels = d.get("marketing", {}).get("channels", [])
        out_channels = []
        for ch in channels:
            plan = _pick(ch.get("plan", []), idx)
            fact = _pick(ch.get("fact", []), idx)
            s_plan, s_fact = sum(plan), sum(fact)
            out_channels.append({
                "channel": ch.get("channel", ""),
                "plan": plan,
                "fact": fact,
                "plan_total": _money(s_plan),
                "fact_total": _money(s_fact),
                "osvoenie_pct": _rate(s_fact, s_plan),
                "deviation_pct": _deviation(s_fact, s_plan),
            })
        plan = [sum(ch["plan"][i] for ch in channels) for i in idx]
        fact = [sum(ch["fact"][i] for ch in channels) for i in idx]
        s_plan, s_fact = sum(plan), sum(fact)
        return {
            "months": labels,
            "plan": plan,
            "fact": fact,
            "plan_total": _money(s_plan),
            "fact_total": _money(s_fact),
            "osvoenie_pct": _rate(s_fact, s_plan),
            "deviation_pct": _deviation(s_fact, s_plan),
            "channels": out_channels,
        }

    def _sales(self, d: Dict[str, Any]) -> Dict[str, Any]:
        funnel = d.get("funnel", [])
        directions = d.get("directions", [])
        leads = funnel[0]["count"] if funnel else 0
        paid = funnel[-1]["count"] if funnel else 0
        revenue = sum(x.get("revenue", 0) for x in directions)
        deals = sum(x.get("deals", 0) for x in directions)
        return {
            "funnel": funnel,
            "directions": directions,
            "leads": leads,
            "paid_deals": paid,
            "revenue_total": _money(revenue),
            "deals_total": deals,
            "avg_check": _money(revenue / deals) if deals else 0,
            "conversion_pct": round(paid / leads * 100, 1) if leads else 0.0,
            # в датасете нет разбивки сделок по месяцам — период не применяется
            "basis": "full",
        }

    def _basis(self, d: Dict[str, Any], idx: List[int],
               plan_total: float, fact_total: float) -> Dict[str, Any]:
        """Суммы для метрик: без НДС, по периоду и по всему датасету."""
        vat = 1 + d.get("vat_rate", 0.0)
        income = d.get("dds", {}).get("income", [])
        funnel = d.get("funnel", [])
        totals = d.get("totals", {}) or {}
        metrics = {m.get("key"): m for m in d.get("metrics", [])}
        leads = funnel[0]["count"] if funnel else 0
        paid = funnel[-1]["count"] if funnel else 0

        income_net_full = totals.get("income_net") or sum(income) / vat
        accr_full = totals.get("revenue_accrued_net") or income_net_full / 0.95
        cash_ratio = income_net_full / accr_full if accr_full else 0.95

        gp = metrics.get("gp_per_lead", {})
        gp_margin = (gp.get("value", 0) * leads / income_net_full) if income_net_full else 0.0

        def pack(income_sum: float, plan_sum: float, fact_sum: float) -> Dict[str, Any]:
            """Суммы «без НДС» для метрик за один и тот же отрезок времени."""
            income_net = income_sum / vat
            return {
                "income_net": income_net,
                "budget_plan_net": plan_sum / vat,
                "budget_fact_net": fact_sum / vat,
                "revenue_accrued_net": income_net / cash_ratio if cash_ratio else 0.0,
                "gross_profit": income_net * gp_margin,
            }

        def channel_sum(month_idx: List[int], field: str) -> float:
            """Сумма плана/факта по всем каналам за выбранные месяцы."""
            return sum(sum(_pick(ch.get(field, []), month_idx))
                       for ch in d["marketing"]["channels"])

        return {
            "vat_rate": d.get("vat_rate", 0.0),
            "leads": leads,
            "paid_deals": paid,
            "cash_ratio": cash_ratio,
            "gp_margin": gp_margin,
            # период: ROAS и Cash Conversion; полный набор — для CAC и валовой прибыли
            "period": pack(sum(_pick(income, idx)), channel_sum(idx, "plan"), channel_sum(idx, "fact")),
            "full": pack(sum(income), plan_total, fact_total),
        }


def _round_half_up(value: float, digits: int = 1) -> float:
    """Округление как в JS Math.round — чтобы API и интерфейс не расходились."""
    mult = 10 ** digits
    return math.floor(value * mult + 0.5) / mult


def _rate(fact: float, plan: float) -> float:
    return _round_half_up(fact / plan * 100) if plan else 0.0


def _deviation(fact: float, plan: float) -> float:
    return _round_half_up((fact / plan - 1) * 100) if plan else 0.0
