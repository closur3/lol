import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
import re

# ================== 配置 ==================
# 定义 CST 时区 (UTC+8)
CST = timezone(timedelta(hours=8))

TOURNAMENTS = [
    # 你可以根据实际页面 URL 调整这里
    {
        "slug": "2026-lpl-split-1", 
        "title": "2026 LPL Split 1", 
        "url": "https://lol.fandom.com/wiki/LPL/2026_Season/Split_1"
    },
    # 示例：如果还要抓 LCK
    # {
    #     "slug": "2026-lck-cup", 
    #     "title": "2026 LCK Cup", 
    #     "url": "https://lol.fandom.com/wiki/LCK_Cup/2026_Season" 
    # },
]

INDEX_FILE = Path("index.html")
TOURNAMENT_DIR = Path("tournament")
GITHUB_REPO = "https://github.com/closur3/lol"

# 确保归档目录存在
TOURNAMENT_DIR.mkdir(exist_ok=True)

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
    # 将所有时间转为 timestamp 进行比较
    ts = date_obj.timestamp()
    max_ts = max(d.timestamp() for d in all_dates)
    min_ts = min(d.timestamp() for d in all_dates)
    
    if max_ts == min_ts: return "hsl(215, 100%, 40%)"
    
    factor = (ts - min_ts) / (max_ts - min_ts)
    return f"hsl(215, {int(factor * 80 + 20)}%, {int(55 - factor * 15)}%)"

# ---------- Fandom 抓取逻辑 ----------
def scrape(tournament):
    print(f"   -> Fetching {tournament['url']}...")
    try:
        response = requests.get(tournament["url"], headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"   !! Error fetching: {e}")
        return {}

    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0, 
        "bo5_full": 0, "bo5_total": 0, 
        "series_wins": 0, "series_total": 0, 
        "game_wins": 0, "game_total": 0, 
        "streak_wins": 0, "streak_losses": 0, 
        "streak_dirty": False, "last_date": None
    })
    
    # Fandom 的赛程通常在 class="matchlist" 或 "wikitable" 中
    # 我们查找包含 "Score" 或类似结构的行
    # 在 Fandom Match Schedule 页面，通常每场比赛是一个 tr
    # 结构通常是: Date | Time | Team1 | Score | Team2 ...
    
    # 策略：遍历所有表格行，寻找符合 "Team vs Team" 且包含比分结构的行
    match_rows = soup.select("tr.matchlist-row, tr.ml-row, table.wikitable tr")
    
    processed_count = 0

    for row in match_rows:
        # Fandom 的结构比较多变，这里采用一种通用的基于内容的提取方式
        cells = row.find_all("td")
        if not cells or len(cells) < 4: continue
        
        text_content = row.get_text(" ", strip=True)
        
        # 提取比分 (例如 "2 - 1", "0 : 2", "FF - W")
        # 忽略未开始的比赛 (通常显示 "vs" 或空)
        score_match = re.search(r'(\d+)\s*[-:]\s*(\d+)', text_content)
        if not score_match: continue
        
        score1 = int(score_match.group(1))
        score2 = int(score_match.group(2))
        
        # 提取队名
        # 通常 Team1 和 Team2 是含有链接的单元格，或者是 class="matchlist-team"
        # 简单策略：在 cells 中寻找 data-team 属性，或者寻找文本
        # Fandom 的标准 matchlist 通常结构：
        # Team1 Cell (class="matchlist-team1") | Score Cell | Team2 Cell
        
        team1_candidates = row.select(".matchlist-team1, .team-1, span.teamname")
        team2_candidates = row.select(".matchlist-team2, .team-2, span.teamname")
        
        t1_name = None
        t2_name = None

        # 尝试从特定 class 提取
        if team1_candidates and team2_candidates:
            # 如果用 span.teamname 这种通用选择器，需要区分前后
            if len(team1_candidates) >= 2 and team1_candidates[0] != team1_candidates[1]:
                t1_name = team1_candidates[0].get_text(strip=True)
                t2_name = team1_candidates[1].get_text(strip=True)
            else:
                # 假设 specialized class
                t1_name = team1_candidates[0].get_text(strip=True)
                t2_name = team2_candidates[0].get_text(strip=True)
        else:
            # Fallback: 假设比分在中间，尝试找比分前后的文本
            # 这是一个比较危险的假设，但在 wikitable 中通常 Date|Time|T1|Score|T2 比较常见
            # 让我们尝试更智能一点：寻找带有 title 或 data-team 的 attributes
            links = row.find_all("a", title=True)
            valid_teams = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
            if len(valid_teams) >= 2:
                # 通常最后两个链接是队伍 (如果前面有赛事链接)
                # 或者就是最明显的两个
                # 为了保险，我们假设离 Score 最近的两个是队伍
                # Fandom 上队伍通常是简写，正是我们要的
                pass 
                # 这里很难通用，还是依赖 class 比较好。
                # 针对 LPL Fandom 页面结构 (matchlist-row)
                t1_node = row.select_one("td[class*='team1']")
                t2_node = row.select_one("td[class*='team2']")
                if t1_node and t2_node:
                    t1_name = t1_node.get_text(strip=True)
                    t2_name = t2_node.get_text(strip=True)

        if not t1_name or not t2_name:
            continue

        # 清理队名 (Fandom 有时会有不换行空格)
        t1_name = t1_name.strip()
        t2_name = t2_name.strip()
        
        # --- 时间处理 ---
        # 尝试查找 data-date (通常是 YYYY-MM-DD)
        # 尝试查找 data-time 或文本时间 (HH:MM)
        date_str = row.get("data-date")
        
        # 或者是从 class="matchlist-date" / "matchlist-time" 提取
        if not date_str:
             date_cell = row.select_one(".matchlist-date")
             if date_cell: date_str = date_cell.get_text(strip=True)
        
        time_str = None
        time_cell = row.select_one(".matchlist-time")
        if time_cell: 
            time_str = time_cell.get_text(strip=True) # 通常是 "17:00" or "19:00"
        
        # 构建 datetime
        series_dt = None
        if date_str:
            try:
                # Fandom 的 data-date 通常是 YYYY-MM-DD
                dt_parse = datetime.strptime(date_str, "%Y-%m-%d")
                
                # 如果有时间，添加时间
                if time_str and ":" in time_str:
                    hm = time_str.split(":")
                    dt_parse = dt_parse.replace(hour=int(hm[0]), minute=int(hm[1]))
                else:
                    # 默认比赛时间，比如中午12点，避免排序问题
                    dt_parse = dt_parse.replace(hour=12, minute=0)
                
                # 设置时区：假设 Fandom 页面上显示的是 LPL 当地时间 (CST)
                # 实际上 Fandom 很多时候用 UTC，但 LPL 页面经常硬编码为 CST
                # 这里我们假设它是 CST 输入，或者我们强制把它当做 CST (如果不含时区信息)
                series_dt = dt_parse.replace(tzinfo=CST)
                
            except ValueError:
                pass
        
        # 如果没有抓到时间，使用一个极小值或者忽略更新 Last Date
        
        # --- 统计逻辑 (与旧代码相同) ---
        winner, loser = (t1_name, t2_name) if score1 > score2 else (t2_name, t1_name)
        max_score, min_score = max(score1, score2), min(score1, score2)
        
        processed_count += 1
        
        for team in (t1_name, t2_name):
            if series_dt:
                # 更新 last_date (找最新的)
                current_last = stats[team]["last_date"]
                if not current_last or series_dt > current_last:
                    stats[team]["last_date"] = series_dt
            
            stats[team]["series_total"] += 1
            stats[team]["game_total"] += (score1 + score2)
        
        stats[winner]["series_wins"] += 1
        stats[t1_name]["game_wins"] += score1
        stats[t2_name]["game_wins"] += score2
        
        # BO3/BO5 判断
        if max_score == 2:
            for team in (t1_name, t2_name):
                stats[team]["bo3_total"] += 1
            if min_score == 1:
                for team in (t1_name, t2_name):
                    stats[team]["bo3_full"] += 1
        elif max_score == 3:
            for team in (t1_name, t2_name):
                stats[team]["bo5_total"] += 1
            if min_score == 2:
                for team in (t1_name, t2_name):
                    stats[team]["bo5_full"] += 1
        
        # 连胜/连败
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

    print(f"   -> Processed {processed_count} matches.")
    return stats

# ---------- 生成 Markdown 归档 ----------
def save_markdown(tournament, team_stats):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    
    sorted_teams = sorted(team_stats.items(), key=lambda x: (
        rate(x[1]["bo3_full"], x[1]["bo3_total"]) if rate(x[1]["bo3_full"], x[1]["bo3_total"]) is not None else -1.0,
        -(rate(x[1]["series_wins"], x[1]["series_total"]) or 0)
    ))
    
    md_content = f"""# {tournament['title']}

**Source:** [{tournament['url']}]({tournament['url']})  
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
        # 修改：显示小时分钟
        last_date_display = stat["last_date"].strftime("%Y-%m-%d %H:%M") if stat["last_date"] else "-"
        
        md_content += f"| {team_name} | {bo3_text} | {pct(bo3_ratio)} | {bo5_text} | {pct(bo5_ratio)} | {series_text} | {pct(series_win_ratio)} | {game_text} | {pct(game_win_ratio)} | {streak_display} | {last_date_display} |\n"
    
    md_content += f"""
---

*Generated by [LoL Stats Scraper]({GITHUB_REPO})*
"""
    
    md_file = TOURNAMENT_DIR / f"{tournament['slug']}.md"
    md_file.write_text(md_content, encoding='utf-8')
    print(f"   ✓ Archived: {md_file}")

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
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 10px; color: #1e293b; }}
        .main-header {{ text-align: center; padding: 30px 0 20px; }}
        .main-header h1 {{ margin: 0; font-size: 2.5rem; }}
        .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 30px; border: 1px solid #e2e8f0; }}
        .table-title {{ padding: 16px 20px; font-weight: 700; border-bottom: 1px solid #f1f5f9; display: flex; align-items: baseline; gap: 10px; }}
        .table-title a.title-link {{ color: #0f172a; text-decoration: none; font-size: 1.1rem; }}
        .table-title a.title-link:hover {{ color: #2563eb; }}
        .archive-link {{ font-size: 0.85rem; color: #64748b; }}
        .archive-link a {{ color: #64748b; text-decoration: none; }}
        .archive-link a:hover {{ text-decoration: underline; }}
        
        table {{ width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #f8fafc; padding: 12px 10px; font-weight: 600; color: #64748b; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; border-bottom: 1px solid #e2e8f0; cursor: pointer; user-select: none; }}
        th:hover {{ background: #f1f5f9; color: #334155; }}
        td {{ padding: 10px 10px; text-align: center; border-bottom: 1px solid #f1f5f9; }}
        
        .team-col {{ position: sticky; left: 0; background: white; z-index: 10; border-right: 1px solid #e2e8f0; text-align: left; font-weight: 700; padding-left: 20px; color: #0f172a; width: 100px; }}
        tr:hover td {{ background-color: #f8fafc; }}
        tr:hover .team-col {{ background-color: #f8fafc; }}
        
        .badge {{ color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; display: inline-block; min-width: 24px; }}
        .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; }}
        
        /* 列宽微调 */
        .col-last {{ width: 140px; font-variant-numeric: tabular-nums; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>📊</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

    for index, tournament in enumerate(TOURNAMENTS):
        team_stats = all_data.get(tournament["slug"], {})
        table_id = f"t{index}"
        dates = [stat["last_date"] for stat in team_stats.values() if stat["last_date"]]
        
        archive_link = f"tournament/{tournament['slug']}.md"
        
        html += f"""
        <div class="wrapper">
            <div class="table-title">
                <a class="title-link" href="{tournament['url']}" target="_blank">{tournament['title']}</a>
                <span class="archive-link">via Fandom • <a href="{archive_link}" target="_blank">Archive</a></span>
            </div>
            <table id="{table_id}">
                <thead>
                    <tr>
                        <th class="team-col" onclick="doSort({COL_TEAM}, '{table_id}')">Team</th>
                        <th onclick="doSort({COL_BO3_PCT}, '{table_id}')">BO3 Fullrate</th>
                        <th onclick="doSort({COL_BO5_PCT}, '{table_id}')">BO5 Fullrate</th>
                        <th onclick="doSort({COL_SERIES_WR}, '{table_id}')">Series WR</th>
                        <th onclick="doSort({COL_GAME_WR}, '{table_id}')">Game WR</th>
                        <th onclick="doSort({COL_STREAK}, '{table_id}')">Streak</th>
                        <th class="col-last" onclick="doSort({COL_LAST_DATE}, '{table_id}')">Last Match (CST)</th>
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
            game_win_ratio = rate(stat.get('game_wins', 0), stat.get('game_total', 0))
            
            streak_val = stat['streak_wins'] if stat['streak_wins'] > 0 else -stat['streak_losses']
            streak_bg = "#10b981" if streak_val > 0 else ("#f43f5e" if streak_val < 0 else "#cbd5e1")
            streak_txt = f"{abs(streak_val)}W" if streak_val > 0 else (f"{abs(streak_val)}L" if streak_val < 0 else "-")
            
            # 修改：显示日期和时间
            last_date_display = stat["last_date"].strftime("%Y-%m-%d %H:%M") if stat["last_date"] else "-"

            bo3_disp = f"{pct(bo3_ratio)} <span style='font-size:10px;opacity:0.6'>({stat['bo3_full']}/{stat['bo3_total']})</span>" if stat['bo3_total'] else "-"
            bo5_disp = f"{pct(bo5_ratio)} <span style='font-size:10px;opacity:0.6'>({stat['bo5_full']}/{stat['bo5_total']})</span>" if stat['bo5_total'] else "-"
            series_disp = f"{pct(series_win_ratio)} <span style='font-size:10px;opacity:0.6'>({stat['series_wins']}-{stat['series_total']-stat['series_wins']})</span>" if stat['series_total'] else "-"
            game_disp = f"{pct(game_win_ratio)} <span style='font-size:10px;opacity:0.6'>({stat['game_wins']}-{stat['game_total']-stat['game_wins']})</span>" if stat['game_total'] else "-"

            html += f"""
                <tr>
                    <td class="team-col">{team_name}</td>
                    <td style="color:{'inherit' if bo3_ratio is not None else '#cbd5e1'};background:{color_by_ratio(bo3_ratio, True) if bo3_ratio is not None else 'transparent'}">{bo3_disp}</td>
                    <td style="color:{'inherit' if bo5_ratio is not None else '#cbd5e1'};background:{color_by_ratio(bo5_ratio, True) if bo5_ratio is not None else 'transparent'}">{bo5_disp}</td>
                    <td style="color:{'inherit' if series_win_ratio is not None else '#cbd5e1'};background:{color_by_ratio(series_win_ratio) if series_win_ratio is not None else 'transparent'}">{series_disp}</td>
                    <td style="color:{'inherit' if game_win_ratio is not None else '#cbd5e1'};background:{color_by_ratio(game_win_ratio) if game_win_ratio is not None else 'transparent'}">{game_disp}</td>
                    <td><span class="badge" style="background:{streak_bg}">{streak_txt}</span></td>
                    <td class="col-last" style="color:{color_by_date(stat['last_date'], dates) if stat['last_date'] else '#cbd5e1'};font-weight:600">{last_date_display}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
    <div class="footer">Last Update: {now} | <a href="{GITHUB_REPO}" target="_blank">GitHub</a></div>
    </div>
    <script>
        const COL_TEAM = {COL_TEAM};
        const COL_LAST_DATE = {COL_LAST_DATE};
        
        function doSort(columnIndex, tableId) {{
            const table = document.getElementById(tableId);
            const tbody = table.tBodies[0];
            const rows = Array.from(tbody.rows);
            const stateKey = 'data-sort-dir-' + columnIndex;
            const currentDir = table.getAttribute(stateKey);
            const nextDir = (!currentDir || currentDir === 'desc') ? 'asc' : 'desc';
            
            rows.sort((rowA, rowB) => {{
                let valA = getCellValue(rowA, columnIndex);
                let valB = getCellValue(rowB, columnIndex);
                
                if (valA !== valB) {{
                    return nextDir === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
                }}
                return 0;
            }});
            
            table.setAttribute(stateKey, nextDir);
            rows.forEach(row => tbody.appendChild(row));
        }}
        
        function getCellValue(row, index) {{
            const text = row.cells[index].innerText;
            if (index === COL_LAST_DATE) {{
                return text === "-" ? 0 : new Date(text).getTime();
            }}
            if (index === COL_TEAM) return text.toLowerCase();
            
            // 提取百分比或数字
            const match = text.match(/([\d\.]+)%/);
            if (match) return parseFloat(match[1]);
            
            const num = parseFloat(text);
            return isNaN(num) ? -1 : num;
        }}
    </script>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")
    print(f"✓ Generated: {INDEX_FILE}")

if __name__ == "__main__":
    print("Starting Fandom Stats Scraper...")
    data = {}
    for tournament in TOURNAMENTS:
        print(f"\nProcessing: {tournament['title']}")
        team_stats = scrape(tournament)
        data[tournament["slug"]] = team_stats
        save_markdown(tournament, team_stats)
    
    build(data)
    print("\n✅ All done!")
