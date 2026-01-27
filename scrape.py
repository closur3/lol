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

# 列索引常量 (用于前端表格排序)
COL_TEAM = 0
COL_BO3_PCT = 2
COL_BO5_PCT = 4
COL_SERIES_WR = 6
COL_GAME_WR = 8
COL_STREAK = 9
COL_LAST_DATE = 10

# --- 数据处理工具 ---
def load_team_map():
    if TEAMS_JSON.exists():
        try:
            return json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
        except:
            pass
    return {}

TEAM_MAP = load_team_map()

def get_short_name(full_name):
    name_upper = full_name.upper()
    for key, short_val in TEAM_MAP.items():
        if key.upper() in name_upper:
            return short_val
    return full_name.replace("Esports", "").replace("Gaming", "").replace("Academy", "").replace("Team", "").strip()

def rate(numerator, denominator):
    return numerator / denominator if denominator > 0 else None

def pct(ratio):
    return f"{ratio*100:.1f}%" if ratio is not None else "-"

def get_hsl(hue, saturation=70, lightness=45):
    return f"hsl({int(hue)}, {saturation}%, {lightness}%)"

def color_by_ratio(ratio, reverse=False):
    if ratio is None:
        return "#f1f5f9"
    # 绿转红或红转绿逻辑
    hue = (1 - max(0, min(1, ratio))) * 140 if reverse else max(0, min(1, ratio)) * 140
    return get_hsl(hue, saturation=65, lightness=48)

def color_by_date(date, all_dates):
    if not date or not all_dates:
        return "#9ca3af"
    max_date, min_date = max(all_dates), min(all_dates)
    if max_date == min_date:
        return "hsl(215, 80%, 45%)"
    factor = (date - min_date).total_seconds() / (max_date - min_date).total_seconds()
    return f"hsl(215, {int(factor * 80 + 20)}%, {int(55 - factor * 15)}%)"

# --- 爬虫逻辑 ---
def scrape(tournament):
    print(f"Scraping {tournament['title']}...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(tournament["url"], headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Error: {e}")
        return {}

    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, 
        "bo5_full": 0, "bo5_total": 0, 
        "series_wins": 0, "series_total": 0, 
        "game_wins": 0, "game_total": 0, 
        "streak_wins": 0, "streak_losses": 0, 
        "streak_dirty": False, "last_date": None
    })

    # 遍历表格行
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 5: continue
        
        team1 = get_short_name(cells[1].text.strip())
        team2 = get_short_name(cells[3].text.strip())
        score = cells[2].text.strip()
        
        try: 
            series_date = datetime.strptime(cells[-1].text.strip(), "%Y-%m-%d")
        except: 
            series_date = None
            
        if "-" not in score: continue
        
        try: 
            score1, score2 = map(int, score.split("-"))
        except: continue
            
        winner, loser = (team1, team2) if score1 > score2 else (team2, team1)
        max_s, min_s = max(score1, score2), min(score1, score2)
        
        for team in (team1, team2):
            if series_date and (not stats[team]["last_date"] or series_date > stats[team]["last_date"]): 
                stats[team]["last_date"] = series_date
            stats[team]["series_total"] += 1
            stats[team]["game_total"] += (score1 + score2)
            
        stats[winner]["series_wins"] += 1
        stats[team1]["game_wins"] += score1
        stats[team2]["game_wins"] += score2
        
        # BO3/BO5 满局率统计
        if max_s == 2: # BO3
            for t in (team1, team2): stats[t]["bo3_total"] += 1
            if min_s == 1: 
                for t in (team1, team2): stats[t]["bo3_full"] += 1
        elif max_s == 3: # BO5
            for t in (team1, team2): stats[t]["bo5_total"] += 1
            if min_s == 2: 
                for t in (team1, team2): stats[t]["bo5_full"] += 1
        
        # 连胜/连败逻辑 (只计算最近状态)
        for team, is_winner in [(winner, True), (loser, False)]:
            if not stats[team]["streak_dirty"]:
                if is_winner:
                    if stats[team]["streak_losses"] > 0: stats[team]["streak_dirty"] = True
                    else: stats[team]["streak_wins"] += 1
                else:
                    if stats[team]["streak_wins"] > 0: stats[team]["streak_dirty"] = True
                    else: stats[team]["streak_losses"] += 1
                
    return stats

# --- 网页构建逻辑 ---
def build(all_data):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
    html_start = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LoL Insights Pro</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f1f5f9; margin: 0; padding: 10px; }}
        .main-header {{ text-align: center; padding: 25px 0; }}
        .main-header h1 {{ margin: 0; font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #0f172a 0%, #2563eb 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 25px; border: 1px solid #e2e8f0; }}
        .table-title {{ padding: 15px; font-weight: 700; border-bottom: 1px solid #f1f5f9; }}
        .table-title a {{ color: #2563eb; text-decoration: none; }}
        table {{ width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
        th {{ background: #f8fafc; padding: 14px 8px; font-weight: 600; color: #64748b; border-bottom: 2px solid #f1f5f9; cursor: pointer; transition: 0.2s; }}
        th:hover {{ background: #eff6ff; color: #2563eb; }}
        td {{ padding: 12px 8px; text-align: center; border-bottom: 1px solid #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .team-col {{ position: sticky; left: 0; background: white !important; z-index: 10; border-right: 2px solid #f1f5f9; text-align: left; font-weight: 800; padding-left: 15px; width: 80px; }}
        .badge {{ color: white; border-radius: 4px; padding: 3px 7px; font-size: 11px; font-weight: 700; }}
        .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>🏆 LoL Insights Pro</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

    content = ""
    for index, tournament in enumerate(TOURNAMENTS):
        team_stats = all_data.get(tournament["slug"], {})
        table_id = f"t{index}"
        dates = [stat["last_date"] for stat in team_stats.values() if stat["last_date"]]
        
        content += f"""
        <div class="wrapper">
            <div class="table-title"><a href="{tournament["url"]}" target="_blank">{tournament["title"]}</a></div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th class="team-col" onclick="doSort({COL_TEAM}, '{table_id}')">Team</th>
                        <th colspan="2">BO3 Fullrate</th>
                        <th colspan="2">BO5 Fullrate</th>
                        <th colspan="2">Series</th>
                        <th colspan="2">Games</th>
                        <th style="width:80px">Streak</th>
                        <th style="width:120px">Last Date</th>
                    </tr>
                </thead>
                <tbody>"""
        
        # 默认按满局率排序
        sorted_teams = sorted(team_stats.items(), key=lambda x: (
            rate(x[1]["bo3_full"], x[1]["bo3_total"]) or -1.0,
            -(rate(x[1]["series_wins"], x[1]["series_total"]) or 0)
        ), reverse=True)

        for team_name, stat in sorted_teams:
            bo3_r = rate(stat["bo3_full"], stat["bo3_total"])
            bo5_r = rate(stat["bo5_full"], stat["bo5_total"])
            ser_r = rate(stat["series_wins"], stat["series_total"])
            gam_r = rate(stat.get("game_wins", 0), stat.get("game_total", 0))
            
            streak = f"<span class='badge' style='background:#10b981'>{stat['streak_wins']}W</span>" if stat["streak_wins"] > 0 else (f"<span class='badge' style='background:#f43f5e'>{stat['streak_losses']}L</span>" if stat["streak_losses"] > 0 else "-")
            last_date = stat["last_date"].strftime("%Y-%m-%d") if stat["last_date"] else "-"

            content += f"""
                <tr>
                    <td class="team-col">{team_name}</td>
                    <td>{stat['bo3_full']}/{stat['bo3_total'] if stat['bo3_total']>0 else '-'}</td>
                    <td style="background:{color_by_ratio(bo3_r, True)};color:white;font-weight:bold">{pct(bo3_r)}</td>
                    <td>{stat['bo5_full']}/{stat['bo5_total'] if stat['bo5_total']>0 else '-'}</td>
                    <td style="background:{color_by_ratio(bo5_r, True)};color:white;font-weight:bold">{pct(bo5_r)}</td>
                    <td>{stat['series_wins']}-{stat['series_total']-stat['series_wins']}</td>
                    <td style="background:{color_by_ratio(ser_r)};color:white;font-weight:bold">{pct(ser_r)}</td>
                    <td>{stat['game_wins']}-{stat['game_total']-stat['game_wins']}</td>
                    <td style="background:{color_by_ratio(gam_r)};color:white;font-weight:bold">{pct(gam_r)}</td>
                    <td>{streak}</td>
                    <td style="color:{color_by_date(stat['last_date'], dates)};font-weight:700">{last_date}</td>
                </tr>"""
        content += "</tbody></table></div>"

    html_end = f"""
    <div class="footer">Updated: {now} | <a href="{GITHUB_REPO}" target="_blank">GitHub</a></div>
    </div>
    <script>
        function doSort(col, id) {{
            const table = document.getElementById(id);
            const rows = Array.from(table.tBodies[0].rows);
            const dir = table.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
            rows.sort((a, b) => {{
                let va = a.cells[col].innerText, vb = b.cells[col].innerText;
                return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }});
            table.setAttribute('data-dir', dir);
            rows.forEach(r => table.tBodies[0].appendChild(r));
        }}
    </script>
</body>
</html>"""
    
    INDEX_FILE.write_text(html_start + content + html_end, encoding="utf-8")
    print(f"Successfully generated {INDEX_FILE}")

# --- 主程序 ---
if __name__ == "__main__":
    results = {}
    for tour in TOURNAMENTS:
        results[tour["slug"]] = scrape(tour)
    build(results)
