"""Точка входа для Vercel (serverless).

Vercel импортирует `app` из этого файла. До импорта настраивает окружение:
файловая система read-only, кроме /tmp, поэтому БД и загруженные ведомости
живут в /tmp (создаются при холодном старте из репозиторных копий).
Важно: между холодными стартами /tmp не сохраняется — для демо с тестовыми
данными это ок, для боевого режима нужен постоянный диск (Amvera) или
внешняя БД.
"""
import os
import shutil


def _serverless_fs() -> bool:
    """True, если файловая система проекта read-only (serverless-платформы).

    Проверяем несколько маркеров платформ и саму возможность записи:
    у части рантаймов переменная VERCEL в функцию не доходит, зато
    «нельзя писать в папку проекта» — объективный признак.
    """
    if (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")
            or os.environ.get("VERCEL_REGION") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")):
        return True
    return not os.access(os.path.dirname(os.path.abspath(__file__)), os.W_OK)


if _serverless_fs():
    # БД: создавать в /tmp при каждом холодном старте
    os.environ["APP_DB"] = "/tmp/app.db"
    # Источник по умолчанию: Excel из репозитория (стаб FinTablo/Битрикс на
    # serverless недоступен; для плана из Sheets задать GSPREAD_KEY_JSON и
    # DATA_SOURCE=google_sheets в настройках проекта Vercel)
    os.environ.setdefault("DATA_SOURCE", "excel_file")
    # Ведомость факта: копия из репозитория как стартовое состояние
    if not os.environ.get("EXCEL_PATH"):
        repo_xlsx = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data", "fact_marketing.xlsx")
        tmp_xlsx = "/tmp/fact_marketing.xlsx"
        if not os.path.exists(tmp_xlsx) and os.path.exists(repo_xlsx):
            shutil.copyfile(repo_xlsx, tmp_xlsx)
        os.environ["EXCEL_PATH"] = tmp_xlsx
    print("[vercel] serverless-режим: APP_DB=%s EXCEL_PATH=%s DATA_SOURCE=%s"
          % (os.environ["APP_DB"], os.environ["EXCEL_PATH"], os.environ["DATA_SOURCE"]))

import sys  # noqa: E402

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_PROJECT, os.path.join(_PROJECT, "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.server import app, init_app  # noqa: E402

init_app()  # один раз на холодный старт: БД, схема, засев нормативов и админа
