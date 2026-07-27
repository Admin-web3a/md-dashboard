#!/usr/bin/env python3
"""
Money-Dick Funnel Dashboard Generator
Embeds raw lead data as JSON; all filtering and chart rendering is client-side.
Charts: daily leads, funnel (with UTM Content filter), UTM Source, landing version.
Table: media plan with dynamic fact column.
Run hourly via GitHub Actions.
"""

import urllib.request
import json
import os
import datetime

# ── Config ─────────────────────────────────────────────────────────────────────

TOKEN  = os.environ["AMO_TOKEN"]
DOMAIN = "simmihur.amocrm.ru"

PIPELINE_ID            = 11095182
UTM_SOURCE_FIELD_ID    = 1323539
UTM_CONTENT_FIELD_ID   = 1323545
MD_AB_VARIANT_FIELD_ID = 1323575

# 2026-07-23 00:00 MSK
CREATED_FROM = 1753228800

FUNNEL_STAGES = [
    (87129254, "Лид Создан"),
    (87129258, "Часть 1 открыта"),
    (87129262, "Часть 1 прочитана"),
    (87315330, "Часть 2 открыта"),
    (87315334, "Часть 2 прочитана"),
    (87315338, "Часть 3 открыта"),
    (87315342, "Часть 3 прочитана"),
    (87315346, "Увидел оффер"),
    (87315350, "Тариф выбран"),
    (87315354, "Checkout открыт"),
    (87315358, "Данные checkout отправлены"),
    (87315362, "Payment intent created"),
    (87315366, "Платёжная форма готова"),
    (87315370, "Оплата не прошла"),
    (87315374, "Оплачено"),
    (142,      "Успешно реализовано"),
]

STATUS_INDEX = {sid: i for i, (sid, _) in enumerate(FUNNEL_STAGES)}

EXCLUDED_STATUSES = {
    87129250,  # Неразобранное
    143,       # Закрыто и не реализовано
}

# ── AMO helpers ────────────────────────────────────────────────────────────────

def amo_get(path, params=None):
    url = f"https://{DOMAIN}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_all_leads():
    leads = []
    page = 1
    while True:
        data = amo_get("/api/v4/leads", {
            "page": page,
            "limit": 250,
            "filter[pipeline_id]": PIPELINE_ID,
            "filter[created_at][from]": CREATED_FROM,
        })
        batch = data.get("_embedded", {}).get("leads", [])
        if not batch:
            break
        leads.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return leads


def get_custom_field(lead, field_id):
    for cf in lead.get("custom_fields_values") or []:
        if cf["field_id"] == field_id:
            vals = cf.get("values") or []
            if vals:
                return str(vals[0].get("value") or "").strip()
    return None


def build_lead_record(lead):
    if lead.get("status_id") in EXCLUDED_STATUSES:
        return None
    status_idx = STATUS_INDEX.get(lead.get("status_id"))
    if status_idx is None:
        return None
    return {
        "c": lead.get("created_at", 0),                               # created_at unix ts
        "s": status_idx,                                               # funnel stage index
        "u": get_custom_field(lead, UTM_SOURCE_FIELD_ID) or "",        # utm_source
        "t": get_custom_field(lead, UTM_CONTENT_FIELD_ID) or "",       # utm_content
        "v": get_custom_field(lead, MD_AB_VARIANT_FIELD_ID) or "",     # A/B variant
    }


# ── HTML generation ────────────────────────────────────────────────────────────

def build_html(leads_raw):
    updated_str = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
                   .strftime("%d.%m.%Y %H:%M МСК"))

    records = [r for r in (build_lead_record(l) for l in leads_raw) if r]
    leads_json  = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    stages_json = json.dumps([name for _, name in FUNNEL_STAGES], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>Money-Dick Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg:     #0f0f0f;
    --card:   #1a1a1a;
    --border: #2a2a2a;
    --text:   #e8e8e8;
    --sub:    #888;
    --accent: #6c63ff;
    --green:  #4caf50;
    --orange: #ff9800;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 24px 20px;
  }}
  h1 {{ text-align: center; font-size: 1.5rem; margin-bottom: 4px; }}
  .subtitle {{ text-align: center; color: var(--sub); font-size: .85rem; margin-bottom: 20px; }}

  /* ── Date filter ── */
  .filter-bar {{
    display: flex; flex-wrap: wrap; justify-content: center;
    align-items: center; gap: 8px; margin-bottom: 28px;
  }}
  .preset-btn {{
    background: var(--card); border: 1px solid var(--border);
    color: var(--sub); border-radius: 6px; padding: 6px 14px;
    font-size: .85rem; cursor: pointer; transition: border-color .15s, color .15s;
  }}
  .preset-btn:hover {{ border-color: var(--accent); color: var(--text); }}
  .preset-btn.active {{ border-color: var(--accent); color: var(--accent); background: #1e1b3a; }}
  .date-sep {{ color: var(--sub); font-size: .85rem; }}
  input[type=date] {{
    background: var(--card); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 5px 10px;
    font-size: .85rem; cursor: pointer;
  }}
  input[type=date]:focus {{ outline: none; border-color: var(--accent); }}

  /* ── Stats ── */
  .stat-row {{
    display: flex; justify-content: center; gap: 16px;
    flex-wrap: wrap; margin-bottom: 32px;
  }}
  .stat {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 24px; text-align: center; min-width: 140px;
  }}
  .stat .val {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .stat .lbl {{ font-size: .8rem; color: var(--sub); margin-top: 4px; }}

  /* ── Cards & charts ── */
  .charts {{ display: flex; flex-direction: column; gap: 28px; max-width: 1000px; margin: 0 auto; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px 24px;
  }}
  .card h2 {{
    font-size: 1rem; margin-bottom: 16px; color: var(--text);
    padding-bottom: 10px; border-bottom: 1px solid var(--border);
  }}

  /* ── Media plan table ── */
  .plan-table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
  .plan-table th {{
    text-align: right; color: var(--sub); font-weight: 600;
    padding: 8px 12px; border-bottom: 1px solid var(--border); white-space: nowrap;
  }}
  .plan-table th:first-child {{ text-align: left; }}
  .plan-table td {{
    padding: 7px 12px; border-bottom: 1px solid #222;
    text-align: right; white-space: nowrap;
  }}
  .plan-table td:first-child {{ text-align: left; color: var(--text); }}
  .plan-table tr.section-header td {{
    background: #1f1f2e; color: var(--accent); font-weight: 600;
    font-size: .8rem; letter-spacing: .04em; text-transform: uppercase;
    padding: 6px 12px; text-align: left;
  }}
  .plan-table .col-prev {{ color: #666; }}
  .plan-table .col-avg  {{ color: #888; }}
  .plan-table .col-tgt  {{ color: #aaa; }}
  .fact-green  {{ color: #4caf50 !important; font-weight: 700; }}
  .fact-orange {{ color: #ff9800 !important; font-weight: 700; }}
  .fact-red    {{ color: #f44336 !important; font-weight: 700; }}
  .fact-neutral {{ color: var(--text); font-weight: 700; }}

  .footer {{ text-align: center; color: var(--sub); font-size: .75rem; margin-top: 32px; }}
</style>
</head>
<body>

<h1>📊 Money-Dick Dashboard</h1>
<p class="subtitle">Обновлено: {updated_str}</p>

<div class="filter-bar">
  <button class="preset-btn" data-preset="today">Сегодня</button>
  <button class="preset-btn" data-preset="7d">7 дней</button>
  <button class="preset-btn active" data-preset="30d">30 дней</button>
  <button class="preset-btn" data-preset="all">Весь период</button>
  <span class="date-sep">|</span>
  <input type="date" id="dateFrom">
  <span class="date-sep">—</span>
  <input type="date" id="dateTo">
</div>

<div class="stat-row">
  <div class="stat"><div class="val" id="statTotal">—</div><div class="lbl">Всего лидов</div></div>
  <div class="stat"><div class="val" id="statPaid" style="color:var(--green)">—</div><div class="lbl">Оплатили</div></div>
  <div class="stat"><div class="val" id="statConv" style="color:var(--orange)">—</div><div class="lbl">Конверсия в оплату</div></div>
</div>

<div class="charts">

  <div class="card">
    <h2>Лиды по дням</h2>
    <div style="position:relative;height:260px"><canvas id="dailyChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Воронка: сколько лидов прошли через каждый этап</h2>
    <div id="contentFilterBar" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px"></div>
    <div style="position:relative;height:420px"><canvas id="funnelChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Распределение по UTM Source</h2>
    <div style="position:relative;height:300px"><canvas id="utmChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Версия лендинга (MD A/B Variant)</h2>
    <div id="sourceFilterBar" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px"></div>
    <div style="position:relative;height:280px"><canvas id="versionChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Медиаплан</h2>
    <div style="overflow-x:auto">
      <table class="plan-table">
        <thead>
          <tr>
            <th style="min-width:200px;text-align:left">Показатель</th>
            <th>Факт (прошлый)</th>
            <th>Усредненный</th>
            <th>Целевой</th>
            <th>Факт</th>
          </tr>
        </thead>
        <tbody id="planTableBody"></tbody>
      </table>
    </div>
  </div>

</div>

<p class="footer">Данные из amoCRM · автообновление каждый час</p>

<script>
const ALL_LEADS   = {leads_json};
const STAGE_NAMES = {stages_json};
const DATA_FROM   = {CREATED_FROM};

const C = {{
  purple: 'rgba(108,99,255,0.85)', green:  'rgba(76,175,80,0.85)',
  blue:   'rgba(33,150,243,0.85)', orange: 'rgba(255,152,0,0.85)',
  pink:   'rgba(233,30,99,0.85)',  teal:   'rgba(0,188,212,0.85)',
}};
const PALETTE = [C.purple, C.blue, C.green, C.orange, C.pink, C.teal,
  'rgba(255,235,59,.85)','rgba(121,85,72,.85)','rgba(96,125,139,.85)',
  'rgba(244,67,54,.85)','rgba(156,39,176,.85)','rgba(3,169,244,.85)'];

Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#2a2a2a';

// ── Chart instances ───────────────────────────────────────────────────────────

const dailyChart = new Chart(document.getElementById('dailyChart'), {{
  type: 'bar',
  data: {{ labels: [], datasets: [{{ label: 'Лидов создано', data: [], backgroundColor: C.teal, borderRadius: 4 }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y}} лидов` }} }} }},
    scales: {{ y: {{ beginAtZero: true, ticks: {{ precision: 0 }}, grid: {{ color: '#2a2a2a' }} }}, x: {{ grid: {{ display: false }} }} }}
  }}
}});

const funnelChart = new Chart(document.getElementById('funnelChart'), {{
  type: 'bar',
  data: {{ labels: STAGE_NAMES, datasets: [{{ label: 'Лидов прошло через этап', data: [], backgroundColor: C.purple, borderRadius: 4 }}] }},
  options: {{
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.x}} лидов` }} }} }},
    scales: {{ x: {{ beginAtZero: true, grid: {{ color: '#2a2a2a' }} }}, y: {{ grid: {{ display: false }} }} }}
  }}
}});

const utmChart = new Chart(document.getElementById('utmChart'), {{
  type: 'bar',
  data: {{ labels: [], datasets: [{{ label: 'Лидов', data: [], backgroundColor: [], borderRadius: 4 }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y}} лидов` }} }} }},
    scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#2a2a2a' }} }}, x: {{ grid: {{ display: false }} }} }}
  }}
}});

const versionChart = new Chart(document.getElementById('versionChart'), {{
  type: 'pie',
  data: {{ labels: [], datasets: [{{ data: [], backgroundColor: [], borderColor: '#1a1a1a', borderWidth: 2 }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right', labels: {{ color: '#e8e8e8', padding: 16 }} }},
      tooltip: {{ callbacks: {{ label: ctx => {{
        const total = ctx.dataset.data.reduce((a,b) => a+b, 0);
        return ` ${{ctx.label}}: ${{ctx.parsed}} лидов (${{(ctx.parsed/total*100).toFixed(1)}}%)`;
      }} }} }}
    }}
  }}
}});

// ── State ─────────────────────────────────────────────────────────────────────
let currentLeads  = [];
let activeSource  = '__all__';
let activeContent = '__all__';

// ── Helpers ───────────────────────────────────────────────────────────────────
function toMidnightTs(dateStr) {{
  const [y,m,d] = dateStr.split('-').map(Number);
  return Date.UTC(y, m-1, d) / 1000 - 3*3600;
}}
function todayStr() {{
  return new Date().toLocaleDateString('sv-SE', {{timeZone:'Europe/Moscow'}});
}}
function nDaysAgoStr(n) {{
  const d = new Date();
  d.setDate(d.getDate() - n + 1);
  return d.toLocaleDateString('sv-SE', {{timeZone:'Europe/Moscow'}});
}}
function mskDate(ts) {{
  return new Date((ts + 3*3600)*1000).toISOString().slice(0,10);
}}

// ── Filter buttons builder ────────────────────────────────────────────────────
function buildFilterButtons(containerId, leads, keyFn, activeVal, onSelect, minCount = 0) {{
  const counts = {{}};
  leads.forEach(l => {{ const k = keyFn(l); if (k) counts[k] = (counts[k]||0)+1; }});
  const values = Object.keys(counts).filter(k => counts[k] >= minCount).sort();
  const bar = document.getElementById(containerId);
  bar.innerHTML = '';
  ['__all__', ...values].forEach(val => {{
    const btn = document.createElement('button');
    btn.className = 'preset-btn' + (val === activeVal ? ' active' : '');
    btn.textContent = val === '__all__' ? 'Все' : val;
    btn.dataset.val = val;
    btn.addEventListener('click', () => {{
      bar.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      onSelect(val);
    }});
    bar.appendChild(btn);
  }});
}}

// ── Main render ───────────────────────────────────────────────────────────────
function render(leads) {{
  currentLeads = leads;

  // Daily chart
  const dayMap = {{}};
  leads.forEach(l => {{ const day = mskDate(l.c); dayMap[day] = (dayMap[day]||0) + 1; }});
  const days = Object.keys(dayMap).sort();
  dailyChart.data.labels = days.map(d => d.slice(5));
  dailyChart.data.datasets[0].data = days.map(d => dayMap[d]);
  dailyChart.update();

  // Summary
  const n = leads.length;
  const paid = leads.filter(l => l.s >= 14).length;
  document.getElementById('statTotal').textContent = n;
  document.getElementById('statPaid').textContent  = paid;
  document.getElementById('statConv').textContent  = n ? (paid/n*100).toFixed(1)+'%' : '—';

  // UTM Source chart
  const utmMap = {{}};
  leads.forEach(l => {{ utmMap[l.u||'(не указан)'] = (utmMap[l.u||'(не указан)']||0)+1; }});
  const utmSorted = Object.entries(utmMap).sort((a,b) => b[1]-a[1]);
  utmChart.data.labels = utmSorted.map(e => e[0]);
  utmChart.data.datasets[0].data = utmSorted.map(e => e[1]);
  utmChart.data.datasets[0].backgroundColor = utmSorted.map((_,i) => PALETTE[i%PALETTE.length]);
  utmChart.update();

  // UTM Content filter (funnel)
  buildFilterButtons('contentFilterBar', leads, l => l.t, activeContent, val => {{
    activeContent = val;
    renderFunnel(leads);
  }}, 5);
  renderFunnel(leads);

  // UTM Source filter (version chart)
  buildFilterButtons('sourceFilterBar', leads, l => l.u, activeSource, val => {{
    activeSource = val;
    renderVersionChart(leads);
  }});
  renderVersionChart(leads);

  renderMediaPlan(leads);
}}

function renderFunnel(leads) {{
  const filtered = activeContent === '__all__'
    ? leads
    : leads.filter(l => l.t === activeContent);
  const data = STAGE_NAMES.map((_,i) => filtered.filter(l => l.s >= i).length);
  funnelChart.data.datasets[0].data = data;
  funnelChart.update();
}}

function renderVersionChart(leads) {{
  const filtered = activeSource === '__all__'
    ? leads
    : leads.filter(l => (l.u||'(не указан)') === activeSource);
  const verMap = {{'1 версия': 0, '2 версия': 0, 'Не определено': 0}};
  filtered.forEach(l => {{
    if (l.v === 'A')      verMap['1 версия']++;
    else if (l.v === 'B') verMap['2 версия']++;
    else                  verMap['Не определено']++;
  }});
  const entries = Object.entries(verMap).filter(e => e[1] > 0);
  versionChart.data.labels = entries.map(e => e[0]);
  versionChart.data.datasets[0].data = entries.map(e => e[1]);
  versionChart.data.datasets[0].backgroundColor = entries.map(e =>
    e[0]==='1 версия' ? C.green : e[0]==='2 версия' ? C.blue : 'rgba(136,136,136,.85)'
  );
  versionChart.update();
}}

// ── Media plan ────────────────────────────────────────────────────────────────
const PLAN_ROWS = [
  {{section: 'Прогрев (статьи)'}},
  {{label:'Регистрации',              key:'regs',      fmt:'n', prev:199,   avg:254,  tgt:313}},
  {{label:'Конверсия в статью 1',     key:'conv1',     fmt:'%', prev:0.40,  avg:0.95, tgt:0.95}},
  {{label:'Дочитали статью 1',        key:'read1',     fmt:'n', prev:79,    avg:241,  tgt:297}},
  {{label:'Конверсия в статью 2',     key:'conv2',     fmt:'%', prev:1.13,  avg:0.70, tgt:0.70}},
  {{label:'Дочитали статью 2',        key:'read2',     fmt:'n', prev:90,    avg:169,  tgt:208}},
  {{label:'Конверсия в статью 3',     key:'conv3',     fmt:'%', prev:1.00,  avg:0.85, tgt:0.85}},
  {{label:'Дочитали статью 3',        key:'read3',     fmt:'n', prev:90,    avg:143,  tgt:177}},
  {{section: 'Продажи и конверсии'}},
  {{label:'Конверсия в заказ',        key:'convOrder', fmt:'%', prev:0.038, avg:0.10, tgt:0.12}},
  {{label:'Заказы',                   key:'orders',    fmt:'n', prev:3,     avg:14,   tgt:21}},
  {{label:'Конверсия заказа в оплату',key:'convPay',   fmt:'%', prev:0.33,  avg:0.50, tgt:0.50}},
  {{label:'Покупки AFK',              key:'purchases', fmt:'n', prev:1,     avg:7,    tgt:11}},
];

function calcFact(leads) {{
  const regs   = leads.length;
  const read1  = leads.filter(l => l.s >= 2).length;
  const read2  = leads.filter(l => l.s >= 4).length;
  const read3  = leads.filter(l => l.s >= 6).length;
  const orders = leads.filter(l => l.s >= 12).length;
  const purch  = leads.filter(l => l.s >= 14).length;
  return {{
    regs, read1, read2, read3, orders, purchases: purch,
    conv1:     regs   ? read1/regs   : null,
    conv2:     read1  ? read2/read1  : null,
    conv3:     read2  ? read3/read2  : null,
    convOrder: read3  ? orders/read3 : null,
    convPay:   orders ? purch/orders : null,
  }};
}}

function fmtV(v, fmt) {{
  if (v === null || v === undefined) return '—';
  return fmt === '%' ? (v*100).toFixed(1)+'%' : v;
}}

function factCls(v, avg, tgt) {{
  if (v === null || v === undefined) return 'fact-neutral';
  if (v >= tgt) return 'fact-green';
  if (v >= avg) return 'fact-orange';
  return 'fact-red';
}}

function renderMediaPlan(leads) {{
  const fact = calcFact(leads);
  const tbody = document.getElementById('planTableBody');
  tbody.innerHTML = '';
  PLAN_ROWS.forEach(row => {{
    const tr = document.createElement('tr');
    if (row.section) {{
      tr.className = 'section-header';
      tr.innerHTML = `<td colspan="5">${{row.section}}</td>`;
    }} else {{
      const fv = fact[row.key];
      tr.innerHTML = `
        <td>${{row.label}}</td>
        <td class="col-prev">${{fmtV(row.prev, row.fmt)}}</td>
        <td class="col-avg">${{fmtV(row.avg,  row.fmt)}}</td>
        <td class="col-tgt">${{fmtV(row.tgt,  row.fmt)}}</td>
        <td class="${{factCls(fv, row.avg, row.tgt)}}">${{fmtV(fv, row.fmt)}}</td>`;
    }}
    tbody.appendChild(tr);
  }});
}}

// ── Date presets ──────────────────────────────────────────────────────────────
function applyFilter() {{
  const from  = toMidnightTs(document.getElementById('dateFrom').value);
  const toVal = toMidnightTs(document.getElementById('dateTo').value) + 86399;
  render(ALL_LEADS.filter(l => l.c >= from && l.c <= toVal));
}}

document.querySelectorAll('.preset-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const today = todayStr();
    const p = btn.dataset.preset;
    if (p === 'today') {{
      document.getElementById('dateFrom').value = today;
      document.getElementById('dateTo').value   = today;
    }} else if (p === '7d') {{
      document.getElementById('dateFrom').value = nDaysAgoStr(7);
      document.getElementById('dateTo').value   = today;
    }} else if (p === '30d') {{
      document.getElementById('dateFrom').value = nDaysAgoStr(30);
      document.getElementById('dateTo').value   = today;
    }} else {{
      const d = new Date(DATA_FROM * 1000);
      document.getElementById('dateFrom').value = d.toLocaleDateString('sv-SE', {{timeZone:'Europe/Moscow'}});
      document.getElementById('dateTo').value   = today;
    }}
    applyFilter();
  }});
}});

['dateFrom','dateTo'].forEach(id => {{
  document.getElementById(id).addEventListener('change', () => {{
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    applyFilter();
  }});
}});

document.querySelector('[data-preset="30d"]').click();
</script>
</body>
</html>"""


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching leads from AMO…")
    leads = fetch_all_leads()
    print(f"  Total fetched: {len(leads)}")

    os.makedirs("docs", exist_ok=True)
    html = build_html(leads)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved docs/index.html ({len(html):,} bytes)")
