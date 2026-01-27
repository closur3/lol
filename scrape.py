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

# ---------- 现代颜色工具函数 ----------

def get_hsl(h, s=70, l=45):
    """生成 HSL 颜色字符串"""
    return f"hsl({int(h)}, {s}%, {l}%)"

def color_by_ratio(r, reverse=False):
    """
    根据比例返回颜色背景色
    r: 0-1 的比例
    reverse: False 为 0红->1绿 (胜率), True 为 0绿->1红 (打满率)
    """
    if r is None: return "#f3f4f6"
    r = max(0, min(1, r))
    # 色相：0是红色，140是绿色
    h = (1 - r) * 140 if reverse else r * 140
    return get_hsl(h, s=65, l=48)

def color_text_by_ratio(r, reverse=False):
    """
    针对白色背景下的文字着色（加深 HSL 的亮度 L 以确保可读性）
    """
    if r is None: return "#6b7280"
    r = max(0, min(1, r))
    h = (1 - r) * 140 if reverse else r * 140
    return get_hsl(h, s=80, l=35)

def color_by_date(match_date, all_dates):
    """根据日期新旧返回颜色：最新为亮蓝色，旧的逐渐变灰"""
    if not match_date or not all_dates: return "#9ca3af"
    max_d, min_d = max(all_dates), min(all_dates)
    if max_d == min_d: return "#3b82f6"
    
    # 计算新鲜度 (0=最旧, 1=最新)
    freshness = (match_date - min_d).total_seconds() / (max_d - min_d).total_seconds()
    # 蓝色系：从灰蓝色到明亮的科技蓝
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

# ---------- 数据抓取 ----------

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
    # 倒序遍历以正确计算当前连胜 (从最近的比赛开始往回推)
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

        # 统计
        for t_ in (t1, t2):
            if match_date:
                if stats[t_]["last_match_date"] is None or match_date > stats[t_]["last_match_date"]:
                    stats[t_]["last_match_date"] = match_date
            stats[t_]["match_total"] += 1
            stats[t_]["game_total"] += (s1 + s2)
        
        stats[winner]["match_win"] += 1
        stats[t1]["game_win"] += s1
        stats[t2]["game_win"] += s2

        # BO3/BO5 判定
        max_s, min_s = max(s1, s2), min(s1, s2)
        if max_s == 2:
            for t_ in (t1, t2): stats[t_]["bo3_total"] += 1
            if min_s == 1:
                for t_ in (t1, t2): stats[t_]["bo3_full"] += 1
        elif max_s == 3:
            for t_ in (t1, t2): stats[t_]["bo5_total"] += 1
            if min_s == 2:
                for t_ in (t1, t2): stats[t_]["bo5_full"] += 1

        # 连胜/连败
        if not stats[winner]["streak_done"]:
            if stats[winner]["streak_l"] > 0: stats[winner]["streak_done"] = True
            else: stats[winner]["streak_w"] += 1
        if not stats[loser]["streak_done"]:
            if stats[loser]["streak_w"] > 0: stats[loser]["streak_done"] = True
            else: stats[loser]["streak_l"] += 1

    return stats

# ---------- 生成输出 ----------

def build_index_html(all_data):
    cst = timezone(timedelta(hours=8))
    last_update = datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S CST")
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOL Pro Stats Dashboard</title>
    <style>
        :root {{
            --bg: #f3f4f6;
            --card-bg: #ffffff;
            --text-main: #111827;
            --text-muted: #6b7280;
            --border: #e5e7eb;
        }}
        body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text-main); margin: 0; padding: 2rem; line-height: 1.5; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ text-align: center; font-size: 2.25rem; font-weight: 800; margin-bottom: 2rem; letter-spacing: -0.025em; }}
        .tournament-section {{ background: var(--card-bg); border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 3rem; overflow: hidden; border: 1px solid var(--border); }}
        .header-bar {{ padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); background: #fafafa; display: flex; justify-content: space-between; align-items: center; }}
        .header-bar h2 {{ margin: 0; font-size: 1.25rem; }}
        .header-bar a {{ color: #3b82f6; text-decoration: none; font-size: 0.875rem; font-weight: 600; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
        th {{ background: #f9fafb; padding: 0.75rem 1rem; text-align: center; font-weight: 600; color: var(--text-muted); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; border-bottom: 2px solid var(--border); cursor: pointer; }}
        td {{ padding: 0.875rem 1rem; text-align: center; border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background-color: #f8fafc; }}
        
        .team-name {{ text-align: left; font-weight: 700; color: var(--text-main); min-width: 120px; }}
        .badge {{ color: white; font-weight: 700; border-radius: 6px; padding: 4px 8px; font-size: 0.8rem; }}
        .streak-w {{ background: #10b981; }}
        .streak-l {{ background: #f43f5e; }}
        .footer {{ text-align: center; margin-top: 4rem; color: var(--text-muted); font-size: 0.875rem; padding-bottom: 2rem; }}
    </style>
    <script>
        function sortTable(n, tableId) {{
            let table = document.getElementById(tableId), rows, switching = true, i, x, y, shouldSwitch, dir = "desc", switchcount = 0;
            while (switching) {{
                switching = false; rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {{
                    shouldSwitch = false;
                    x = rows[i].getElementsByTagName("TD")[n].innerText.replace('%','');
                    y = rows[i+1].getElementsByTagName("TD")[n].innerText.replace('%','');
                    if(x.includes('/')) x = eval(x); if(y.includes('/')) y = eval(y);
                    if(x.includes('-')) x = parseFloat(x.split('-')[0]); if(y.includes('-')) y = parseFloat(y.split('-')[0]);
                    x = parseFloat(x) || 0; y = parseFloat(y) || 0;
                    if (dir == "asc") {{ if (x > y) {{ shouldSwitch = true; break; }} }}
                    else {{ if (x < y) {{ shouldSwitch = true; break; }} }}
                }}
                if (shouldSwitch) {{ rows[i].parentNode.insertBefore(rows[i + 1], rows[i]); switching = true; switchcount ++; }}
                else if (switchcount == 0 && dir == "desc") {{ dir = "asc"; switching = true; }}
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>🏆 LoL Tournament Insights</h1>
    """

    for idx, t in enumerate(TOURNAMENTS):
        stats = all_data.get(t["slug"], {})
        table_id = f"table_{idx}"
        all_dates = [s["last_match_date"] for s in stats.values() if s["last_match_date"]]
        
        html += f"""
        <div class="tournament-section">
            <div class="header-bar">
                <h2>{t['title']}</h2>
                <a href="{t['url']}" target="_blank">View Original Source →</a>
            </div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th onclick="sortTable(0, '{table_id}')">Team</th>
                        <th onclick="sortTable(1, '{table_id}')">BO3 Full</th>
                        <th onclick="sortTable(2, '{table_id}')">BO3 %</th>
                        <th onclick="sortTable(3, '{table_id}')">BO5 Full</th>
                        <th onclick="sortTable(4, '{table_id}')">BO5 %</th>
                        <th onclick="sortTable(5, '{table_id}')">Match W/L</th>
                        <th onclick="sortTable(6, '{table_id}')">Match WR</th>
                        <th onclick="sortTable(7, '{table_id}')">Game W/L</th>
                        <th onclick="sortTable(8, '{table_id}')">Game WR</th>
                        <th onclick="sortTable(9, '{table_id}')">Streak</th>
                        <th onclick="sortTable(10, '{table_id}')">Last Match</th>
                    </tr>
                </thead>
                <tbody>"""

        # 排序：默认按大场胜率排
        sorted_teams = sorted(stats.items(), key=lambda x: (rate(x[1]["match_win"], x[1]["match_total"]) or 0), reverse=True)

        for team, s in sorted_teams:
            b3r, b5r = rate(s["bo3_full"], s["bo3_total"]), rate(s["bo5_full"], s["bo5_total"])
            mwr, gwr = rate(s["match_win"], s["match_total"]), rate(s["game_win"], s["game_total"])
            
            streak_html = "-"
            if s["streak_w"] > 0: streak_html = f"<span class='badge streak-w'>{s['streak_w']}W</span>"
            elif s["streak_l"] > 0: streak_html = f"<span class='badge streak-l'>{s['streak_l']}L</span>"
            
            last_date_str = s["last_match_date"].strftime("%Y-%m-%d") if s["last_match_date"] else "-"
            
            html += f"""
                <tr>
                    <td class="team-name">{team}</td>
                    <td style="color:{color_text_by_ratio(b3r, True)}">{s['bo3_full']}/{s['bo3_total']}</td>
                    <td style="background:{color_by_ratio(b3r, True)}; color:white; font-weight:700">{pct(b3r)}</td>
                    <td style="color:{color_text_by_ratio(b5r, True)}">{s['bo5_full']}/{s['bo5_total']}</td>
                    <td style="background:{color_by_ratio(b5r, True)}; color:white; font-weight:700">{pct(b5r)}</td>
                    <td style="color:{color_text_by_ratio(mwr)}">{s['match_win']}-{s['match_total']-s['match_win']}</td>
                    <td style="background:{color_by_ratio(mwr)}; color:white; font-weight:700">{pct(mwr)}</td>
                    <td style="color:{color_text_by_ratio(gwr)}">{s['game_win']}-{s['game_total']-s['game_win']}</td>
                    <td style="background:{color_by_ratio(gwr)}; color:white; font-weight:700">{pct(gwr)}</td>
                    <td>{streak_html}</td>
                    <td style="color:{color_by_date(s['last_match_date'], all_dates)}; font-weight:600">{last_date_str}</td>
                </tr>"""
        
        html += "</tbody></table></div>"

    html += f"""
        <div class="footer">
            Data synchronized on {last_update} • Powered by Gemini AI
        </div>
    </div>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_data = {}
    for t in TOURNAMENTS:
        print(f"Scraping {t['title']}...")
        try:
            stats = scrape_tournament(t)
            all_data[t["slug"]] = stats
        except Exception as e:
            print(f"Error scraping {t['title']}: {e}")
    
    build_index_html(all_data)
    print("\nSuccess! index.html has been generated with modern HSL coloring.")

if __name__ == "__main__":
    main()
