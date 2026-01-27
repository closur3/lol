import requests
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
GITHUB_REPO = "https://github.com/closur3/lol"

# ---------- 辅助函数 ----------
def get_hsl(h, s=70, l=45): return f"hsl({int(h)}, {s}%, {l}%)"
def color_by_ratio(r, rev=False):
    if r is None: return "#f3f4f6"
    h = (1 - max(0, min(1, r))) * 140 if rev else max(0, min(1, r)) * 140
    return get_hsl(h, s=65, l=48)
def color_text_by_ratio(r, rev=False):
    if r is None: return "#6b7280"
    h = (1 - max(0, min(1, r))) * 140 if rev else max(0, min(1, r)) * 140
    return get_hsl(h, s=80, l=35)
def color_by_date(d, dates):
    if not d or not dates: return "#9ca3af"
    mx, mn = max(dates), min(dates)
    if mx == mn: return "#3b82f6"
    f = (d - mn).total_seconds() / (mx - mn).total_seconds()
    return f"hsl(215, {int(f * 80 + 20)}%, {int(55 - f * 15)}%)"
def rate(n, d): return n / d if d > 0 else None
def pct(r): return f"{r*100:.1f}%" if r is not None else "-"

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
        t1, sc, t2 = tds[1].text.strip(), tds[2].text.strip(), tds[3].text.strip()
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
    <title>LoL Stats Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f1f5f9; margin: 0; padding: 15px; color: #1e293b; }}
        
        /* 标题样式处理 */
        .main-header {{ 
            text-align: center; 
            padding: 20px 0 30px 0; 
        }}
        .main-header h1 {{ 
            margin: 0; 
            font-size: 2.2rem; 
            font-weight: 800; 
            letter-spacing: -1px;
            background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        @media (max-width: 600px) {{
            .main-header h1 {{ font-size: 1.6rem; }}
        }}

        .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 25px; border: 1px solid #e2e8f0; }}
        .table-title {{ padding: 15px; background: #fff; border-bottom: 1px solid #f1f5f9; border-radius: 12px 12px 0 0; font-weight: 700; font-size: 1.1rem; }}
        .table-title a {{ color: #2563eb; text-decoration: none; }}
        
        table {{ width: 100%; min-width: 1050px; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #f8fafc; padding: 14px 8px; font-weight: 600; color: #64748b; border-bottom: 2px solid #f1f5f9; cursor: pointer; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }}
        th:hover {{ background: #f1f5f9; color: #2563eb; }}
        
        td {{ padding: 12px 8px; text-align: center; border-bottom: 1px solid #f8fafc; white-space: nowrap; }}
        .team-col {{ position: sticky; left: 0; background: white !important; z-index: 10; border-right: 2px solid #f1f5f9; text-align: left; font-weight: 700; padding-left: 15px; color: #0f172a; }}
        th.team-col {{ background: #f8fafc !important; z-index: 11; }}
        
        .badge {{ color: white; border-radius: 5px; padding: 3px 7px; font-size: 11px; font-weight: 700; }}
        .footer {{ text-align: center; font-size: 12px; color: #94a3b8; margin: 40px 0; padding-top: 20px; border-top: 1px solid #e2e8f0; }}
        .footer a {{ color: #3b82f6; text-decoration: none; font-weight: 600; }}
    </style>
</head>
<body>
    <header class="main-header">
        <h1>🏆 LoL Tournament Insights</h1>
    </header>

    <div style="max-width:1400px; margin:0 auto">"""

    for idx, t in enumerate(TOURNAMENTS):
        st = all_data.get(t["slug"], {})
        tid = f"t{idx}"
        dates = [s["ld"] for s in st.values() if s["ld"]]
        html += f"""
        <div class="wrapper">
            <div class="table-title">
                <a href="{t['url']}" target="_blank">{t['title']}</a>
            </div>
            <table id="{tid}">
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
        
        # 初始排序：BO3打满率升序，胜率降序
        sorted_teams = sorted(st.items(), key=lambda x: (rate(x[1]["bo3_f"], x[1]["bo3_t"]) or 999, -(rate(x[1]["m_w"], x[1]["m_t"]) or 0)))

        for team, s in sorted_teams:
            b3r, b5r, mwr, gwr = rate(s["bo3_f"], s["bo3_t"]), rate(s["bo5_f"], s["bo5_t"]), rate(s["m_w"], s["m_t"]), rate(s["g_w"], s["g_t"])
            stk = f"<span class='badge' style='background:#10b981'>{s['sw']}W</span>" if s['sw']>0 else (f"<span class='badge' style='background:#f43f5e'>{s['sl']}L</span>" if s['sl']>0 else "-")
            ld = s["ld"].strftime("%Y-%m-%d") if s["ld"] else "-"
            html += f"""
                <tr>
                    <td class="team-col">{team}</td>
                    <td style="color:{color_text_by_ratio(b3r,True)}">{s['bo3_f']}/{s['bo3_t']}</td>
                    <td style="background:{color_by_ratio(b3r,True)};color:white;font-weight:bold">{pct(b3r)}</td>
                    <td style="color:{color_text_by_ratio(b5r,True)}">{s['bo5_f']}/{s['bo5_t']}</td>
                    <td style="background:{color_by_ratio(b5r,True)};color:white;font-weight:bold">{pct(b5r)}</td>
                    <td style="color:{color_text_by_ratio(mwr)}">{s['m_w']}-{s['m_t']-s['m_w']}</td>
                    <td style="background:{color_by_ratio(mwr)};color:white;font-weight:bold">{pct(mwr)}</td>
                    <td style="color:{color_text_by_ratio(gwr)}">{s['g_w']}-{s['g_t']-s['g_w']}</td>
                    <td style="background:{color_by_ratio(gwr)};color:white;font-weight:bold">{pct(gwr)}</td>
                    <td>{stk}</td>
                    <td style="color:{color_by_date(s['ld'], dates)};font-weight:700">{ld}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
    <div class="footer">
        Generated at {now} | <a href="{GITHUB_REPO}" target="_blank">View on GitHub</a>
    </div>
    </div>
    <script>
        function doSort(colIdx, tableId) {{
            const table = document.getElementById(tableId);
            const tbody = table.tBodies[0];
            const rows = Array.from(tbody.rows);
            const isAsc = table.getAttribute('data-dir') === 'asc';
            
            rows.sort((a, b) => {{
                let valA = a.cells[colIdx].innerText;
                let valB = b.cells[colIdx].innerText;
                
                // 日期特殊处理 (Last Match 列)
                if (colIdx === 10) {{
                    valA = valA === "-" ? 0 : new Date(valA).getTime();
                    valB = valB === "-" ? 0 : new Date(valB).getTime();
                }} else {{
                    valA = parseVal(valA);
                    valB = parseVal(valB);
                }}
                
                if (valA === valB) return 0;
                return isAsc ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
            }});
            
            table.setAttribute('data-dir', isAsc ? 'desc' : 'asc');
            rows.forEach(r => tbody.appendChild(r));
        }}
        
        function parseVal(v) {{
            if (v.includes('%')) return parseFloat(v);
            if (v.includes('/')) {{
                const parts = v.split('/');
                return parseFloat(parts[0]) / parseFloat(parts[1]) || 0;
            }}
            if (v.includes('-') && v.split('-').length === 2) return parseFloat(v.split('-')[0]);
            const n = parseFloat(v);
            return isNaN(n) ? v.toLowerCase() : n;
        }}
    </script>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    data = {t["slug"]: scrape(t) for t in TOURNAMENTS}
    build(data)
