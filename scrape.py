import requests
import json
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ================== 配置 ==================
TOURNAMENTS = [
    {"slug": "2026-lck-cup", "title": "2026 LCK Cup", "url": "https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/"},
    {"slug": "2026-lpl-split-1", "title": "2026 LPL Split 1", "url": "https://gol.gg/tournament/tournament-matchlist/LPL%202026%20Split%201/"},
]
INDEX_FILE = Path("index.html")
TEAMS_JSON = Path("teams.json")
GITHUB_REPO = "https://github.com/closur3/lol"

# ---------- 队名映射处理器 (支持模糊匹配) ----------
def load_team_map():
    if TEAMS_JSON.exists():
        try:
            return json.loads(TEAMS_JSON.read_text(encoding='utf-8'))
        except: pass
    return {}

TEAM_MAP = load_team_map()

def get_short_name(full_name):
    # 1. 模糊匹配逻辑：只要 JSON 里的 key 在全称里出现过，就使用对应的缩写
    name_upper = full_name.upper()
    for key, short_val in TEAM_MAP.items():
        if key.upper() in name_upper:
            return short_val
    # 2. 兜底清洗
    return full_name.replace("Esports", "").replace("Gaming", "").replace("Academy", "").replace("Team", "").strip()

# ---------- 辅助函数 ----------
def rate(n, d): return n / d if d > 0 else 0.0 # 修改：默认回退到 0.0 而非 999
def pct(r): return f"{r*100:.1f}%"
def get_hsl(h, s=70, l=45): return f"hsl({int(h)}, {s}%, {l}%)"
def color_by_ratio(r, rev=False):
    h = (1 - max(0, min(1, r))) * 140 if rev else max(0, min(1, r)) * 140
    return get_hsl(h, s=65, l=48)
def color_text_by_ratio(r, rev=False):
    h = (1 - max(0, min(1, r))) * 140 if rev else max(0, min(1, r)) * 140
    return get_hsl(h, s=80, l=35)
def color_by_date(d, dates):
    if not d or not dates: return "#9ca3af"
    mx, mn = max(dates), min(dates)
    f = (d - mn).total_seconds() / (mx - mn).total_seconds() if mx != mn else 1
    return f"hsl(215, {int(f * 80 + 20)}%, {int(55 - f * 15)}%)"

# ---------- 抓取逻辑 ----------
def scrape(t):
    try:
        r = requests.get(t["url"], headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
    except: return {}
    stats = defaultdict(lambda: {"bo3_f": 0, "bo3_t": 0, "bo5_f": 0, "bo5_t": 0, "m_w": 0, "m_t": 0, "g_w": 0, "g_t": 0, "sw": 0, "sl": 0, "sd": False, "ld": None})
    for row in soup.select("table tr"):
        tds = row.find_all("td")
        if len(tds) < 5: continue
        t1_raw, sc, t2_raw = tds[1].text.strip(), tds[2].text.strip(), tds[3].text.strip()
        t1, t2 = get_short_name(t1_raw), get_short_name(t2_raw)
        try: dt = datetime.strptime(tds[-1].text.strip(), "%Y-%m-%d")
        except: dt = None
        if "-" not in sc: continue
        try: s1, s2 = map(int, sc.split("-"))
        except: continue
        win, los = (t1, t2) if s1 > s2 else (t2, t1)
        for t_ in (t1, t2):
            if dt and (not stats[t_]["ld"] or dt > stats[t_]["ld"]): stats[t_]["ld"] = dt
            stats[t_]["m_t"] += 1; stats[t_]["g_t"] += (s1+s2)
        stats[win]["m_w"] += 1; stats[t1]["g_w"] += s1; stats[t2]["g_w"] += s2
        mx, mn = max(s1, s2), min(s1, s2)
        if mx == 2:
            for t_ in (t1, t2): stats[t_]["bo3_t"] += 1
            if mn == 1: 
                for t_ in (t1, t2): stats[t_]["bo3_f"] += 1
        elif mx == 3:
            for t_ in (t1, t2): stats[t_]["bo5_t"] += 1
            if mn == 2: 
                for t_ in (t1, t2): stats[t_]["bo5_f"] += 1
        if not stats[win]["sd"]:
            if stats[win]["sl"] > 0: stats[win]["sd"] = True
            else: stats[win]["sw"] += 1
        if not stats[los]["sd"]:
            if stats[los]["sw"] > 0: stats[los]["sd"] = True
            else: stats[los]["sl"] += 1
    return stats

# ---------- 生成 HTML ----------
def build(all_data):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
    html = f"""<!DOCTYPE html>
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
        table {{ width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #f8fafc; padding: 14px 8px; font-weight: 600; color: #64748b; border-bottom: 2px solid #f1f5f9; cursor: pointer; transition: 0.2s; }}
        th:hover {{ background: #eff6ff; color: #2563eb; }}
        td {{ padding: 12px 8px; text-align: center; border-bottom: 1px solid #f8fafc; white-space: nowrap; }}
        .team-col {{ position: sticky; left: 0; background: white !important; z-index: 10; border-right: 2px solid #f1f5f9; text-align: left; font-weight: 800; padding-left: 15px; }}
        .badge {{ color: white; border-radius: 4px; padding: 3px 7px; font-size: 11px; font-weight: 700; }}
        .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; }}
    </style>
</head>
<body>
    <header class="main-header"><h1>🏆 LoL Insights Pro</h1></header>
    <div style="max-width:1400px; margin:0 auto">"""

    for idx, t in enumerate(TOURNAMENTS):
        st = all_data.get(t["slug"], {})
        tid = f"t{idx}"
        dates = [s["ld"] for s in st.values() if s["ld"]]
        html += f"""
        <div class="wrapper">
            <div class="table-title"><a href="{t['url']}" target="_blank">{t['title']}</a></div>
            <table id="{tid}" data-dir="asc">
                <thead>
                    <tr>
                        <th class="team-col" onclick="doSort(0, '{tid}')">Team</th>
                        <th onclick="doSort(1, '{tid}')">BO3</th>
                        <th onclick="doSort(2, '{tid}')">BO3%</th>
                        <th onclick="doSort(3, '{tid}')">BO5</th>
                        <th onclick="doSort(4, '{tid}')">BO5%</th>
                        <th onclick="doSort(5, '{tid}')">Match</th>
                        <th onclick="doSort(6, '{tid}')">Match WR</th>
                        <th onclick="doSort(7, '{tid}')">Game</th>
                        <th onclick="doSort(8, '{tid}')">Game WR</th>
                        <th onclick="doSort(9, '{tid}')">Streak</th>
                        <th onclick="doSort(10, '{tid}')">Last Match</th>
                    </tr>
                </thead>
                <tbody>"""
        
        # 初始排序修正：0.0 会排在前面（升序）
        sorted_teams = sorted(st.items(), key=lambda x: (rate(x[1]["bo3_f"], x[1]["bo3_t"]), -(rate(x[1]["m_w"], x[1]["m_t"]))))

        for team, s in sorted_teams:
            b3r, b5r, mwr, gwr = rate(s["bo3_f"], s["bo3_t"]), rate(s["bo5_f"], s["bo5_t"]), rate(s["m_w"], s["m_t"]), rate(s["g_w"], s["g_t"])
            stk = f"<span class='badge' style='background:#10b981'>{s['sw']}W</span>" if s['sw']>0 else (f"<span class='badge' style='background:#f43f5e'>{s['sl']}L</span>" if s['sl']>0 else "-")
            ld = s["ld"].strftime("%Y-%m-%d") if s["ld"] else "-"
            html += f"""
                <tr>
                    <td class="team-col">{team}</td>
                    <td>{s['bo3_f']}/{s['bo3_t']}</td>
                    <td style="background:{color_by_ratio(b3r,True)};color:white;font-weight:bold">{pct(b3r)}</td>
                    <td>{s['bo5_f']}/{s['bo5_t']}</td>
                    <td style="background:{color_by_ratio(b5r,True)};color:white;font-weight:bold">{pct(b5r)}</td>
                    <td>{s['m_w']}-{s['m_t']-s['m_w']}</td>
                    <td style="background:{color_by_ratio(mwr)};color:white;font-weight:bold">{pct(mwr)}</td>
                    <td>{s['g_w']}-{s['g_t']-s['g_w']}</td>
                    <td style="background:{color_by_ratio(gwr)};color:white;font-weight:bold">{pct(gwr)}</td>
                    <td>{stk}</td>
                    <td style="color:{color_by_date(s['ld'], dates)};font-weight:700">{ld}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
    <div class="footer">Updated: {now} | <a href="{GITHUB_REPO}" target="_blank">GitHub</a></div>
    </div>
    <script>
        function doSort(n, id) {{
            const t = document.getElementById(id), b = t.tBodies[0], r = Array.from(b.rows);
            // 核心修复：如果当前是 asc 就变 desc，如果是 desc 就变 asc。
            // 确保第一次点击后，data-dir 被设置为对应的方向
            const currentDir = t.getAttribute('data-sort-dir-' + n) || 'desc';
            const nextDir = currentDir === 'desc' ? 'asc' : 'desc';
            
            r.sort((a, b) => {{
                let x = a.cells[n].innerText, y = b.cells[n].innerText;
                if (n === 10) {{ 
                    x = x === "-" ? 0 : new Date(x).getTime(); 
                    y = y === "-" ? 0 : new Date(y).getTime(); 
                }} else {{ 
                    x = parse(x); y = parse(y); 
                }}
                if (x === y) return 0;
                return nextDir === 'asc' ? (x > y ? 1 : -1) : (x < y ? 1 : -1);
            }});
            
            t.setAttribute('data-sort-dir-' + n, nextDir);
            r.forEach(row => b.appendChild(row));
        }}
        function parse(v) {{
            if (v.includes('%')) return parseFloat(v) || 0;
            if (v.includes('/')) {{ let p = v.split('/'); return parseFloat(p[0])/parseFloat(p[1]) || 0; }}
            if (v.includes('-') && v.split('-').length === 2) return parseFloat(v.split('-')[0]) || 0;
            const n = parseFloat(v); return isNaN(n) ? v.toLowerCase() : n;
        }}
    </script>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    data = {t["slug"]: scrape(t) for t in TOURNAMENTS}
    build(data)
    print("Success: Data sorted correctly (0% at top for ASC)!")
