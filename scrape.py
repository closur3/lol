import requests
import json
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

# --- 配置区 ---
TOURNAMENTS = [
    {"slug": "2026-lck-cup", "title": "2026 LCK Cup", "url": "https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/"},
    {"slug": "2026-lpl-split-1", "title": "2026 LPL Split 1", "url": "https://gol.gg/tournament/tournament-matchlist/LPL%202026%20Split%201/"},
]
INDEX_FILE = Path("index.html")
TEAMS_JSON = Path("teams.json")
GITHUB_REPO = "https://github.com/closur3/lol"

# 列索引常量
COL_TEAM = 0
COL_BO3_PCT = 2
COL_BO5_PCT = 4
COL_SERIES_WR = 6
COL_GAME_WR = 8
COL_STREAK = 9
COL_LAST_DATE = 10

def load_team_map():
    if TEAMS_JSON.exists():
        try: return json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
        except: pass
    return {}

TEAM_MAP = load_team_map()

def get_short_name(full_name):
    name_upper = full_name.upper()
    for key, short_val in TEAM_MAP.items():
        if key.upper() in name_upper: return short_val
    return full_name.replace("Esports", "").replace("Gaming", "").replace("Academy", "").replace("Team", "").strip()

def rate(n, d): return n / d if d > 0 else None
def pct(r): return f"{r*100:.1f}%" if r is not None else "-"

def get_cell_style(value, ratio=None, is_pct=False, reverse=False):
    """统一处理无数据时的灰色样式"""
    if value == "-" or value is None or value == "":
        return 'style="background:#f1f5f9;color:#cbd5e1"'
    if is_pct:
        hue = (1 - max(0, min(1, ratio))) * 140 if reverse else max(0, min(1, ratio)) * 140
        return f'style="background:hsl({int(hue)}, 65%, 48%);color:white;font-weight:bold"'
    return ""

def scrape(tournament):
    print(f"Scraping {tournament['title']}...")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(tournament["url"], headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
    except: return {}

    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, "bo5_full": 0, "bo5_total": 0, 
        "series_wins": 0, "series_total": 0, "game_wins": 0, "game_total": 0, 
        "streak_wins": 0, "streak_losses": 0, "streak_dirty": False, "last_date": None
    })

    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 5: continue
        t1, t2, score_raw = get_short_name(cells[1].text), get_short_name(cells[3].text), cells[2].text.strip()
        try: s_date = datetime.strptime(cells[-1].text.strip(), "%Y-%m-%d")
        except: s_date = None
        if "-" not in score_raw: continue
        try: s1, s2 = map(int, score_raw.split("-"))
        except: continue
        
        win, los = (t1, t2) if s1 > s2 else (t2, t1)
        mx, mn = max(s1, s2), min(s1, s2)

        for t in (t1, t2):
            if s_date and (not stats[t]["last_date"] or s_date > stats[t]["last_date"]): stats[t]["last_date"] = s_date
            stats[t]["series_total"] += 1
            stats[t]["game_total"] += (s1 + s2)
        
        stats[win]["series_wins"] += 1
        stats[t1]["game_wins"] += s1
        stats[t2]["game_wins"] += s2

        if mx == 2:
            for t in (t1, t2): stats[t]["bo3_total"] += 1
            if mn == 1: 
                for t in (t1, t2): stats[t]["bo3_full"] += 1
        elif mx == 3:
            for t in (t1, t2): stats[t]["bo5_total"] += 1
            if mn == 2: 
                for t in (t1, t2): stats[t]["bo5_full"] += 1

        for t, is_w in [(win, True), (los, False)]:
            if not stats[t]["streak_dirty"]:
                if is_w:
                    if stats[t]["streak_losses"] > 0: stats[t]["streak_dirty"] = True
                    else: stats[t]["streak_wins"] += 1
                else:
                    if stats[t]["streak_wins"] > 0: stats[t]["streak_dirty"] = True
                    else: stats[t]["streak_losses"] += 1
    return stats

def build(all_data):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LoL Insights Pro</title>
    <style>
        :root {{ --bg-gray: #f1f5f9; --text-muted: #94a3b8; --primary: #2563eb; }}
        body {{ font-family: -apple-system, system-ui, sans-serif; background: var(--bg-gray); margin: 0; padding: 10px; color: #1e293b; }}
        .main-header {{ text-align: center; padding: 30px 0; }}
        .main-header h1 {{ margin: 0; font-size: 2rem; font-weight: 800; color: #0f172a; letter-spacing: -0.025em; }}
        
        .wrapper {{ background: #fff; border-radius: 12px; overflow: hidden; margin-bottom: 30px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
        
        .table-title-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; background: #fff; border-bottom: 1px solid #f1f5f9; }}
        .table-title-bar .title {{ font-size: 1.1rem; font-weight: 700; color: #334155; }}
        .table-title-bar .links {{ font-size: 0.85rem; }}
        .table-title-bar a {{ color: var(--primary); text-decoration: none; margin-left: 15px; font-weight: 500; border-bottom: 1px solid transparent; transition: 0.2s; }}
        .table-title-bar a:hover {{ border-bottom-color: var(--primary); }}

        table {{ width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
        th {{ background: #f8fafc; padding: 12px 8px; cursor: pointer; border-bottom: 2px solid #f1f5f9; color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
        th:hover {{ background: #f1f5f9; color: var(--primary); }}
        td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid #f8fafc; }}

        /* 宽度分配优化 */
        .col-team {{ width: 120px; position: sticky; left: 0; background: white !important; font-weight: 800; border-right: 2px solid #f1f5f9; text-align: left; padding-left: 15px; }}
        .col-data-sm {{ width: 55px; }}  /* 计数列 */
        .col-data-md {{ width: 75px; }}  /* 百分比列 */
        .col-streak {{ width: 70px; }}
        .col-date {{ width: 100px; }}

        .badge {{ color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold; display: inline-block; min-width: 24px; }}
        .footer {{ text-align: center; color: var(--text-muted); font-size: 12px; margin: 40px; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>🏆 LoL Insights Pro</h1></header>
    <div style="max-width:1300px; margin:0 auto">"""

    for idx, tour in enumerate(TOURNAMENTS):
        t_stats = all_data.get(tour["slug"], {})
        t_id = f"t{idx}"
        dates = [s["last_date"] for s in t_stats.values() if s["last_date"]]
        
        html += f"""
        <div class="wrapper">
            <div class="table-title-bar">
                <div class="title">{tour["title"]}</div>
                <div class="links">
                    <a href="{tour["url"]}" target="_blank">↗ Gol.gg Data</a>
                    <a href="{GITHUB_REPO}" target="_blank">↗ Source Code</a>
                </div>
            </div>
            <table id="{t_id}">
                <thead>
                    <tr>
                        <th class="col-team" onclick="doSort({COL_TEAM}, '{t_id}')">Team</th>
                        <th class="col-data-sm" onclick="doSort({COL_BO3_PCT}, '{t_id}')">BO3-F</th>
                        <th class="col-data-md" onclick="doSort({COL_BO3_PCT}, '{t_id}')">Fullrate</th>
                        <th class="col-data-sm" onclick="doSort({COL_BO5_PCT}, '{t_id}')">BO5-F</th>
                        <th class="col-data-md" onclick="doSort({COL_BO5_PCT}, '{t_id}')">Fullrate</th>
                        <th class="col-data-sm" onclick="doSort({COL_SERIES_WR}, '{t_id}')">S-Win</th>
                        <th class="col-data-md" onclick="doSort({COL_SERIES_WR}, '{t_id}')">Series</th>
                        <th class="col-data-sm" onclick="doSort({COL_GAME_WR}, '{t_id}')">G-Win</th>
                        <th class="col-data-md" onclick="doSort({COL_GAME_WR}, '{t_id}')">Games</th>
                        <th class="col-streak" onclick="doSort({COL_STREAK}, '{t_id}')">Streak</th>
                        <th class="col-date" onclick="doSort({COL_LAST_DATE}, '{t_id}')">Last Date</th>
                    </tr>
                </thead>
                <tbody>"""
        
        sorted_teams = sorted(t_stats.items(), key=lambda x: (rate(x[1]["bo3_full"], x[1]["bo3_total"]) if x[1]["bo3_total"] > 0 else 999))

        for name, s in sorted_teams:
            b3r, b5r = rate(s["bo3_full"], s["bo3_total"]), rate(s["bo5_full"], s["bo5_total"])
            ser_r, gam_r = rate(s["series_wins"], s["series_total"]), rate(s["game_wins"], s["game_total"])
            
            b3t = f"{s['bo3_full']}/{s['bo3_total']}" if s['bo3_total']>0 else "-"
            b5t = f"{s['bo5_full']}/{s['bo5_total']}" if s['bo5_total']>0 else "-"
            sert = f"{s['series_wins']}-{s['series_total']-s['series_wins']}" if s['series_total']>0 else "-"
            gamt = f"{s['game_wins']}-{s['game_total']-s['game_wins']}" if s['game_total']>0 else "-"
            stk = f"<span class='badge' style='background:#10b981'>{s['streak_wins']}W</span>" if s["streak_wins"] > 0 else (f"<span class='badge' style='background:#f43f5e'>{s['streak_losses']}L</span>" if s["streak_losses"] > 0 else "-")
            ld = s["last_date"].strftime("%Y-%m-%d") if s["last_date"] else "-"

            html += f"""
                <tr>
                    <td class="col-team">{name}</td>
                    <td {get_cell_style(b3t)}>{b3t}</td>
                    <td {get_cell_style(b3t, b3r, True, True)}>{pct(b3r)}</td>
                    <td {get_cell_style(b5t)}>{b5t}</td>
                    <td {get_cell_style(b5t, b5r, True, True)}>{pct(b5r)}</td>
                    <td {get_cell_style(sert)}>{sert}</td>
                    <td {get_cell_style(sert, ser_r, True)}>{pct(ser_r)}</td>
                    <td {get_cell_style(gamt)}>{gamt}</td>
                    <td {get_cell_style(gamt, gam_r, True)}>{pct(gam_r)}</td>
                    <td {get_cell_style(stk if s['streak_wins']+s['streak_losses']>0 else "-")}>{stk}</td>
                    <td {get_cell_style(ld)} style="color:#64748b;font-weight:700">{ld}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
    <div class="footer">Last Update: {now}</div>
    </div>
    <script>
    function parseValue(v) {{
        if (!v || v === "-") return -1000;
        if (v.includes("%")) return parseFloat(v);
        if (v.includes("/")) {{ let p = v.split("/"); return parseFloat(p[0])/(parseFloat(p[1])||1); }}
        if (v.includes("-") && v.split("-").length === 2) return parseFloat(v.split("-")[0]);
        if (v.includes("W")) return 100 + parseFloat(v);
        if (v.includes("L")) return -100 - parseFloat(v);
        let d = Date.parse(v); if (!isNaN(d)) return d;
        return v.toLowerCase();
    }}
    function doSort(col, id) {{
        const table = document.getElementById(id);
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        const currDir = table.getAttribute('data-dir-' + col) || 'desc';
        const nextDir = currDir === 'desc' ? 'asc' : 'desc';
        rows.sort((a, b) => {{
            let va = parseValue(a.cells[col].innerText), vb = parseValue(b.cells[col].innerText);
            return nextDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
        }});
        rows.forEach(r => tbody.appendChild(r));
        table.setAttribute('data-dir-' + col, nextDir);
    }}
    </script>
</body></html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    data = {t["slug"]: scrape(t) for t in TOURNAMENTS}
    build(data)
