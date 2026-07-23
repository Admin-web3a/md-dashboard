#!/usr/bin/env python3
"""
Money-Dick Funnel Dashboard Generator
Generates docs/index.html with three Chart.js charts:
  1. Cumulative funnel by status (how many leads passed through each stage)
  2. UTM Source distribution (bar chart)
  3. Landing page version (MD Last Event: part_1_opened vs part_2_opened)
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

PIPELINE_ID   = 11095182   # Money-Dick
UTM_SOURCE_FIELD_ID  = 1323539
MD_LAST_EVENT_FIELD_ID = 1323553

# July 23, 2026 00:00 MSK = July 22 21:00 UTC
CREATED_FROM = 1753228800

# Statuses ordered by funnel stage (excluding Неразобранное and Закрыто и не реализовано)
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

# Map status_id → funnel index (0-based)
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


# ── Stats calculation ──────────────────────────────────────────────────────────

def calc_stats(leads):
    # Only leads in known funnel statuses (exclude Неразобранное and Закрыто)
    active_leads = [l for l in leads if l.get("status_id") not in EXCLUDED_STATUSES]

    # Graph 1: cumulative funnel
    # For each stage index i, count leads whose current status index >= i
    stage_indices = []
    for lead in active_leads:
        idx = STATUS_INDEX.get(lead.get("status_id"))
        if idx is not None:
            stage_indices.append(idx)

    funnel_counts = []
    for i in range(len(FUNNEL_STAGES)):
        count = sum(1 for idx in stage_indices if idx >= i)
        funnel_counts.append(count)

    # Graph 2: UTM Source distribution
    utm_counter = Counter()
    for lead in active_leads:
        utm = get_custom_field(lead, UTM_SOURCE_FIELD_ID) or "(не указан)"
        utm_counter[utm] += 1

    utm_sorted = utm_counter.most_common()

    # Graph 3: MD Last Event (landing version)
    version_counter = Counter()
    for lead in active_leads:
        event = get_custom_field(lead, MD_LAST_EVENT_FIELD_ID)
        if event == "part_1_opened":
            version_counter["1 версия"] += 1
        elif event == "part_2_opened":
            version_counter["2 версия"] += 1
        else:
            version_counter["Не определено"] += 1

    return {
        "total": len(active_leads),
        "funnel_counts": funnel_counts,
        "utm": utm_sorted,
        "versions": dict(version_counter),
    }


# ── HTML generation ────────────────────────────────────────────────────────────

def build_html(stats):
    updated_str = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
                   .strftime("%d.%m.%Y %H:%M МСК"))

    funnel_labels = json.dumps([name for _, name in FUNNEL_STAGES], ensure_ascii=False)
    funnel_data   = json.dumps(stats["funnel_counts"])

    utm_labels = json.dumps([k for k, _ in stats["utm"]], ensure_ascii=False)
    utm_data   = json.dumps([v for _, v in stats["utm"]])

    ver_labels = json.dumps(list(stats["versions"].keys()), ensure_ascii=False)
    ver_data   = json.dumps(list(stats["versions"].values()))

    total = stats["total"]

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
    --bg: #0f0f0f;
    --card: #1a1a1a;
    --border: #2a2a2a;
    --text: #e8e8e8;
    --sub: #888;
    --accent: #6c63ff;
    --green: #4caf50;
    --orange: #ff9800;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 24px 20px;
  }}
  h1 {{
    text-align: center;
    font-size: 1.5rem;
    margin-bottom: 4px;
  }}
  .subtitle {{
    text-align: center;
    color: var(--sub);
    font-size: .85rem;
    margin-bottom: 28px;
  }}
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
  .stat .val {{
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
  }}
  .stat .lbl {{
    font-size: .8rem;
    color: var(--sub);
    margin-top: 4px;
  }}
  .charts {{
    display: flex;
    flex-direction: column;
    gap: 28px;
    max-width: 1000px;
    margin: 0 auto;
  }}
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
  .chart-wrap {{
    position: relative;
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
<p class="subtitle">Воронка с 23 июля 2026 · Обновлено: {updated_str}</p>

<div class="stat-row">
  <div class="stat">
    <div class="val">{total}</div>
    <div class="lbl">Всего лидов</div>
  </div>
  <div class="stat">
    <div class="val" style="color:var(--green)">{stats["funnel_counts"][-1] if stats["funnel_counts"] else 0}</div>
    <div class="lbl">Оплатили</div>
  </div>
  <div class="stat">
    <div class="val" style="color:var(--orange)">{f'{stats["funnel_counts"][-1]/total*100:.1f}%' if total else '—'}</div>
    <div class="lbl">Конверсия в оплату</div>
  </div>
</div>

<div class="charts">

  <div class="card">
    <h2>Воронка: сколько лидов прошли через каждый этап</h2>
    <div class="chart-wrap" style="height:420px">
      <canvas id="funnelChart"></canvas>
    </div>
  </div>

  <div class="card">
    <h2>Распределение по UTM Source</h2>
    <div class="chart-wrap" style="height:300px">
      <canvas id="utmChart"></canvas>
    </div>
  </div>

  <div class="card">
    <h2>Версия лендинга (MD Last Event)</h2>
    <div class="chart-wrap" style="height:280px">
      <canvas id="versionChart"></canvas>
    </div>
  </div>

</div>

<p class="footer">Данные из amoCRM · автообновление каждый час</p>

<script>
const PURPLE  = 'rgba(108,99,255,0.85)';
const GREEN   = 'rgba(76,175,80,0.85)';
const ORANGE  = 'rgba(255,152,0,0.85)';
const BLUE    = 'rgba(33,150,243,0.85)';
const PINK    = 'rgba(233,30,99,0.85)';
const TEAL    = 'rgba(0,188,212,0.85)';

const PALETTE = [PURPLE, BLUE, GREEN, ORANGE, PINK, TEAL,
  'rgba(255,235,59,.85)', 'rgba(121,85,72,.85)', 'rgba(96,125,139,.85)',
  'rgba(244,67,54,.85)', 'rgba(156,39,176,.85)', 'rgba(3,169,244,.85)'];

Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#2a2a2a';

// Chart 1 — Funnel (horizontal bar)
new Chart(document.getElementById('funnelChart'), {{
  type: 'bar',
  data: {{
    labels: {funnel_labels},
    datasets: [{{
      label: 'Лидов прошло через этап',
      data: {funnel_data},
      backgroundColor: PURPLE,
      borderRadius: 4,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.x}} лидов`
        }}
      }}
    }},
    scales: {{
      x: {{ beginAtZero: true, grid: {{ color: '#2a2a2a' }} }},
      y: {{ grid: {{ display: false }} }}
    }}
  }}
}});

// Chart 2 — UTM Source (bar)
new Chart(document.getElementById('utmChart'), {{
  type: 'bar',
  data: {{
    labels: {utm_labels},
    datasets: [{{
      label: 'Лидов',
      data: {utm_data},
      backgroundColor: {utm_labels}.map((_, i) => PALETTE[i % PALETTE.length]),
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.y}} лидов`
        }}
      }}
    }},
    scales: {{
      y: {{ beginAtZero: true, grid: {{ color: '#2a2a2a' }} }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});

// Chart 3 — Landing version (pie)
const verLabels = {ver_labels};
const verColors = verLabels.map((l, i) => {{
  if (l === '1 версия') return GREEN;
  if (l === '2 версия') return BLUE;
  return 'rgba(136,136,136,.85)';
}});
new Chart(document.getElementById('versionChart'), {{
  type: 'pie',
  data: {{
    labels: verLabels,
    datasets: [{{
      data: {ver_data},
      backgroundColor: verColors,
      borderColor: '#1a1a1a',
      borderWidth: 2,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{
        position: 'right',
        labels: {{ color: '#e8e8e8', padding: 16 }}
      }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.label}}: ${{ctx.parsed}} лидов (${{(ctx.parsed / ctx.dataset.data.reduce((a,b)=>a+b,0)*100).toFixed(1)}}%)`
        }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching leads from AMO…")
    leads = fetch_all_leads()
    print(f"  Total fetched: {len(leads)}")

    stats = calc_stats(leads)
    print(f"  Active leads: {stats['total']}")
    print(f"  Funnel top: {stats['funnel_counts'][0] if stats['funnel_counts'] else 0}")
    print(f"  Paid: {stats['funnel_counts'][-1] if stats['funnel_counts'] else 0}")

    os.makedirs("docs", exist_ok=True)
    html = build_html(stats)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved docs/index.html ({len(html):,} bytes)")
