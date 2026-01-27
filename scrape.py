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

OUTPUT_DIR = Path("tournaments")
INDEX_FILE = Path("index.html")
GITHUB_REPO = "https://github.com/closur3/lol"  # 你的仓库地址

# ---------- 现代 HSL 颜色工具函数 ----------

def get_hsl(h, s=70, l=45):
    return f"hsl({int(h)}, {s}%, {l}%)"

def color_by_ratio(r, reverse=False):
    if r is None: return "#f3f4f6"
    r = max(0, min(1, r))
    h = (1 - r) * 140 if reverse else r * 140
    return get_hsl(h, s=65, l=48)

def color_text_by_ratio(r, reverse=False):
    if r is None: return "#6b7280"
    r = max(0, min(1, r))
    h = (1 - r) * 140 if reverse else r * 140
    return get_hsl(h, s=80, l=35)

def color_by_date(match_date, all_dates):
    if not match_date or not all_dates: return "#9ca3af"
    max_d, min_d = max(all_dates), min(all_dates)
    if max_d == min_d: return "#3b82f6"
    freshness = (match_date - min_d).total_seconds() / (max_d - min_d).total_seconds()
    return f"hsl(215, {int(freshness * 80 + 20)}%, {int(55 - freshness * 15)}%)"

def rate(n, d):
    return n / d if d > 0 else None

def pct(r):
    return f"{r*100:.1f}%" if r is not None else "-"

def parse_date(date_str):
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
        try: return datetime.strptime(date_str, fmt)
        except: continue
    return None

# ---------- 数据抓取逻辑 ----------

def scrape_tournament(t):
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(t["url"], headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0,
        "bo5_full": 0, "bo5_total": 0,
        "match_win": 0, "match_total": 0,
        "game_win": 0, "game_total": 0,
        "streak_w": 0, "streak_l": 0,
        "streak_done": False,
        "last_match_date": None,
    })

    rows = soup.select("table tr")
    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 5: continue

        t1, score, t2 = tds[1].get_text(strip=True), tds[2].get_text(strip=True), tds[3].get_text(strip=True)
        date_str = tds[-1].get_text(strip=True) if len(tds) >= 7 else ""
        match_date = parse_date(date_str)

        if "-" not in score: continue
        try:
            s1, s2 = map(int, score.split("-"))
        except: continue

        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)

        for t_ in (t1, t2):
            if match_date:
                if stats[t_]["last_match_date"] is None or match_date > stats[t_]["last_match_date"]:
                    stats[t_]["last_match_date"] = match_date
            stats[t_]["match_total"] += 1
            stats[t_]["game_total"] += (s1 + s2)
        
        stats[winner]["match_win"] += 1
        stats[t1]["game_win"] += s1
        stats[t2]["game_win"] += s2

        max_s, min_s = max(s1, s2), min(s1, s2)
        if max_s == 2:
            for t_ in (t1, t2): stats[t_]["bo3_total"] += 1
            if min_s == 1:
                for t_ in (t1, t2): stats[t_]["bo3_full"] += 1
        elif max_s == 3:
            for t_ in (t1, t2): stats[t_]["bo5_total"] += 1
            if min_s == 2:
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
    cst = timezone(timedelta(hours=8))
    last_update = datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S CST")
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LoL Tournament Stats Dashboard</title>
    <style>
        :root {{ --bg: #f8fafc; --card-bg: #ffffff; --text-main: #1e293b; --text-muted: #64748b; --border: #e2e8f0; --primary: #3b82f6; }}
        body {{ font-family: 'Inter', -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text-main); margin: 0; padding: 2rem; line-height: 1.5; }}
        .container {{ max-width: 1440px; margin: 0 auto; }}
        h1 {{ text-align: center; font-size: 2.25rem; font-weight: 800; margin-bottom: 2rem; color: #0f172a; }}
        .tournament-section {{ background: var(--card-bg); border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 3rem; overflow: hidden; border: 1px solid var(--border); }}
        .header-bar {{ padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); background: #fafafa; }}
        .header-bar h2 {{ margin: 0; font-size: 1.4rem; font-weight: 700; }}
        .header-bar h2 a {{ color: var(--text-main); text-decoration: none; transition: color 0.2s; }}
        .header-bar h2 a:hover {{ color: var(--primary); text-decoration: underline; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
        th {{ background: #f1f5f9; padding: 0.8rem; text-align: center; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 0.75rem; border-bottom: 2px solid var(--border); cursor: pointer; user-select: none; }}
        th:hover {{ background: #e2e8f0; }}
        td {{ padding: 0.9rem; text-align: center; border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }}
        tr:hover td {{ background-color: #f8fafc; }}
        
        .team-name {{ text-align: left; font-weight: 800; color: #0f172a; min-width: 140px; }}
        .badge {{ color: white; font-weight: 800; border-radius: 6px; padding: 4px 10px; font-size: 0.82rem; }}
        .streak-w {{ background: #10b981; }}
        .streak-l {{ background: #f43f5e; }}
        
        .footer {{ text-align: center; margin-top: 4rem; padding-top: 2rem; border-top: 1px solid var(--border); color: var(--text-muted); font-size: 0.9rem; }}
        .footer a {{ color: var(--primary); text-decoration: none; font-weight: 600; }}
        .footer a:hover {{ text-decoration: underline; }}
    </style>
    <script>
        function sortTable(n, tableId) {{
            let table = document.getElementById(tableId), rows, switching = true, i, x, y, shouldSwitch, dir = table.getAttribute("data-dir-" + n) === "asc" ? "desc" : "asc";
            while (switching) {{
                switching = false; rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {{
                    shouldSwitch = false;
                    x = parseVal(rows[i].getElementsByTagName("TD")[n].innerText);
                    y = parseVal(rows[i+1].getElementsByTagName("TD")[n].innerText);
                    if (dir === "asc") {{ if (x > y) {{ shouldSwitch = true; break; }} }}
                    else {{ if (x < y) {{ shouldSwitch = true; break; }} }}
                }}
                if (shouldSwitch) {{ rows[i].parentNode.insertBefore(rows[i+1], rows[i]); switching = true; }}
            }}
            table.setAttribute("data-dir-" + n, dir);
        }}
        function parseVal(v) {{
            if (v.includes('%')) return parseFloat(v) || 0;
            if (v.includes('/')) {{ let p = v.split('/'); return parseFloat(p[0])/parseFloat(p[1]) || 0; }}
            if (v.includes('-')) return parseFloat(v.split('-')[0]) || 0;
            let n = parseFloat(v); return isNaN(n) ? v.toLowerCase() : n;
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>🏆 LoL Tournament Stats</h1>
    """

    for idx, t in enumerate(TOURNAMENTS):
        stats = all_data.get(t["slug"], {})
        table_id = f"table_{idx}"
        all_dates = [s["last_match_date"] for s in stats.values() if s["last_match_date"]]
        
        html += f"""
        <div class="tournament-section">
            <div class="header-bar">
                <h2><a href="{t['url']}" target="_blank">{t['title']}</a></h2>
            </div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th onclick="sortTable(0, '{table_id}')">Team</th>
                        <th onclick="sortTable(1, '{table_id}')">BO3 Full</th>
                        <th onclick="sortTable(2, '{table_id}')">BO3%</th>
                        <th onclick="sortTable(3, '{table_id}')">BO5 Full</th>
                        <th onclick="sortTable(4, '{table_id}')">BO5%</th>
                        <th onclick="sortTable(5, '{table_id}')">Match W-L</th>
                        <th onclick="sortTable(6, '{table_id}')">Match WR</th>
                        <th onclick="sortTable(7, '{table_id}')">Game W-L</th>
                        <th onclick="sortTable(8, '{table_id}')">Game WR</th>
                        <th onclick="sortTable(9, '{table_id}')">Streak</th>
                        <th onclick="sortTable(10, '{table_id}')">Last Match</th>
                    </tr>
                </thead>
                <tbody>"""

        # 默认排序：BO3% 升序，相同则按 Match WR 降序
        sorted_teams = sorted(stats.items(), key=lambda x: (
            rate(x[1]["bo3_full"], x[1]["bo3_total"]) if x[1]["bo3_total"] > 0 else 999,
            -(rate(x[1]["match_win"], x[1]["match_total"]) or 0)
        ))

        for team, s in sorted_teams:
            b3r, b5r = rate(s["bo3_full"], s["bo3_total"]), rate(s["bo5_full"], s["bo5_total"])
            mwr, gwr = rate(s["match_win"], s["match_total"]), rate(s["game_win"], s["game_total"])
            streak = "-"
            if s["streak_w"] > 0: streak = f"<span class='badge streak-w'>{s['streak_w']}W</span>"
            elif s["streak_l"] > 0: streak = f"<span class='badge streak-l'>{s['streak_l']}L</span>"
            last_date = s["last_match_date"].strftime("%Y-%m-%d") if s["last_match_date"] else "-"

            html += f"""
                <tr>
                    <td class="team-name">{team}</td>
                    <td style="color:{color_text_by_ratio(b3r, True)}">{s['bo3_full']}/{s['bo3_total']}</td>
                    <td style="background:{color_by_ratio(b3r, True)}; color:white; font-weight:800">{pct(b3r)}</td>
                    <td style="color:{color_text_by_ratio(b5r, True)}">{s['bo5_full']}/{s['bo5_total']}</td>
                    <td style="background:{color_by_ratio(b5r, True)}; color:white; font-weight:800">{pct(b5r)}</td>
                    <td style="color:{color_text_by_ratio(mwr)}">{s['match_win']}-{s['match_total']-s['match_win']}</td>
                    <td style="background:{color_by_ratio(mwr)}; color:white; font-weight:800">{pct(mwr)}</td>
                    <td style="color:{color_text_by_ratio(gwr)}">{s['game_win']}-{s['game_total']-s['game_win']}</td>
                    <td style="background:{color_by_ratio(gwr)}; color:white; font-weight:800">{pct(gwr)}</td>
                    <td>{streak}</td>
                    <td style="color:{color_by_date(s['last_match_date'], all_dates)}; font-weight:700">{last_date}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
        <div class="footer">
            最后更新: {last_update} | 
            <a href="{GITHUB_REPO}" target="_blank">GitHub Repository</a>
        </div>
    </div>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    all_data = {t["slug"]: scrape_tournament(t) for t in TOURNAMENTS}
    build_index_html(all_data)
    print(f"index.html 生成完毕，已包含 GitHub 仓库链接：{GITHUB_REPO}")
