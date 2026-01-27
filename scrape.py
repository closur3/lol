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
    <title>LoL Stats</title>
    <style>
        body {{ font-family: sans-serif; background: #f8fafc; margin: 0; padding: 10px; }}
        .wrapper {{ width: 100%; overflow-x: auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 20px; }}
        table {{ width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; table-layout: auto; }}
        th {{ background: #f1f5f9; padding: 12px 5px; font-weight: 700; border-bottom: 2px solid #e2e8f0; cursor: pointer; position: sticky; top: 0; z-index: 5; }}
        th:hover {{ background: #e2e8f0; }}
        td {{ padding: 10px 5px; text-align: center; border-bottom: 1px solid #e2e8f0; white-space: nowrap; }}
        .team-col {{ position: sticky; left: 0; background: white !important; z-index: 10; border-right: 2px solid #e2e8f0; text-align: left; font-weight: 800; padding-left: 10px; }}
        th.team-col {{ background: #f1f5f9 !important; z-index: 11; }}
        .badge {{ color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold; }}
        .footer {{ text-align: center; font-size: 12px; color: #64748b; margin: 20px 0; }}
    </style>
</head>
<body>
    <h2 style="text-align:center">🏆 LoL Stats Dashboard</h2>
    <div style="max-width:1400px; margin:0 auto">"""

    for idx, t in enumerate(TOURNAMENTS):
        st = all_data.get(t["slug"], {})
        tid = f"t{idx}"
        dates = [s["ld"] for s in st.values() if s["ld"]]
        html += f"""
        <div class="wrapper">
            <div style="padding:10px; font-weight:bold; border-bottom:1px solid #eee"><a href="{t['url']}">{t['title']}</a></div>
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
                    <td style="color:{color_by_date(s['ld'], dates)};font-weight:bold">{ld}</td>
                </tr>"""
        html += "</tbody></table></div>"

    html += f"""
    <div class="footer">Updated: {now} | <a href="{GITHUB_REPO}">GitHub</a></div>
    </div>
    <script>
        function doSort(n, id) {{
            const t = document.getElementById(id);
            const b = t.tBodies[0];
            const rows = Array.from(b.rows);
            const dir = t.getAttribute('data-dir') === 'asc' ? -1 : 1;
            
            rows.sort((a, b) => {{
                let x = parse(a.cells[n].innerText);
                let y = parse(b.cells[n].innerText);
                if (n === 10) {{ // 专门针对日期的排序
                    x = a.cells[n].innerText === "-" ? 0 : new Date(a.cells[n].innerText).getTime();
                    y = b.cells[n].innerText === "-" ? 0 : new Date(b.cells[n].innerText).getTime();
                }}
                return x > y ? dir : x < y ? -dir : 0;
            }});
            
            t.setAttribute('data-dir', dir === 1 ? 'asc' : 'desc');
            rows.forEach(r => b.appendChild(r));
        }}
        function parse(v) {{
            if (v.includes('%')) return parseFloat(v);
            if (v.includes('/')) return eval(v) || 0;
            if (v.includes('-') && v.length < 6) return parseFloat(v.split('-')[0]);
            return isNaN(v) ? v.toLowerCase() : parseFloat(v);
        }}
    </script>
</body>
</html>"""
    INDEX_FILE.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    data = {t["slug"]: scrape(t) for t in TOURNAMENTS}
    build(data)
