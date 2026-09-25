#!/usr/bin/env python3
"""Генератор тестового датасета для учебного дашборда (синтетика, без данных клиентов).

Компания-пример: маркетинговая группа «Вектор» (3 направления, НДС 22%).
Период: январь–сентябрь 2026, сентябрь частичный (23 из 30 дней) — для Run Rate.

Что выгружает (в data/):
  mock_data.json    — всё одним файлом (для макета и каркаса)
  plan_marketing.csv — план маркетинга по каналам/месяцам (пойдёт в Google-таблицу, Ф4)
  fact_marketing.csv — факт маркетинга (пойдёт в Excel-ведомость, Ф4)
  dds_operations.csv — операции ДДС для сервиса учёта (Ф4)

Метрики считаются «как в курсе»: всё без НДС, Cash Conversion = поступления / начисленная выручка.

Запуск:  python3 gen_test_data.py
"""
import csv
import json
import os
import random

random.seed(42)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(OUT, exist_ok=True)

MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен"]
DAYS_PASSED = 23
DAYS_TOTAL = 30
VAT = 0.22

SEASON = [0.82, 0.88, 1.05, 0.95, 0.90, 1.02, 0.85, 0.92, 1.08]  # сезонность спроса


def jitter(base, spread):
    return base * (1 + random.uniform(-spread, spread))


# --- Маркетинг: план vs факт (сначала — он определяет статью «Реклама») ----
CHANNELS = [
    ("Яндекс Директ", 700_000), ("VK Ads", 400_000),
    ("Telegram Ads", 300_000), ("SEO и контент", 250_000),
]
channels, plan_marketing, fact_marketing = [], [], []
for name, base in CHANNELS:
    plan = [round(jitter(base * s, 0.03), -3) for s in SEASON]
    fact = []
    for i, p in enumerate(plan):
        f = jitter(p, 0.12)
        if i == len(plan) - 1:  # сентябрь не закончился
            f = f * DAYS_PASSED / DAYS_TOTAL
        fact.append(round(f, -3))
    channels.append({"channel": name, "plan": plan, "fact": fact})
    plan_marketing.append([name] + plan)
    fact_marketing.append([name] + fact)

marketing_plan_total = sum(sum(ch["plan"]) for ch in channels)   # с НДС
marketing_fact_total = sum(sum(ch["fact"]) for ch in channels)   # с НДС

# --- ДДС: поступления и списания -------------------------------------------
income, expense = [], []
for i, s in enumerate(SEASON):
    inc = jitter(10_200_000 * s, 0.06)
    exp = jitter(9_900_000 * (0.95 + 0.05 * s), 0.05)
    if i == len(SEASON) - 1:  # сентябрь: месяц не закончился
        inc = inc * DAYS_PASSED / DAYS_TOTAL
        exp = exp * DAYS_PASSED / DAYS_TOTAL
    income.append(round(inc))
    expense.append(round(exp))

# Статья «Реклама» = факт маркетинга; остальные статьи — от остатка бюджета.
rest = sum(expense) - marketing_fact_total
OTHERS = {"ФОТ": 0.47, "Подрядчики": 0.22, "Аренда и офис": 0.08,
          "ПО и сервисы": 0.055, "Налоги (без НДС)": 0.13, "Прочее": 0.045}
expense_by_article = [{"article": "Реклама", "amount": round(marketing_fact_total)}]
expense_by_article += [{"article": a, "amount": round(rest * w)} for a, w in OTHERS.items()]
expense_by_article.sort(key=lambda x: -x["amount"])

COUNTERPARTIES = ["ООО «Яндекс»", "ИП Смирнов", "ООО «Тендер»", "АО «Фриланс-Хаб»",
                  "ООО «Клиент-Плюс»", "ИП Ковалёва", "ООО «Софт-Лицензии»", "ЗАО «Аренда-Центр»"]
operations = []
for d in range(22, 0, -1):
    if len(operations) >= 12:
        break
    if d % 2 == 0:
        operations.append({
            "date": f"2026-09-{d:02d}",
            "article": random.choice(["ФОТ", "Реклама", "Подрядчики", "ПО и сервисы", "Аренда и офис"]),
            "counterparty": random.choice(COUNTERPARTIES),
            "direction": random.choice(["списание", "списание", "поступление"]),
            "amount": round(jitter(940_000, 0.7), -3),
        })

# --- Воронка CRM и направления --------------------------------------------
funnel = [
    {"stage": "Лиды", "count": 486},
    {"stage": "Квалифицированные", "count": 302},
    {"stage": "КП отправлено", "count": 181},
    {"stage": "Оплачено", "count": 97},
]
directions = [
    {"name": "Брендинг", "revenue": 31_400_000, "deals": 34, "avg_check": 923_000, "conversion": 0.24},
    {"name": "Веб-разработка", "revenue": 26_900_000, "deals": 41, "avg_check": 656_000, "conversion": 0.19},
    {"name": "Перформанс", "revenue": 12_500_000, "deals": 22, "avg_check": 568_000, "conversion": 0.16},
]

# --- Метрики (все без НДС) -------------------------------------------------
income_net = sum(income) / (1 + VAT)                  # поступления без НДС
budget_plan_net = marketing_plan_total / (1 + VAT)
budget_fact_net = marketing_fact_total / (1 + VAT)
revenue_accrued_net = income_net / 0.95               # начислено больше, чем поступило
paid_deals = funnel[-1]["count"]
leads = funnel[0]["count"]
gross_profit = income_net * 0.38

metrics = [
    {"key": "roas", "name": "ROAS", "formula": "Выручка (без НДС) / рекламный бюджет",
     "value": round(income_net / budget_fact_net, 2), "norm": 4.0, "unit": "×",
     "good_is_higher": True},
    {"key": "cac", "name": "CAC", "formula": "Рекламный бюджет / оплаченные сделки",
     "value": round(budget_fact_net / paid_deals), "norm": 110_000, "unit": "₽",
     "good_is_higher": False},
    {"key": "gp_per_lead", "name": "Валовая прибыль на лида",
     "formula": "Валовая прибыль / количество лидов",
     "value": round(gross_profit / leads), "norm": 50_000, "unit": "₽",
     "good_is_higher": True},
    {"key": "cash_conv", "name": "Cash Conversion", "formula": "Поступления / начисленная выручка",
     "value": round(income_net / revenue_accrued_net, 3), "norm": 1.0, "unit": "%",
     "good_is_higher": True},
]

balance = round(sum(income) - sum(expense) + 12_400_000)

data = {
    "company": "Маркетинговая группа «Вектор»",
    "currency": "₽",
    "vat_rate": VAT,
    "months": MONTHS,
    "partial_last_month": {"days_passed": DAYS_PASSED, "days_total": DAYS_TOTAL},
    "dds": {"income": income, "expense": expense, "balance": balance},
    "expense_by_article": expense_by_article,
    "operations": operations,
    "marketing": {"channels": channels},
    "funnel": funnel,
    "directions": directions,
    "metrics": metrics,
    "totals": {
        "income_net": round(income_net),
        "budget_plan_net": round(budget_plan_net),
        "budget_fact_net": round(budget_fact_net),
        "revenue_accrued_net": round(revenue_accrued_net),
    },
}

with open(os.path.join(OUT, "mock_data.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


write_csv("plan_marketing.csv", ["Канал"] + MONTHS, plan_marketing)
write_csv("fact_marketing.csv", ["Канал"] + MONTHS, fact_marketing)
write_csv("dds_operations.csv", ["Дата", "Статья", "Контрагент", "Направление", "Сумма"],
          [[o["date"], o["article"], o["counterparty"], o["direction"], o["amount"]] for o in operations])

print("OK: data/mock_data.json + 3 CSV")
print(f"Поступления янв-сен: {sum(income):,} ₽; списания: {sum(expense):,} ₽; остаток: {balance:,} ₽")
print(f"Маркетинг план: {marketing_plan_total:,} ₽; факт: {marketing_fact_total:,} ₽ (с НДС)")
for m in metrics:
    print(f"  {m['name']}: {m['value']} (норма {m['norm']})")
