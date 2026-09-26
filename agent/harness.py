"""«Руки» агента: валидация ответа движка по схеме + запись в Google-таблицу.

Таблица: GOOGLE_SHEET_ID (.env), лист «Расходы (агент)» — создаётся сам,
шапка проставляется при первом запуске. Каждая запись — строка листа;
state.json хранит номер последней записи для правок.
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(AGENT_DIR, "state.json")
SHEET_NAME = u"Расходы (агент)"
HEADERS = [u"Дата расхода", u"Сумма", u"Валюта", u"Продавец/описание", u"Статья",
           u"Способ оплаты", u"Тип", u"Кто прислал", u"Статус", u"Комментарий", u"Записано"]


class ValidationError(Exception):
    pass


def validate(result: Dict[str, Any]) -> Dict[str, Any]:
    """Проверка ответа движка по schema.json (без внешних зависимостей)."""
    if not isinstance(result, dict) or "action" not in result:
        raise ValidationError(u"ответ движка не содержит action")
    action = result["action"]
    if action == "expense":
        txs = result.get("transactions")
        if not isinstance(txs, list) or not txs:
            raise ValidationError(u"action=expense без транзакций")
        for i, tx in enumerate(txs, 1):
            if tx.get("article") not in HEADERS[4:5] + [u"ФОТ", u"Реклама", u"Подрядчики",
                                                        u"Аренда и офис", u"ПО и сервисы",
                                                        u"Налоги", u"Прочее"]:
                raise ValidationError(u"транзакция %s: статья вне закрытого списка" % i)
            if tx.get("status") not in (u"готово", u"требует проверки"):
                raise ValidationError(u"транзакция %s: неизвестный статус" % i)
            if tx.get("amount") is None and tx.get("status") != u"требует проверки":
                raise ValidationError(u"транзакция %s: без суммы, но статус «готово»" % i)
    elif action == "correct":
        if not result.get("fields"):
            raise ValidationError(u"action=correct без полей")
    return result


def _client():
    import gspread
    keyfile = os.environ.get("GSPREAD_KEYFILE") or os.path.expanduser(
        os.environ.get("GSPREAD_KEY_JSON", "") and "/tmp/gspread_key.json" or "~/.gcp/cfo-sheets-bot.json")
    raw = os.environ.get("GSPREAD_KEY_JSON")
    if raw and not os.path.exists("/tmp/gspread_key.json"):
        with open("/tmp/gspread_key.json", "w", encoding="utf-8") as f:
            f.write(raw)
    gc = gspread.service_account(filename=keyfile)
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or ""
    return gc.open_by_key(sheet_id)


def ensure_worksheet(sh) -> Any:
    titles = [ws.title for ws in sh.worksheets()]
    if SHEET_NAME not in titles:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=100, cols=len(HEADERS))
    else:
        ws = sh.worksheet(SHEET_NAME)
    if not ws.row_values(1):
        ws.update(values=[HEADERS], range_name="A1")
    return ws


def _state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(st: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def write_expense(result: Dict[str, Any], who: str = u"Дмитрий") -> List[Dict[str, Any]]:
    """Запись транзакций в лист; возвращает записанные строки (для интерфейса)."""
    sh = _client()
    ws = ensure_worksheet(sh)
    written = []
    for tx in result.get("transactions", []):
        row = [tx.get("date") or datetime.now().date().isoformat(),
               tx.get("amount"), tx.get("currency") or u"₽",
               tx.get("vendor") or u"", tx.get("article") or u"Прочее",
               tx.get("payment_method") or u"неизвестно",
               tx.get("type") or u"расход",
               who, tx.get("status") or u"требует проверки",
               tx.get("comment") or u"", datetime.now().isoformat(timespec="seconds")]
        ws.append_row(row, value_input_option="USER_ENTERED")
        written.append({"row": len(ws.col_values(1)), "tx": tx})
    if written:
        st = _state()
        st["last_row"] = written[-1]["row"]
        _save_state(st)
    return written


def apply_correction(result: Dict[str, Any]) -> Dict[str, Any]:
    """Правка последней записи (action=correct)."""
    st = _state()
    last = st.get("last_row")
    if not last:
        raise ValidationError(u"нечего исправлять: агент ещё ничего не записывал")
    sh = _client()
    ws = ensure_worksheet(sh)
    headers = ws.row_values(1)
    col = {name: i + 1 for i, name in enumerate(headers)}
    fields = result.get("fields", {})
    for name, value in fields.items():
        if name in col:
            ws.update_cell(last, col[name], value)
    return {"row": last, "fields": fields}


def recent_rows(limit: int = 10) -> List[List[Any]]:
    sh = _client()
    ws = ensure_worksheet(sh)
    rows = ws.get_all_values()
    return rows[-limit:]
