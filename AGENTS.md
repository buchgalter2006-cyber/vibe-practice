# AGENTS.md — правила проекта «vibe-practice»

## Назначение
Учебный сервис отчётности для маркетинговой группы «Вектор» (практический трек «Вайбкодинг», Ф3).
Flask отдаёт статику и JSON API с данными из тестового датасета; настройки и нормативы — в SQLite.

## Стек
Python 3.9 + Flask + SQLite (`sqlite3`), vanilla JS (без фреймворков и сборки), pip + `.venv`.

## Запуск
```bash
cd ~/Projects/vibe-practice
.venv/bin/python app/server.py        # http://127.0.0.1:5000 (порт из .env PORT)
curl -s http://127.0.0.1:5000/api/meta
```

## Где что лежит
- `app/server.py` — роуты (статика + `/api/*`), `app/db.py` — SQLite (`data/app.db`, создаётся сам)
- `app/services/sources.py` — интерфейс источника + заглушки Ф4; `mock_source.py` — рабочий источник
- `app/static/` — фронтенд: `index.html`, `styles.css`, `app.js` (данные только через `fetch('/api/...')`)
- `data/mock_data.json` — тестовый датасет, `mockup/` — эталон дизайна (Ф2)

## Конвенции
- Python 3.9: без `match`, без `X | Y` в аннотациях, `typing.Optional/List/Dict`.
- API: JSON UTF-8, числа числами, ошибки `{"error": "..."}` + HTTP-код; период — `?period=all|q3|sep`.
- Метрики считаются **без НДС** (ставка из датасета); ДДС и маркетинг — с НДС, в подписях это указано.
- Секреты из `.env`/БД наружу не отдаются (только `{"set": true, "hint": "••••1234"}`) и не логируются.
- Вид вкладок — из `mockup/index.html`, менять нельзя; расчёты форматируются по-русски (запятая, «млн ₽»).

## Нельзя
- Менять `mockup/` и `data/*.json` (генератор — `scripts/gen_test_data.py`, seed=42).
- Подключать реальные Google/Excel/FinTablo/Битрикс и внешние API — это Ф4 (сейчас только mock).
- Добавлять фреймворки фронтенда, ORM, деплой (Ф6), данные реальных клиентов.
