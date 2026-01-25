import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path

# ====== 赛事配置（之后加赛事只动这里） ======
SLUG = "2026-lck-cup"
URL = "https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/"
OUTPUT_DIR = Path("tournaments")
# ==========================================

OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_MD = OUTPUT_DIR / f"{SLUG}.md"

resp = requests.get(URL, timeout=15)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "html.parser")

stats = defaultdict(lambda: {
    "bo3_total": 0,
    "bo3_full": 0,
    "bo5_total": 0,
    "bo5_full": 0,
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

    max_score = max(s1, s2)
    min_score = min(s1, s2)

    if max_score == 2:  # BO3
        for t in (team1, team2):
            stats[t]["bo3_total"] += 1
        if min_score == 1:
            for t in (team1, team2):
                stats[t]["bo3_full"] += 1

    elif max_score == 3:  # BO5
        for t in (team1, team2):
            stats[t]["bo5_total"] += 1
        if min_score == 2:
            for t in (team1, team2):
                stats[t]["bo5_full"] += 1

# ====== 输出 Markdown ======

lines = []
lines.append("# LCK Cup 2026 – BO3 / BO5 打满率\n")
lines.append("| Team | BO3 (Full/Total) | BO3 Full Rate | BO5 (Full/Total) | BO5 Full Rate |")
lines.append("|------|------------------|---------------|------------------|---------------|")

for team, s in sorted(stats.items()):
    bo3_rate = f"{s['bo3_full'] / s['bo3_total']:.2%}" if s["bo3_total"] else "-"
    bo5_rate = f"{s['bo5_full'] / s['bo5_total']:.2%}" if s["bo5_total"] else "-"

    lines.append(
        f"| {team} | "
        f"{s['bo3_full']}/{s['bo3_total']} | {bo3_rate} | "
        f"{s['bo5_full']}/{s['bo5_total']} | {bo5_rate} |"
    )

OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")

print(f"Updated {OUTPUT_MD}")
