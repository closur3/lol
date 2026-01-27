import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# ================== 赛事配置（唯一来源） ==================
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
# ==========================================================

OUTPUT_DIR = Path("tournaments")
INDEX_FILE = Path("index.html")

# ---------- 工具函数 ----------
def rate(n, d):
    return n / d if d > 0 else None

def pct(r):
    return f"{r*100:.1f}%" if r is not None else "-"

def color_streak_wl(streak_type):
    """连胜/连败颜色 - 使用现代渐变色"""
    return "#4ade80" if streak_type == "W" else "#f87171"  # 绿色胜利 / 红色失败

def color_by_streak(r):
    """根据胜率着色 - 0%绿色到100%红色"""
    if r is None:
        return "#f3f4f6"  # 浅灰色
    
    # 0%绿色 -> 50%黄色 -> 100%红色
    if r <= 0.5:
        # 0%-50%: 绿色到黄色
        intensity = r / 0.5
        red = int(34 + intensity * 216)
        green = int(197 - intensity * 7)
        return f"rgb({red}, {green}, 94)"  # 绿色到黄色
    else:
        # 50%-100%: 黄色到红色
        intensity = (r - 0.5) / 0.5
        red = int(250 - intensity * 30)
        green = int(204 - intensity * 166)
        return f"rgb({red}, {green}, 21)"  # 黄色到红色

def parse_date(date_str):
    """解析日期字符串，返回datetime对象"""
    try:
        # 尝试多种日期格式
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
    except:
        return None

# ---------- 抓取 ----------
def scrape_tournament(t):
    resp = requests.get(t["url"], timeout=15)
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

    for row in soup.select("table tr"):
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        t1 = tds[1].get_text(strip=True)
        t2 = tds[3].get_text(strip=True)
        score = tds[2].get_text(strip=True)
        
        # 提取日期（在最后一列）
        date_str = tds[-1].get_text(strip=True) if len(tds) >= 7 else ""
        match_date = parse_date(date_str)

        if "-" not in score:
            continue

        try:
            s1, s2 = map(int, score.split("-"))
        except ValueError:
            continue

        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)

        # 更新最后比赛日期
        for t_ in (t1, t2):
            if match_date:
                if stats[t_]["last_match_date"] is None or match_date > stats[t_]["last_match_date"]:
                    stats[t_]["last_match_date"] = match_date

        # 大场统计
        for t_ in (t1, t2):
            stats[t_]["match_total"] += 1
        stats[winner]["match_win"] += 1

        # 小局统计
        stats[t1]["game_win"] += s1
        stats[t1]["game_total"] += s1 + s2
        stats[t2]["game_win"] += s2
        stats[t2]["game_total"] += s1 + s2

        max_s, min_s = max(s1, s2), min(s1, s2)

        # BO3 / BO5
        if max_s == 2:
            for t_ in (t1, t2):
                stats[t_]["bo3_total"] += 1
            if min_s == 1:
                for t_ in (t1, t2):
                    stats[t_]["bo3_full"] += 1
        if max_s == 3:
            for t_ in (t1, t2):
                stats[t_]["bo5_total"] += 1
            if min_s == 2:
                for t_ in (t1, t2):
                    stats[t_]["bo5_full"] += 1

        # 当前连胜/连败
        if not stats[winner]["streak_done"]:
            if stats[winner]["streak_l"] > 0:
                stats[winner]["streak_done"] = True
            else:
                stats[winner]["streak_w"] += 1
        if not stats[loser]["streak_done"]:
            if stats[loser]["streak_w"] > 0:
                stats[loser]["streak_done"] = True
            else:
                stats[loser]["streak_l"] += 1

    return stats

# ---------- 输出 ----------
def build_md_backup(t, stats):
    OUTPUT_DIR.mkdir(exist_ok=True)
    md_file = OUTPUT_DIR / f"{t['slug']}.md"
    lines = []
    lines.append(f"# {t['title']}\n")
    lines.append("| Team | BO3 (Full/Total) | BO3 Rate | BO5 (Full/Total) | BO5 Rate | Match | Match WR | Game | Game WR | Streak | Last Match |")
    lines.append("|------|------------------|----------|------------------|----------|-------|----------|------|---------|--------|------------|")

    for team, s in sorted(stats.items(), key=lambda x: (rate(x[1]["bo3_full"], x[1]["bo3_total"]) or -1)):
        bo3_r = rate(s["bo3_full"], s["bo3_total"])
        bo5_r = rate(s["bo5_full"], s["bo5_total"])
        match_wr = rate(s["match_win"], s["match_total"])
        game_wr = rate(s["game_win"], s["game_total"])

        streak = "-"
        if s["streak_w"] > 0:
            streak = f"{s['streak_w']}W"
        elif s["streak_l"] > 0:
            streak = f"{s['streak_l']}L"

        last_match = s["last_match_date"].strftime("%Y-%m-%d") if s["last_match_date"] else "-"

        lines.append(
            f"| {team} | "
            f"{s['bo3_full']}/{s['bo3_total']} | {pct(bo3_r)} | "
            f"{s['bo5_full']}/{s['bo5_total']} | {pct(bo5_r)} | "
            f"{s['match_win']}-{s['match_total']-s['match_win']} | {pct(match_wr)} | "
            f"{s['game_win']}-{s['game_total']-s['game_win']} | {pct(game_wr)} | "
            f"{streak} | {last_match} |"
        )
    md_file.write_text("\n".join(lines), encoding="utf-8")
    return md_file

def build_index_html(all_data):
    html = """<html><head><meta charset="utf-8">
<title>LOL Tournament Stats</title>
<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f8f9fa;
  min-height: 100vh;
  padding: 2rem;
}

h1 {
  color: #1f2937;
  text-align: center;
  margin-bottom: 2rem;
  font-size: 2.5rem;
}

h2 {
  color: #374151;
  margin: 2rem 0 1rem 0;
  font-size: 1.8rem;
}

h2 a {
  color: #374151;
  text-decoration: none;
  transition: color 0.2s;
}

h2 a:hover {
  color: #3b82f6;
  text-decoration: underline;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
  margin-bottom: 2rem;
}

th {
  background: #3b82f6;
  color: white;
  padding: 1rem;
  text-align: center;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.2s;
  user-select: none;
}

th:hover {
  background: #2563eb;
}

td {
  padding: 0.8rem 1rem;
  text-align: center;
  border-bottom: 1px solid #e5e7eb;
  transition: all 0.2s;
  font-weight: 500;
}

tr:hover td {
  background-color: #f3f4f6;
}

tr:last-child td {
  border-bottom: none;
}

td:first-child {
  font-weight: 700;
  color: #1f2937;
  text-align: left;
}

.container {
  max-width: 1600px;
  margin: 0 auto;
}
</style>
<script>
function sortTable(n, tableId) {
  var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
  table = document.getElementById(tableId);
  switching = true;
  dir = "asc";
  while (switching) {
    switching = false;
    rows = table.rows;
    for (i = 1; i < rows.length - 1; i++) {
      shouldSwitch = false;
      x = rows[i].getElementsByTagName("TD")[n].innerText;
      y = rows[i + 1].getElementsByTagName("TD")[n].innerText;
      x = x.replace('%',''); y = y.replace('%','');
      if (!isNaN(x) && !isNaN(y)) {x=parseFloat(x); y=parseFloat(y);}
      if (dir == "asc") {if (x > y) {shouldSwitch=true; break;}} 
      else {if (x < y) {shouldSwitch=true; break;}}
    }
    if (shouldSwitch) {rows[i].parentNode.insertBefore(rows[i + 1], rows[i]); switching = true; switchcount++;}
    else {if (switchcount == 0 && dir=="asc") {dir="desc"; switching=true;}}
  }
}
</script>
</head><body>
<div class="container">
<h1>🏆 LOL Tournament Stats</h1>
"""
    for idx, t in enumerate(TOURNAMENTS):
        stats = all_data[t["slug"]]
        table_id = f"table{idx}"
        html += f"<h2><a href='{t['url']}' target='_blank' style='color:#374151;text-decoration:none'>{t['title']}</a></h2><table id='{table_id}'>"
        html += "<tr>"
        headers = ["Team","BO3","BO3 Rate","BO5","BO5 Rate",
                   "Match","Match WR","Game","Game WR","Streak","Last Match"]
        for i,h in enumerate(headers):
            html += f"<th onclick='sortTable({i}, \"{table_id}\")'>{h}</th>"
        html += "</tr>"

        for team, s in sorted(stats.items(), key=lambda x: (rate(x[1]["bo3_full"], x[1]["bo3_total"]) or -1)):
            bo3_r = rate(s["bo3_full"], s["bo3_total"])
            bo5_r = rate(s["bo5_full"], s["bo5_total"])
            match_wr = rate(s["match_win"], s["match_total"])
            game_wr = rate(s["game_win"], s["game_total"])

            streak = "-"
            streak_color = "#f3f4f6"
            if s["streak_w"] > 0:
                streak = f"{s['streak_w']}W"
                streak_color = color_streak_wl("W")
            elif s["streak_l"] > 0:
                streak = f"{s['streak_l']}L"
                streak_color = color_streak_wl("L")

            last_match = s["last_match_date"].strftime("%Y-%m-%d") if s["last_match_date"] else "-"

            html += "<tr>"
            html += f"<td>{team}</td>"
            html += f"<td>{s['bo3_full']}/{s['bo3_total']}</td>"
            html += f"<td style='background:{color_by_streak(bo3_r)};color:white;font-weight:600'>{pct(bo3_r)}</td>"
            html += f"<td>{s['bo5_full']}/{s['bo5_total']}</td>"
            html += f"<td style='background:{color_by_streak(bo5_r)};color:white;font-weight:600'>{pct(bo5_r)}</td>"
            html += f"<td>{s['match_win']}-{s['match_total']-s['match_win']}</td>"
            html += f"<td>{pct(match_wr)}</td>"
            html += f"<td>{s['game_win']}-{s['game_total']-s['game_win']}</td>"
            html += f"<td>{pct(game_wr)}</td>"
            html += f"<td style='background:{streak_color};color:white;font-weight:700;font-size:1.1em'>{streak}</td>"
            html += f"<td style='color:#6b7280;font-size:0.9em'>{last_match}</td>"
            html += "</tr>"
        html += "</table>"
    html += "</div></body></html>"
    INDEX_FILE.write_text(html, encoding="utf-8")

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_data = {}
    for t in TOURNAMENTS:
        stats = scrape_tournament(t)
        all_data[t["slug"]] = stats
        build_md_backup(t, stats)
    build_index_html(all_data)
    print("index.html generated and tournament backups updated.")

if __name__ == "__main__":
    main()
