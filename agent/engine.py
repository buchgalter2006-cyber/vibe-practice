"""Движок агента: сообщение -> JSON по agent/schema.json (Ф7).

Два движка, выбор по переменным окружения (.env):
  1. LLM (основной): OpenAI-совместимый API.
     ENGINE_BASE_URL (напр. https://api.deepseek.com/v1), ENGINE_API_KEY,
     ENGINE_MODEL (напр. deepseek-chat). Запрос: agent/prompt.md + схема.
  2. Offline (fallback, для тестов без ключа): детерминированный разбор по
     правилам — суммы, статьи и способ оплаты по словарям. Познаёт только
     явные формулировки; всё сложное -> «требует проверки» (правило
     «не угадывать»).

Оба движка возвращают dict по схеме; валидация схемы — в harness.py.
"""
import json
import os
import re
import urllib.request
from datetime import date
from typing import Any, Dict, List

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

ARTICLE_KEYWORDS = {
    "Реклама": ["реклам", "директ", "vk ads", "телеграм ads", "telegram ads", "сео", "seo", "продвижен"],
    "ФОТ": ["зарплат", "оклад", "фот", "преми", "аванс"],
    "Подрядчики": ["подрядчик", "фриланс", "за сайт", "за дизайн", "разработк"],
    "Аренда и офис": ["аренд", "офис", "клининг"],
    "ПО и сервисы": ["подписк", "лиценз", "софт", "сервис", "хостинг", "домен", " notchion", "figma"],
    "Налоги": ["налог", "взнос", "ндс", "пени"],
}
PAYMENT_KEYWORDS = {"карта": ["карт", "картой"], "наличные": ["наличн"],
                    "перевод": ["перевод", "счёту", "счету", "по счету"]}


def _load_prompt() -> str:
    with open(os.path.join(AGENT_DIR, "prompt.md"), encoding="utf-8") as f:
        return f.read()


def _schema() -> Dict[str, Any]:
    with open(os.path.join(AGENT_DIR, "schema.json"), encoding="utf-8") as f:
        return json.load(f)


def engine_mode() -> str:
    return "llm" if (os.environ.get("ENGINE_API_KEY") and os.environ.get("ENGINE_BASE_URL")) else "offline"


def parse_message(text: str) -> Dict[str, Any]:
    if engine_mode() == "llm":
        try:
            return _llm_parse(text)
        except Exception as exc:  # сеть/ключ упали — не молчим, но и не падаем
            offline = _offline_parse(text)
            offline["comment"] = u"LLM-движок недоступен (%s), разбор офлайн-правилами" % exc.__class__.__name__
            return offline
    return _offline_parse(text)


# ------------------------------------------------------------------- LLM --
def _llm_parse(text: str) -> Dict[str, Any]:
    base = os.environ["ENGINE_BASE_URL"].rstrip("/")
    body = json.dumps({
        "model": os.environ.get("ENGINE_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": _load_prompt() +
             "\n\nСХЕМА ОТВЕТА (JSON Schema):\n" + json.dumps(_schema(), ensure_ascii=False)},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=body, headers={
        "Authorization": "Bearer %s" % os.environ["ENGINE_API_KEY"],
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


# --------------------------------------------------------------- offline --
_NUM_RE = re.compile(r"(\d[\d\s.,]{0,11})\s*(тыс\.?\w*|тысяч\w*|млн\w*)?(?:\s*(?:руб\w*|₽|р\.))?", re.I)


def _amounts(text: str) -> List[float]:
    out = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
        if not raw or not re.search(r"\d", raw):
            continue
        value = float(raw.rstrip("."))
        mult = m.group(2) or ""
        if mult.lower().startswith("тыс"):
            value *= 1000
        elif mult.lower().startswith("млн"):
            value *= 1_000_000
        out.append(round(value))
    return out


def _article(text: str) -> str:
    low = text.lower()
    for article, words in ARTICLE_KEYWORDS.items():
        if any(w in low for w in words):
            return article
    return "Прочее"


def _payment(text: str) -> str:
    low = text.lower()
    for name, words in PAYMENT_KEYWORDS.items():
        if any(w in low for w in words):
            return name
    return "неизвестно"


def _vendor(text: str) -> str:
    m = re.search(r"(?:за|в|у)\s+«?([А-ЯЁA-Z][\w\- ]{2,40})", text)
    return m.group(1).strip() if m else "Не указан"


def _offline_parse(text: str) -> Dict[str, Any]:
    low = text.lower().strip()

    # правка: «исправь … не X, а Y» — новое значение после «а»; иначе последнее число
    if low.startswith("исправь"):
        def to_amount(raw, mult=""):
            value = float(raw.replace(" ", "").replace(",", ".").rstrip("."))
            if mult and mult.lower().startswith("тыс"):
                value *= 1000
            if mult and mult.lower().startswith("млн"):
                value *= 1_000_000
            return round(value)

        m_new = re.search(r"а\s+(\d[\d\s.,]{0,11})\s*(тыс\.?\w*|тысяч\w*|млн\w*)?", text, re.I)
        if m_new:
            fields: Dict[str, Any] = {"amount": to_amount(m_new.group(1), m_new.group(2) or "")}
        else:
            found = _NUM_RE.findall(text)
            if not found:
                return {"action": "ignore",
                        "comment": u"правка распознана, но новое значение суммы не найдено"}
            fields = {"amount": to_amount(found[-1][0], found[-1][1] or "")}
        return {"action": "correct", "fields": fields,
                "comment": u"офлайн-правка: меняем сумму последней записи"}

    amounts = _amounts(text)
    if not amounts:
        return {"action": "ignore",
                "comment": u"сумма не найдена — офлайн-движок не угадывает"}

    txs = []
    for amount in amounts:
        status = "готово"
        comment = u"дата = сегодня, в сообщении не указана"
        if amount <= 0:
            status, comment = "требует проверки", u"сумма нулевая или отрицательная"
        txs.append({
            "date": date.today().isoformat(),
            "amount": amount,
            "currency": "₽",
            "vendor": _vendor(text),
            "article": _article(text),
            "payment_method": _payment(text),
            "type": "расход",
            "status": status,
            "comment": comment,
        })
    return {"action": "expense", "transactions": txs}
