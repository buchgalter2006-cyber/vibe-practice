"""Реестр источников данных: интерфейс + выбор активного источника из .env.

Сейчас работает только mock (data/mock_data.json). Реальные источники — Ф4:
их классы-заглушки лежат ниже и намеренно бросают NotImplementedError, чтобы
подключение не «просочилось» в каркас случайно.
"""
import os
from typing import Any, Dict, List, Optional

# Индексы месяцев датасета в периодах переключателя (см. PLAN.md §5)
PERIOD_INDEXES = {
    "all": [0, 1, 2, 3, 4, 5, 6, 7, 8],
    "q3": [6, 7, 8],
    "sep": [8],
}
PERIODS = ("all", "q3", "sep")

PERIOD_LABELS = {
    "all": u"Янв – Сен 2026",
    "q3": u"Q3 2026",
    "sep": u"Сентябрь 2026",
}


class SourceError(Exception):
    """Ошибка источника данных (наружу отдаём как 500/400 с понятным текстом)."""


class DataSource:
    """Интерфейс, который реализуют все источники (Ф4 подключит реальные)."""

    name = "base"
    title = u"абстрактный источник"

    def rows_count(self) -> int:
        return 0

    def fetch(self, period: str) -> Dict[str, Any]:
        # -> dict с ключами meta, dds, marketing, sales, basis
        raise NotImplementedError


class GoogleSheetsSource(DataSource):
    """План маркетинга из Google-таблицы."""
    name = "google_sheets"
    title = u"Google Sheets"

    def fetch(self, period: str) -> Dict[str, Any]:
        # TODO Ф4: gviz/Sheets API по GOOGLE_SHEET_URL + сервисный аккаунт
        raise NotImplementedError("google_sheets: подключение в Ф4")


class ExcelFileSource(DataSource):
    """Факт маркетинга из Excel-ведомости — реализован, см. excel_source.py."""
    name = "excel_file"
    title = u"Excel-файл (факт маркетинга)"

    def fetch(self, period: str) -> Dict[str, Any]:
        from .excel_source import ExcelSource  # локальный импорт: нет цикла
        return ExcelSource().fetch(period)


class FintabloApiSource(DataSource):
    """ДДС/остатки из FinTablo API."""
    name = "fintablo_api"
    title = u"FinTablo API"

    def fetch(self, period: str) -> Dict[str, Any]:
        # TODO Ф4: REST-выгрузка по FINTABLO_TOKEN (токен не логировать)
        raise NotImplementedError("fintablo_api: подключение в Ф4")


class BitrixWebhookSource(DataSource):
    """Воронка и сделки из Битрикс24 (вебхук)."""
    name = "bitrix_webhook"
    title = u"Битрикс24 (вебхук)"

    def fetch(self, period: str) -> Dict[str, Any]:
        # TODO Ф4: crm.deal.list по BITRIX_WEBHOOK_URL
        raise NotImplementedError("bitrix_webhook: подключение в Ф4")


def get_source(name: Optional[str] = None) -> DataSource:
    """Активный источник: аргумент или DATA_SOURCE из .env (по умолчанию mock)."""
    key = (name or os.environ.get("DATA_SOURCE") or "mock").strip().lower()
    if key == "mock":
        from .mock_source import MockSource  # локальный импорт: нет циклической зависимости
        return MockSource()
    if key == "excel_file":
        from .excel_source import ExcelSource
        return ExcelSource()
    stubs = {
        "google_sheets": GoogleSheetsSource,
        "fintablo_api": FintabloApiSource,
        "bitrix_webhook": BitrixWebhookSource,
    }
    if key in stubs:
        return stubs[key]()
    raise SourceError(u"неизвестный DATA_SOURCE: %s (доступно: mock, excel_file)" % key)


def available_sources() -> List[Dict[str, Any]]:
    """Список источников для интерфейса: что уже работает, а что — Ф4."""
    return [
        {"name": "mock", "title": u"Тестовый датасет (mock)", "ready": True},
        {"name": "excel_file", "title": u"Excel-файл (факт маркетинга)", "ready": True},
        {"name": "google_sheets", "title": u"Google Sheets", "ready": False},
        {"name": "fintablo_api", "title": u"FinTablo API", "ready": False},
        {"name": "bitrix_webhook", "title": u"Битрикс24 (вебхук)", "ready": False},
    ]
