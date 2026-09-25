#!/usr/bin/env python3
"""Данные для стаба внешних систем (синтетика, Ф4).

Из тестового датасета data/mock_data.json собирает stub/stub_data.json:
  operations — ~120 операций ДДС за янв–сен: суммы по каждому месяцу сходятся
               ТОЧНО в ноль с dds.income/dds.expense датасета (последняя операция
               месяца — балансирующая), статьи — по весам expense_by_article;
  deals      — 486 сделок CRM со стадиями воронки (NEW 184 / QUALIFIED 121 /
               PROPOSAL 84 / WON 97), у WON сумма OPPORTUNITY в точности
               равна выручке направлений из directions.

Запуск:  scripts/gen_stub_data.py
"""
import json
import os
import random
from datetime import date

random.seed(2026)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK = os.path.join(BASE, "data", "mock_data.json")
OUT = os.path.join(BASE, "stub", "stub_data.json")

d = json.load(open(MOCK, encoding="utf-8"))
MONTHS = d["months"]
NUM2MON = {1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн", 7: "Июл", 8: "Авг", 9: "Сен"}
DAYS_PASSED, DAYS_TOTAL = d["partial_last_month"]["days_passed"], d["partial_last_month"]["days_total"]

ARTICLES = {a["article"]: a["amount"] for a in d["expense_by_article"]}
ART_NAMES = list(ARTICLES)
CP = ["ООО «Яндекс»", "ИП Смирнов", "ООО «Тендер»", "АО «Фриланс-Хаб»",
      "ООО «Клиент-Плюс»", "ИП Ковалёва", "ООО «Софт-Лицензии»", "ЗАО «Аренда-Центр»",
      "ООО «Реклама-Про»", "ИП Быстров"]

operations = []
op_id = 1000


def split_exact(total, n):
    """n положительных целых с суммой ровно total."""
    weights = [random.uniform(0.7, 1.3) for _ in range(n)]
    s = sum(weights)
    parts = [max(1000, round(total * w / s / 1000)) * 1000 for w in weights[:-1]]
    parts.append(total - sum(parts))
    return parts


for mi, mon in enumerate(MONTHS):
    m_num = mi + 1
    scale = DAYS_PASSED / DAYS_TOTAL if mi == len(MONTHS) - 1 else 1.0

    # поступления: 5 операций, сумма месяца — точно
    for k, amount in enumerate(split_exact(d["dds"]["income"][mi], 5), start=1):
        op_id += 1
        day = min(28, k * 5 + random.randint(-2, 2))
        if mi == len(MONTHS) - 1 and day > DAYS_PASSED:
            day = DAYS_PASSED - k
        operations.append({
            "id": op_id, "date": f"2026-{m_num:02d}-{day:02d}",
            "type": "income", "amount": amount,
            "article": "Поступления от клиентов",
            "counterparty": random.choice(CP),
            "direction": random.choice(["Брендинг", "Веб-разработка", "Перформанс"]),
        })

    # списания: по статьям, пропорция от общих весов; сумма месяца — точно
    month_expense = d["dds"]["expense"][mi]
    per_article = {a: round(month_expense * ARTICLES[a] / sum(ARTICLES.values()) / 1000) * 1000
                   for a in ART_NAMES}
    diff = month_expense - sum(per_article.values())
    per_article[ART_NAMES[0]] += diff  # балансирующая правка на первую статью
    for ai, (article, art_month_total) in enumerate(per_article.items()):
        n_ops = 3 if ai % 2 == 0 else 2
        for k, amount in enumerate(split_exact(art_month_total, n_ops), start=1):
            op_id += 1
            day = min(28, k * 8 + random.randint(-2, 2))
            if mi == len(MONTHS) - 1 and day > DAYS_PASSED:
                day = DAYS_PASSED - k - 1
            operations.append({
                "id": op_id, "date": f"2026-{m_num:02d}-{max(1, day):02d}",
                "type": "expense", "amount": amount,
                "article": article,
                "counterparty": random.choice(CP),
                "direction": "",
            })

# --- CRM: сделки ------------------------------------------------------------
WON_ONLY = {"NEW": 184, "QUALIFIED": 121, "PROPOSAL": 84, "WON": 97}
STAGE_ORDER = ["NEW", "QUALIFIED", "PROPOSAL", "WON"]
DIRECTIONS = d["directions"]

deals = []
deal_id = 1
# WON: распределить выручку направлений точно (deals_count == 97 всего)
won_plans = []
for dr in DIRECTIONS:
    won_plans += [(dr["name"], v) for v in split_exact(dr["revenue"], dr["deals"])]
random.shuffle(won_plans)
won_iter = iter(won_plans)

for stage, count in WON_ONLY.items():
    for _ in range(count):
        if stage == "WON":
            direction, opportunity = next(won_iter)
        else:
            direction = random.choice([dr["name"] for dr in DIRECTIONS])
            opportunity = 0
        deals.append({
            "ID": str(deal_id), "TITLE": f"Сделка {deal_id}",
            "STAGE_ID": stage, "OPPORTUNITY": opportunity,
            "CATEGORY": direction, "ASSIGNED_BY": random.choice([1, 5, 7]),
        })
        deal_id += 1

# контроль: суммы воронки и направлений
def funnel_count(stage):
    i = STAGE_ORDER.index(stage)
    return sum(1 for x in deals if STAGE_ORDER.index(x["STAGE_ID"]) >= i)

check = {
    "funnel": {s: funnel_count(s) for s in STAGE_ORDER},
    "revenue_by_direction": {},
}
for x in deals:
    if x["STAGE_ID"] == "WON":
        check["revenue_by_direction"][x["CATEGORY"]] = \
            check["revenue_by_direction"].get(x["CATEGORY"], 0) + x["OPPORTUNITY"]

exp_funnel = {"NEW": 486, "QUALIFIED": 302, "PROPOSAL": 181, "WON": 97}
assert check["funnel"] == exp_funnel, check["funnel"]
for dr in DIRECTIONS:
    got = check["revenue_by_direction"].get(dr["name"], 0)
    assert got == dr["revenue"], (dr["name"], got, dr["revenue"])

# контроль: месячные суммы операций == dds датасета
for mi, mon in enumerate(MONTHS):
    pref = f"2026-{mi + 1:02d}"
    inc = sum(o["amount"] for o in operations if o["date"].startswith(pref) and o["type"] == "income")
    exp = sum(o["amount"] for o in operations if o["date"].startswith(pref) and o["type"] == "expense")
    assert inc == d["dds"]["income"][mi], (mon, "income", inc, d["dds"]["income"][mi])
    assert exp == d["dds"]["expense"][mi], (mon, "expense", exp, d["dds"]["expense"][mi])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({"operations": operations, "deals": deals},
          open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print(f"OK: {OUT}")
print(f"операций: {len(operations)}, сделок: {len(deals)} — контроль сумм и воронки пройден")
