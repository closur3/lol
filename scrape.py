import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path

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

    for row in soup.select("table tr"):
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

        # ---------- BO3 / BO5 ----------
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

        # ---------- Series ----------
        stats[winner]["series_win"] += 1
        stats[winner]["series_total"] += 1
        stats[loser]["series_total"] += 1

        # ---------- Game ----------
        stats[team1]["game_win"] += s1
        stats[team1]["game_total"] += s1 + s2
        stats[team2]["game_win"] += s2
        stats[team2]["game_total"] += s1 + s2

        # ---------- Streak ----------
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

    rows = []
    for team, s in stats.items():
        rows.append({
            "team": team,
            "bo3": s,
            "bo5": s,
            "series": s,
            "game": s,
            "streak": s["win"] if s["win"] > 0 else -s["lose"] if s["lose"] > 0 else 0,
        })

    return {"title": t["title"], "rows": rows}


def build_index(all_data):
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Tournament Stats</title>
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
        headers = [
            "Team",
            "BO3 Full",
            "BO5 Full",
            "Series WR",
            "Game WR",
            "Streak",
        ]
        for i, h in enumerate(headers):
            html += f"<th onclick=\"sortTable(this.closest('table'),{i},true)\">{h}</th>"
        html += "</tr></thead><tbody>"

        for r in block["rows"]:
            s = r["bo3"]
            def rate(a, b): return a / b if b else None

            bo3r = rate(s["bo3_full"], s["bo3_total"])
            bo5r = rate(s["bo5_full"], s["bo5_total"])
            ser = rate(s["series_win"], s["series_total"])
            game = rate(s["game_win"], s["game_total"])

            html += f"""
<tr>
<td>{r["team"]}</td>
<td data-v="{bo3r or -1}">{s["bo3_full"]}/{s["bo3_total"]} ({bo3r:.1%})</td>
<td data-v="{bo5r or -1}">{s["bo5_full"]}/{s["bo5_total"]} ({bo5r:.1%})</td>
<td data-v="{ser or -1}">{s["series_win"]}/{s["series_total"]} ({ser:.1%})</td>
<td data-v="{game or -1}">{s["game_win"]}/{s["game_total"]} ({game:.1%})</td>
<td data-v="{r["streak"]}">{r["streak"]:+d}</td>
</tr>
"""

        html += "</tbody></table>"

    html += "<script>document.querySelectorAll('table').forEach(t=>sortTable(t,1,true));</script></body></html>"
    INDEX_HTML.write_text(html, encoding="utf-8")


def main():
    data = [scrape_tournament(t) for t in TOURNAMENTS]
    build_index(data)
    print("index.html generated")


if __name__ == "__main__":
    main()
