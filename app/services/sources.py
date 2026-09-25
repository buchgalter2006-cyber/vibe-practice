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



class ExcelFileSource(DataSource):
    """Факт маркетинга из Excel-ведомости — реализован, см. excel_source.py."""
    name = "excel_file"
    title = u"Excel-файл (факт маркетинга)"

    def fetch(self, period: str) -> Dict[str, Any]:
        from .excel_source import ExcelSource  # локальный импорт: нет цикла
        return ExcelSource().fetch(period)




def get_source(name: Optional[str] = None) -> DataSource:
    """Активный источник: аргумент или DATA_SOURCE из .env (по умолчанию mock)."""
    key = (name or os.environ.get("DATA_SOURCE") or "mock").strip().lower()
    if key == "mock":
        from .mock_source import MockSource  # локальный импорт: нет циклической зависимости
        return MockSource()
    if key == "excel_file":
        from .excel_source import ExcelSource
        return ExcelSource()
    if key == "google_sheets":
        from .google_source import GoogleSheetsSource
        return GoogleSheetsSource()
    if key == "fintablo_api":
        from .fintablo_source import FintabloSource
        return FintabloSource()
    if key == "bitrix_webhook":
        from .bitrix_source import BitrixSource
        return BitrixSource()
    raise SourceError(u"неизвестный DATA_SOURCE: %s (доступно: mock, excel_file, google_sheets, fintablo_api, bitrix_webhook)" % key)


def available_sources() -> List[Dict[str, Any]]:
    """Список источников для интерфейса: что уже работает, а что — Ф4."""
    return [
        {"name": "mock", "title": u"Тестовый датасет (mock)", "ready": True},
        {"name": "excel_file", "title": u"Excel-файл (факт маркетинга)", "ready": True},
        {"name": "google_sheets", "title": u"Google Sheets (план маркетинга)", "ready": True},
        {"name": "fintablo_api", "title": u"FinTablo API (ДДС)", "ready": True},
        {"name": "bitrix_webhook", "title": u"Битрикс24 (воронка и сделки)", "ready": True},
    ]
