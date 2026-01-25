import requests
from bs4 import BeautifulSoup
from collections import defaultdict

URL = "https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/"
OUTPUT_MD = "2026-lck-cup.md"

resp = requests.get(URL, timeout=15)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "html.parser")

# 统计结构
stats = defaultdict(lambda: {
    "bo3_total": 0,
    "bo3_full": 0,
    "bo5_total": 0,
    "bo5_full": 0,
})

# gol.gg 的比赛行
rows = soup.select("table tr")

for row in rows:
    tds = row.find_all("td")
    if len(tds) < 5:
        continue

    team1 = tds[1].get_text(strip=True)
    score = tds[2].get_text(strip=True)
    team2 = tds[3].get_text(strip=True)

    # 必须是已完场比分
    if "-" not in score:
        continue

    try:
        s1, s2 = map(int, score.split("-"))
    except ValueError:
        continue

    max_score = max(s1, s2)
    min_score = min(s1, s2)

    # BO3
    if max_score == 2:
        for team in (team1, team2):
            stats[team]["bo3_total"] += 1
        if min_score == 1:
            for team in (team1, team2):
                stats[team]["bo3_full"] += 1

    # BO5
    elif max_score == 3:
        for team in (team1, team2):
            stats[team]["bo5_total"] += 1
        if min_score == 2:
            for team in (team1, team2):
                stats[team]["bo5_full"] += 1

# 输出 Markdown
lines = []
lines.append("# LCK Cup 2026 BO3 / BO5 打满率\n")
lines.append("| Team | BO3 (Full/Total) | BO3 Full Rate | BO5 (Full/Total) | BO5 Full Rate |")
lines.append("|------|------------------|---------------|------------------|---------------|")

for team, s in sorted(stats.items()):
    bo3_rate = (
        f"{s['bo3_full'] / s['bo3_total']:.2%}"
        if s["bo3_total"] else "-"
    )
    bo5_rate = (
        f"{s['bo5_full'] / s['bo5_total']:.2%}"
        if s["bo5_total"] else "-"
    )

    lines.append(
        f"| {team} "
        f"| {s['bo3_full']}/{s['bo3_total']} "
        f"| {bo3_rate} "
        f"| {s['bo5_full']}/{s['bo5_total']} "
        f"| {bo5_rate} |"
    )

with open(OUTPUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Written to {OUTPUT_MD}")
