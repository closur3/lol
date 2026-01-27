import requests
import json
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

TOURNAMENTS = [
{“slug”: “2026-lck-cup”, “title”: “2026 LCK Cup”, “url”: “https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/”},
{“slug”: “2026-lpl-split-1”, “title”: “2026 LPL Split 1”, “url”: “https://gol.gg/tournament/tournament-matchlist/LPL%202026%20Split%201/”},
]
INDEX_FILE = Path(“index.html”)
TEAMS_JSON = Path(“teams.json”)
GITHUB_REPO = “https://github.com/closur3/lol”

COL_TEAM = 0
COL_BO3 = 1
COL_BO3_PCT = 2
COL_BO5 = 3
COL_BO5_PCT = 4
COL_SERIES = 5
COL_SERIES_WR = 6
COL_GAME = 7
COL_GAME_WR = 8
COL_STREAK = 9
COL_LAST_DATE = 10

def load_team_map():
if TEAMS_JSON.exists():
try:
return json.loads(TEAMS_JSON.read_text(encoding=“utf-8”))
except:
pass
return {}

TEAM_MAP = load_team_map()

def get_short_name(full_name):
name_upper = full_name.upper()
for key, short_val in TEAM_MAP.items():
if key.upper() in name_upper:
return short_val
return full_name.replace(“Esports”, “”).replace(“Gaming”, “”).replace(“Academy”, “”).replace(“Team”, “”).strip()

def rate(numerator, denominator):
return numerator / denominator if denominator > 0 else None

def pct(ratio):
return f”{ratio*100:.1f}%” if ratio is not None else “-”

def get_hsl(hue, saturation=70, lightness=45):
return f”hsl({int(hue)}, {saturation}%, {lightness}%)”

def color_by_ratio(ratio, reverse=False):
if ratio is None:
return “#f1f5f9”
hue = (1 - max(0, min(1, ratio))) * 140 if reverse else max(0, min(1, ratio)) * 140
return get_hsl(hue, saturation=65, lightness=48)

def color_by_date(date, all_dates):
if not date or not all_dates:
return “#9ca3af”
max_date, min_date = max(all_dates), min(all_dates)
factor = (date - min_date).total_seconds() / (max_date - min_date).total_seconds() if max_date != min_date else 1
return f”hsl(215, {int(factor * 80 + 20)}%, {int(55 - factor * 15)}%)”

def scrape(tournament):
try:
response = requests.get(tournament[“url”], headers={“User-Agent”: “Mozilla/5.0”}, timeout=15)
soup = BeautifulSoup(response.text, “html.parser”)
except:
return {}

```
stats = defaultdict(lambda: {
    "bo3_full": 0, "bo3_total": 0, 
    "bo5_full": 0, "bo5_total": 0, 
    "series_wins": 0, "series_total": 0, 
    "game_wins": 0, "game_total": 0, 
    "streak_wins": 0, "streak_losses": 0, 
    "streak_dirty": False, "last_date": None
})

for row in soup.select("table tr"):
    cells = row.find_all("td")
    if len(cells) < 5: 
        continue
    
    team1 = get_short_name(cells[1].text.strip())
    team2 = get_short_name(cells[3].text.strip())
    score = cells[2].text.strip()
    
    try: 
        series_date = datetime.strptime(cells[-1].text.strip(), "%Y-%m-%d")
    except: 
        series_date = None
        
    if "-" not in score: 
        continue
    
    try: 
        score1, score2 = map(int, score.split("-"))
    except: 
        continue
        
    winner, loser = (team1, team2) if score1 > score2 else (team2, team1)
    max_score, min_score = max(score1, score2), min(score1, score2)
    
    for team in (team1, team2):
        if series_date and (not stats[team]["last_date"] or series_date > stats[team]["last_date"]): 
            stats[team]["last_date"] = series_date
        stats[team]["series_total"] += 1
        stats[team]["game_total"] += (score1 + score2)
        
    stats[winner]["series_wins"] += 1
    stats[team1]["game_wins"] += score1
    stats[team2]["game_wins"] += score2
    
    if max_score == 2:
        for team in (team1, team2): 
            stats[team]["bo3_total"] += 1
        if min_score == 1: 
            for team in (team1, team2): 
                stats[team]["bo3_full"] += 1
    elif max_score == 3:
        for team in (team1, team2): 
            stats[team]["bo5_total"] += 1
        if min_score == 2: 
            for team in (team1, team2): 
                stats[team]["bo5_full"] += 1
    
    if not stats[winner]["streak_dirty"]:
        if stats[winner]["streak_losses"] > 0: 
            stats[winner]["streak_dirty"] = True
        else: 
            stats[winner]["streak_wins"] += 1
            
    if not stats[loser]["streak_dirty"]:
        if stats[loser]["streak_wins"] > 0: 
            stats[loser]["streak_dirty"] = True
        else: 
            stats[loser]["streak_losses"] += 1
            
return stats
```

def build(all_data):
now = datetime.now(timezone(timedelta(hours=8))).strftime(”%Y-%m-%d %H:%M:%S CST”)
html = f”””<!DOCTYPE html>

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
        .col-bo3 {{ width: 70px; }}
        .col-bo3-pct {{ width: 85px; }}
        .col-bo5 {{ width: 70px; }}
        .col-bo5-pct {{ width: 85px; }}
        .col-series {{ width: 80px; }}
        .col-series-wr {{ width: 100px; }}
        .col-game {{ width: 80px; }}
        .col-game-wr {{ width: 100px; }}
        .col-streak {{ width: 80px; }}
        .col-last {{ width: 120px; }}
        .badge {{ color: white; border-radius: 4px; padding: 3px 7px; font-size: 11px; font-weight: 700; }}
        .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>🏆 LoL Insights Pro</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

```
for index, tournament in enumerate(TOURNAMENTS):
    team_stats = all_data.get(tournament["slug"], {})
    table_id = f"t{index}"
    dates = [stat["last_date"] for stat in team_stats.values() if stat["last_date"]]
    html += f"""
    <div class="wrapper">
        <div class="table-title"><a href="{tournament["url"]}" target="_blank">{tournament["title"]}</a></div>
        <table id="{table_id}">
            <thead>
                <tr>
                    <th class="team-col" onclick="doSort({COL_TEAM}, '{table_id}')">Team</th>
                    <th colspan="2" onclick="doSort({COL_BO3_PCT}, '{table_id}')" style="text-align:center;">BO3 Fullrate</th>
                    <th colspan="2" onclick="doSort({COL_BO5_PCT}, '{table_id}')" style="text-align:center;">BO5 Fullrate</th>
                    <th colspan="2" onclick="doSort({COL_SERIES_WR}, '{table_id}')" style="text-align:center;">Series</th>
                    <th colspan="2" onclick="doSort({COL_GAME_WR}, '{table_id}')" style="text-align:center;">Games</th>
                    <th class="col-streak" onclick="doSort({COL_STREAK}, '{table_id}')">Streak</th>
                    <th class="col-last" onclick="doSort({COL_LAST_DATE}, '{table_id}')">Last Date</th>
                </tr>
            </thead>
            <tbody>"""
    
    sorted_teams = sorted(team_stats.items(), key=lambda x: (
        rate(x[1]["bo3_full"], x[1]["bo3_total"]) if rate(x[1]["bo3_full"], x[1]["bo3_total"]) is not None else -1.0,
        -(rate(x[1]["series_wins"], x[1]["series_total"]) or 0)
    ))

    for team_name, stat in sorted_teams:
        bo3_ratio = rate(stat["bo3_full"], stat["bo3_total"])
        bo5_ratio = rate(stat["bo5_full"], stat["bo5_total"])
        series_win_ratio = rate(stat["series_wins"], stat["series_total"])
        game_wins = stat.get("game_wins", 0)
        game_total = stat.get("game_total", 0)
        game_win_ratio = rate(game_wins, game_total)
        
        streak_display = f"<span class='badge' style='background:#10b981'>{stat['streak_wins']}W</span>" if stat["streak_wins"] > 0 else (f"<span class='badge' style='background:#f43f5e'>{stat['streak_losses']}L</span>" if stat["streak_losses"] > 0 else "-")
        last_date_display = stat["last_date"].strftime("%Y-%m-%d") if stat["last_date"] else "-"
        
        bo3_text = f"{stat['bo3_full']}/{stat['bo3_total']}" if stat["bo3_total"] > 0 else "-"
        bo5_text = f"{stat['bo5_full']}/{stat['bo5_total']}" if stat["bo5_total"] > 0 else "-"
        series_text = f"{stat['series_wins']}-{stat['series_total']-stat['series_wins']}" if stat["series_total"] > 0 else "-"
        game_text = f"{game_wins}-{game_total-game_wins}" if game_total > 0 else "-"

        html += f"""
            <tr>
                <td class="team-col">{team_name}</td>
                <td class="col-bo3" style="background:{'#f1f5f9' if stat['bo3_total'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['bo3_total'] == 0 else 'inherit'}">{bo3_text}</td>
                <td class="col-bo3-pct" style="background:{color_by_ratio(bo3_ratio, reverse=True)};color:{'white' if bo3_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(bo3_ratio)}</td>
                <td class="col-bo5" style="background:{'#f1f5f9' if stat['bo5_total'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['bo5_total'] == 0 else 'inherit'}">{bo5_text}</td>
                <td class="col-bo5-pct" style="background:{color_by_ratio(bo5_ratio, reverse=True)};color:{'white' if bo5_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(bo5_ratio)}</td>
                <td class="col-series" style="background:{'#f1f5f9' if stat['series_total'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['series_total'] == 0 else 'inherit'}">{series_text}</td>
                <td class="col-series-wr" style="background:{color_by_ratio(series_win_ratio)};color:{'white' if series_win_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(series_win_ratio)}</td>
                <td class="col-game" style="background:{'#f1f5f9' if game_total == 0 else 'transparent'};color:{'#cbd5e1' if game_total == 0 else 'inherit'}">{game_text}</td>
                <td class="col-game-wr" style="background:{color_by_ratio(game_win_ratio)};color:{'white' if game_win_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(game_win_ratio)}</td>
                <td class="col-streak" style="background:{'#f1f5f9' if stat['streak_wins'] == 0 and stat['streak_losses'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['streak_wins'] == 0 and stat['streak_losses'] == 0 else 'inherit'}">{streak_display}</td>
                <td class="col-last" style="background:{'#f1f5f9' if not stat['last_date'] else 'transparent'};color:{color_by_date(stat['last_date'], dates) if stat['last_date'] else '#cbd5e1'};font-weight:700">{last_date_display}</td>
            </tr>"""
    html += "</tbody></table></div>"

html += f"""
<div class="footer">Updated: {now} | <a href="{GITHUB_REPO}" target="_blank">GitHub</a></div>
</div>
<script>
    const COL_TEAM = {COL_TEAM};
    const COL_SERIES_WR = {COL_SERIES_WR};
    const COL_GAME_WR = {COL_GAME_WR};
    const COL_LAST_DATE = {COL_LAST_DATE};
    
    function doSort(columnIndex, tableId) {{
        const table = document.getElementById(tableId);
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        const stateKey = 'data-sort-dir-' + columnIndex;
        const currentDir = table.getAttribute(stateKey);
        
        let nextDir;
        if (!currentDir) {{
            nextDir = (columnIndex === COL_TEAM) ? 'asc' : 'desc';
        }} else {{
            nextDir = currentDir === 'desc' ? 'asc' : 'desc';
        }}
        
        rows.sort((rowA, rowB) => {{
            let valueA = rowA.cells[columnIndex].innerText;
            let valueB = rowB.cells[columnIndex].innerText;
            
            if (columnIndex === COL_LAST_DATE) {{ 
                valueA = valueA === "-" ? 0 : new Date(valueA).getTime(); 
                valueB = valueB === "-" ? 0 : new Date(valueB).getTime(); 
            }} else {{ 
                valueA = parseValue(valueA);
                valueB = parseValue(valueB); 
            }}
            
            if (valueA !== valueB) {{
                return nextDir === 'asc' ? (valueA > valueB ? 1 : -1) : (valueA < valueB ? 1 : -1);
            }}
            
            if (columnIndex === COL_SERIES_WR) {{
                let gameWrA = parseValue(rowA.cells[COL_GAME_WR].innerText);
                let gameWrB = parseValue(rowB.cells[COL_GAME_WR].innerText);
                if (gameWrA !== gameWrB) {{
                    return nextDir === 'asc' ? (gameWrA > gameWrB ? 1 : -1) : (gameWrA < gameWrB ? 1 : -1);
                }}
            }}
            
            return 0;
        }});
        
        table.setAttribute(stateKey, nextDir);
        rows.forEach(row => tbody.appendChild(row));
    }}
    
    function parseValue(value) {{
        if (value === "-") return -1;
        if (value.includes("%")) return parseFloat(value);
        if (value.includes("/")) {{ 
            let parts = value.split("/"); 
            return parts[1] === "-" ? -1 : parseFloat(parts[0])/parseFloat(parts[1]); 
        }}
        if (value.includes("-") && value.split("-").length === 2) {{
            return parseFloat(value.split("-")[0]);
        }}
        const number = parseFloat(value);
        return isNaN(number) ? value.toLowerCase() : number;
    }}
</script>
```

</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if **name** == “**main**”:
data = {tournament[“slug”]: scrape(tournament) for tournament in TOURNAMENTS}
build(data)