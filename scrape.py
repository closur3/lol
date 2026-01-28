import requests
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import sys

# ================== 1. 核心配置 ==================
TOURNAMENTS = [
    {
        "slug": "2026-lck-cup", 
        "title": "2026 LCK Cup", 
        "overview_page": "LCK/2026 Season/Cup",
        "region": "LCK" # 新增字段：用于区分赛区统计
    },
    {
        "slug": "2026-lpl-split-1", 
        "title": "2026 LPL Split 1", 
        "overview_page": "LPL/2026 Season/Split 1",
        "region": "LPL" # 新增字段
    },
]

INDEX_FILE = Path("index.html")
TEAMS_JSON = Path("teams.json")
TOURNAMENT_DIR = Path("tournament")
GITHUB_REPO = "https://github.com/closur3/lol"

TOURNAMENT_DIR.mkdir(exist_ok=True)
CST = timezone(timedelta(hours=8)) # 北京时间

# 表格列索引
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

# ================== 2. 辅助工具 ==================
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

def rate(n, d): return n / d if d > 0 else None 
def pct(r): return f"{r*100:.1f}%" if r is not None else "-"

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

def wait_with_progress(seconds):
    print(f"      ⏳ Cooling down: ", end="", flush=True)
    for i in range(seconds, 0, -1):
        if i < 4 or i % 5 == 0:
            print(f"{i}..", end="", flush=True)
        time.sleep(1)
    print("Go!", flush=True)

# ================== 3. 核心抓取逻辑 ==================
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
    matches = []
    limit = 500
    offset = 0
    session = requests.Session()
    session.headers.update({'User-Agent': 'LoLStatsBot/MultiTables (https://github.com/closur3/lol)'})

    print(f"Fetching data for: {overview_page}...", flush=True)

    while True:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": "MatchSchedule",
            "fields": "Team1, Team2, Team1Score, Team2Score, DateTime_UTC, BestOf, N_MatchInPage",
            "where": f"OverviewPage='{overview_page}'",
            "order_by": "DateTime_UTC ASC", 
            "limit": limit,
            "offset": offset
        }

        wait_with_progress(3)

        try:
            print(f"      -> Requesting offset {offset}...", end=" ", flush=True)
            response = session.get(api_url, params=params, timeout=20)
            data = response.json()
            
            if "error" in data:
                print("FAILED!", flush=True)
                print(f"      ⚠️ API RATE LIMIT! Sleeping 60s...", flush=True)
                wait_with_progress(60)
                continue
            
            if "cargoquery" in data:
                batch = [item["title"] for item in data["cargoquery"]]
                matches.extend(batch)
                print(f"OK! Got {len(batch)} items. (Total: {len(matches)})", flush=True)
                
                if len(batch) < limit: break
                offset += limit
            else:
                print("Empty response.", flush=True)
                break
        except Exception as e:
            print(f"\n      ❌ Network Error: {e}", flush=True)
            time.sleep(5)
            break

    # --- 数据处理 ---
    print(f"   ... Processing & Sorting {len(matches)} matches...", flush=True)
    valid_matches = []
    
    for m in matches:
        t1 = get_short_name(m.get("Team1", ""))
        t2 = get_short_name(m.get("Team2", ""))
        date_str = m.get("DateTime_UTC") or m.get("DateTime UTC") or m.get("DateTime")
        
        try: match_order = float(m.get("N_MatchInPage", 0))
        except: match_order = 0.0

        raw_s1, raw_s2 = m.get("Team1Score"), m.get("Team2Score")
        
        if not (t1 and t2 and date_str) or raw_s1 in [None, ""] or raw_s2 in [None, ""]:
            continue
        try: s1, s2 = int(raw_s1), int(raw_s2)
        except: continue
        if s1 == 0 and s2 == 0: continue

        try:
            clean_date = date_str.replace(" UTC", "").split("+")[0].strip()
            dt_obj = datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(CST)
        except:
            dt_obj = datetime.min.replace(tzinfo=timezone.utc)
            
        # 记录每场比赛的详细信息，用于后续两张表的生成
        valid_matches.append({
            "t1": t1, "t2": t2, "s1": s1, "s2": s2,
            "date": dt_obj, "best_of": m.get("BestOf"),
            "order": match_order,
            "region": tournament.get("region", "Unknown") # 记录赛区
        })

    valid_matches.sort(key=lambda x: (x["date"], x["order"]))

    # --- 统计逻辑 (Table 1: 队伍数据) ---
    for m in valid_matches:
        t1, t2, s1, s2, dt = m["t1"], m["t2"], m["s1"], m["s2"], m["date"]
        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)
        max_s, min_s = max(s1, s2), min(s1, s2)
        
        for team in (t1, t2):
            if dt > datetime.min.replace(tzinfo=timezone.utc) and (not stats[team]["last_date"] or dt > stats[team]["last_date"]):
                stats[team]["last_date"] = dt
            stats[team]["series_total"] += 1
            stats[team]["game_total"] += (s1 + s2)
            
        stats[winner]["series_wins"] += 1
        stats[t1]["game_wins"] += s1
        stats[t2]["game_wins"] += s2
        
        if m["best_of"] == "3" or (not m["best_of"] and max_s == 2):
            for team in (t1, t2): stats[team]["bo3_total"] += 1
            if min_s == 1:
                for team in (t1, t2): stats[team]["bo3_full"] += 1
        elif m["best_of"] == "5" or (not m["best_of"] and max_s == 3):
            for team in (t1, t2): stats[team]["bo5_total"] += 1
            if min_s == 2:
                for team in (t1, t2): stats[team]["bo5_full"] += 1
        
        if stats[winner]["streak_losses"] > 0:
            stats[winner]["streak_losses"] = 0
            stats[winner]["streak_wins"] = 1
        else: stats[winner]["streak_wins"] += 1
            
        if stats[loser]["streak_wins"] > 0:
            stats[loser]["streak_wins"] = 0
            stats[loser]["streak_losses"] = 1
        else: stats[loser]["streak_losses"] += 1
                
    # 返回统计数据 和 原始比赛列表(用于Table 2)
    return stats, valid_matches

# ================== 4. 新增: 时间分布表计算 ==================
def process_time_stats(all_matches):
    """
    计算 [赛区][时间][星期] 的打满数据
    结构: data[region][hour][weekday] = {'full': 0, 'total': 0}
    """
    # 初始化数据结构
    # hour_keys: LCK=[16, 18], LPL=[15, 17, 19]
    time_data = {
        "LCK": {h: {w: {'full':0, 'total':0} for w in range(8)} for h in [16, 18, 'Total']},
        "LPL": {h: {w: {'full':0, 'total':0} for w in range(8)} for h in [15, 17, 19, 'Total']},
        "ALL": {w: {'full':0, 'total':0} for w in range(8)} # 合并总计
    }
    
    # 辅助：星期索引 0-6 (Mon-Sun), 7 (Total)
    
    for m in all_matches:
        region = m['region']
        if region not in time_data: continue
        
        dt = m['date']
        weekday = dt.weekday() # 0=Mon, 6=Sun
        hour = dt.hour
        
        # 判断是否打满
        is_full = False
        s1, s2 = m['s1'], m['s2']
        max_s, min_s = max(s1, s2), min(s1, s2)
        bo = m['best_of']
        
        if bo == "3" or (not bo and max_s == 2):
            if min_s == 1: is_full = True
        elif bo == "5" or (not bo and max_s == 3):
            if min_s == 2: is_full = True
        else:
            continue # 不统计 BO1
            
        # 归类时间段 (模糊匹配)
        target_hour = None
        if region == "LCK":
            if hour <= 16: target_hour = 16
            else: target_hour = 18 # 17:00, 18:00, 19:00 都算第二场
        elif region == "LPL":
            if hour <= 15: target_hour = 15
            elif hour <= 17: target_hour = 17
            else: target_hour = 19
            
        # 写入数据
        targets = []
        if target_hour is not None:
            targets.append(time_data[region][target_hour]) # 具体时间行
            
        targets.append(time_data[region]['Total']) # 赛区总计行
        
        for t in targets:
            # 每日数据
            t[weekday]['total'] += 1
            if is_full: t[weekday]['full'] += 1
            # 横向总计 (索引7)
            t[7]['total'] += 1
            if is_full: t[7]['full'] += 1
            
        # 写入 Grand Total
        time_data["ALL"][weekday]['total'] += 1
        if is_full: time_data["ALL"][weekday]['full'] += 1
        time_data["ALL"][7]['total'] += 1
        if is_full: time_data["ALL"][7]['full'] += 1
        
    return time_data

def generate_time_table_html(time_data):
    """生成时间分布表的 HTML"""
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Total"]
    rows_config = [
        ("LCK", 16, "LCK 16:00"),
        ("LCK", 18, "LCK 18:00"),
        ("LCK", "Total", "LCK Total"),
        ("LPL", 15, "LPL 15:00"),
        ("LPL", 17, "LPL 17:00"),
        ("LPL", 19, "LPL 19:00"),
        ("LPL", "Total", "LPL Total"),
    ]
    
    html = """
    <div class="wrapper" style="margin-top: 40px;">
        <div class="table-title">📅 Full Series Distribution (Time in CST)</div>
        <table id="time-stats">
            <thead>
                <tr>
                    <th class="team-col">Time Slot</th>
    """
    for day in weekdays:
        html += f"<th>{day}</th>"
    html += "</tr></thead><tbody>"
    
    # 渲染各行
    for region, hour, label in rows_config:
        is_total_row = (hour == "Total")
        row_style = "font-weight:bold; background:#f8fafc;" if is_total_row else ""
        label_style = "background:#f1f5f9;" if is_total_row else ""
        
        html += f"<tr style='{row_style}'><td class='team-col' style='{label_style}'>{label}</td>"
        
        for w in range(8):
            cell = time_data[region][hour][w]
            total = cell['total']
            full = cell['full']
            
            if total == 0:
                html += "<td style='color:#e2e8f0'>-</td>"
            else:
                ratio = full / total
                bg_color = color_by_ratio(ratio, reverse=False).replace("48%)", "85%)") # 浅色背景
                text_color = "black"
                html += f"<td style='background:{bg_color}; color:{text_color}'>{full} <span style='font-size:11px; opacity:0.7'>({int(ratio*100)}%)</span></td>"
        html += "</tr>"
        
    # 渲染 Grand Total
    html += "<tr style='border-top: 2px solid #cbd5e1; font-weight:800'><td class='team-col'>GRAND TOTAL</td>"
    for w in range(8):
        cell = time_data["ALL"][w]
        total = cell['total']
        full = cell['full']
        if total == 0:
            html += "<td>-</td>"
        else:
            ratio = full / total
            html += f"<td>{full} <span style='font-size:11px'>({int(ratio*100)}%)</span></td>"
    html += "</tr></tbody></table></div>"
    return html

# ================== 5. 输出生成 ==================
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

def build(all_data, all_matches_global):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    
    # 计算时间分布数据
    time_stats = process_time_stats(all_matches_global)
    time_table_html = generate_time_table_html(time_stats)
    
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

    # --- 渲染原有的赛事表 ---
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

    # --- 渲染新的时间分布表 ---
    html += time_table_html

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
    print("Starting LoL Stats Scraper (MultiTables)...", flush=True)
    data = {}
    all_matches_global = [] # 存储所有赛事的比赛，用于时间统计
    
    for tournament in TOURNAMENTS:
        print(f"\nProcessing: {tournament['title']}", flush=True)
        # 获取 team_stats 和 raw_matches
        team_stats, matches = scrape(tournament)
        
        data[tournament["slug"]] = team_stats
        all_matches_global.extend(matches) # 收集原始比赛数据
        
        save_markdown(tournament, team_stats)
    
    # 传入原始数据生成最终 HTML
    build(data, all_matches_global)
    print("\n✅ All done!", flush=True)
