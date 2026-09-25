"""SQLite-хранилище каркаса: настройки, нормативы метрик, журнал импортов.

Схема создаётся при старте (init_db). Никаких ORM — прямые запросы sqlite3.
Python 3.9: аннотации только через typing.*
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)

DEFAULT_DB = os.path.join("data", "app.db")
MOCK_DATA = os.path.join("data", "mock_data.json")

# Поля формы «Настройки» (Ф3 подключает их вручную, Ф4 — реально)
SETTING_KEYS = ("google_sheet_url", "excel_path", "fintablo_token", "bitrix_webhook_url")
# Эти значения не отдаём целиком в GET /api/settings (только «задан/••••1234»)
SECRET_KEYS = ("fintablo_token", "bitrix_webhook_url")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS norms (
  metric_key TEXT PRIMARY KEY, norm_value REAL, unit TEXT, good_is_higher INTEGER
);
CREATE TABLE IF NOT EXISTS import_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, started_at TEXT, finished_at TEXT,
  rows_imported INTEGER, status TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL,
  created_at TEXT
);
"""


def _resolve(path: str) -> str:
    """Относительный путь считаем от корня проекта."""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def db_path(path: Optional[str] = None) -> str:
    return _resolve(path or os.environ.get("APP_DB", DEFAULT_DB))


def data_path(path: Optional[str] = None) -> str:
    return _resolve(path or os.environ.get("MOCK_DATA", MOCK_DATA))


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    full = db_path(path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    conn = sqlite3.connect(full)
    conn.row_factory = sqlite3.Row
    return conn


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# схема + засев
# --------------------------------------------------------------------------- #
def load_metrics_seed(data_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """Метрики из тестового датасета — источник нормативов при первом запуске."""
    try:
        with open(data_path(data_file), "r", encoding="utf-8") as f:
            return json.load(f).get("metrics", [])
    except (IOError, ValueError):
        return []


def init_db(path: Optional[str] = None) -> str:
    """Создаёт data/app.db, таблицы и засеивает нормативы/пустые настройки."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)

        have = conn.execute("SELECT COUNT(*) AS c FROM norms").fetchone()["c"]
        if not have:
            for m in load_metrics_seed():
                conn.execute(
                    "INSERT OR REPLACE INTO norms (metric_key, norm_value, unit, good_is_higher)"
                    " VALUES (?, ?, ?, ?)",
                    (m.get("key"), float(m.get("norm", 0)), m.get("unit", ""),
                     1 if m.get("good_is_higher") else 0),
                )

        for key in SETTING_KEYS:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, '', ?)",
                (key, now()),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path(path)


# --------------------------------------------------------------------------- #
# настройки
# --------------------------------------------------------------------------- #
def get_settings(path: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """Сырые значения настроек + дата последнего изменения."""
    conn = connect(path)
    try:
        rows = conn.execute("SELECT key, value, updated_at FROM settings").fetchall()
    finally:
        conn.close()
    out = {}
    for r in rows:
        out[r["key"]] = {"value": r["value"] or "", "updated_at": r["updated_at"] or ""}
    for key in SETTING_KEYS:  # на случай, если строку удалили руками
        out.setdefault(key, {"value": "", "updated_at": ""})
    return out


def mask_secret(value: str) -> Dict[str, Any]:
    """Секрет наружу целиком не отдаём: только факт наличия и последние 4 знака."""
    value = (value or "").strip()
    if not value:
        return {"set": False, "hint": "", "value": None}
    return {"set": True, "hint": u"\u2022\u2022\u2022\u2022" + value[-4:], "value": None}


def public_settings(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Вид настроек для GET /api/settings: секреты маскируются."""
    raw = get_settings(path)
    out = {}
    for key in SETTING_KEYS:
        item = raw.get(key, {"value": "", "updated_at": ""})
        value = item["value"]
        if key in SECRET_KEYS:
            entry = mask_secret(value)
        else:
            entry = {"set": bool(value.strip()), "hint": "", "value": value}
        entry["key"] = key
        entry["secret"] = key in SECRET_KEYS
        entry["updated_at"] = item["updated_at"]
        out[key] = entry
    return out


def save_settings(values: Dict[str, Any], path: Optional[str] = None) -> Dict[str, str]:
    """Сохраняет только переданные ключи. Пустая строка = очистить значение."""
    conn = connect(path)
    try:
        for key, value in values.items():
            if key not in SETTING_KEYS:
                continue
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                " updated_at = excluded.updated_at",
                (key, "" if value is None else str(value).strip(), now()),
            )
        conn.commit()
    finally:
        conn.close()
    return get_settings(path)


# --------------------------------------------------------------------------- #
# нормативы метрик
# --------------------------------------------------------------------------- #
def get_norms(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT metric_key, norm_value, unit, good_is_higher FROM norms ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    return {
        r["metric_key"]: {
            "value": r["norm_value"],
            "unit": r["unit"] or "",
            "good_is_higher": bool(r["good_is_higher"]),
        }
        for r in rows
    }


def save_norms(values: Dict[str, float], path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    conn = connect(path)
    try:
        for key, value in values.items():
            conn.execute("UPDATE norms SET norm_value = ? WHERE metric_key = ?", (float(value), key))
        conn.commit()
    finally:
        conn.close()
    return get_norms(path)


# --------------------------------------------------------------------------- #
# пользователи и роли (Ф5)
# --------------------------------------------------------------------------- #
ROLES = ("admin", "editor", "view")


def count_users(path: Optional[str] = None) -> int:
    conn = connect(path)
    try:
        return int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"])
    finally:
        conn.close()


def count_role(role: str, path: Optional[str] = None) -> int:
    conn = connect(path)
    try:
        return int(conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = ?", (role,)).fetchone()["c"])
    finally:
        conn.close()


def get_user(username: str, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT username, password_hash, role, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_users(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Список пользователей без хэшей — для GET /api/users."""
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY created_at, username"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def insert_user(username: str, password_hash: str, role: str,
                path: Optional[str] = None) -> None:
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, now()),
        )
        conn.commit()
    finally:
        conn.close()


def set_password(username: str, password_hash: str, path: Optional[str] = None) -> None:
    conn = connect(path)
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                     (password_hash, username))
        conn.commit()
    finally:
        conn.close()


def delete_user(username: str, path: Optional[str] = None) -> None:
    conn = connect(path)
    try:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# журнал импортов (задел на Ф4)
# --------------------------------------------------------------------------- #
def log_import(source: str, rows_imported: int, status: str, message: str = "",
               started_at: Optional[str] = None, path: Optional[str] = None) -> None:
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO import_log (source, started_at, finished_at, rows_imported, status, message)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (source, started_at or now(), now(), int(rows_imported), status, message),
        )
        conn.commit()
    finally:
        conn.close()


def recent_imports(limit: int = 10, path: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT source, started_at, finished_at, rows_imported, status, message"
            " FROM import_log ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
