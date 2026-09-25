"""Источник google_sheets: план маркетинга из Google-таблицы (Ф4, срез 2).

Цепочка источников «как у клиента»: план — из Google-таблицы (читаем через
сервисный аккаунт, ключ ~/.gcp/cfo-sheets-bot.json), факт — из Excel-ведомости
(наследуется от ExcelSource), остальное — из тестового датасета.

Таблица: GOOGLE_SHEET_ID (или URL — ID вырезается), лист GOOGLE_SHEET_NAME.
Раскладка листа: строка 1 — заголовок, строка 2 — шапка (Канал, месяцы),
далее строки каналов. Данные кэшируются на 5 секунд — правки в таблице
подхватываются без перезапуска сервера.
"""
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .excel_source import ExcelSource
from .sources import SourceError

DEFAULT_SHEET_NAME = u"Лист1"
PLAN_CACHE_TTL = 5.0  # сек


def _sheet_id(raw: str) -> str:
    """ID таблицы из GOOGLE_SHEET_ID или из полного URL."""
    raw = (raw or "").strip()
    if not raw:
        raise SourceError(u"не задан GOOGLE_SHEET_ID (или URL таблицы) в .env")
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", raw)
    return m.group(1) if m else raw


def _money(value: Any) -> int:
    try:
        s = str(value).strip().replace(" ", "").replace(u"\xa0", "").replace(",", ".")
        return int(round(float(s)))
    except (TypeError, ValueError):
        raise SourceError(u"в таблице не число: %r" % (value,))


class GoogleSheetsSource(ExcelSource):
    """План — из Google-таблицы; факт — из Excel; остальное — датасет."""

    name = "google_sheets"
    title = u"Google Sheets (план маркетинга)"

    def __init__(self, data_file=None, xlsx_file=None, sheet_id=None) -> None:
        ExcelSource.__init__(self, data_file, xlsx_file)
        self.sheet_id = _sheet_id(sheet_id or os.environ.get("GOOGLE_SHEET_ID", ""))
        self.sheet_name = (os.environ.get("GOOGLE_SHEET_NAME") or DEFAULT_SHEET_NAME).strip()
        self._plan_cache = None  # type: Optional[Tuple[Dict[str, List[int]], List[str]]]
        self._plan_ts = 0.0

    # ------------------------------------------------------------- таблица --
    def _plan_by_channel(self) -> Tuple[Dict[str, List[int]], List[str]]:
        """Чтение листа: ({канал: [план по месяцам]}, [месяцы]). Кэш 5 c."""
        if self._plan_cache is None or time.time() - self._plan_ts > PLAN_CACHE_TTL:
            try:
                import gspread
                gc = gspread.service_account(
                    filename=os.path.expanduser(
                        os.environ.get("GSPREAD_KEYFILE", "~/.gcp/cfo-sheets-bot.json")))
                sh = gc.open_by_key(self.sheet_id)
                ws = sh.worksheet(self.sheet_name) if self.sheet_name else sh.sheet1
                rows = ws.get_all_values()
            except SourceError:
                raise
            except Exception as exc:
                # не логируем содержимое исключения — может попасть имя файла ключа
                raise SourceError(u"не удалось прочитать Google-таблицу: %s"
                                  % exc.__class__.__name__)
            if len(rows) < 2:
                raise SourceError(u"таблица пуста (нет шапки)")
            header = [c.strip() for c in rows[1]]
            months = header[1:]
            if not months:
                raise SourceError(u"в шапке таблицы нет месяцев")
            plan = {}
            for row in rows[2:]:
                if not row or not (row[0] or "").strip():
                    continue
                channel = row[0].strip()
                values = list(row[1:len(months) + 1])
                if len(values) < len(months):
                    values += [""] * (len(months) - len(values))
                plan[channel] = [_money(v) if str(v).strip() else 0 for v in values]
            if not plan:
                raise SourceError(u"в таблице нет строк с каналами")
            self._plan_cache = (plan, months)
            self._plan_ts = time.time()
        return self._plan_cache

    # ------------------------------------------------------------------ API --
    def _merged_dataset(self):
        """План из таблицы + факт из Excel (родитель) + остальное из датасета."""
        merged = ExcelSource._merged_dataset(self)
        plan, months_sheet = self._plan_by_channel()
        channels = merged["marketing"]["channels"]
        names = [ch.get("channel", "") for ch in channels]

        unknown = sorted(set(plan) - set(names))
        missing = [n for n in names if n not in plan]
        problems = []
        if unknown:
            problems.append(u"нет в каркасе: %s" % u", ".join(unknown))
        if missing:
            problems.append(u"нет в таблице: %s" % u", ".join(missing))
        if problems:
            raise SourceError(u"таблица не сходится с планом (%s)" % u"; ".join(problems))
        if months_sheet and list(months_sheet) != list(merged.get("months", [])):
            raise SourceError(u"месяцы таблицы (%s) не совпадают с датасетом (%s)"
                              % (u", ".join(months_sheet), u", ".join(merged.get("months", []))))

        merged_channels = []
        for ch in channels:
            ch_copy = dict(ch)
            ch_copy["plan"] = list(plan[ch.get("channel", "")])
            merged_channels.append(ch_copy)
        merged["marketing"] = {"channels": merged_channels,
                               "plan_source": {"kind": "google_sheets",
                                               "sheet_id": self.sheet_id,
                                               "sheet": self.sheet_name}}
        return merged

    def rows_count(self) -> int:
        plan, _ = self._plan_by_channel()
        return ExcelSource.rows_count(self) + len(plan)
