import requests
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time

# ================== 配置 ==================
# 使用你刚刚探测到的准确 Key
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
TOURNAMENT_DIR = Path("tournament")
GITHUB_REPO = "https://github.com/closur3/lol"

# 确保归档目录存在
TOURNAMENT_DIR.mkdir(exist_ok=True)

# 时区定义 (CST = UTC+8)
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

def color_by_date(date_obj, all_dates):
    if not date_obj or not all_dates: return "#9ca3af"
    try:
        ts = date_obj.timestamp()
        max_ts = max(d.timestamp() for d in all_dates)
        min_ts = min(d.timestamp() for d in all_dates)
        
        if max_ts == min_ts: return "hsl(215, 100%, 40%)"
        
        factor = (ts - min_ts) / (max_ts - min_ts)
        return f"hsl(215, {int(factor * 80 + 20)}%, {int(55 - factor * 15)}%)"
    except:
        return "#9ca3af"

# ---------- Leaguepedia API 抓取逻辑 ----------
def fetch_leaguepedia_data(overview_page):
    """
    使用 CargoQuery 获取比赛数据
    """
    api_url = "https://lol.fandom.com/api.php"
    matches = []
    limit = 500
    offset = 0
    
    print(f"   Fetching data for: {overview_page}...")
    
    while True:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": "MatchSchedule",
            "fields": "Team1, Team2, Team1Score, Team2Score, Winner, DateTime_UTC, BestOf",
            # 只要是这个赛事的，且有比分的（说明打完了）
            "where": f"OverviewPage='{overview_page}' AND Team1Score IS NOT NULL",
            "order_by": "DateTime_UTC ASC",
            "limit": limit,
            "offset": offset
        }
        
        try:
            response = requests.get(api_url, params=params, headers={'User-Agent': 'LoLStatsBot/2.0'}, timeout=15)
            data = response.json()
            
            if "cargoquery" not in data:
                print(f"   Warning: No data found (Check API name?) {data}")
                break
                
            batch = [item["title"] for item in data["cargoquery"]]
            if not batch: break
            
            matches.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            time.sleep(0.5) 
            
        except Exception as e:
            print(f"   Error fetching data: {e}")
            break
            
    return matches

def process_matches(matches):
    # 初始化统计字典
    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, 
        "bo5_full": 0, "bo5_total": 0, 
        "series_wins": 0, "series_total": 0, 
        "game_wins": 0, "game_total": 0, 
        "streak_wins": 0, "streak_losses": 0, 
        "streak_dirty": False, "last_date": None
    })
    
    print(f"   Processing {len(matches)} matches...")
    
    for m in matches:
        team1 = m.get("Team1")
        team2 = m.get("Team2")
        winner_field = m.get("Winner")
        date_str = m.get("DateTime_UTC")
        best_of = m.get("BestOf")
        
        # 1. 基础数据完整性检查
        if not (team1 and team2 and date_str):
            continue
            
        # 2. 分数解析
        try:
            s1 = int(m.get("Team1Score", 0))
            s2 = int(m.get("Team2Score", 0))
        except:
            continue # 分数不是数字，跳过
            
        # 3. 确定胜负关系 (鲁棒性处理：如果Winner字段缺失，根据比分判断)
        if s1 > s2:
            real_winner, real_loser = team1, team2
        elif s2 > s1:
            real_winner, real_loser = team2, team1
        else:
            # 平局 (Bo2等情况)，暂时不处理胜负场，只加小分
            # 但 LCK/LPL 只有 BO3/BO5，理论上不会有平局
            continue 

        # 4. 时间处理 (UTC -> CST)
        try:
            # 格式通常为 "2026-01-20 09:00:00"
            dt_utc = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            dt_cst = dt_utc.astimezone(CST)
        except:
            dt_cst = None

        # 5. 更新基础统计
        for team in (team1, team2):
            # 更新最后比赛时间
            if dt_cst:
                if stats[team]["last_date"] is None or dt_cst > stats[team]["last_date"]:
                    stats[team]["last_date"] = dt_cst
            
            stats[team]["series_total"] += 1
            stats[team]["game_total"] += (s1 + s2)
        
        stats[real_winner]["series_wins"] += 1
        stats[team1]["game_wins"] += s1
        stats[team2]["game_wins"] += s2
        
        # 6. 判断 BO3 / BO5
        max_score = max(s1, s2)
        min_score = min(s1, s2)
        
        # 如果 API 没给 BestOf，可以尝试推断
        # LPL/LCK 常规赛多为 BO3
        if best_of == "3" or (not best_of and max_score == 2):
            for team in (team1, team2):
                stats[team]["bo3_total"] += 1
            if min_score == 1:
                for team in (team1, team2):
                    stats[team]["bo3_full"] += 1
        
        elif best_of == "5" or (not best_of and max_score == 3):
            for team in (team1, team2):
                stats[team]["bo5_total"] += 1
            if min_score == 2:
                for team in (team1, team2):
                    stats[team]["bo5_full"] += 1
                    
        # 7. 更新连胜/连败 (前提：matches 是按时间正序排列的)
        # Winner 处理
        if stats[real_winner]["streak_losses"] > 0:
            stats[real_winner]["streak_losses"] = 0
            stats[real_winner]["streak_wins"] = 1
        else:
            stats[real_winner]["streak_wins"] += 1
            
        # Loser 处理
        if stats[real_loser]["streak_wins"] > 0:
            stats[real_loser]["streak_wins"] = 0
            stats[real_loser]["streak_losses"] = 1
        else:
            stats[real_loser]["streak_losses"] += 1

    return stats

# ---------- 生成 Markdown 归档 ----------
def save_markdown(tournament, team_stats):
    if not team_stats:
        print(f"   Skipping markdown for {tournament['slug']} (No data)")
        return

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

| Team | BO3 Full | BO3 Fullrate | BO5 Full | BO5 Fullrate | Series | Series WR | Games | Game WR | Streak | Last Date |
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
        # 带小时的日期格式
        last_date_display = stat["last_date"].strftime("%Y-%m-%d %H:%M") if stat["last_date"] else "-"
        
        md_content += f"| {team_name} | {bo3_text} | {pct(bo3_ratio)} | {bo5_text} | {pct(bo5_ratio)} | {series_text} | {pct(series_win_ratio)} | {game_text} | {pct(game_win_ratio)} | {streak_display} | {last_date_display} |\n"
    
    md_content += f"""
---

*Generated by [LoL Stats Scraper]({GITHUB_REPO})*
"""
    
    md_file = TOURNAMENT_DIR / f"{tournament['slug']}.md"
    md_file.write_text(md_content, encoding='utf-8')
    print(f"✓ Archived: {md_file}")

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
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f1f5f9; margin: 0; padding: 10px; color: #1e293b; }}
        .main-header {{ text-align: center; padding: 25px 0; }}
        .main-header h1 {{ margin: 0;font-size: 2.2rem;font-weight: 800; letter-spacing: -0.025em; }}
        .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 25px; border: 1px solid #e2e8f0; }}
        .table-title {{ padding: 15px 20px; font-weight: 700; border-bottom: 1px solid #f1f5f9; display: flex; align-items: center; justify-content: space-between; }}
        .table-title a {{ color: #2563eb; text-decoration: none; transition: 0.2s; }}
        .table-title a:hover {{ color: #1d4ed8; text-decoration: underline; }}
        .archive-link {{ font-size: 0.85rem; color: #64748b; font-weight: 500; }}
        table {{ width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
        th {{ background: #f8fafc; padding: 12px 8px; font-weight: 600; color: #64748b; border-bottom: 2px solid #e2e8f0; cursor: pointer; transition: 0.2s; user-select: none; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.75rem; }}
        th:hover {{ background: #eff6ff; color: #2563eb; }}
        td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .team-col {{ position: sticky; left: 0; background: white !important; z-index: 10; border-right: 2px solid #f1f5f9; text-align: left; font-weight: 700; padding-left: 20px; width: 100px; color: #0f172a; }}
        .col-bo3 {{ width: 70px; }}
        .col-bo3-pct {{ width: 85px; }}
        .col-bo5 {{ width: 70px; }}
        .col-bo5-pct {{ width: 85px; }}
        .col-series {{ width: 80px; }}
        .col-series-wr {{ width: 100px; }}
        .col-game {{ width: 80px; }}
        .col-game-wr {{ width: 100px; }}
        .col-streak {{ width: 80px; }}
        .col-last {{ width: 130px; font-variant-numeric: tabular-nums; }}
        .badge {{ color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; display: inline-block; min-width: 24px; }}
        .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; }}
        tr:hover td {{ background-color: #f8fafc; }}
        tr:hover td.team-col {{ background-color: #f8fafc !important; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>🏆 League Stats</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

    for index, tournament in enumerate(TOURNAMENTS):
        team_stats = all_data.get(tournament["slug"], {})
        if not team_stats: continue # 跳过没有数据的赛事表格
        
        table_id = f"t{index}"
        dates = [stat["last_date"] for stat in team_stats.values() if stat["last_date"]]
        
        lp_url = f"https://lol.fandom.com/wiki/{tournament['overview_page'].replace(' ', '_')}"
        archive_link = f"tournament/{tournament['slug']}.md"
        
        html += f"""
        <div class="wrapper">
            <div class="table-title">
                <span>{tournament['title']}</span>
                <span class="archive-link">
                    <a href="{lp_url}" target="_blank">Source</a> • 
                    <a href="{archive_link}" target="_blank">Archive</a>
                </span>
            </div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th class="team-col" onclick="doSort({COL_TEAM}, '{table_id}')">Team</th>
                        <th colspan="2" onclick="doSort({COL_BO3_PCT}, '{table_id}')" style="text-align:center;">BO3 Fullrate</th>
                        <th colspan="2" onclick="doSort({COL_BO5_PCT}, '{table_id}')" style="text-align:center;">BO5 Fullrate</th>
                        <th colspan="2" onclick="doSort({COL_SERIES_WR}, '{table_id}')" style="text-align:center;">Series</th>
                        <th colspan="2" onclick="doSort({COL_GAME_WR}, '{table_id}')" style="text-align:center;">Games</th>
                        <th class="col-streak" onclick="doSort({COL_STREAK}, '{table_id}')">Streak</th>
                        <th class="col-last" onclick="doSort({COL_LAST_DATE}, '{table_id}')">Last Date (CST)</th>
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
                    <td class="col-bo3" style="background:{'#f8fafc' if stat['bo3_total'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['bo3_total'] == 0 else 'inherit'}">{bo3_text}</td>
                    <td class="col-bo3-pct" style="background:{color_by_ratio(bo3_ratio, reverse=True)};color:{'white' if bo3_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(bo3_ratio)}</td>
                    <td class="col-bo5" style="background:{'#f8fafc' if stat['bo5_total'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['bo5_total'] == 0 else 'inherit'}">{bo5_text}</td>
                    <td class="col-bo5-pct" style="background:{color_by_ratio(bo5_ratio, reverse=True)};color:{'white' if bo5_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(bo5_ratio)}</td>
                    <td class="col-series" style="background:{'#f8fafc' if stat['series_total'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['series_total'] == 0 else 'inherit'}">{series_text}</td>
                    <td class="col-series-wr" style="background:{color_by_ratio(series_win_ratio)};color:{'white' if series_win_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(series_win_ratio)}</td>
                    <td class="col-game" style="background:{'#f8fafc' if game_total == 0 else 'transparent'};color:{'#cbd5e1' if game_total == 0 else 'inherit'}">{game_text}</td>
                    <td class="col-game-wr" style="background:{color_by_ratio(game_win_ratio)};color:{'white' if game_win_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(game_win_ratio)}</td>
                    <td class="col-streak" style="background:{'#f8fafc' if stat['streak_wins'] == 0 and stat['streak_losses'] == 0 else 'transparent'};color:{'#cbd5e1' if stat['streak_wins'] == 0 and stat['streak_losses'] == 0 else 'inherit'}">{streak_display}</td>
                    <td class="col-last" style="background:{'#f8fafc' if not stat['last_date'] else 'transparent'};color:{color_by_date(stat['last_date'], dates) if stat['last_date'] else '#cbd5e1'};font-weight:600;font-size:12px;">{last_date_display}</td>
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
                    valueA = valueA === "-" ? 0 : new Date(valueA.replace(/-/g, '/')).getTime(); 
                    valueB = valueB === "-" ? 0 : new Date(valueB.replace(/-/g, '/')).getTime(); 
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
    print(f"✓ Generated: {INDEX_FILE}")

if __name__ == "__main__":
    print("Starting LoL Stats Scraper (Leaguepedia API)...")
    data = {}
    
    for tournament in TOURNAMENTS:
        print(f"\nProcessing: {tournament['title']}")
        # 1. 获取数据
        matches = fetch_leaguepedia_data(tournament["overview_page"])
        
        if matches:
            # 2. 统计
            team_stats = process_matches(matches)
            if team_stats:
                data[tournament["slug"]] = team_stats
                # 3. 归档
                save_markdown(tournament, team_stats)
            else:
                print("   No valid match data extracted.")
        else:
            print("   No matches found in API.")
    
    build(data)
    print("\n✅ All done!")
