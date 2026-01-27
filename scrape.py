import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ================== 赛事配置 ==================
TOURNAMENTS = [
    {
        "slug": "2026-lck-cup",
        "title": "2026 LCK Cup",
        "url": "https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/",
    },
    {
        "slug": "2026-lpl-split-1",
        "title": "2026 LPL Split 1",
        "url": "https://gol.gg/tournament/tournament-matchlist/LPL%202026%20Split%201/",
    },
]
# =============================================

INDEX_FILE = Path("index.html")
GITHUB_REPO = "https://github.com/closur3/lol"

# ---------- 颜色与逻辑函数 ----------

def get_hsl(h, s=70, l=45): return f"hsl({int(h)}, {s}%, {l}%)"

def color_by_ratio(r, reverse=False):
    if r is None: return "#f3f4f6"
    h = (1 - max(0, min(1, r))) * 140 if reverse else max(0, min(1, r)) * 140
    return get_hsl(h, s=65, l=48)

def color_text_by_ratio(r, reverse=False):
    if r is None: return "#6b7280"
    h = (1 - max(0, min(1, r))) * 140 if reverse else max(0, min(1, r)) * 140
    return get_hsl(h, s=80, l=35)

def color_by_date(match_date, all_dates):
    if not match_date or not all_dates: return "#9ca3af"
    max_d, min_d = max(all_dates), min(all_dates)
    if max_d == min_d: return "#3b82f6"
    freshness = (match_date - min_d).total_seconds() / (max_d - min_d).total_seconds()
    return f"hsl(215, {int(freshness * 80 + 20)}%, {int(55 - freshness * 15)}%)"

def rate(n, d): return n / d if d > 0 else None
def pct(r): return f"{r*100:.1f}%" if r is not None else "-"
def parse_date(date_str):
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
        try: return datetime.strptime(date_str, fmt)
        except: continue
    return None

# ---------- 抓取逻辑 ----------

def scrape_tournament(t):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(t["url"], headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
    except: return {}

    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, "bo5_full": 0, "bo5_total": 0,
        "match_win": 0, "match_total": 0, "game_win": 0, "game_total": 0,
        "streak_w": 0, "streak_l": 0, "streak_done": False, "last_match_date": None,
    })

    for row in soup.select("table tr"):
        tds = row.find_all("td")
        if len(tds) < 5: continue
        t1, score, t2 = tds[1].text.strip(), tds[2].text.strip(), tds[3].text.strip()
        match_date = parse_date(tds[-1].text.strip())
        if "-" not in score: continue
        try: s1, s2 = map(int, score.split("-"))
        except: continue
        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)
        for t_ in (t1, t2):
            if match_date and (not stats[t_]["last_match_date"] or match_date > stats[t_]["last_match_date"]):
                stats[t_]["last_match_date"] = match_date
            stats[t_]["match_total"] += 1
            stats[t_]["game_total"] += (s1 + s2)
        stats[winner]["match_win"] += 1
        stats[t1]["game_win"] += s1
        stats[t2]["game_win"] += s2
        mx, mn = max(s1, s2), min(s1, s2)
        if mx == 2:
            for t_ in (t1, t2): stats[t_]["bo3_total"] += 1
            if mn == 1:
                for t_ in (t1, t2): stats[t_]["bo3_full"] += 1
        elif mx == 3:
            for t_ in (t1, t2): stats[t_]["bo5_total"] += 1
            if mn == 2:
                for t_ in (t1, t2): stats[t_]["bo5_full"] += 1
        if not stats[winner]["streak_done"]:
            if stats[winner]["streak_l"] > 0: stats[winner]["streak_done"] = True
            else: stats[winner]["streak_w"] += 1
        if not stats[loser]["streak_done"]:
            if stats[loser]["streak_w"] > 0: stats[loser]["streak_done"] = True
            else: stats[loser]["streak_l"] += 1
    return stats

# ---------- 生成 HTML ----------

def build_index_html(all_data):
    last_update = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
    
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>LoL Tournament Stats</title>
    <style>
        :root {{ --bg: #f8fafc; --card: #ffffff; --text: #1e293b; --border: #e2e8f0; --blue: #3b82f6; }}
        body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 10px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        
        /* 核心修复：移除不必要的绝对定位 */
        .table-container {{ 
            width: 100%; 
            overflow-x: auto; 
            background: var(--card); 
            border: 1px solid var(--border); 
            border-radius: 8px; 
            margin-bottom: 2rem; 
        }}
        
        table {{ 
            width: 100%; 
            min-width: 1050px; /* 保证手机端可以滑动 */
            border-collapse: collapse; 
            font-size: 13px;
        }}
        
        /* 表头样式：确保可点击 */
        th {{ 
            background: #f1f5f9; 
            padding: 12px 8px; 
            font-weight: 700; 
            border-bottom: 2px solid var(--border); 
            cursor: pointer; 
            user-select: none;
            position: relative;
        }}
        th:active {{ background: #cbd5e1; }} /* 点击时的视觉反馈 */

        td {{ padding: 12px 8px; text-align: center; border-bottom: 1px solid var(--border); }}
        
        /* Team列固定 */
        .sticky-col {{ 
            position: sticky; 
            left: 0; 
            background: white; 
            z-index: 10; 
            border-right: 2px solid var(--border); 
            text-align: left;
            font-weight: 800;
        }}
        th.sticky-col {{ z-index: 20; background: #f1f5f9; }}

        .badge {{ color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold; }}
        .streak-w {{ background: #10b981; }}
        .streak-l {{ background: #f43f5e; }}
        
        .footer {{ text-align: center; margin: 2rem 0; font-size: 12px; color: #64748b; }}
        a {{ color: var(--blue); text-decoration: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1 style="text-align:center; font-size:1.5rem;">🏆 LoL Tournament Dashboard</h1>
    """

    for idx, t in enumerate(TOURNAMENTS):
        stats = all_data.get(t["slug"], {})
        table_id = f"table_{idx}"
        all_dates = [s["last_match_date"] for s in stats.values() if s["last_match_date"]]
        
        html += f"""
        <div class="table-container">
            <div style="padding: 12px; border-bottom: 1px solid var(--border); font-weight: bold;">
                <a href="{t['url']}" target="_blank">{t['title']}</a>
            </div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th class="sticky-col" onclick="sortTable(0, '{table_id}')">Team</th>
                        <th onclick="sortTable(1, '{table_id}')">BO3</th>
                        <th onclick="sortTable(2, '{table_id}')">BO3%</th>
                        <th onclick="sortTable(3, '{table_id}')">BO5</th>
                        <th onclick="sortTable(4, '{table_id}')">BO5%</th>
                        <th onclick="sortTable(5, '{table_id}')">Match</th>
                        <th onclick="sortTable(6, '{table_id}')">Match WR</th>
                        <th onclick="sortTable(7, '{table_id}')">Game</th>
                        <th onclick="sortTable(8, '{table_id}')">Game WR</th>
                        <th onclick="sortTable(9, '{table_id}')">Streak</th>
                        <th onclick="sortTable(10, '{table_id}')">Last Match</th>
                    </tr>
                </thead>
                <tbody>"""

        sorted_teams = sorted(stats.items(), key=lambda x: (
            rate(x[1]["bo3_full"], x[1]["bo3_total"]) if x[1]["bo3_total"] > 0 else 999,
            -(rate(x[1]["match_win"], x[1]["match_total"]) or 0)
        ))

        for team, s in sorted_teams:
            b3r, b5r = rate(s["bo3_full"], s["bo3_total"]), rate(s["bo5_full"], s["bo5_total"])
            mwr, gwr = rate(s["match_win"], s["match_total"]), rate(s["game_win"], s["game_total"])
            stk = f"<span class='badge streak-w'>{s['streak_w']}W</span>" if s['streak_w']>0 else (f"<span class='badge streak-l'>{s['streak_l']}L</span>" if s['streak_l']>0 else "-")
            ld = s["last_match_date"].strftime("%Y-%m-%d") if s["last_match_date"] else "-"

            html += f"""
                <tr>
                    <td class="sticky-col">{team}</td>
                    <td style="color:{color_text_by_ratio(b3r,True)}">{s['bo3_full']}/{s['bo3_total']}</td>
                    <td style="background:{color_by_ratio(b3r,True)};color:white;font-weight:bold">{pct(b3r)}</td>
                    <td style="color:{color_text_by_ratio(b5r,True)}">{s['bo5_full']}/{s['bo5_total']}</td>
                    <td style="background:{color_by_ratio(b5r,True)};color:white;font-weight:bold">{pct(b5r)}</td>
                    <td style="color:{color_text_by_ratio(mwr)}">{s['match_win']}-{s['match_total']-s['match_win']}</td>
                    <td style="background:{color_by_ratio(mwr)};color:white;font-weight:bold">{pct(mwr)}</td>
                    <td style="color:{color_text_by_ratio(gwr)}">{s['game_win']}-{s['game_total']-s['game_win']}</td>
                    <td style="background:{color_by_ratio(gwr)};color:white;font-weight:bold">{pct(gwr)}</td>
                    <td>{stk}</td>
                    <td style="color:{color_by_date(s['last_match_date'], all_dates)};font-weight:bold">{ld}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
        <div class="footer">
            Updated: {last_update} | <a href="{GITHUB_REPO}" target="_blank">GitHub Repo</a>
        </div>
    </div>
    <script>
        function sortTable(n, id) {{
            const table = document.getElementById(id);
            const rows = Array.from(table.rows).slice(1);
            const dir = table.dataset.dir === "asc" ? -1 : 1;
            
            rows.sort((a, b) => {{
                let x = parse(a.cells[n].innerText);
                let y = parse(b.cells[n].innerText);
                return x > y ? dir : x < y ? -dir : 0;
            }});
            
            table.dataset.dir = dir === 1 ? "asc" : "desc";
            rows.forEach(row => table.tBodies[0].appendChild(row));
        }}
        function parse(v) {{
            if (v.includes('%')) return parseFloat(v);
            if (v.includes('/')) return v.split('/').reduce((a,b)=>a/b);
            if (v.includes('-')) return parseFloat(v.split('-')[0]);
            return isNaN(v) ? v : parseFloat(v);
        }}
    </script>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    d = {t["slug"]: scrape_tournament(t) for t in TOURNAMENTS}
    build_index_html(d)
