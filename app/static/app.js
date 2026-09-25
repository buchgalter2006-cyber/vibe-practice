/* Каркас Ф3: вид перенесён из макета Ф2 (1:1), данные берутся из JSON API.
   Фильтрация по периоду выполняется на сервере — клиент только рисует ответ. */
const PERIOD_LABELS = { all: "Янв – Сен 2026", q3: "Q3 2026", sep: "Сентябрь 2026" };
let period = "all";
let META = null;
let current = "overview";
/* Ф5: текущий пользователь (из /api/whoami) и роли */
const ROLE_LEVEL = { view: 1, editor: 2, admin: 3 };
const ROLE_LABEL = { admin: "админ", editor: "редактор", view: "просмотр" };
let ME = { user: null, role: null };
const roleAtLeast = r => !!ME.user && (ROLE_LEVEL[ME.role] || 0) >= ROLE_LEVEL[r];
const state = { overview: null, marketing: null, sales: null, metrics: null, settings: null };
const tokens = {};

/* ---------- форматирование (как в макете) ---------- */
const fmtM = v => {
  const a = Math.abs(v);
  if (a >= 1e6) return (v/1e6).toFixed(1).replace(".", ",") + " млн ₽";
  if (a >= 1e3) return Math.round(v/1e3).toLocaleString("ru-RU") + " тыс ₽";
  return Math.round(v).toLocaleString("ru-RU") + " ₽";
};
const fmtN = v => Math.round(v).toLocaleString("ru-RU");
const pct = (a, b) => Math.round((a/b - 1) * 1000) / 10;
const fmtPct = d => (d > 0 ? "+" : "") + String(d).replace(".", ",") + "%";
const num1 = v => v.toFixed(1).replace(".", ",");
const sum = a => a.reduce((x, y) => x + y, 0);
const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const partialNote = d => d.is_partial && d.partial_last_month
  ? `<span class="warn">сен — неполный месяц (${d.partial_last_month.days_passed} из ${d.partial_last_month.days_total} дней)</span>`
  : "";

/* ---------- SVG: линия ---------- */
function lineChart(series, labels) {
  const W = 720, H = 250, L = 66, R = 16, T = 14, B = 34;
  const max = Math.max(...series.flatMap(s => s.values)) * 1.12;
  const n = labels.length;
  const x = i => L + (n === 1 ? (W-L-R)/2 : i * (W-L-R) / (n-1));
  const y = v => T + (H-T-B) * (1 - v/max);
  const grid = [0, .5, 1].map(k => {
    const v = max * k, yy = y(v);
    return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="#eef0f3"/>
            <text x="${L-9}" y="${yy+4}" text-anchor="end" font-size="11" fill="#9aa1ae">${(v/1e6).toFixed(0)} млн</text>`;
  }).join("");
  const paths = series.map(s => {
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const dots = s.values.map((v, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3.4" fill="#fff" stroke="${s.color}" stroke-width="2"/>`).join("");
    return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.2" stroke-linejoin="round"/>${dots}`;
  }).join("");
  // подписи последних значений: если точки близко — разнести вверх/вниз
  const lastX = x(n - 1);
  const lastVals = series.map(s => ({v: s.values[s.values.length - 1], color: s.color,
    yy: y(s.values[s.values.length - 1])}));
  const close = lastVals.length === 2 && Math.abs(lastVals[0].yy - lastVals[1].yy) < 26;
  const lbl = lastVals.map((p, i) => {
    const dy = close ? (i === 0 ? -12 : 22) : -11;
    return `<text x="${lastX - (close ? 4 : 0)}" y="${p.yy + dy}" text-anchor="end" font-size="11.5" font-weight="600" fill="${p.color}" stroke="#fff" stroke-width="3" paint-order="stroke">${fmtM(p.v)}</text>`;
  }).join("");
  const xs = labels.map((t, i) => `<text x="${x(i)}" y="${H-12}" text-anchor="middle" font-size="11.5" fill="#7b8290">${t}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">${grid}${paths}${lbl}${xs}</svg>`;
}

/* ---------- SVG: сгруппированные бары ---------- */
function groupBars(plan, fact, labels) {
  const W = 720, H = 235, L = 66, R = 16, T = 12, B = 34;
  const max = Math.max(...plan, ...fact) * 1.15;
  const n = labels.length, slot = (W - L - R) / Math.max(n, 1);
  const bw = Math.min(20, slot / 3);
  const y = v => T + (H-T-B) * (1 - v/max);
  const grid = [0, .5, 1].map(k => {
    const v = max * k, yy = y(v);
    return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="#eef0f3"/>
            <text x="${L-9}" y="${yy+4}" text-anchor="end" font-size="11" fill="#9aa1ae">${num1(v/1e6)} млн</text>`;
  }).join("");
  let bars = "", xs = "";
  labels.forEach((t, i) => {
    const cx = L + slot * i + slot/2;
    const h1 = H - B - y(plan[i]), h2 = H - B - y(fact[i]);
    bars += `<rect x="${cx-bw-2}" y="${y(plan[i])}" width="${bw}" height="${h1}" rx="3" fill="#c6cff2"/>
             <rect x="${cx+2}" y="${y(fact[i])}" width="${bw}" height="${h2}" rx="3" fill="#4b63d8"/>`;
    xs += `<text x="${cx}" y="${H-12}" text-anchor="middle" font-size="11.5" fill="#7b8290">${t}</text>`;
  });
  return { svg: `<svg viewBox="0 0 ${W} ${H}" width="100%">${grid}${bars}${xs}</svg>`,
    legend: `<div class="muted" style="font-size:12px;padding:2px 16px 0">
      <span style="display:inline-block;width:9px;height:9px;background:#c6cff2;border-radius:2px;margin-right:5px"></span>план
      <span style="display:inline-block;width:9px;height:9px;background:#4b63d8;border-radius:2px;margin:0 5px 0 14px"></span>факт</div>` };
}

/* ---------- вкладка: Обзор ---------- */
function renderOverview(M) {
  const inc = M.income, exp = M.expense;
  const labels = M.months;
  const sInc = sum(inc), sExp = sum(exp), diff = sInc - sExp;

  let html = `<div class="kpis">
    <div class="card kpi"><div class="t">Поступления <span class="muted">с НДС</span></div>
      <div class="v num">${fmtM(sInc)}</div><div class="d">за период</div></div>
    <div class="card kpi"><div class="t">Списания <span class="muted">с НДС</span></div>
      <div class="v num">${fmtM(sExp)}</div><div class="d">за период</div></div>
    <div class="card kpi"><div class="t">Кассовый результат</div>
      <div class="v num ${diff >= 0 ? "up" : "down"}">${diff >= 0 ? "+" : "−"}${fmtM(Math.abs(diff))}</div>
      <div class="d">поступления − списания</div></div>
    <div class="card kpi"><div class="t">Остаток на счёте</div>
      <div class="v num">${fmtM(M.balance)}</div><div class="d">текущий, вне периода</div></div>
  </div>

  <div class="grid2">
    <div class="card"><h2>Динамика по месяцам</h2>
      <div class="hint">${partialNote(M)}</div>
      <div class="pad">${lineChart([
        {values: inc, color: "#0f9d58"}, {values: exp, color: "#d93025"}
      ], labels)}</div></div>
    <div class="card"><h2>Структура расходов</h2>
      <div class="hint">Янв – Сен 2026 · ${fmtM(M.expense_full_total)} всего</div>
      <div class="pad bars">${M.expense_by_article.map((a, i) => {
        const w = a.amount / M.expense_by_article[0].amount * 100;
        return `<div class="bar"><div>${a.article}</div>
          <div class="track"><div class="fill ${i > 2 ? "g" : ""}" style="width:${w.toFixed(1)}%"></div></div>
          <div class="val num">${fmtM(a.amount)}</div></div>`;
      }).join("")}</div></div>
  </div>

  <div class="card"><h2>Последние операции</h2>
    <div class="hint">синтетические данные для макета</div>
    <div class="pad"><table>
      <thead><tr><th>Дата</th><th>Статья</th><th>Контрагент</th><th>Тип</th><th class="r">Сумма</th></tr></thead>
      <tbody>${M.operations.map(o => `<tr>
        <td class="num">${o.date.split("-").reverse().join(".")}</td><td>${o.article}</td>
        <td>${o.counterparty}</td>
        <td><span class="pill ${o.direction === "поступление" ? "in" : "out"}">${o.direction}</span></td>
        <td class="r num">${fmtM(o.amount)}</td></tr>`).join("")}</tbody>
    </table></div></div>`;
  document.getElementById("pane-overview").innerHTML = html;
}

/* ---------- вкладка: Маркетинг ---------- */
function renderMarketing(M) {
  const labels = M.months;
  const p = M.plan, f = M.fact;
  const sP = sum(p), sF = sum(f), osvoenie = sF / sP * 100;
  const dev = pct(sF, sP);

  const rows = M.channels.map(c => {
    const cp = c.plan_total, cf = c.fact_total;
    const d = pct(cf, cp);
    return `<tr><td>${c.channel}</td><td class="r num">${fmtM(cp)}</td><td class="r num">${fmtM(cf)}</td>
      <td class="r num ${d <= 0 ? "up" : "down"}">${fmtPct(d)}</td>
      <td class="r num">${Math.round(cf / cp * 100)}%</td></tr>`;
  }).join("");
  const totP = M.plan_total, totF = M.fact_total;

  document.getElementById("pane-marketing").innerHTML = `
  <div class="kpis">
    <div class="card kpi"><div class="t">План <span class="muted">с НДС</span></div>
      <div class="v num">${fmtM(sP)}</div><div class="d">за период</div></div>
    <div class="card kpi"><div class="t">Факт <span class="muted">с НДС</span></div>
      <div class="v num">${fmtM(sF)}</div><div class="d">за период</div></div>
    <div class="card kpi"><div class="t">Освоение бюджета</div>
      <div class="v num ${osvoenie > 105 ? "down" : ""}">${num1(osvoenie)}%</div>
      <div class="d">факт / план</div></div>
    <div class="card kpi"><div class="t">Отклонение</div>
      <div class="v num ${dev <= 0 ? "up" : "down"}">${fmtPct(dev)}</div>
      <div class="d">${dev <= 0 ? "экономия к плану" : "перерасход к плану"}</div></div>
  </div>
  <div class="card"><h2>План и факт по месяцам</h2>
    <div class="hint">${partialNote(M)}</div>
    ${groupBars(p, f, labels).legend}
    <div class="pad">${groupBars(p, f, labels).svg}</div></div>
  <div class="card" style="margin-top:16px"><h2>По каналам</h2>
    <div class="hint">Янв – Сен 2026 · отклонение = факт − план</div>
    <div class="pad"><table>
      <thead><tr><th>Канал</th><th class="r">План</th><th class="r">Факт</th><th class="r">Отклонение</th><th class="r">Освоение</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td>Итого</td><td class="r num">${fmtM(totP)}</td><td class="r num">${fmtM(totF)}</td>
        <td class="r num">${fmtPct(pct(totF, totP))}</td>
        <td class="r num">${Math.round(totF / totP * 100)}%</td></tr></tfoot>
    </table></div></div>`;
}

/* ---------- вкладка: Продажи ---------- */
function renderSales(M) {
  const f = M.funnel, top = f[0].count;
  const conv = (a, b) => (b / a * 100).toFixed(0) + "%";
  const paid = f[f.length - 1].count;
  const deals = sum(M.directions.map(d => d.deals));
  const rev = sum(M.directions.map(d => d.revenue));
  const rows = M.directions.map(d => `<tr><td>${d.name}</td><td class="r num">${fmtM(d.revenue)}</td>
      <td class="r num">${d.deals}</td><td class="r num">${fmtM(d.avg_check)}</td>
      <td class="r num">${(d.conversion * 100).toFixed(0)}%</td></tr>`).join("");

  document.getElementById("pane-sales").innerHTML = `
  <div class="kpis">
    <div class="card kpi"><div class="t">Выручка начисленная <span class="muted">без НДС</span></div>
      <div class="v num">${fmtM(rev)}</div><div class="d">янв – сен 2026</div></div>
    <div class="card kpi"><div class="t">Оплаченных сделок</div>
      <div class="v num">${paid}</div><div class="d">из ${f[0].count} лидов</div></div>
    <div class="card kpi"><div class="t">Конверсия в оплату</div>
      <div class="v num">${conv(top, paid)}</div><div class="d">лид → оплата</div></div>
    <div class="card kpi"><div class="t">Средний чек</div>
      <div class="v num">${fmtM(rev / deals)}</div><div class="d">по ${deals} сделкам</div></div>
  </div>
  <div class="grid2">
    <div class="card"><h2>Воронка продаж</h2>
      <div class="hint">Битрикс24 · янв – сен 2026</div>
      <div class="pad funnel">${f.map((s, i) => {
        const w = s.count / top * 100;
        const convRow = i ? `<div class="conv"><div></div><div class="arrow">↑ ${conv(f[i-1].count, s.count)}</div></div>` : "";
        return `${convRow}<div class="frow"><div class="stage"><b class="num">${fmtN(s.count)}</b><br><span class="muted">${s.stage}</span></div>
          <div class="track"><div class="fill" style="width:${w.toFixed(1)}%">${w >= 25 ? fmtN(s.count) : ""}</div></div></div>`;
      }).join("")}</div></div>
    <div class="card"><h2>По направлениям</h2>
      <div class="hint">выручка без НДС</div>
      <div class="pad"><table>
        <thead><tr><th>Направление</th><th class="r">Выручка</th><th class="r">Сделки</th><th class="r">Ср. чек</th><th class="r">Конв.</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot><tr><td>Итого</td><td class="r num">${fmtM(rev)}</td><td class="r num">${deals}</td>
          <td class="r num">${fmtM(rev / deals)}</td><td class="r num">${conv(top, paid)}</td></tr></tfoot>
      </table></div></div>
  </div>`;
}

/* ---------- вкладка: Метрики ---------- */
function renderMetrics(M) {
  const cards = M.metrics.map(m => {
    const isPct = m.unit === "%";
    const val = isPct ? Math.round(m.value * 100) + "%"
      : (m.unit === "×" ? String(m.value).replace(".", ",") + "×" : fmtM(m.value));
    const norm = isPct ? Math.round(m.norm * 100) + "%"
      : (m.unit === "×" ? String(m.norm).replace(".", ",") + "×" : fmtM(m.norm));
    const d = pct(m.value, m.norm);
    const ok = m.good_is_higher ? d >= 0 : d <= 0;
    return `<div class="card mcard">
      <div class="top"><div><div class="name">${m.name}</div><div class="form">${m.formula}</div></div>
        <div class="dev ${ok ? "ok" : "no"}">${fmtPct(d)} к норме</div></div>
      <div class="big num">${val}</div>
      <div class="norm">Норматив: <b>${norm}</b> · без НДС</div></div>`;
  }).join("");

  document.getElementById("pane-metrics").innerHTML = `
  <div class="mgrid">${cards}</div>
  <div class="note">Поступления, которые тянутся из сервиса учёта, включают НДС ${Math.round(M.vat_rate * 100)}% — <b>на этой вкладке все показатели считаются без НДС</b>.
  Период: ${M.period_label}. ${M.note}</div>`;
}

/* ---------- вкладка: Настройки ---------- */
const SETTING_FIELDS = [
  {key: "google_sheet_url", label: "Google-таблица — план маркетинга",
   placeholder: "https://docs.google.com/spreadsheets/d/...", wide: true},
  {key: "excel_path", label: "Excel-ведомость — факт маркетинга", placeholder: "data/fact_marketing.xlsx"},
  {key: "fintablo_token", label: "FinTablo API-токен", placeholder: "не задан"},
  {key: "bitrix_webhook_url", label: "Вебхук Битрикс24", placeholder: "https://.../rest/1/xxxxxxxx/"},
];

function renderSettings(M) {
  const s = M.settings;
  const fields = SETTING_FIELDS.map(f => {
    const item = s[f.key] || {secret: false, set: false, value: "", hint: ""};
    const ph = item.secret && item.set ? item.hint + " — оставьте пустым, чтобы не менять" : f.placeholder;
    const value = item.secret ? "" : (item.value || "");
    return `<div class="field${f.wide ? " wide" : ""}">
      <label for="set-${f.key}">${f.label}${item.secret ? " (секрет)" : ""}</label>
      <input id="set-${f.key}" data-key="${f.key}" data-secret="${item.secret ? "1" : "0"}"
             type="${item.secret ? "password" : "text"}" value="${esc(value)}"
             placeholder="${esc(ph)}" autocomplete="off" spellcheck="false">
      <div class="hintline">${item.set ? (item.secret ? "задан: " + esc(item.hint) : "задано") : "не задано"}</div>
    </div>`;
  }).join("");

  const norms = (META && META.metrics ? META.metrics : []).map(m => {
    const n = M.norms[m.key] || {value: m.norm, unit: m.unit, good_is_higher: m.good_is_higher};
    const v = String(n.value).replace(".", ",");
    return `<div class="field">
      <label for="norm-${m.key}">${m.name}, ${n.unit === "%" ? "доля" : n.unit} ${n.good_is_higher ? "· чем выше, тем лучше" : "· чем ниже, тем лучше"}</label>
      <input id="norm-${m.key}" data-norm="${m.key}" type="text" inputmode="decimal" value="${esc(v)}">
    </div>`;
  }).join("");

  document.getElementById("pane-settings").innerHTML = `
  <div class="card"><h2>Источники данных</h2>
    <div class="hint">активный источник: ${esc(M.data_source)} · реальные подключения — фаза 4</div>
    <div class="pad">
      <div class="form">${fields}</div>
      <div class="muted" style="font-size:11.5px;margin-top:10px">Секреты не отдаются сервером целиком: видно только «задан» и последние 4 знака.</div>
    </div></div>

  <div class="card" style="margin-top:16px"><h2>Нормативы метрик</h2>
    <div class="hint">используются на вкладке «Метрики» для расчёта отклонения</div>
    <div class="pad"><div class="form">${norms}</div>
      <div class="actions">
        <button class="btn" id="save-settings">Сохранить</button>
        <span class="status" id="set-status"></span>
      </div>
    </div></div>

  <div class="card" style="margin-top:16px"><h2>Загрузка ведомости факта</h2>
    <div class="hint">Excel (.xlsx), лист «Факт маркетинга», шапка в строке 2 — после загрузки факт обновится на вкладке «Маркетинг»</div>
    <div class="pad">
      <div class="dropzone" id="dropzone" tabindex="0">
        <input type="file" id="file-input" accept=".xlsx" hidden>
        <b>Перетащите файл сюда</b> или <span class="linklike">выберите на диске</span>
        <div class="muted" style="font-size:11.5px;margin-top:6px">файл проходит валидацию: месяцы, каналы, контрольная сверка с текущим фактом</div>
      </div>
      <div class="status imp-status" id="upload-status"></div>
    </div></div>

  <div class="card" style="margin-top:16px"><h2>Журнал импортов</h2>
    <div class="hint">последние 20 загрузок — включая неудачные попытки</div>
    <div class="pad" id="imports-box"><div class="muted">Загрузка…</div></div></div>

  <div class="card" style="margin-top:16px" id="users-card" hidden><h2>Пользователи</h2>
    <div class="hint">создание, удаление и смена паролей — только для администратора</div>
    <div class="pad" id="users-box"><div class="muted">Загрузка…</div></div>
    <div class="pad users-form" id="users-form">
      <div class="field"><label>Логин</label><input id="nu-name" type="text" spellcheck="false"></div>
      <div class="field"><label>Пароль (от 8 символов)</label><input id="nu-pass" type="password"></div>
      <div class="field"><label>Роль</label>
        <select id="nu-role" class="role">
          <option value="view">просмотр</option>
          <option value="editor" selected>редактор</option>
          <option value="admin">админ</option>
        </select></div>
      <div class="actions" style="margin-top:0"><button class="btn" id="nu-create">Создать</button>
        <span class="status" id="users-status"></span></div>
    </div></div>`;

  const status = document.getElementById("set-status");
  const form = document.getElementById("pane-settings");
  form.querySelectorAll("input").forEach(inp => inp.addEventListener("input", () => {
    status.className = "status"; status.textContent = "";
  }));
  document.getElementById("save-settings").addEventListener("click", saveSettings);
  wireUpload();
  loadImports();
  if (ME.role === "admin") {
    document.getElementById("users-card").hidden = false;
    wireUsers();
    loadUsers();
  }
}

async function saveSettings() {
  const btn = document.getElementById("save-settings");
  const status = document.getElementById("set-status");
  const body = {settings: {}, norms: {}};

  document.querySelectorAll("#pane-settings input[data-key]").forEach(inp => {
    const isSecret = inp.dataset.secret === "1";
    const value = inp.value.trim();
    if (isSecret && !value) return;          // пустое поле секрета = «не менять»
    body.settings[inp.dataset.key] = value;
  });
  document.querySelectorAll("#pane-settings input[data-norm]").forEach(inp => {
    const value = parseFloat(inp.value.replace(",", ".").replace(/\s/g, ""));
    if (isNaN(value)) { body.norms[inp.dataset.norm] = null; return; }
    body.norms[inp.dataset.norm] = value;
  });
  const bad = Object.keys(body.norms).filter(k => body.norms[k] === null);
  if (bad.length) {
    status.className = "status err";
    status.textContent = "Норматив должен быть числом: " + bad.join(", ");
    return;
  }

  btn.disabled = true;
  status.className = "status"; status.textContent = "Сохранение…";
  try {
    const res = await api("/api/settings", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    renderSettings(res);
    state.metrics = null;                    // нормативы могли измениться
    const st = document.getElementById("set-status");
    st.className = "status ok";
    st.textContent = "Сохранено · " + new Date().toLocaleTimeString("ru-RU") +
      " (настройки: " + res.changed.settings.length + ", нормативы: " + res.changed.norms.length + ")";
    setStatus("Сохранено", false);
  } catch (err) {
    status.className = "status err";
    status.textContent = "Не сохранено: " + err.message;
    setStatus("Не сохранено: " + err.message, true);
  } finally {
    btn.disabled = false;
  }
}

/* ---------- Ф5: загрузка ведомости, журнал импортов, пользователи ---------- */
function wireUpload() {
  const zone = document.getElementById("dropzone");
  const input = document.getElementById("file-input");
  if (!zone || !input) return;
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", ev => { ev.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", ev => {
    ev.preventDefault();
    zone.classList.remove("drag");
    if (ev.dataTransfer.files && ev.dataTransfer.files.length) uploadFact(ev.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files && input.files.length) uploadFact(input.files[0]);
    input.value = "";                       // повторная загрузка того же файла
  });
}

async function uploadFact(file) {
  const st = document.getElementById("upload-status");
  if (!/\.xlsx$/i.test(file.name)) {
    st.className = "status err";
    st.textContent = "Нужен файл Excel (.xlsx): «" + file.name + "» не подходит";
    return;
  }
  st.className = "status";
  st.textContent = "Загрузка и проверка «" + file.name + "»…";
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await api("/api/upload/fact_marketing", { method: "POST", body: fd });
    st.className = "status ok";
    st.textContent = "Загружено: " + res.file + " · каналов: " + res.rows + " · сумма факта " + fmtM(res.total);
    state.marketing = null;                 // вкладка «Маркетинг» перечитает данные при показе
    state.overview = null;
    state.metrics = null;
    setStatus("Ведомость загружена: " + res.file, false);
    loadImports();
  } catch (err) {
    st.className = "status err";
    st.textContent = "Не загружено: " + err.message;
  }
}

async function loadImports() {
  const box = document.getElementById("imports-box");
  if (!box) return;
  try {
    const res = await api("/api/imports");
    const rows = res.imports || [];
    if (!rows.length) { box.innerHTML = '<div class="muted">Импортов пока не было</div>'; return; }
    box.innerHTML = `<table>
      <thead><tr><th>Время</th><th>Источник</th><th class="r">Строк</th><th>Статус</th><th>Сообщение</th></tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td class="num">${esc(String(r.started_at).replace("T", " "))}</td>
        <td>${esc(r.source)}</td>
        <td class="r num">${r.rows_imported}</td>
        <td><span class="pill ${r.status === "ok" ? "ok" : "err"}">${r.status === "ok" ? "ок" : "ошибка"}</span></td>
        <td>${esc(r.message || "")}</td></tr>`).join("")}</tbody></table>`;
  } catch (err) {
    box.innerHTML = '<div class="muted">Не удалось загрузить журнал: ' + esc(err.message) + '</div>';
  }
}

function wireUsers() {
  const st = document.getElementById("users-status");
  document.getElementById("nu-create").addEventListener("click", async () => {
    st.className = "status"; st.textContent = "";
    const btn = document.getElementById("nu-create");
    btn.disabled = true;
    try {
      await api("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("nu-name").value.trim(),
          password: document.getElementById("nu-pass").value,
          role: document.getElementById("nu-role").value,
        }),
      });
      st.className = "status ok";
      st.textContent = "Пользователь создан";
      document.getElementById("nu-name").value = "";
      document.getElementById("nu-pass").value = "";
      loadUsers();
    } catch (err) {
      st.className = "status err";
      st.textContent = err.status === 401 ? "Требуется вход" : err.message;
    } finally {
      btn.disabled = false;
    }
  });
}

async function loadUsers() {
  const box = document.getElementById("users-box");
  if (!box) return;
  try {
    const res = await api("/api/users");
    box.innerHTML = `<table>
      <thead><tr><th>Логин</th><th>Роль</th><th>Создан</th><th></th></tr></thead>
      <tbody>${res.users.map(u => `<tr>
        <td><b>${esc(u.username)}</b>${u.username === ME.user ? ' <span class="muted">(вы)</span>' : ""}</td>
        <td>${ROLE_LABEL[u.role] || esc(u.role)}</td>
        <td class="muted">${esc(String(u.created_at || "").replace("T", " "))}</td>
        <td class="users-actions">
          <button class="btn btn-sm secondary" data-pass="${esc(u.username)}">Сменить пароль</button>
          <button class="btn btn-sm danger" data-del="${esc(u.username)}">Удалить</button>
        </td></tr>`).join("")}</tbody></table>`;
    box.querySelectorAll("button[data-pass]").forEach(b => b.addEventListener("click", () => changePassword(b.dataset.pass)));
    box.querySelectorAll("button[data-del]").forEach(b => b.addEventListener("click", () => deleteUser(b.dataset.del)));
  } catch (err) {
    box.innerHTML = '<div class="muted">Не удалось загрузить список: ' + esc(err.message) + '</div>';
  }
}

async function changePassword(username) {
  const pwd = prompt("Новый пароль для «" + username + "» (от 8 символов):");
  if (pwd === null) return;
  if (pwd.length < 8) { alert("Пароль должен быть не короче 8 символов"); return; }
  try {
    await api("/api/users/" + encodeURIComponent(username) + "/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd }),
    });
    setStatus("Пароль обновлён: " + username, false);
    if (document.getElementById("users-box")) loadUsers();
  } catch (err) {
    alert("Не удалось сменить пароль: " + err.message);
  }
}

async function deleteUser(username) {
  if (!confirm("Удалить пользователя «" + username + "»?")) return;
  try {
    await api("/api/users/" + encodeURIComponent(username), { method: "DELETE" });
    setStatus("Пользователь удалён: " + username, false);
    loadUsers();
  } catch (err) {
    alert("Не удалось удалить: " + err.message);
  }
}

/* ---------- Ф5: блок пользователя в сайдбаре ---------- */
function applyUserUI() {
  const box = document.getElementById("userbox");
  const settingsLink = document.getElementById("nav-settings");
  if (ME.user) {
    box.hidden = false;
    document.getElementById("u-name").textContent = ME.user;
    document.getElementById("u-role").textContent = ROLE_LABEL[ME.role] || ME.role;
  } else {
    box.hidden = true;
  }
  /* «Настройки» — только editor/admin; view и не вошедшие их не видят */
  const canSettings = roleAtLeast("editor");
  settingsLink.hidden = !canSettings;
  const sep = document.getElementById("nav-sep");
  if (sep) sep.hidden = !canSettings;
  if (!canSettings && current === "settings") current = "overview";
  document.getElementById("logout-btn").addEventListener("click", async () => {
    await fetch("/logout", { method: "POST" });
    location.replace("/login");
  });
  document.getElementById("pass-btn").addEventListener("click", () => changePassword(ME.user));
}


async function api(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new Error("сервер недоступен — запустите .venv/bin/python app/server.py");
  }
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (!res.ok) {
    const err = new Error((body && body.error) || ("HTTP " + res.status));
    err.status = res.status;
    /* Ф5: сессия истекла / не выполнен вход — страница логина */
    if (res.status === 401 && !(options && options.noRedirect)) {
      setStatus("Требуется вход", true);
      setTimeout(() => location.replace("/login"), 300);
    }
    throw err;
  }
  return body;
}

const TAB_PERIOD = {overview: true, marketing: true, metrics: true, sales: false, settings: false};
const TAB_URL = {
  overview: () => "/api/overview?period=" + encodeURIComponent(period),
  marketing: () => "/api/marketing?period=" + encodeURIComponent(period),
  metrics: () => "/api/metrics?period=" + encodeURIComponent(period),
  sales: () => "/api/sales",
  settings: () => "/api/settings",
};
const RENDER = {overview: renderOverview, marketing: renderMarketing, sales: renderSales,
                metrics: renderMetrics, settings: renderSettings};
const TABS = ["overview", "marketing", "sales", "metrics", "settings"];

function setStatus(text, isError) {
  const box = document.getElementById("net-status");
  document.getElementById("net-status-text").textContent = text;
  box.className = "toast" + (isError ? " err" : "");
  box.hidden = !text;
}

function renderError(tab, err) {
  const pane = document.getElementById("pane-" + tab);
  if (!pane) return;
  pane.hidden = false;
  pane.innerHTML = `<div class="card errbox">
    <b>Не удалось получить данные</b>
    <div class="muted" style="margin-top:6px">${esc(err.message)}</div>
    <div class="actions"><button class="btn" id="retry-${tab}">Повторить</button></div></div>`;
  const btn = document.getElementById("retry-" + tab);
  if (btn) btn.addEventListener("click", () => ensureData(tab, true));
}

async function ensureData(tab, force) {
  const key = TAB_PERIOD[tab] ? period : "all";
  const cached = state[tab];
  if (!force && cached && cached.key === key) return;
  const token = (tokens[tab] || 0) + 1;
  tokens[tab] = token;
  setStatus("Загрузка…", false);
  try {
    const d = await api(TAB_URL[tab]());
    if (tokens[tab] !== token) return;       // ответ устарел (сменили период/вкладку)
    state[tab] = {key: key, data: d};
    RENDER[tab](d);
    setStatus("", false);
  } catch (err) {
    if (tokens[tab] !== token) return;
    state[tab] = null;
    setStatus("Сервер недоступен: " + err.message, true);
    renderError(tab, err);
  }
}

/* ---------- переключение вкладок и периода ---------- */
function titles() {
  return {
    overview: ["Обзор", (META ? META.company : "Компания") + " · данные: синтетика"],
    marketing: ["Маркетинг", "бюджет: план из Google-таблицы, факт из Excel-ведомости"],
    sales: ["Продажи", "воронка и сделки из CRM"],
    metrics: ["Метрики", "расчётные показатели · факт vs норматив"],
    settings: ["Настройки", "ключи API, ссылки на таблицы, нормативы"],
  };
}
function show(tab) {
  if (!document.getElementById("pane-" + tab)) tab = "overview";
  current = tab;
  TABS.forEach(t => { document.getElementById("pane-" + t).hidden = t !== tab; });
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.tab === tab));
  const t = titles()[tab];
  document.getElementById("title").textContent = t[0];
  document.getElementById("subtitle").textContent = t[1];
  ensureData(tab, false);
}

document.getElementById("period").addEventListener("change", e => {
  period = e.target.value;
  ["overview", "marketing", "metrics"].forEach(t => { state[t] = null; });
  ensureData(current, true);
});
window.addEventListener("hashchange", () => show(location.hash.slice(1)));

async function boot() {
  setStatus("Загрузка…", false);
  /* Ф5: кто вошёл — от этого зависят видимость «Настроек» и блок пользователя */
  try {
    const r = await fetch("/api/whoami");
    ME = await r.json();
  } catch (e) {
    ME = { user: null, role: null };
  }
  applyUserUI();
  try {
    META = await api("/api/meta");
  } catch (err) {
    setStatus("Сервер недоступен: " + err.message, true);
    TABS.forEach(t => renderError(t, err));
    return;
  }
  setStatus("", false);
  show(location.hash.slice(1) || "overview");
}
boot();
