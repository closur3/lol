import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path

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

INDEX_HTML = Path("index.html")


def scrape_tournament(t):
    resp = requests.get(t["url"], timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    stats = defaultdict(lambda: {
        "bo3_full": 0,
        "bo3_total": 0,
        "bo5_full": 0,
        "bo5_total": 0,
        "series_win": 0,
        "series_total": 0,
        "game_win": 0,
        "game_total": 0,
        "win": 0,
        "lose": 0,
        "streak_done": False,
    })

    rows = soup.select("table tr")

    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        team1 = tds[1].get_text(strip=True)
        score = tds[2].get_text(strip=True)
        team2 = tds[3].get_text(strip=True)

        if "-" not in score:
            continue

        try:
            s1, s2 = map(int, score.split("-"))
        except ValueError:
            continue

        winner, loser = (team1, team2) if s1 > s2 else (team2, team1)
        max_s, min_s = max(s1, s2), min(s1, s2)

        # ===== BO3 / BO5 打满 =====
        if max_s == 2:
            for tname in (team1, team2):
                stats[tname]["bo3_total"] += 1
            if min_s == 1:
                for tname in (team1, team2):
                    stats[tname]["bo3_full"] += 1

        elif max_s == 3:
            for tname in (team1, team2):
                stats[tname]["bo5_total"] += 1
            if min_s == 2:
                for tname in (team1, team2):
                    stats[tname]["bo5_full"] += 1

        # ===== 大场胜率 =====
        stats[winner]["series_win"] += 1
        stats[winner]["series_total"] += 1
        stats[loser]["series_total"] += 1

        # ===== 小场胜率 =====
        stats[team1]["game_win"] += s1
        stats[team1]["game_total"] += s1 + s2
        stats[team2]["game_win"] += s2
        stats[team2]["game_total"] += s1 + s2

        # ===== 当前 streak =====
        if not stats[winner]["streak_done"]:
            if stats[winner]["lose"] > 0:
                stats[winner]["streak_done"] = True
            else:
                stats[winner]["win"] += 1

        if not stats[loser]["streak_done"]:
            if stats[loser]["win"] > 0:
                stats[loser]["streak_done"] = True
            else:
                stats[loser]["lose"] += 1

    result = []
    for team, s in stats.items():
        result.append({
            "team": team,
            "bo3_rate": s["bo3_full"] / s["bo3_total"] if s["bo3_total"] else None,
            "bo5_rate": s["bo5_full"] / s["bo5_total"] if s["bo5_total"] else None,
            "series_rate": s["series_win"] / s["series_total"] if s["series_total"] else None,
            "game_rate": s["game_win"] / s["game_total"] if s["game_total"] else None,
            "streak": s["win"] if s["win"] > 0 else -s["lose"] if s["lose"] > 0 else 0,
        })

    return {"title": t["title"], "data": result}


def build_index(all_data):
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>League Tournament Stats</title>
<style>
body{font-family:system-ui;padding:20px}
table{border-collapse:collapse;margin-bottom:40px}
th,td{border:1px solid #ccc;padding:6px 10px;text-align:center}
th{cursor:pointer;background:#f5f5f5}
</style>
<script>
function sortTable(t,c,a=true){
const b=t.tBodies[0],r=[...b.rows];
r.sort((x,y)=>(parseFloat(x.cells[c].dataset.v||0)-parseFloat(y.cells[c].dataset.v||0))*(a?1:-1));
r.forEach(e=>b.appendChild(e));
}
</script>
</head><body>
<h1>Tournament Summary</h1>
"""

    for block in all_data:
        html += f"<h2>{block['title']}</h2><table><thead><tr>"
        html += "<th>Team</th>"
        html += "<th onclick=\"sortTable(this.closest('table'),1,true)\">BO3 Rate</th>"
        html += "<th onclick=\"sortTable(this.closest('table'),2,true)\">BO5 Rate</th>"
        html += "<th onclick=\"sortTable(this.closest('table'),3,false)\">Series WR</th>"
        html += "<th onclick=\"sortTable(this.closest('table'),4,false)\">Game WR</th>"
        html += "<th onclick=\"sortTable(this.closest('table'),5,false)\">Streak</th>"
        html += "</tr></thead><tbody>"

        for r in block["data"]:
            html += f"""
<tr>
<td>{r["team"]}</td>
<td data-v="{r["bo3_rate"] or -1}">{f'{r["bo3_rate"]:.1%}' if r["bo3_rate"] is not None else '-'}</td>
<td data-v="{r["bo5_rate"] or -1}">{f'{r["bo5_rate"]:.1%}' if r["bo5_rate"] is not None else '-'}</td>
<td data-v="{r["series_rate"] or -1}">{f'{r["series_rate"]:.1%}' if r["series_rate"] is not None else '-'}</td>
<td data-v="{r["game_rate"] or -1}">{f'{r["game_rate"]:.1%}' if r["game_rate"] is not None else '-'}</td>
<td data-v="{r["streak"]}">{r["streak"]:+d}</td>
</tr>
"""
        html += "</tbody></table>"

    html += "<script>document.querySelectorAll('table').forEach(t=>sortTable(t,1,true));</script></body></html>"
    INDEX_HTML.write_text(html, encoding="utf-8")


def main():
    all_data = [scrape_tournament(t) for t in TOURNAMENTS]
    build_index(all_data)
    print("Updated index.html")


if __name__ == "__main__":
    main()
