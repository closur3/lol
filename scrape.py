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

OUTPUT_DIR = Path("tournaments")
README_FILE = Path("README.md")
INDEX_FILE = Path("index.html")


# ---------- 工具函数 ----------
def pct(n, d):
    """安全百分比字符串"""
    if d == 0:
        return "-"
    return f"{n / d:.2%}"


def color_by_rate(rate):
    """
    rate: 0~1
    低 -> 绿，高 -> 红
    """
    if rate is None:
        return "#999"
    r = int(255 * rate)
    g = int(255 * (1 - rate))
    return f"rgb({r},{g},80)"


# ---------- 抓取 ----------
def scrape_tournament(title, url):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    stats = defaultdict(lambda: {
        "bo3_total": 0,
        "bo3_full": 0,
        "bo5_total": 0,
        "bo5_full": 0,
        "map_win": 0,
        "map_total": 0,
        "win": 0,
        "lose": 0,
        "streak_done": False,
    })

    rows = soup.select("table tr")

    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        t1 = tds[1].get_text(strip=True)
        score = tds[2].get_text(strip=True)
        t2 = tds[3].get_text(strip=True)

        if "-" not in score:
            continue

        try:
            s1, s2 = map(int, score.split("-"))
        except ValueError:
            continue

        max_s, min_s = max(s1, s2), min(s1, s2)

        # map
        stats[t1]["map_win"] += s1
        stats[t1]["map_total"] += s1 + s2
        stats[t2]["map_win"] += s2
        stats[t2]["map_total"] += s1 + s2

        # BO3 / BO5
        if max_s == 2:
            for t in (t1, t2):
                stats[t]["bo3_total"] += 1
            if min_s == 1:
                for t in (t1, t2):
                    stats[t]["bo3_full"] += 1
        elif max_s == 3:
            for t in (t1, t2):
                stats[t]["bo5_total"] += 1
            if min_s == 2:
                for t in (t1, t2):
                    stats[t]["bo5_full"] += 1

        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)

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

    return stats


# ---------- Markdown ----------
def write_md(slug, title, stats):
    lines = [
        f"# {title}",
        "",
        "| Team | BO3 Full | BO3 Rate | BO5 Full | BO5 Rate | Map WR | Streak |",
        "|------|----------|----------|----------|----------|--------|--------|",
    ]

    for team, s in sorted(stats.items()):
        lines.append(
            f"| {team} | "
            f"{s['bo3_full']}/{s['bo3_total']} | {pct(s['bo3_full'], s['bo3_total'])} | "
            f"{s['bo5_full']}/{s['bo5_total']} | {pct(s['bo5_full'], s['bo5_total'])} | "
            f"{pct(s['map_win'], s['map_total'])} | "
            f"{s['win']}W/{s['lose']}L |"
        )

    (OUTPUT_DIR / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")


# ---------- HTML / GitHub Pages ----------
def build_index(all_data):
    html = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>LoL Tournament Stats</title>
<style>
body { font-family: system-ui; padding: 20px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ccc; padding: 6px; text-align: center; }
th { background: #f5f5f5; }
</style>
</head>
<body>
<h1>LoL Tournament Stats</h1>
"""

    for t in TOURNAMENTS:
        slug = t["slug"]
        html += f"<h2>{t['title']}</h2><table>"
        html += (
            "<tr><th>Team</th><th>BO3</th><th>BO3 Rate</th>"
            "<th>BO5</th><th>BO5 Rate</th><th>Map WR</th><th>Streak</th></tr>"
        )

        stats = all_data[slug]

        def bo3_rate(s):
            return s["bo3_full"] / s["bo3_total"] if s["bo3_total"] else -1

        for team, s in sorted(stats.items(), key=lambda x: bo3_rate(x[1])):
            r3 = bo3_rate(s)
            r5 = s["bo5_full"] / s["bo5_total"] if s["bo5_total"] else None
            mr = s["map_win"] / s["map_total"] if s["map_total"] else None

            html += f"""
<tr>
<td>{team}</td>
<td>{s['bo3_full']}/{s['bo3_total']}</td>
<td style="color:{color_by_rate(r3 if r3 >= 0 else None)}">{pct(s['bo3_full'], s['bo3_total'])}</td>
<td>{s['bo5_full']}/{s['bo5_total']}</td>
<td style="color:{color_by_rate(r5)}">{pct(s['bo5_full'], s['bo5_total'])}</td>
<td style="color:{color_by_rate(mr)}">{pct(s['map_win'], s['map_total'])}</td>
<td>{s['win']}W/{s['lose']}L</td>
</tr>
"""

        html += "</table>"

    html += "</body></html>"
    INDEX_FILE.write_text(html, encoding="utf-8")


# ---------- main ----------
def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_data = {}

    for t in TOURNAMENTS:
        stats = scrape_tournament(t["title"], t["url"])
        all_data[t["slug"]] = stats
        write_md(t["slug"], t["title"], stats)

    build_index(all_data)
    print("Generated tournaments/*.md and index.html")


if __name__ == "__main__":
    main()
