import requests
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time

# ================== 1. 核心配置 ==================
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

TOURNAMENT_DIR.mkdir(exist_ok=True)
CST = timezone(timedelta(hours=8))

# ================== 2. 辅助工具 ==================
COL_TEAM, COL_BO3, COL_BO3_PCT, COL_BO5, COL_BO5_PCT = 0, 1, 2, 3, 4
COL_SERIES, COL_SERIES_WR, COL_GAME, COL_GAME_WR, COL_STREAK, COL_LAST_DATE = 5, 6, 7, 8, 9, 10

def rate(n, d): return n / d if d > 0 else None 
def pct(r): return f"{r*100:.1f}%" if r is not None else "-"
def get_hsl(h, s=70, l=45): return f"hsl({int(h)}, {s}%, {l}%)"
def color_by_ratio(r, rev=False):
    if r is None: return "#f1f5f9"
    h = (1 - max(0, min(1, r))) * 140 if rev else max(0, min(1, r)) * 140
    return get_hsl(h, 65, 48)
def color_by_date(d, all_d):
    if not d or not all_d: return "#9ca3af"
    try:
        ts, max_ts, min_ts = d.timestamp(), max(x.timestamp() for x in all_d), min(x.timestamp() for x in all_d)
        if max_ts == min_ts: return "hsl(215, 100%, 40%)"
        f = (ts - min_ts) / (max_ts - min_ts)
        # 越新越亮蓝 (hue 215)
        return f"hsl(215, {int(f * 80 + 20)}%, {int(55 - f * 15)}%)"
    except: return "#9ca3af"

# ================== 3. 抓取逻辑 (API) ==================
def fetch_leaguepedia_data(overview_page):
    api_url = "https://lol.fandom.com/api.php"
    matches = []
    limit = 500
    offset = 0
    session = requests.Session()
    session.headers.update({'User-Agent': 'LoLStatsBot/Final (https://github.com/closur3/lol)'})
    
    print(f"   🚀 Fetching: {overview_page}...")
    
    while True:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": "MatchSchedule",
            # 修正点：使用 'DateTime_UTC=DateTime_UTC' 强制指定返回键名，防止返回 'DateTime UTC'
            "fields": "Team1, Team2, Team1Score, Team2Score, Winner, DateTime_UTC=DateTime_UTC, BestOf",
            "where": f"OverviewPage='{overview_page}'", 
            "order_by": "DateTime_UTC ASC",
            "limit": limit,
            "offset": offset
        }
        
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                time.sleep(1.5) 
                resp = session.get(api_url, params=params, timeout=15)
                
                if resp.status_code == 429:
                    print(f"      ⛔ HTTP 429 (Rate Limit). Sleeping 30s...")
                    time.sleep(30)
                    continue
                
                data = resp.json()
                if 'error' in data:
                    print(f"      ⚠️ API Error: {data['error'].get('info', 'Unknown')}")
                    time.sleep(5)
                    continue
                    
                if "cargoquery" in data:
                    batch = [item["title"] for item in data["cargoquery"]]
                    matches.extend(batch)
                    print(f"      ✓ Got {len(batch)} rows (Total: {len(matches)})")
                    if len(batch) < limit:
                        return matches
                    offset += limit
                    success = True
                    break
            except Exception as e:
                print(f"      ❌ Network Error: {e}")
                time.sleep(3)
        
        if not success: break
            
    return matches

# ================== 4. 处理逻辑 ==================
def process_matches(matches):
    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, "bo5_full": 0, "bo5_total": 0, 
        "series_wins": 0, "series_total": 0, "game_wins": 0, "game_total": 0, 
        "streak_wins": 0, "streak_losses": 0, "streak_dirty": False, "last_date": None
    })
    
    print(f"   Processing {len(matches)} matches...")
    valid_count = 0
    
    for m in matches:
        t1, t2 = m.get("Team1"), m.get("Team2")
        raw_s1, raw_s2 = m.get("Team1Score"), m.get("Team2Score")
        
        # 1. 鲁棒的日期获取：尝试多种可能的键名
        date_str = m.get("DateTime_UTC") or m.get("DateTime UTC") or m.get("DateTime")
        
        # 2. 基础过滤
        if not (t1 and t2) or raw_s1 in [None, ""] or raw_s2 in [None, ""]:
            continue
            
        try:
            s1, s2 = int(raw_s1), int(raw_s2)
        except: continue

        if s1 == 0 and s2 == 0: continue
            
        valid_count += 1
        
        # 3. 统计
        if s1 > s2: winner, loser = t1, t2
        elif s2 > s1: winner, loser = t2, t1
        else: continue 
            
        # 时间转换
        dt_cst = None
        if date_str:
            try:
                # 尝试解析常用的 Cargo 时间格式
                dt_utc = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                dt_cst = dt_utc.astimezone(CST)
            except: pass
        
        for t in (t1, t2):
            if dt_cst and (stats[t]["last_date"] is None or dt_cst > stats[t]["last_date"]):
                stats[t]["last_date"] = dt_cst
            stats[t]["series_total"] += 1
            stats[t]["game_total"] += (s1 + s2)
            
        stats[winner]["series_wins"] += 1
        stats[t1]["game_wins"] += s1
        stats[t2]["game_wins"] += s2
        
        # BO3/BO5
        best_of = m.get("BestOf")
        max_s, min_s = max(s1, s2), min(s1, s2)
        
        if best_of == "3" or (not best_of and max_s == 2):
            for t in (t1, t2): stats[t]["bo3_total"] += 1
            if min_s == 1:
                for t in (t1, t2): stats[t]["bo3_full"] += 1
        elif best_of == "5" or (not best_of and max_s == 3):
            for t in (t1, t2): stats[t]["bo5_total"] += 1
            if min_s == 2:
                for t in (t1, t2): stats[t]["bo5_full"] += 1
        
        # Streak
        if stats[winner]["streak_losses"] > 0:
            stats[winner]["streak_losses"] = 0
            stats[winner]["streak_wins"] = 1
        else: stats[winner]["streak_wins"] += 1
        
        if stats[loser]["streak_wins"] > 0:
            stats[loser]["streak_wins"] = 0
            stats[loser]["streak_losses"] = 1
        else: stats[loser]["streak_losses"] += 1

    return stats

# ================== 5. 输出生成 ==================
def save_markdown(tournament, team_stats):
    if not team_stats: return
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    lp_url = f"https://lol.fandom.com/wiki/{tournament['overview_page'].replace(' ', '_')}"
    
    sorted_teams = sorted(team_stats.items(), key=lambda x: (
        rate(x[1]["bo3_full"], x[1]["bo3_total"]) if rate(x[1]["bo3_full"], x[1]["bo3_total"]) is not None else -1.0,
        -(rate(x[1]["series_wins"], x[1]["series_total"]) or 0)
    ))
    
    md_content = f"# {tournament['title']}\n\n**Source:** [Leaguepedia]({lp_url})  \n**Updated:** {now}\n\n---\n\n## Statistics\n\n| Team | BO3 Full | BO3 Fullrate | BO5 Full | BO5 Fullrate | Series | Series WR | Games | Game WR | Streak | Last Date |\n|------|----------|--------------|----------|--------------|--------|-----------|-------|---------|--------|-----------|\n"
    
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
    (TOURNAMENT_DIR / f"{tournament['slug']}.md").write_text(md_content, encoding='utf-8')
    print(f"      ✓ Archived: {tournament['slug']}.md")

def build(all_data):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    html = f"""<!DOCTYPE html><html><head><link rel="icon" href="./favicon.png"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>LoL Insights</title><style>body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f1f5f9; margin: 0; padding: 10px; color: #1e293b; }} .main-header {{ text-align: center; padding: 25px 0; }} .main-header h1 {{ margin: 0;font-size: 2.2rem;font-weight: 800; letter-spacing: -0.025em; }} .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 25px; border: 1px solid #e2e8f0; }} .table-title {{ padding: 15px 20px; font-weight: 700; border-bottom: 1px solid #f1f5f9; display: flex; align-items: center; justify-content: space-between; }} .table-title a {{ color: #2563eb; text-decoration: none; transition: 0.2s; }} .table-title a:hover {{ color: #1d4ed8; text-decoration: underline; }} .archive-link {{ font-size: 0.85rem; color: #64748b; font-weight: 500; }} table {{ width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; table-layout: fixed; }} th {{ background: #f8fafc; padding: 12px 8px; font-weight: 600; color: #64748b; border-bottom: 2px solid #e2e8f0; cursor: pointer; transition: 0.2s; user-select: none; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.75rem; }} th:hover {{ background: #eff6ff; color: #2563eb; }} td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }} .team-col {{ position: sticky; left: 0; background: white !important; z-index: 10; border-right: 2px solid #f1f5f9; text-align: left; font-weight: 700; padding-left: 20px; width: 100px; color: #0f172a; }} .col-bo3 {{ width: 70px; }} .col-bo3-pct {{ width: 85px; }} .col-bo5 {{ width: 70px; }} .col-bo5-pct {{ width: 85px; }} .col-series {{ width: 80px; }} .col-series-wr {{ width: 100px; }} .col-game {{ width: 80px; }} .col-game-wr {{ width: 100px; }} .col-streak {{ width: 80px; }} .col-last {{ width: 130px; font-variant-numeric: tabular-nums; }} .badge {{ color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; display: inline-block; min-width: 24px; }} .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; }} tr:hover td {{ background-color: #f8fafc; }} tr:hover td.team-col {{ background-color: #f8fafc !important; }}</style></head><body><header class="main-header"><h1>🏆 League Stats</h1></header><div style="max-width:1400px; margin:0 auto">"""

    for index, tournament in enumerate(TOURNAMENTS):
        team_stats = all_data.get(tournament["slug"], {})
        if not team_stats: continue
        table_id = f"t{index}"
        dates = [stat["last_date"] for stat in team_stats.values() if stat["last_date"]]
        lp_url = f"https://lol.fandom.com/wiki/{tournament['overview_page'].replace(' ', '_')}"
        
        html += f"""<div class="wrapper"><div class="table-title"><span>{tournament['title']}</span><span class="archive-link"><a href="{lp_url}" target="_blank">Source</a> • <a href="tournament/{tournament['slug']}.md" target="_blank">Archive</a></span></div><table id="{table_id}"><thead><tr><th class="team-col" onclick="doSort({COL_TEAM}, '{table_id}')">Team</th><th colspan="2" onclick="doSort({COL_BO3_PCT}, '{table_id}')" style="text-align:center;">BO3 Fullrate</th><th colspan="2" onclick="doSort({COL_BO5_PCT}, '{table_id}')" style="text-align:center;">BO5 Fullrate</th><th colspan="2" onclick="doSort({COL_SERIES_WR}, '{table_id}')" style="text-align:center;">Series</th><th colspan="2" onclick="doSort({COL_GAME_WR}, '{table_id}')" style="text-align:center;">Games</th><th class="col-streak" onclick="doSort({COL_STREAK}, '{table_id}')">Streak</th><th class="col-last" onclick="doSort({COL_LAST_DATE}, '{table_id}')">Last Date (CST)</th></tr></thead><tbody>"""
        
        sorted_teams = sorted(team_stats.items(), key=lambda x: (
            rate(x[1]["bo3_full"], x[1]["bo3_total"]) if rate(x[1]["bo3_full"], x[1]["bo3_total"]) is not None else -1.0,
            -(rate(x[1]["series_wins"], x[1]["series_total"]) or 0)
        ))

        for team_name, stat in sorted_teams:
            bo3_ratio, bo5_ratio = rate(stat["bo3_full"], stat["bo3_total"]), rate(stat["bo5_full"], stat["bo5_total"])
            series_wr, game_wr = rate(stat["series_wins"], stat["series_total"]), rate(stat["game_wins"], stat["game_total"])
            
            streak_display = f"<span class='badge' style='background:#10b981'>{stat['streak_wins']}W</span>" if stat['streak_wins'] > 0 else (f"<span class='badge' style='background:#f43f5e'>{stat['streak_losses']}L</span>" if stat['streak_losses'] > 0 else "-")
            last_date = stat["last_date"].strftime("%Y-%m-%d %H:%M") if stat["last_date"] else "-"
            
            html += f"""<tr><td class="team-col">{team_name}</td>
                <td class="col-bo3" style="color:{'#cbd5e1' if stat['bo3_total']==0 else 'inherit'}">{stat['bo3_full']}/{stat['bo3_total'] if stat['bo3_total']>0 else '-'}</td><td class="col-bo3-pct" style="background:{color_by_ratio(bo3_ratio, True)};color:{'white' if bo3_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(bo3_ratio)}</td>
                <td class="col-bo5" style="color:{'#cbd5e1' if stat['bo5_total']==0 else 'inherit'}">{stat['bo5_full']}/{stat['bo5_total'] if stat['bo5_total']>0 else '-'}</td><td class="col-bo5-pct" style="background:{color_by_ratio(bo5_ratio, True)};color:{'white' if bo5_ratio is not None else '#cbd5e1'};font-weight:bold">{pct(bo5_ratio)}</td>
                <td class="col-series" style="color:{'#cbd5e1' if stat['series_total']==0 else 'inherit'}">{stat['series_wins']}-{stat['series_total']-stat['series_wins'] if stat['series_total']>0 else '-'}</td><td class="col-series-wr" style="background:{color_by_ratio(series_wr)};color:{'white' if series_wr is not None else '#cbd5e1'};font-weight:bold">{pct(series_wr)}</td>
                <td class="col-game" style="color:{'#cbd5e1' if stat['game_total']==0 else 'inherit'}">{stat['game_wins']}-{stat['game_total']-stat['game_wins'] if stat['game_total']>0 else '-'}</td><td class="col-game-wr" style="background:{color_by_ratio(game_wr)};color:{'white' if game_wr is not None else '#cbd5e1'};font-weight:bold">{pct(game_wr)}</td>
                <td class="col-streak">{streak_display}</td><td class="col-last" style="color:{color_by_date(stat['last_date'], dates) if stat['last_date'] else '#cbd5e1'};font-weight:600;font-size:12px;">{last_date}</td></tr>"""
        html += "</tbody></table></div>"

    html += f"""<div class="footer">Updated: {now} | <a href="{GITHUB_REPO}" target="_blank">GitHub</a></div></div><script>
    const COL_TEAM={COL_TEAM},COL_SERIES_WR={COL_SERIES_WR},COL_GAME_WR={COL_GAME_WR},COL_LAST_DATE={COL_LAST_DATE};
    function doSort(c,t){{const T=document.getElementById(t),B=T.tBodies[0],R=Array.from(B.rows),S='data-sort-dir-'+c,D=T.getAttribute(S);let N=!D?((c===COL_TEAM)?'asc':'desc'):(D==='desc'?'asc':'desc');R.sort((a,b)=>{{let A=a.cells[c].innerText,B=b.cells[c].innerText;if(c===COL_LAST_DATE){{A=A==='-'?0:new Date(A.replace(/-/g,'/')).getTime();B=B==='-'?0:new Date(B.replace(/-/g,'/')).getTime()}}else{{A=pV(A);B=pV(B)}}if(A!==B)return N==='asc'?(A>B?1:-1):(A<B?1:-1);if(c===COL_SERIES_WR){{let x=pV(a.cells[COL_GAME_WR].innerText),y=pV(b.cells[COL_GAME_WR].innerText);if(x!==y)return N==='asc'?(x>y?1:-1):(x<y?1:-1)}}return 0}});T.setAttribute(S,N);R.forEach(r=>B.appendChild(r))}}
    function pV(v){{if(v==="-")return-1;if(v.includes('%'))return parseFloat(v);if(v.includes('/')){{let p=v.split('/');return p[1]==='-'?-1:parseFloat(p[0])/parseFloat(p[1])}}if(v.includes('-')&&v.split('-').length===2)return parseFloat(v.split('-')[0]);const n=parseFloat(v);return isNaN(n)?v.toLowerCase():n}}
    </script></body></html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")
    print(f"✓ Generated: {INDEX_FILE}")

if __name__ == "__main__":
    print("Starting LoL Stats Scraper (Final Production)...")
    data = {}
    for tournament in TOURNAMENTS:
        print(f"\nProcessing: {tournament['title']}")
        matches = fetch_leaguepedia_data(tournament["overview_page"])
        if matches:
            team_stats = process_matches(matches)
            if team_stats:
                data[tournament["slug"]] = team_stats
                save_markdown(tournament, team_stats)
            else:
                print("   No valid matches derived (check logs).")
        else:
            print("   No matches found (check connection/limit).")
    
    if data: build(data)
    print("\n✅ All done!")
