"""Источник bitrix_webhook: воронка и сделки из CRM (Ф4, срез 4).

Общается с Битрикс24 через входящий вебхук (сейчас — локальный стаб,
при переходе на реальный сервис меняется только BITRIX_WEBHOOK_URL).

Что берёт из CRM (POST crm.deal.list.json):
  воронка   — счёт по стадиям сделок: Лиды = все, далее накопительно
              QUALIFIED / PROPOSAL / WON;
  выручка   — сумма OPPORTUNITY по стадиям WON, разрез по направлениям;
  средний чек, конверсия — считаются в MockSource._sales как раньше.

ДДС (FinTablo), план (Sheets) и факт (Excel) наследуются по цепочке.
"""
import json
import os
import urllib.request
from typing import Any, Dict, List

from .fintablo_source import FintabloSource
from .sources import SourceError

STAGE_ORDER = ["NEW", "QUALIFIED", "PROPOSAL", "WON"]
STAGE_LABELS = {"NEW": u"Лиды", "QUALIFIED": u"Квалифицированные",
                "PROPOSAL": u"КП отправлено", "WON": u"Оплачено"}
STAGE_INDEX = {s: i for i, s in enumerate(STAGE_ORDER)}
CACHE_TTL = 5.0


def _post_json(url: str) -> Dict[str, Any]:
    """POST вебхука; ошибки — SourceError (URL содержит секрет, не логируем его)."""
    data = json.dumps({"start": -1}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise SourceError(u"Битрикс24: вебхук отклонён (403) — проверь секрет в URL")
        if exc.code == 404:
            raise SourceError(u"Битрикс24: метод не найден (404)")
        raise SourceError(u"Битрикс24: HTTP %s" % exc.code)
    except urllib.error.URLError as exc:
        raise SourceError(u"Битрикс24: сервис недоступен (%s)" % exc.reason)


class BitrixSource(FintabloSource):
    """Продажи — из Битрикс24; ДДС, план и факт — по цепочке источников."""

    name = "bitrix_webhook"
    title = u"Битрикс24 (воронка и сделки)"

    def __init__(self, data_file=None, xlsx_file=None, sheet_id=None) -> None:
        FintabloSource.__init__(self, data_file, xlsx_file, sheet_id)
        self.webhook_url = (os.environ.get("BITRIX_WEBHOOK_URL") or "").strip()
        if not self.webhook_url:
            raise SourceError(u"не задан BITRIX_WEBHOOK_URL в .env")
        if not self.webhook_url.endswith("crm.deal.list.json"):
            self.webhook_url = self.webhook_url.rstrip("/") + "/crm.deal.list.json"
        self._crm_cache = None  # type: List[Dict[str, Any]] | None
        self._crm_ts = 0.0

    # ------------------------------------------------------------------ CRM --
    def _deals(self) -> List[Dict[str, Any]]:
        import time
        if self._crm_cache is None or time.time() - self._crm_ts > CACHE_TTL:
            body = _post_json(self.webhook_url)
            deals = body.get("result") or []
            if not deals:
                raise SourceError(u"Битрикс24: ни одной сделки в ответе")
            self._crm_cache = deals
            self._crm_ts = time.time()
        return self._crm_cache

    # ------------------------------------------------------------------ API --
    def _merged_dataset(self):
        merged = FintabloSource._merged_dataset(self)
        deals = self._deals()

        counts = {s: 0 for s in STAGE_ORDER}
        revenue_by_dir: Dict[str, int] = {}
        won_by_dir_count: Dict[str, int] = {}
        for x in deals:
            stage = (x.get("STAGE_ID") or "").upper()
            if stage not in STAGE_INDEX:
                continue
            # сделка достигла стадии stage — засчитывается в неё и во все более ранние
            for s in STAGE_ORDER[:STAGE_INDEX[stage] + 1]:
                counts[s] += 1
            if stage == "WON":
                direction = (x.get("CATEGORY") or u"Прочее").strip()
                revenue_by_dir[direction] = revenue_by_dir.get(direction, 0) + int(x.get("OPPORTUNITY") or 0)
                won_by_dir_count[direction] = won_by_dir_count.get(direction, 0) + 1

        funnel = [{"stage": STAGE_LABELS[s], "count": counts[s]}
                  for s in ["NEW", "QUALIFIED", "PROPOSAL", "WON"]]
        directions = []
        for direction, revenue in sorted(revenue_by_dir.items(), key=lambda kv: -kv[1]):
            n = won_by_dir_count.get(direction, 0)
            directions.append({
                "name": direction, "revenue": revenue, "deals": n,
                "avg_check": round(revenue / n) if n else 0,
                # доля 0..1 — формат, который ждёт фронтенд ((conversion*100).toFixed(0))
                "conversion": round(n / counts["NEW"], 3) if counts["NEW"] else 0.0,
            })

        merged["funnel"] = funnel
        merged["directions"] = directions
        merged["crm_source"] = {"kind": "bitrix_webhook", "deals": len(deals)}
        return merged

    def rows_count(self) -> int:
        return FintabloSource.rows_count(self) + len(self._deals())
