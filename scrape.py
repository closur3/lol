import requests
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import sys

# ================== 配置 ==================
TOURNAMENTS = [
    {
        "slug": "2026-lck-cup", 
        "title": "2026 LCK Cup", 
        "overview_page": "LCK/2026 Season/Cup"
    },
    {
        "slug": "2026-lpl-split-1", 
        "title": "2026 LPL Split 1", 
        "overview_page": "LPL/2026 Season/Split 1"
    },
]

INDEX_FILE = Path("index.html")
TEAMS_JSON = Path("teams.json")
TOURNAMENT_DIR = Path("tournament")
GITHUB_REPO = "https://github.com/closur3/lol"

TOURNAMENT_DIR.mkdir(exist_ok=True)
CST = timezone(timedelta(hours=8))

# ================== 列索引常量 ==================
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

# ---------- 队名映射处理器 ----------
def load_team_map():
    if TEAMS_JSON.exists():
        try: return json.loads(TEAMS_JSON.read_text(encoding='utf-8'))
        except: pass
    return {}

TEAM_MAP = load_team_map()

def get_short_name(full_name):
    name_upper = full_name.upper()
    for key, short_val in TEAM_MAP.items():
        if key.upper() in name_upper: return short_val
    return full_name.replace("Esports", "").replace("Gaming", "").replace("Academy", "").replace("Team", "").strip()

# ---------- 辅助函数 ----------
def rate(numerator, denominator): 
    return numerator / denominator if denominator > 0 else None 

def pct(ratio): 
    return f"{ratio*100:.1f}%" if ratio is not None else "-"

def get_hsl(hue, saturation=70, lightness=45): 
    return f"hsl({int(hue)}, {saturation}%, {lightness}%)"

def color_by_ratio(ratio, reverse=False):
    if ratio is None: return "#f1f5f9"
    hue = (1 - max(0, min(1, ratio))) * 140 if reverse else max(0, min(1, ratio)) * 140
    return get_hsl(hue, saturation=65, lightness=48)

def color_by_date(date, all_dates):
    if not date or not all_dates: return "#9ca3af"
    try:
        ts = date.timestamp()
        max_ts = max(d.timestamp() for d in all_dates)
        min_ts = min(d.timestamp() for d in all_dates)
        factor = (ts - min_ts) / (max_ts - min_ts) if max_ts != min_ts else 1
        return f"hsl(215, {int(factor * 80 + 20)}%, {int(55 - factor * 15)}%)"
    except:
        return "#9ca3af"

# ---------- 进度条辅助函数 ----------
def wait_with_countdown(seconds):
    """显示倒计时，证明程序没死机"""
    print(f"      ⏳ Cooling down: ", end="", flush=True)
    # 简单的进度条
    for i in range(seconds, 0, -1):
        if i % 5 == 0 or i < 5: # 每5秒或最后几秒显示
            print(f"{i}..", end="", flush=True)
        time.sleep(1)
    print("Go!", flush=True)

# ---------- 抓取逻辑 (防卡死版) ----------
def scrape(tournament):
    overview_page = tournament["overview_page"]
    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, 
        "bo5_full": 0, "bo5_total": 0, 
        "series_wins": 0, "series_total": 0, 
        "game_wins": 0, "game_total": 0, 
        "streak_wins": 0, "streak_losses": 0, 
        "streak_dirty": False, "last_date": None
    })

    api_url = "https://lol.fandom.com/api.php"
    session = requests.Session()
    session.headers.update({'User-Agent': 'LoLStatsBot/AntiStuck (https://github.com/closur3/lol)'})

    # ==========================================
    # 阶段 1: 抓取 MatchSchedule
    # ==========================================
    print(f"   [Phase 1] Fetching Match Schedule...", flush=True)
    matches = []
    limit = 500
    offset = 0
    
    while True:
        params = {
            "action": "cargoquery", "format": "json", "tables": "MatchSchedule",
            "fields": "Team1, Team2, Team1Score, Team2Score, DateTime_UTC, BestOf",
            "where": f"OverviewPage='{overview_page}'",
            "order_by": "DateTime_UTC ASC", "limit": limit, "offset": offset
        }
        
        wait_with_countdown(3) # 基础等待
        
        try:
            print(f"      -> Requesting offset {offset}...", end=" ", flush=True)
            response = session.get(api_url, params=params, timeout=20)
            data = response.json()
            
            if "error" in data:
                print("FAILED!", flush=True)
                print(f"      ⚠️ API RATE LIMIT! Sleeping 70s to reset quota...", flush=True)
                wait_with_countdown(70) # 延长到70秒，确保封禁解除
                continue
            
            if "cargoquery" in data:
                batch = [item["title"] for item in data["cargoquery"]]
                matches.extend(batch)
                print(f"OK! Got {len(batch)} items. (Total: {len(matches)})", flush=True)
                
                if len(batch) < limit: 
                    break
                offset += limit
            else: 
                print("Empty response.", flush=True)
                break
        except Exception as e:
            print(f"\n      ❌ Network Error: {e}", flush=True)
            break

    # 处理 Match 数据
    print(f"   ... Analyzing {len(matches)} matches for BO stats...", flush=True)
    for m in matches:
        t1 = get_short_name(m.get("Team1", ""))
        t2 = get_short_name(m.get("Team2", ""))
        date_str = m.get("DateTime_UTC") or m.get("DateTime UTC") or m.get("DateTime")
        
        try: s1, s2 = int(m.get("Team1Score")), int(m.get("Team2Score"))
        except: continue
        if s1 == 0 and s2 == 0: continue 

        try:
            clean_date = date_str.replace(" UTC", "").split("+")[0].strip()
            series_date = datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(CST)
        except: series_date = None

        max_s, min_s = max(s1, s2), min(s1, s2)
        best_of = m.get("BestOf")
        
        # [Backup Calculation]
        # 我们在这里也计算胜负场和Streak，以防Phase 2失败。
        # 如果Phase 2成功，这些值会被覆盖；如果失败，至少有这些值兜底。
        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)
        
        # 更新基础胜负 (Backup)
        stats[winner]["series_wins"] += 1
        stats[t1]["series_total"] += 1
        stats[t2]["series_total"] += 1
        stats[t1]["game_wins"] += s1
        stats[t2]["game_wins"] += s2
        stats[t1]["game_total"] += (s1 + s2)
        stats[t2]["game_total"] += (s1 + s2)
        
        # 更新 Streak (Backup)
        if stats[winner]["streak_losses"] > 0:
            stats[winner]["streak_losses"] = 0
            stats[winner]["streak_wins"] = 1
        else: stats[winner]["streak_wins"] += 1
        if stats[loser]["streak_wins"] > 0:
            stats[loser]["streak_wins"] = 0
            stats[loser]["streak_losses"] = 1
        else: stats[loser]["streak_losses"] += 1

        for team in (t1, t2):
            if series_date and (not stats[team]["last_date"] or series_date > stats[team]["last_date"]):
                stats[team]["last_date"] = series_date
            
            if best_of == "3" or (not best_of and max_s == 2):
                stats[team]["bo3_total"] += 1
                if min_s == 1: stats[team]["bo3_full"] += 1
            elif best_of == "5" or (not best_of and max_s == 3):
                stats[team]["bo5_total"] += 1
                if min_s == 2: stats[team]["bo5_full"] += 1

    # ==========================================
    # 阶段 2: 抓取 Standings
    # ==========================================
    print(f"   [Phase 2] Fetching Official Standings...", flush=True)
    # [核心修改] 增加阶段间隙，防止连续请求触发封禁
    print(f"      ☕ Taking a 10s break before asking for Standings...", flush=True)
    wait_with_countdown(10)
    
    standings_data = []
    standings_retry = 0
    standings_success = False
    
    while standings_retry < 3: # 最多重试3次，不行就跳过
        params = {
            "action": "cargoquery", "format": "json", "tables": "Standings",
            "fields": "Team, Win, Loss, GameWin, GameLoss, Streak, StreakDirection",
            "where": f"OverviewPage='{overview_page}'",
            "limit": 500
        }
        
        try:
            print(f"      -> Requesting standings (Attempt {standings_retry+1}/3)...", end=" ", flush=True)
            response = session.get(api_url, params=params, timeout=20)
            data = response.json()
            
            if "error" in data:
                print("FAILED!", flush=True)
                print(f"      ⚠️ API RATE LIMIT! Sleeping 70s...", flush=True)
                wait_with_countdown(70)
                standings_retry += 1
                continue

            if "cargoquery" in data:
                standings_data = [item["title"] for item in data["cargoquery"]]
                print(f"OK! Got {len(standings_data)} records.", flush=True)
                standings_success = True
                break 
            else:
                print("Empty response.", flush=True)
                break
        except Exception as e:
            print(f"\n      ❌ Error: {e}", flush=True)
            standings_retry += 1
            time.sleep(5)
            
    if not standings_success:
        print("      ⚠️ Skipping Standings (Using calculated stats from Phase 1 instead).", flush=True)
    else:
        # 处理 Standings 数据 (覆盖 Phase 1 的计算值)
        print(f"   ... Overwriting with OFFICIAL stats...", flush=True)
        for row in standings_data:
            team_name = get_short_name(row.get("Team", ""))
            if not team_name: continue
            
            try:
                w = int(row.get("Win", 0))
                l = int(row.get("Loss", 0))
                stats[team_name]["series_wins"] = w
                stats[team_name]["series_total"] = w + l
            except: pass

            try:
                gw = int(row.get("GameWin", 0))
                gl = int(row.get("GameLoss", 0))
                stats[team_name]["game_wins"] = gw
                stats[team_name]["game_total"] = gw + gl
            except: pass

            try:
                s_val = int(row.get("Streak", 0))
                s_dir = row.get("StreakDirection", "") 
                
                if s_dir == "Win":
                    stats[team_name]["streak_wins"] = s_val
                    stats[team_name]["streak_losses"] = 0
                elif s_dir == "Loss":
                    stats[team_name]["streak_wins"] = 0
                    stats[team_name]["streak_losses"] = s_val
            except: pass

    return stats

# ---------- 生成 Markdown 归档 ----------
def save_markdown(tournament, team_stats):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    lp_url = f"https://lol.fandom.com/wiki/{tournament['overview_page'].replace(' ', '_')}"
    
    sorted_teams = sorted(team_stats.items(), key=lambda x: (
        rate(x[1]["bo3_full"], x[1]["bo3_total"]) if rate(x[1]["bo3_full"], x[1]["bo3_total"]) is not None else -1.0,
        -(rate(x[1]["series_wins"], x[1]["series_total"]) or 0)
    ))
    
    md_content = f"""# {tournament['title']}

**Source:** [Leaguepedia]({lp_url})  
**Updated:** {now}

---

## Statistics

| TEAM | BO3 FULL | BO3 FULLRATE | BO5 FULL | BO5 FULLRATE | SERIES | SERIES WR | GAMES | GAME WR | STREAK | LAST DATE |
|------|----------|--------------|----------|--------------|--------|-----------|-------|---------|--------|-----------|
"""
    
    for team_name, stat in sorted_teams:
        bo3_ratio = rate(stat["bo3_full"], stat["bo3_total"])
        bo5_ratio = rate(stat["bo5_full"], stat["bo5_total"])
        series_win_ratio = rate(stat["series_wins"], stat["series_total"])
        game_wins = stat.get('game_wins', 0)
        game_total = stat.get('game_total', 0)
        game_win_ratio = rate(game_wins, game_total)
        
        bo3_text = f"{stat['bo3_full']}/{stat['bo3_total']}" if stat['bo3_total'] > 0 else "-"
        bo5_text = f"{stat['bo5_full']}/{stat['bo5_total']}" if stat['bo5_total'] > 0 else "-"
        series_text = f"{stat['series_wins']}-{stat['series_total']-stat['series_wins']}" if stat['series_total'] > 0 else "-"
        game_text = f"{game_wins}-{game_total-game_wins}" if game_total > 0 else "-"
        streak_display = f"{stat['streak_wins']}W" if stat['streak_wins'] > 0 else (f"{stat['streak_losses']}L" if stat['streak_losses'] > 0 else "-")
        last_date_display = stat["last_date"].strftime("%Y-%m-%d %H:%M") if stat["last_date"] else "-"
        
        md_content += f"| {team_name} | {bo3_text} | {pct(bo3_ratio)} | {bo5_text} | {pct(bo5_ratio)} | {series_text} | {pct(series_win_ratio)} | {game_text} | {pct(game_win_ratio)} | {streak_display} | {last_date_display} |\n"
    
    md_content += f"\n---\n\n*Generated by [LoL Stats Scraper]({GITHUB_REPO})*\n"
    md_file = TOURNAMENT_DIR / f"{tournament['slug']}.md"
    md_file.write_text(md_content, encoding='utf-8')
    print(f"   ✓ Archived Markdown: {md_file}", flush=True)

# ---------- 生成 HTML ----------
def build(all_data):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    html = f"""<!DOCTYPE html>
<html>
<head>
    <link rel="icon" href="./favicon.png">
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LoL Insights</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f1f5f9; margin: 0; padding: 10px; }}
        .main-header {{ text-align: center; padding: 25px 0; }}
        .main-header h1 {{ margin: 0;font-size: 2.2rem;font-weight: 800; }}
        .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 25px; border: 1px solid #e2e8f0; }}
        .table-title {{ padding: 15px; font-weight: 700; border-bottom: 1px solid #f1f5f9; }}
        .table-title a {{ color: #2563eb; text-decoration: none; }}
        .archive-link {{ margin-left: 10px; font-size: 12px; color: #64748b; }}
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
    <header class="main-header"><h1>🏆</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

    for index, tournament in enumerate(TOURNAMENTS):
        team_stats = all_data.get(tournament["slug"], {})
        table_id = f"t{index}"
        dates = [stat["last_date"] for stat in team_stats.values() if stat["last_date"]]
        
        lp_url = f"https://lol.fandom.com/wiki/{tournament['overview_page'].replace(' ', '_')}"
        archive_link = f"tournament/{tournament['slug']}.md"
        
        html += f"""
        <div class="wrapper">
            <div class="table-title">
                <a href="{lp_url}" target="_blank">{tournament['title']}</a>
                <span class="archive-link">| <a href="{archive_link}" target="_blank">📄 View Archive</a></span>
            </div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th class="team-col" onclick="doSort({COL_TEAM}, '{table_id}')">TEAM</th>
                        <th colspan="2" onclick="doSort({COL_BO3_PCT}, '{table_id}')" style="text-align:center;">BO3 FULLRATE</th>
                        <th colspan="2" onclick="doSort({COL_BO5_PCT}, '{table_id}')" style="text-align:center;">BO5 FULLRATE</th>
                        <th colspan="2" onclick="doSort({COL_SERIES_WR}, '{table_id}')" style="text-align:center;">SERIES</th>
                        <th colspan="2" onclick="doSort({COL_GAME_WR}, '{table_id}')" style="text-align:center;">GAMES</th>
                        <th class="col-streak" onclick="doSort({COL_STREAK}, '{table_id}')">STREAK</th>
                        <th class="col-last" onclick="doSort({COL_LAST_DATE}, '{table_id}')">LAST DATE</th>
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
            game_wins = stat.get('game_wins', 0)
            game_total = stat.get('game_total', 0)
            game_win_ratio = rate(game_wins, game_total)
            
            streak_display = f"<span class='badge' style='background:#10b981'>{stat['streak_wins']}W</span>" if stat['streak_wins'] > 0 else (f"<span class='badge' style='background:#f43f5e'>{stat['streak_losses']}L</span>" if stat['streak_losses'] > 0 else "-")
            
            last_date_display = stat["last_date"].strftime("%Y-%m-%d %H:%M") if stat["last_date"] else "-"
            
            bo3_text = f"{stat['bo3_full']}/{stat['bo3_total']}" if stat['bo3_total'] > 0 else "-"
            bo5_text = f"{stat['bo5_full']}/{stat['bo5_total']}" if stat['bo5_total'] > 0 else "-"
            series_text = f"{stat['series_wins']}-{stat['series_total']-stat['series_wins']}" if stat['series_total'] > 0 else "-"
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
            if (value.includes('%')) return parseFloat(value);
            if (value.includes('/')) {{ 
                let parts = value.split('/'); 
                return parts[1] === '-' ? -1 : parseFloat(parts[0])/parseFloat(parts[1]); 
            }}
            if (value.includes('-') && value.split('-').length === 2) {{
                return parseFloat(value.split('-')[0]);
            }}
            const number = parseFloat(value);
            return isNaN(number) ? value.toLowerCase() : number;
        }}
    </script>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")
    print(f"✓ Generated: {INDEX_FILE}", flush=True)

if __name__ == "__main__":
    print("Starting LoL Stats Scraper (Interactive Log Mode)...", flush=True)
    data = {}
    
    for tournament in TOURNAMENTS:
        print(f"\nProcessing: {tournament['title']}", flush=True)
        team_stats = scrape(tournament)
        data[tournament["slug"]] = team_stats
        save_markdown(tournament, team_stats)
    
    build(data)
    print("\n✅ All done!", flush=True)
