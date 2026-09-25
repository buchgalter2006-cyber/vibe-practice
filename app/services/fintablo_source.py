"""Источник fintablo_api: ДДС из сервиса учёта (Ф4, срез 3).

Общается с API FinTablo (сейчас — локальный стаб stub/stub_server.py,
при переходе на реальный сервис меняются только FINTABLO_URL и FINTABLO_TOKEN).

Что берёт из API:
  /v1/operations  — все операции за период, агрегирует по месяцам
                    (поступления/списания), по статьям (структура расходов)
                    и отдаёт последние операции для таблицы;
  /v1/balance     — остаток на счёте.

План/факт маркетинга (Sheets/Excel) и CRM наследуются по цепочке источников.
Ошибка токена/сети — SourceError с понятным текстом, без содержимого ключей.
"""
import json
import os
import time
import urllib.request
from collections import defaultdict
from typing import Any, Dict, List

from .google_source import GoogleSheetsSource
from .sources import SourceError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_MONTHS = [u"Янв", u"Фев", u"Мар", u"Апр", u"Май", u"Июн", u"Июл", u"Авг", u"Сен"]
LAST_OPS_SHOWN = 12


def _get_json(url: str, token: str) -> Dict[str, Any]:
    """GET c Bearer-токеном; ошибки — SourceError без утечки секрета."""
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % token,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SourceError(u"FinTablo: не принят токен (401) — проверь FINTABLO_TOKEN")
        raise SourceError(u"FinTablo: HTTP %s от %s" % (exc.code, url.split("/v1")[0]))
    except urllib.error.URLError as exc:
        raise SourceError(u"FinTablo: сервис недоступен (%s)" % exc.reason)


class FintabloSource(GoogleSheetsSource):
    """ДДС — из FinTablo API; план (Sheets), факт (Excel) — по цепочке."""

    name = "fintablo_api"
    title = u"FinTablo API (ДДС)"

    def __init__(self, data_file=None, xlsx_file=None, sheet_id=None) -> None:
        GoogleSheetsSource.__init__(self, data_file, xlsx_file, sheet_id)
        self.api_url = (os.environ.get("FINTABLO_URL") or "http://127.0.0.1:5001").rstrip("/")
        self.api_token = os.environ.get("FINTABLO_TOKEN") or ""
        if not self.api_token:
            raise SourceError(u"не задан FINTABLO_TOKEN в .env")
        self._dds_cache = None  # type: Dict[str, Any] | None
        self._dds_ts = 0.0

    # ------------------------------------------------------------------ API --
    def _dds_data(self) -> Dict[str, Any]:
        """Операции + баланс из API. Кэш 5 c (в стабе данные перечитываются по mtime)."""
        if not self._dds_cache or time.time() - self._dds_ts > 5.0:
            ops = _get_json(self.api_url + "/v1/operations", self.api_token).get("items", [])
            bal = _get_json(self.api_url + "/v1/balance", self.api_token).get("balance", 0)
            if not ops:
                raise SourceError(u"FinTablo: пустой список операций")
            self._dds_cache = {"operations": ops, "balance": bal}
            self._dds_ts = time.time()
        return self._dds_cache

    def _merged_dataset(self):
        merged = GoogleSheetsSource._merged_dataset(self)
        dds = self._dds_data()
        ops = sorted(dds["operations"], key=lambda o: o["date"], reverse=True)

        months = list(merged.get("months", [])) or DEFAULT_MONTHS
        pref_by_idx = ["2026-%02d" % (i + 1) for i in range(len(months))]
        income = defaultdict(int)
        expense = defaultdict(int)
        by_article = defaultdict(int)
        for o in ops:
            for i, pref in enumerate(pref_by_idx):
                if o["date"].startswith(pref):
                    if o["type"] == "income":
                        income[i] += o["amount"]
                    else:
                        expense[i] += o["amount"]
                        by_article[o["article"]] += o["amount"]
                    break
        missing = [months[i] for i in range(len(months)) if i not in income and i not in expense]
        if missing:
            raise SourceError(u"FinTablo: нет операций за %s" % u", ".join(missing))

        articles = [{"article": a, "amount": v}
                    for a, v in sorted(by_article.items(), key=lambda kv: -kv[1])]

        merged["dds"] = {
            "income": [income.get(i, 0) for i in range(len(months))],
            "expense": [expense.get(i, 0) for i in range(len(months))],
            "balance": dds["balance"],
            "operations": ops[:LAST_OPS_SHOWN],
            "expense_by_article": articles,
        }
        merged["dds_source"] = {"kind": "fintablo_api", "url": self.api_url}
        return merged

    def rows_count(self) -> int:
        return GoogleSheetsSource.rows_count(self) + len(self._dds_data()["operations"])
