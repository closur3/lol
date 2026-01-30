import requests
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import sys
import re

# ================== 0. 全局常量 ==================
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

INDEX_FILE = Path("index.html")
TEAMS_JSON = Path("teams.json")
# 🔥 配置文件路径
TOURNAMENTS_FILE = Path("tournaments.json") 
TOURNAMENT_DIR = Path("tournament")
GITHUB_REPO = "https://github.com/closur3/lol"

TOURNAMENT_DIR.mkdir(exist_ok=True)
CST = timezone(timedelta(hours=8)) # 北京时间

# ================== 1. 赛事配置 (读取文件) ==================
def load_tournaments():
    if not TOURNAMENTS_FILE.exists():
        print("❌ Error: tournaments.json not found!")
        sys.exit(1)
    
    try:
        content = TOURNAMENTS_FILE.read_text(encoding='utf-8')
        return json.loads(content)
    except Exception as e:
        print(f"❌ Error parsing tournaments.json: {e}")
        sys.exit(1)

TOURNAMENTS = load_tournaments()
print(f"✅ Loaded {len(TOURNAMENTS)} tournaments from config.")

# ================== 2. 辅助工具 ==================
def load_team_map():
    if TEAMS_JSON.exists():
        try: return json.loads(TEAMS_JSON.read_text(encoding='utf-8'))
        except: pass
    return {}

TEAM_MAP = load_team_map()

def get_short_name(full_name):
    if not full_name: return None
    upper_name = full_name.upper()
    
    ignore_list = ["TBD", "TBA", "TO BE DETERMINED", "UNKNOWN", "?"]
    for bad_word in ignore_list:
        if bad_word in upper_name: return None

    for key, short_val in TEAM_MAP.items():
        if key.upper() in upper_name: return short_val
    return full_name.replace("Esports", "").replace("Gaming", "").replace("Academy", "").replace("Team", "").strip()

def rate(n, d): return n / d if d > 0 else None 
def pct(r): return f"{int(r*100)}%" if r is not None else "-"

def get_hsl(hue, saturation=55, lightness=50): 
    return f"hsl({int(hue)}, {saturation}%, {lightness}%)"

def color_by_ratio(ratio, reverse=False):
    if ratio is None: return "#f1f5f9"
    hue = (1 - max(0, min(1, ratio))) * 140 if reverse else max(0, min(1, ratio)) * 140
    return get_hsl(hue)

def color_by_date(date, all_dates):
    if not date or not all_dates: return "#9ca3af"
    try:
        ts = date.timestamp()
        max_ts = max(d.timestamp() for d in all_dates)
        min_ts = min(d.timestamp() for d in all_dates)
        factor = (ts - min_ts) / (max_ts - min_ts) if max_ts != min_ts else 1
        return f"hsl(215, {int(factor * 60 + 20)}%, {int(60 - factor * 10)}%)"
    except:
        return "#9ca3af"

def wait_simple(seconds, reason="Cooldown"):
    print(f"      ⏳ {reason} ({seconds}s)...", end="", flush=True)
    time.sleep(seconds)
    print(" Done.", flush=True)

def smart_write(file_path, new_content):
    if not file_path.exists():
        file_path.write_text(new_content, encoding='utf-8')
        print(f"   ✓ Created new file: {file_path.name}")
        return

    old_content = file_path.read_text(encoding='utf-8')

    def clean_content(text):
        return "\n".join([
            line for line in text.splitlines() 
            if "Updated:" not in line and "Updated at:" not in line
        ])

    if clean_content(new_content) == clean_content(old_content):
        print(f"   💤 No data changes for {file_path.name}, skipping write.")
    else:
        file_path.write_text(new_content, encoding='utf-8')
        print(f"   🚀 Data changed! Updated {file_path.name}")

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
    session.headers.update({'User-Agent': 'LoLStatsBot/StableV1 (https://github.com/closur3/lol)'})

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

        wait_simple(3, "Safety delay")

        try:
            print(f"      -> Requesting offset {offset}...", end=" ", flush=True)
            response = session.get(api_url, params=params, timeout=20)
            data = response.json()
            
            if "error" in data:
                print("FAILED!", flush=True)
                print(f"      ⚠️  RATE LIMIT HIT! (API refused connection)", flush=True)
                wait_simple(60, "Resetting Quota")
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
    future_matches = [] 
    
    for m in matches:
        t1 = get_short_name(m.get("Team1", ""))
        t2 = get_short_name(m.get("Team2", ""))
        date_str = m.get("DateTime_UTC") or m.get("DateTime UTC") or m.get("DateTime")
        
        try: match_order = float(m.get("N_MatchInPage", 0))
        except: match_order = 0.0

        raw_s1, raw_s2 = m.get("Team1Score"), m.get("Team2Score")
        
        if not (t1 and t2 and date_str): continue

        s1 = int(raw_s1) if raw_s1 not in [None, ""] else 0
        s2 = int(raw_s2) if raw_s2 not in [None, ""] else 0
        
        best_of_str = m.get("BestOf")
        try: bo_val = int(best_of_str) if best_of_str else 3
        except: bo_val = 3
        
        try:
            clean_date = date_str.replace(" UTC", "").split("+")[0].strip()
            dt_obj = datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(CST)
        except:
            dt_obj = datetime.min.replace(tzinfo=timezone.utc)
            
        match_data = {
            "t1": t1, "t2": t2, "s1": s1, "s2": s2,
            "date": dt_obj, "best_of": str(bo_val),
            "order": match_order,
            "region": tournament.get("region", "Unknown")
        }

        required_wins = (bo_val // 2) + 1
        if max(s1, s2) < required_wins:
            future_matches.append(match_data) 
        else:
            valid_matches.append(match_data) 

    valid_matches.sort(key=lambda x: (x["date"], x["order"]))

    # --- 统计逻辑 ---
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
        
        if m["best_of"] == "3":
            for team in (t1, t2): stats[team]["bo3_total"] += 1
            if min_s == 1:
                for team in (t1, t2): stats[team]["bo3_full"] += 1
        elif m["best_of"] == "5":
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
                
    return stats, valid_matches, future_matches

# ================== 4. 时间分布表计算 ==================
def process_time_stats(all_matches):
    time_data = {
        "LCK": {h: {w: {'full':0, 'total':0, 'matches':[]} for w in range(8)} for h in [16, 18, 'Total']},
        "LPL": {h: {w: {'full':0, 'total':0, 'matches':[]} for w in range(8)} for h in [15, 17, 19, 'Total']},
        "ALL": {w: {'full':0, 'total':0, 'matches':[]} for w in range(8)}
    }
    
    for m in all_matches:
        region = m['region']
        if region not in time_data: continue
        
        dt = m['date']
        weekday = dt.weekday()
        hour = dt.hour
        
        is_full = False
        s1, s2 = m['s1'], m['s2']
        min_s = min(s1, s2)
        bo = m['best_of']
        
        if bo == "3":
            if min_s == 1: is_full = True
        elif bo == "5":
            if min_s == 2: is_full = True
        else: continue
            
        target_hour = None
        if region == "LCK":
            if hour <= 16: target_hour = 16
            else: target_hour = 18
        elif region == "LPL":
            if hour <= 15: target_hour = 15
            elif hour <= 17: target_hour = 17
            else: target_hour = 19
            
        match_str_html = f"<span class='date'>{dt.strftime('%m-%d')}</span> <span class='{'full-match' if is_full else ''}'>{m['t1']} vs {m['t2']} <b>{s1}-{s2}</b></span>"
        
        targets = []
        if target_hour is not None: targets.append(time_data[region][target_hour])
        targets.append(time_data[region]['Total'])
        
        for t in targets:
            t[weekday]['total'] += 1
            t[weekday]['matches'].append(match_str_html)
            if is_full: t[weekday]['full'] += 1
            t[7]['total'] += 1
            t[7]['matches'].append(match_str_html)
            if is_full: t[7]['full'] += 1
            
        time_data["ALL"][weekday]['total'] += 1
        time_data["ALL"][weekday]['matches'].append(match_str_html)
        if is_full: time_data["ALL"][weekday]['full'] += 1
        
        time_data["ALL"][7]['total'] += 1
        time_data["ALL"][7]['matches'].append(match_str_html)
        if is_full: time_data["ALL"][7]['full'] += 1
        
    return time_data

def generate_markdown_time_table(time_data):
    md = "\n### Time Distribution (Full Series Rate)\n\n"
    md += "| Time Slot | Mon | Tue | Wed | Thu | Fri | Sat | Sun | Total |\n"
    md += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    
    rows_config = [
        ("LCK", 16, "LCK 16:00"), 
        ("LCK", 18, "LCK 18:00"), 
        ("LCK", "Total", "**LCK Total**"),
        ("LPL", 15, "LPL 15:00"), 
        ("LPL", 17, "LPL 17:00"), 
        ("LPL", 19, "LPL 19:00"), 
        ("LPL", "Total", "**LPL Total**"),
        ("ALL", "Grand", "**GRAND**")
    ]

    for region, h_key, label in rows_config:
        line = f"| {label} |"
        for w in range(8):
            if region == "ALL":
                cell = time_data["ALL"][w]
            else:
                cell = time_data[region][h_key][w]
                
            total, full = cell['total'], cell['full']
            
            if total == 0:
                line += " - |"
            else:
                pct_val = int(full / total * 100)
                line += f" {full}/{total} ({pct_val}%) |"
        md += line + "\n"
    
    return md

# ================== 5. 输出生成 ==================
def save_markdown(tournament, team_stats, global_matches):
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
    
    time_stats = process_time_stats(global_matches)
    md_table = generate_markdown_time_table(time_stats)
    md_content += md_table
    
    md_content += f"\n---\n\n*Generated by [LoL Stats Scraper]({GITHUB_REPO})*\n"
    
    md_file = TOURNAMENT_DIR / f"{tournament['slug']}.md"
    
    smart_write(md_file, md_content)

def generate_time_table_html(time_data):
    html = """
    <div class="wrapper" style="margin-top: 40px;">
        <div class="table-title">📅 Full Series Distribution</div>
        <table id="time-stats">
            <thead>
                <tr>
                    <th class="team-col">Time Slot</th>
    """
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Total"]:
        html += f"<th>{day}</th>"
    html += "</tr></thead><tbody>"
    
    rows_config = [
        ("LCK", 16, "LCK 16:00"), ("LCK", 18, "LCK 18:00"), ("LCK", "Total", "LCK Total"),
        ("LPL", 15, "LPL 15:00"), ("LPL", 17, "LPL 17:00"), ("LPL", 19, "LPL 19:00"), ("LPL", "Total", "LPL Total"),
    ]
    
    for region, hour, label in rows_config:
        is_total_row = (hour == "Total")
        row_style = "font-weight:bold; background:#f8fafc;" if is_total_row else ""
        label_style = "background:#f1f5f9;" if is_total_row else ""
        
        html += f"<tr style='{row_style}'><td class='team-col' style='{label_style}'>{label}</td>"
        
        for w in range(8):
            cell = time_data[region][hour][w]
            total, full = cell['total'], cell['full']
            matches_json = json.dumps(cell['matches']).replace("'", "&apos;").replace('"', '&quot;')
            
            if total == 0:
                html += "<td style='background:#f1f5f9; color:#cbd5e1'>-</td>"
            else:
                ratio = full / total
                bg_color = color_by_ratio(ratio, reverse=True)
                html += f"<td style='background:{bg_color}; color:white; font-weight:bold; cursor:pointer;' onclick='showPopup(\"{label}\", {w}, {matches_json})'>{full}/{total} <span style='font-size:11px; opacity:0.8; font-weight:normal'>({int(ratio*100)}%)</span></td>"
        html += "</tr>"
    
    html += "<tr style='border-top: 2px solid #cbd5e1; font-weight:800'><td class='team-col'>GRAND</td>"
    for w in range(8):
        cell = time_data["ALL"][w]
        total, full = cell['total'], cell['full']
        matches_json = json.dumps(cell['matches']).replace("'", "&apos;").replace('"', '&quot;')
        
        if total == 0:
            html += "<td style='background:#f1f5f9; color:#cbd5e1'>-</td>"
        else:
            ratio = full / total
            bg_color = color_by_ratio(ratio, reverse=True)
            html += f"<td style='background:{bg_color}; color:white; cursor:pointer;' onclick='showPopup(\"GRAND\", {w}, {matches_json})'>{full}/{total} <span style='font-size:11px; opacity:0.8; font-weight:normal'>({int(ratio*100)}%)</span></td>"
    html += "</tr></tbody></table></div>"
    
    html += """
    <div id="matchModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closePopup()">&times;</span>
            <h3 id="modalTitle">Match History</h3>
            <div id="modalList" class="match-list"></div>
        </div>
    </div>
    """
    return html

def build(all_data, all_matches_global, is_done_today):
    # [修改] 1. 去掉 CST 后缀
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    time_table_html = generate_time_table_html(process_time_stats(all_matches_global))
    
    # [修改] 2. 状态指示器逻辑
    if is_done_today:
        # Finished: 灰色
        status_html = '<span style="color:#9ca3af; margin-left:6px">● FINISHED</span>'
    else:
        # Ongoing: 绿色
        status_html = '<span style="color:#10b981; margin-left:6px">● ONGOING</span>'
    
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
        
        /* Modal Styles */
        .modal {{ display: none; position: fixed; z-index: 99; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.4); backdrop-filter: blur(2px); }}
        .modal-content {{ background-color: #fefefe; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 300px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); animation: fadeIn 0.2s; }}
        .close {{ color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }}
        .close:hover {{ color: black; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .match-list {{ margin-top: 15px; max-height: 300px; overflow-y: auto; }}
        .match-item {{ padding: 8px 0; border-bottom: 1px solid #eee; font-size: 13px; display: flex; justify-content: space-between; }}
        .date {{ color: #94a3b8; font-family: monospace; margin-right: 10px; }}
        .full-match {{ color: #e11d48; font-weight: 600; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>🏆</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

    # --- 渲染原有的赛事表 (使用配置好的 TOURNAMENTS) ---
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

    html += time_table_html

    # [修改] 3. 页脚拼接 status_html (取代 CST)
    html += f"""
    <div class="footer">{status_html} | <a href="{GITHUB_REPO}" target="_blank" style="color:inherit; text-decoration:none">Updated: {now_str}</a></div>
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

        function showPopup(title, dayIndex, matches) {{
            const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Total"];
            document.getElementById('modalTitle').innerText = title + " - " + days[dayIndex];
            const list = document.getElementById('modalList');
            list.innerHTML = "";
            
            if (matches.length === 0) {{
                list.innerHTML = "<div style='text-align:center;color:#999;padding:20px'>No matches found</div>";
            }} else {{
                matches.forEach(m => {{
                    const div = document.createElement('div');
                    div.className = 'match-item';
                    div.innerHTML = m;
                    list.appendChild(div);
                }});
            }}
            
            document.getElementById('matchModal').style.display = "block";
        }}
        
        function closePopup() {{
            document.getElementById('matchModal').style.display = "none";
        }}
        
        window.onclick = function(event) {{
            const modal = document.getElementById('matchModal');
            if (event.target == modal) {{
                modal.style.display = "none";
            }}
        }}
    </script>
</body>
</html>"""
    
    smart_write(INDEX_FILE, html)

if __name__ == "__main__":
    print("Starting LoL Stats Scraper (Global View)...", flush=True)
    
    data_store = []
    all_matches_global = [] 
    all_future_matches = [] 
    
    # [修改] 这里遍历全局加载的 TOURNAMENTS
    for tournament in TOURNAMENTS:
        print(f"\nProcessing: {tournament['title']}", flush=True)
        # 获取三个返回值：统计, 完场, 未完场
        team_stats, matches, futures = scrape(tournament)
        
        all_matches_global.extend(matches)
        all_future_matches.extend(futures)
        
        data_store.append({
            "tournament": tournament,
            "stats": team_stats
        })
    
    print("\nWriting files with GLOBAL data...", flush=True)
    
    for item in data_store:
        save_markdown(item["tournament"], item["stats"], all_matches_global)
    
    # [新增] 计算今日完赛状态，只在这里算一次
    today_str = datetime.now(CST).strftime("%Y-%m-%d")
    remaining_today = [
        m for m in all_future_matches 
        if m['date'].strftime("%Y-%m-%d") == today_str
    ]
    is_done_for_today = (len(remaining_today) == 0)

    html_data = {item["tournament"]["slug"]: item["stats"] for item in data_store}
    # [传参] 把 is_done_today 传给 build
    build(html_data, all_matches_global, is_done_for_today)
    
    print(f"\n[Smart Sleep] Remaining matches for {today_str}: {len(remaining_today)}")
    print("\n✅ All done!", flush=True)
