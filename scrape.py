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
INDEX_FILE = Path("index.html")


def rate(n, d):
    return n / d if d > 0 else None


def pct(r):
    return f"{r*100:.1f}%" if r is not None else "-"


def color_by_rate(r):
    if r is None:
        return "#eeeeee"
    # 从绿到红，绿色胜率高，红色胜率低
    red = int(255 * r)
    green = int(255 * (1 - r))
    return f"rgb({red},{green},200)"


def scrape_tournament(t):
    resp = requests.get(t["url"], timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    stats = defaultdict(lambda: {
        "bo3_full": 0, "bo3_total": 0,
        "bo5_full": 0, "bo5_total": 0,
        "match_win": 0, "match_total": 0,
        "match_scores": [],
        "game_win": 0, "game_total": 0,
        "game_scores": [],
        "streak_w": 0, "streak_l": 0,
        "streak_done": False,
    })

    for row in soup.select("table tr"):
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        t1 = tds[1].get_text(strip=True)
        t2 = tds[3].get_text(strip=True)
        score = tds[2].get_text(strip=True)

        if "-" not in score:
            continue

        try:
            s1, s2 = map(int, score.split("-"))
        except ValueError:
            continue

        winner, loser = (t1, t2) if s1 > s2 else (t2, t1)

        # 大场比分
        stats[t1]["match_scores"].append(f"{s1}-{s2}")
        stats[t2]["match_scores"].append(f"{s2}-{s1}")

        # 大场统计
        for t_ in (t1, t2):
            stats[t_]["match_total"] += 1
        stats[winner]["match_win"] += 1

        # 小局比分
        for _ in range(s1):
            stats[t1]["game_scores"].append("W")
            stats[t2]["game_scores"].append("L")
        for _ in range(s2):
            stats[t1]["game_scores"].append("L")
            stats[t2]["game_scores"].append("W")

        # 小局统计
        stats[t1]["game_win"] += s1
        stats[t1]["game_total"] += s1 + s2
        stats[t2]["game_win"] += s2
        stats[t2]["game_total"] += s1 + s2

        max_s, min_s = max(s1, s2), min(s1, s2)

        # BO3 / BO5 打满
        if max_s == 2:
            for t_ in (t1, t2):
                stats[t_]["bo3_total"] += 1
            if min_s == 1:
                for t_ in (t1, t2):
                    stats[t_]["bo3_full"] += 1
        if max_s == 3:
            for t_ in (t1, t2):
                stats[t_]["bo5_total"] += 1
            if min_s == 2:
                for t_ in (t1, t2):
                    stats[t_]["bo5_full"] += 1

        # 当前连胜/连败
        if not stats[winner]["streak_done"]:
            if stats[winner]["streak_l"] > 0:
                stats[winner]["streak_done"] = True
            else:
                stats[winner]["streak_w"] += 1
        if not stats[loser]["streak_done"]:
            if stats[loser]["streak_w"] > 0:
                stats[loser]["streak_done"] = True
            else:
                stats[loser]["streak_l"] += 1

    # 输出备份 md
    OUTPUT_DIR.mkdir(exist_ok=True)
    md_file = OUTPUT_DIR / f"{t['slug']}.md"
    lines = [f"# {t['title']}\n"]
    lines.append("| Team | BO3 (Full/Total) | BO3 Rate | BO5 (Full/Total) | BO5 Rate | Match X-X | Match WR | Game X-X | Game WR | Streak |")
    lines.append("|------|------------------|----------|------------------|----------|-----------|----------|----------|---------|--------|")
    for team, s in sorted(stats.items(), key=lambda x: rate(x[1]["bo3_full"], x[1]["bo3_total"]) or 0):
        bo3_r = rate(s["bo3_full"], s["bo3_total"])
        bo5_r = rate(s["bo5_full"], s["bo5_total"])
        match_r = rate(s["match_win"], s["match_total"])
        game_r = rate(s["game_win"], s["game_total"])
        if s["streak_w"] > 0:
            streak = f"{s['streak_w']}W"
            streak_color = "lightgreen"
        elif s["streak_l"] > 0:
            streak = f"{s['streak_l']}L"
            streak_color = "salmon"
        else:
            streak = "-"
            streak_color = "#eee"

        lines.append(
            f"| {team} | "
            f"{s['bo3_full']}/{s['bo3_total']} | {pct(bo3_r)} | "
            f"{s['bo5_full']}/{s['bo5_total']} | {pct(bo5_r)} | "
            f"{', '.join(s['match_scores'])} | {pct(match_r)} | "
            f"{', '.join(s['game_scores'])} | {pct(game_r)} | "
            f"<span style='background:{streak_color}'>{streak}</span> |"
        )
    md_file.write_text("\n".join(lines), encoding="utf-8")
    return stats


def build_index(all_data):
    html = """<html><head><meta charset="utf-8">
<title>LOL Tournament Stats</title>
<style>
table{border-collapse:collapse}
th,td{border:1px solid #ccc;padding:6px 10px;text-align:center}
</style>
</head><body>
<h1>LOL Tournament Stats</h1>
"""
    for t in TOURNAMENTS:
        stats = all_data[t["slug"]]
        # 按 BO3 rate 升序
        rows = sorted(stats.items(), key=lambda x: rate(x[1]["bo3_full"], x[1]["bo3_total"]) or 0)
        html += f"<h2>{t['title']}</h2><table>"
        html += "<tr><th>Team</th><th>BO3 (Full/Total)</th><th>BO3 Rate</th><th>BO5 (Full/Total)</th><th>BO5 Rate</th>"
        html += "<th>Match X-X</th><th>Match WR</th><th>Game X-X</th><th>Game WR</th><th>Streak</th></tr>"
        for team, s in rows:
            bo3_r = rate(s["bo3_full"], s["bo3_total"])
            bo5_r = rate(s["bo5_full"], s["bo5_total"])
            match_r = rate(s["match_win"], s["match_total"])
            game_r = rate(s["game_win"], s["game_total"])
            if s["streak_w"] > 0:
                streak = f"{s['streak_w']}W"
                streak_color = "lightgreen"
            elif s["streak_l"] > 0:
                streak = f"{s['streak_l']}L"
                streak_color = "salmon"
            else:
                streak = "-"
                streak_color = "#eee"
            html += "<tr>"
            html += f"<td>{team}</td>"
            html += f"<td>{s['bo3_full']}/{s['bo3_total']}</td>"
            html += f"<td style='background:{color_by_rate(bo3_r)}'>{pct(bo3_r)}</td>"
            html += f"<td>{s['bo5_full']}/{s['bo5_total']}</td>"
            html += f"<td style='background:{color_by_rate(bo5_r)}'>{pct(bo5_r)}</td>"
            html += f"<td>{', '.join(s['match_scores'])}</td>"
            html += f"<td>{pct(match_r)}</td>"
            html += f"<td>{', '.join(s['game_scores'])}</td>"
            html += f"<td>{pct(game_r)}</td>"
            html += f"<td style='background:{streak_color}'>{streak}</td>"
            html += "</tr>"
        html += "</table><br>"
    html += "</body></html>"
    INDEX_FILE.write_text(html, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_data = {}
    for t in TOURNAMENTS:
        stats = scrape_tournament(t)
        all_data[t["slug"]] = stats
    build_index(all_data)
    print("index.html generated")


if __name__ == "__main__":
    main()
