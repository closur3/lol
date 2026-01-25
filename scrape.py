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
        "streak_done": False,  # 当前 streak 是否已被截断
    })

    rows = soup.select("table tr")

    # gol.gg：新 → 旧（我们只统计“当前” streak）
    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        team1 = tds[1].get_text(strip=True)
        score = tds[2].get_text(strip=True)
        team2 = tds[3].get_text(strip=True)

        # 未完赛
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

        # ===== 当前连胜 / 连败（只从最近开始算） =====
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
    lines = []
    lines.append(f"# {title}\n")
    lines.append(
        "| Team | BO3 (Full/Total) | BO3 Rate | "
        "BO5 (Full/Total) | BO5 Rate | Streak |"
    )
    lines.append(
        "|------|------------------|----------|"
        "------------------|----------|----------------|"
    )

    for team, s in sorted(stats.items()):
        bo3_rate = f"{s['bo3_full']/s['bo3_total']:.2%}" if s["bo3_total"] else "-"
        bo5_rate = f"{s['bo5_full']/s['bo5_total']:.2%}" if s["bo5_total"] else "-"

        streak = (
            f"{s['current_win']}W" if s["current_win"] > 0 else
            f"{s['current_lose']}L" if s["current_lose"] > 0 else "-"
        )

        lines.append(
            f"| {team} | "
            f"{s['bo3_full']}/{s['bo3_total']} | {bo3_rate} | "
            f"{s['bo5_full']}/{s['bo5_total']} | {bo5_rate} | "
            f"{streak} |"
        )

    output_md.write_text("\n".join(lines), encoding="utf-8")


def build_readme():
    lines = []
    lines.append("# Tournament Summary\n")

    for t in TOURNAMENTS:
        md_file = OUTPUT_DIR / f"{t['slug']}.md"
        if not md_file.exists():
            continue

        lines.append(md_file.read_text(encoding="utf-8").strip())
        lines.append("\n---\n")

    README_FILE.write_text("\n".join(lines), encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1️⃣ 按 TOURNAMENTS 抓取并生成 md
    for t in TOURNAMENTS:
        output_md = OUTPUT_DIR / f"{t['slug']}.md"
        scrape_tournament(t["title"], t["url"], output_md)
        print(f"Updated {output_md}")

    # 2️⃣ 按 TOURNAMENTS 顺序合并 README
    build_readme()
    print("Updated README.md")


if __name__ == "__main__":
    main()
