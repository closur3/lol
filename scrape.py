import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path

# ================== 赛事配置 ==================
TOURNAMENTS = [
    {
        "slug": "2026-lck-cup",
        "title": "2026 LCK Cup,
        "url": "https://gol.gg/tournament/tournament-matchlist/LCK%20Cup%202026/",
    },
    {
        "slug": "2026-lpl-split-1",
        "title": "2026 LPL Split 1",
        "url": "https://gol.gg/tournament/tournament-matchlist/LPL%202026%20Split%201/",
    },
]
# ==============================================


def scrape_tournament(title: str, url: str, output_md: Path):
    resp = requests.get(url, timeout=15)
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

        # 未完场比赛通常没有合法比分
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

    # ===== 输出 Markdown =====
    lines = []
    lines.append(f"# {title} – BO3 / BO5 打满率\n")
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

    output_md.write_text("\n".join(lines), encoding="utf-8")


def main():
    output_dir = Path("tournaments")
    output_dir.mkdir(exist_ok=True)

    for t in TOURNAMENTS:
        output_md = output_dir / f"{t['slug']}.md"
        scrape_tournament(
            title=t["title"],
            url=t["url"],
            output_md=output_md,
        )
        print(f"Updated {output_md}")


if __name__ == "__main__":
    main()
