#!/usr/bin/env python3
"""
Money-Dick Funnel Dashboard Generator
Embeds raw lead data as JSON; all filtering and chart rendering is client-side.
Three charts:
  1. Cumulative funnel by status
  2. UTM Source distribution (bar)
  3. Landing page version: MD A/B Variant (pie)
Run hourly via GitHub Actions.
"""

import urllib.request
import json
import os
import datetime
from collections import Counter

# ── Config ─────────────────────────────────────────────────────────────────────

TOKEN  = os.environ["AMO_TOKEN"]
DOMAIN = "simmihur.amocrm.ru"

PIPELINE_ID            = 11095182   # Money-Dick
UTM_SOURCE_FIELD_ID    = 1323539
MD_AB_VARIANT_FIELD_ID = 1323575

# Fetch leads created from this date onwards (2026-07-23 00:00 MSK)
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
    """Returns a compact dict for client-side JS consumption."""
    if lead.get("status_id") in EXCLUDED_STATUSES:
        return None
    status_idx = STATUS_INDEX.get(lead.get("status_id"))
    if status_idx is None:
        return None
    utm = get_custom_field(lead, UTM_SOURCE_FIELD_ID) or ""
    variant = get_custom_field(lead, MD_AB_VARIANT_FIELD_ID) or ""
    return {
        "c": lead.get("created_at", 0),   # unix timestamp
        "s": status_idx,                   # funnel stage index
        "u": utm,                          # utm_source
        "v": variant,                      # A/B variant
    }


# ── HTML generation ────────────────────────────────────────────────────────────

def build_html(leads_raw):
    updated_str = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
                   .strftime("%d.%m.%Y %H:%M МСК"))

    records = [r for r in (build_lead_record(l) for l in leads_raw) if r]
    leads_json    = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    stages_json   = json.dumps([name for _, name in FUNNEL_STAGES], ensure_ascii=False)
    created_from  = CREATED_FROM  # for JS "All time" preset lower bound

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
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-bottom: 28px;
  }}
  .preset-btn {{
    background: var(--card);
    border: 1px solid var(--border);
    color: var(--sub);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: .85rem;
    cursor: pointer;
    transition: border-color .15s, color .15s;
  }}
  .preset-btn:hover {{ border-color: var(--accent); color: var(--text); }}
  .preset-btn.active {{ border-color: var(--accent); color: var(--accent); background: #1e1b3a; }}
  .date-sep {{ color: var(--sub); font-size: .85rem; }}
  input[type=date] {{
    background: var(--card);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: .85rem;
    cursor: pointer;
  }}
  input[type=date]:focus {{ outline: none; border-color: var(--accent); }}

  /* ── Stats ── */
  .stat-row {{
    display: flex;
    justify-content: center;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 32px;
  }}
  .stat {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 24px;
    text-align: center;
    min-width: 140px;
  }}
  .stat .val {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .stat .lbl {{ font-size: .8rem; color: var(--sub); margin-top: 4px; }}

  /* ── Charts ── */
  .charts {{ display: flex; flex-direction: column; gap: 28px; max-width: 1000px; margin: 0 auto; }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
  }}
  .card h2 {{
    font-size: 1rem;
    margin-bottom: 16px;
    color: var(--text);
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}
  .footer {{
    text-align: center;
    color: var(--sub);
    font-size: .75rem;
    margin-top: 32px;
  }}
</style>
</head>
<body>

<h1>📊 Money-Dick Dashboard</h1>
<p class="subtitle">Обновлено: {updated_str}</p>

<!-- Date filter -->
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

<!-- Summary -->
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
</div>

<p class="footer">Данные из amoCRM · автообновление каждый час</p>

<script>
// ── Raw data embedded by Python ──────────────────────────────────────────────
const ALL_LEADS   = {leads_json};
const STAGE_NAMES = {stages_json};
const DATA_FROM   = {created_from};  // earliest possible lead unix ts

// ── Colors ───────────────────────────────────────────────────────────────────
const C = {{
  purple: 'rgba(108,99,255,0.85)',
  green:  'rgba(76,175,80,0.85)',
  blue:   'rgba(33,150,243,0.85)',
  orange: 'rgba(255,152,0,0.85)',
  pink:   'rgba(233,30,99,0.85)',
  teal:   'rgba(0,188,212,0.85)',
}};
const PALETTE = [C.purple, C.blue, C.green, C.orange, C.pink, C.teal,
  'rgba(255,235,59,.85)','rgba(121,85,72,.85)','rgba(96,125,139,.85)',
  'rgba(244,67,54,.85)','rgba(156,39,176,.85)','rgba(3,169,244,.85)'];

Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#2a2a2a';

// ── Chart instances ──────────────────────────────────────────────────────────
const dailyChart = new Chart(document.getElementById('dailyChart'), {{
  type: 'bar',
  data: {{ labels: [], datasets: [{{ label: 'Лидов создано', data: [], backgroundColor: C.teal, borderRadius: 4 }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y}} лидов` }} }} }},
    scales: {{
      y: {{ beginAtZero: true, ticks: {{ precision: 0 }}, grid: {{ color: '#2a2a2a' }} }},
      x: {{ grid: {{ display: false }} }}
    }}
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
        const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
        return ` ${{ctx.label}}: ${{ctx.parsed}} лидов (${{(ctx.parsed / total * 100).toFixed(1)}}%)`;
      }} }} }}
    }}
  }}
}});

// ── Filtering & rendering ────────────────────────────────────────────────────
function toMidnightTs(dateStr) {{
  // dateStr: "YYYY-MM-DD", returns unix ts at 00:00:00 UTC+3
  const [y, m, d] = dateStr.split('-').map(Number);
  return Date.UTC(y, m - 1, d) / 1000 - 3 * 3600;
}}

function todayStr() {{
  return new Date().toLocaleDateString('sv-SE', {{ timeZone: 'Europe/Moscow' }});
}}

function nDaysAgoStr(n) {{
  const d = new Date();
  d.setDate(d.getDate() - n + 1);
  return d.toLocaleDateString('sv-SE', {{ timeZone: 'Europe/Moscow' }});
}}

function applyFilter() {{
  const from = toMidnightTs(document.getElementById('dateFrom').value);
  const toStr = document.getElementById('dateTo').value;
  // end of day = next day 00:00 minus 1 sec
  const to   = toMidnightTs(toStr) + 86399;
  render(ALL_LEADS.filter(l => l.c >= from && l.c <= to));
}}

function mskDate(ts) {{
  // Convert unix ts to YYYY-MM-DD in Moscow time (UTC+3)
  const d = new Date((ts + 3 * 3600) * 1000);
  return d.toISOString().slice(0, 10);
}}

function render(leads) {{
  currentLeads = leads;
  buildSourceButtons(leads);
  const n = leads.length;

  // Daily chart
  const dayMap = {{}};
  leads.forEach(l => {{ const day = mskDate(l.c); dayMap[day] = (dayMap[day] || 0) + 1; }});
  const days = Object.keys(dayMap).sort();
  dailyChart.data.labels = days.map(d => d.slice(5));  // show MM-DD
  dailyChart.data.datasets[0].data = days.map(d => dayMap[d]);
  dailyChart.update();

  // Funnel: for each stage i, count leads with status_idx >= i
  const funnelData = STAGE_NAMES.map((_, i) => leads.filter(l => l.s >= i).length);
  const paid = funnelData[funnelData.length - 1] || 0;

  document.getElementById('statTotal').textContent = n;
  document.getElementById('statPaid').textContent  = paid;
  document.getElementById('statConv').textContent  = n ? (paid / n * 100).toFixed(1) + '%' : '—';

  funnelChart.data.datasets[0].data = funnelData;
  funnelChart.update();

  // UTM Source
  const utmMap = {{}};
  leads.forEach(l => {{ utmMap[l.u || '(не указан)'] = (utmMap[l.u || '(не указан)'] || 0) + 1; }});
  const utmSorted = Object.entries(utmMap).sort((a, b) => b[1] - a[1]);
  utmChart.data.labels = utmSorted.map(e => e[0]);
  utmChart.data.datasets[0].data = utmSorted.map(e => e[1]);
  utmChart.data.datasets[0].backgroundColor = utmSorted.map((_, i) => PALETTE[i % PALETTE.length]);
  utmChart.update();

  renderVersionChart(leads);
}}

// ── Preset buttons ───────────────────────────────────────────────────────────
document.querySelectorAll('.preset-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const today = todayStr();
    const preset = btn.dataset.preset;
    if (preset === 'today') {{
      document.getElementById('dateFrom').value = today;
      document.getElementById('dateTo').value   = today;
    }} else if (preset === '7d') {{
      document.getElementById('dateFrom').value = nDaysAgoStr(7);
      document.getElementById('dateTo').value   = today;
    }} else if (preset === '30d') {{
      document.getElementById('dateFrom').value = nDaysAgoStr(30);
      document.getElementById('dateTo').value   = today;
    }} else {{
      // All time — from DATA_FROM
      const d = new Date(DATA_FROM * 1000);
      document.getElementById('dateFrom').value = d.toLocaleDateString('sv-SE', {{ timeZone: 'Europe/Moscow' }});
      document.getElementById('dateTo').value   = today;
    }}
    applyFilter();
  }});
}});

// Manual date change clears preset highlight
['dateFrom', 'dateTo'].forEach(id => {{
  document.getElementById(id).addEventListener('change', () => {{
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    applyFilter();
  }});
}});

// ── Source filter for version chart ─────────────────────────────────────────
let activeSource = '__all__';

function buildSourceButtons(leads) {{
  const sources = [...new Set(leads.map(l => l.u || '(не указан)'))].sort();
  const bar = document.getElementById('sourceFilterBar');
  bar.innerHTML = '';

  ['__all__', ...sources].forEach(src => {{
    const btn = document.createElement('button');
    btn.className = 'preset-btn' + (src === activeSource ? ' active' : '');
    btn.textContent = src === '__all__' ? 'Все источники' : src;
    btn.dataset.src = src;
    btn.addEventListener('click', () => {{
      activeSource = src;
      bar.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderVersionChart(currentLeads);
    }});
    bar.appendChild(btn);
  }});
}}

let currentLeads = [];

function renderVersionChart(leads) {{
  const filtered = activeSource === '__all__'
    ? leads
    : leads.filter(l => (l.u || '(не указан)') === activeSource);

  const verMap = {{ '1 версия': 0, '2 версия': 0, 'Не определено': 0 }};
  filtered.forEach(l => {{
    if (l.v === 'A')      verMap['1 версия']++;
    else if (l.v === 'B') verMap['2 версия']++;
    else                  verMap['Не определено']++;
  }});
  const verEntries = Object.entries(verMap).filter(e => e[1] > 0);
  versionChart.data.labels = verEntries.map(e => e[0]);
  versionChart.data.datasets[0].data = verEntries.map(e => e[1]);
  versionChart.data.datasets[0].backgroundColor = verEntries.map(e =>
    e[0] === '1 версия' ? C.green : e[0] === '2 версия' ? C.blue : 'rgba(136,136,136,.85)'
  );
  versionChart.update();
}}

// ── Init: trigger "30 days" preset ──────────────────────────────────────────
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
