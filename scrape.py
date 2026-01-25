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
# =========================================================

OUTPUT_DIR = Path("tournaments")
README_FILE = Path("README.md")
INDEX_FILE = Path("index.html")


def scrape_tournament(title: str, url: str, output_md: Path):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    stats = defaultdict(lambda: {
        "bo3_total": 0,
        "bo3_full": 0,
        "bo5_total": 0,
        "bo5_full": 0,
        "current_win": 0,
        "current_lose": 0,
        "streak_done": False,
    })

    rows = soup.select("table tr")

    # gol.gg：从新到旧
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
        max_score = max(s1, s2)
        min_score = min(s1, s2)

        # ===== BO3 / BO5 =====
        if max_score == 2:
            for t in (team1, team2):
                stats[t]["bo3_total"] += 1
            if min_score == 1:
                for t in (team1, team2):
                    stats[t]["bo3_full"] += 1

        elif max_score == 3:
            for t in (team1, team2):
                stats[t]["bo5_total"] += 1
            if min_score == 2:
                for t in (team1, team2):
                    stats[t]["bo5_full"] += 1

        # ===== 当前连胜 / 连败 =====
        if not stats[winner]["streak_done"]:
            if stats[winner]["current_lose"] > 0:
                stats[winner]["streak_done"] = True
            else:
                stats[winner]["current_win"] += 1

        if not stats[loser]["streak_done"]:
            if stats[loser]["current_win"] > 0:
                stats[loser]["streak_done"] = True
            else:
                stats[loser]["current_lose"] += 1

    # ===== 输出 Markdown =====
    lines = [
        f"# {title}",
        "",
        "| Team | BO3 | BO3 Rate | BO5 | BO5 Rate | Streak |",
        "|------|-----|----------|-----|----------|--------|",
    ]

    for team, s in sorted(stats.items()):
        bo3_rate = f"{s['bo3_full']/s['bo3_total']:.2%}" if s["bo3_total"] else "-"
        bo5_rate = f"{s['bo5_full']/s['bo5_total']:.2%}" if s["bo5_total"] else "-"
        streak = f"{s['current_win']}W" if s["current_win"] > 0 else (
            f"{s['current_lose']}L" if s["current_lose"] > 0 else "-"
        )

        lines.append(
            f"| {team} | "
            f"{s['bo3_full']}/{s['bo3_total']} | {bo3_rate} | "
            f"{s['bo5_full']}/{s['bo5_total']} | {bo5_rate} | "
            f"{streak} |"
        )

    output_md.write_text("\n".join(lines), encoding="utf-8")
    return stats


def build_readme():
    README_FILE.write_text(
        "# Tournament Stats\n\n"
        "➡️ View sortable tables on **GitHub Pages**:\n\n"
        "- `index.html`\n",
        encoding="utf-8",
    )


def build_index_html(all_stats):
    html = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        "<title>Tournament Stats</title>",
        "<style>",
        "body{font-family:system-ui;margin:40px}",
        "table{border-collapse:collapse;width:100%;margin-bottom:40px}",
        "th,td{border:1px solid #ccc;padding:6px;text-align:center}",
        "th{cursor:pointer;background:#f5f5f5}",
        "</style>",
        "<script>",
        "function sortTable(t,c,n){",
        "const b=t.tBodies[0];",
        "const r=[...b.rows];",
        "const a=t.dataset.c==c&&t.dataset.d=='a'?false:true;",
        "r.sort((x,y)=>{",
        "let A=x.cells[c].innerText.replace('%','');",
        "let B=y.cells[c].innerText.replace('%','');",
        "return n?(a?A-B:B-A):(a?A.localeCompare(B):B.localeCompare(A));",
        "});",
        "r.forEach(tr=>b.appendChild(tr));",
        "t.dataset.c=c;t.dataset.d=a?'a':'d';}",
        "</script>",
        "</head><body>",
        "<h1>Tournament Summary</h1>",
        "<p>Click table headers to sort</p>",
    ]

    for t in TOURNAMENTS:
        slug = t["slug"]
        title = t["title"]
        stats = all_stats.get(slug, {})

        html.append(f"<h2>{title}</h2>")
        html.append("<table><thead><tr>")
        headers = ["Team", "BO3", "BO3 Rate", "BO5", "BO5 Rate", "Streak"]
        for i, h in enumerate(headers):
            num = "true" if h != "Team" else "false"
            html.append(f"<th onclick='sortTable(this.closest(\"table\"),{i},{num})'>{h}</th>")
        html.append("</tr></thead><tbody>")

        for team, s in stats.items():
            bo3_rate = s["bo3_full"]/s["bo3_total"]*100 if s["bo3_total"] else 0
            bo5_rate = s["bo5_full"]/s["bo5_total"]*100 if s["bo5_total"] else 0
            streak = s["current_win"] if s["current_win"] > 0 else -s["current_lose"]

            html.append(
                f"<tr><td>{team}</td>"
                f"<td>{s['bo3_full']}/{s['bo3_total']}</td>"
                f"<td>{bo3_rate:.2f}</td>"
                f"<td>{s['bo5_full']}/{s['bo5_total']}</td>"
                f"<td>{bo5_rate:.2f}</td>"
                f"<td>{streak}</td></tr>"
            )

        html.append("</tbody></table>")

    html.append("</body></html>")
    INDEX_FILE.write_text("\n".join(html), encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_stats = {}

    for t in TOURNAMENTS:
        md = OUTPUT_DIR / f"{t['slug']}.md"
        all_stats[t["slug"]] = scrape_tournament(t["title"], t["url"], md)

    build_readme()
    build_index_html(all_stats)


if __name__ == "__main__":
    main()
