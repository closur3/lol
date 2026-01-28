import requests
import json

def probe_tournament_name(team_code, year="2026"):
    print(f"🔍 正在探测 {team_code} 在 {year} 年的比赛记录...")
    
    url = "https://lol.fandom.com/api.php"
    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": "MatchSchedule",
        "fields": "OverviewPage, Tournament, DateTime_UTC, Team1, Team2, Winner",
        # 查找 Team1 是该队伍 且 时间在 2026年之后 的比赛
        "where": f"(Team1='{team_code}' OR Team2='{team_code}') AND DateTime_UTC >= '{year}-01-01'",
        "order_by": "DateTime_UTC DESC",
        "limit": 5
    }
    
    try:
        response = requests.get(url, params=params, headers={'User-Agent': 'DebugBot/1.0'}, timeout=10)
        data = response.json()
        
        matches = data.get("cargoquery", [])
        if not matches:
            print(f"❌ 未找到 {team_code} 在 {year} 的任何比赛数据。")
            print("   可能原因：")
            print("   1. 该队伍今年还没打比赛。")
            print("   2. Wiki 还没录入数据。")
            return

        print(f"✅ 找到 {len(matches)} 场比赛。以下是 API 返回的关键字段：")
        print("-" * 60)
        print(f"{'Date':<20} | {'OverviewPage (复制这个!)':<30} | {'Tournament'}")
        print("-" * 60)
        
        found_names = set()
        for item in matches:
            m = item["title"]
            date = m.get("DateTime_UTC", "N/A")
            overview = m.get("OverviewPage", "Unknown")
            tourney = m.get("Tournament", "Unknown")
            print(f"{date:<20} | {overview:<30} | {tourney}")
            found_names.add(overview)
            
        print("-" * 60)
        print("💡 建议在配置中使用的名称:")
        for name in found_names:
            print(f'   "overview_page": "{name}"')

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # 探测 LPL (用 BLG 代表)
    probe_tournament_name("BLG")
    print("\n" + "="*60 + "\n")
    # 探测 LCK (用 T1 代表)
    probe_tournament_name("T1")
