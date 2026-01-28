import requests
import json

def find_exact_league_names():
    print("🔍 正在数据库中搜索 LPL 和 LCK 的 2026 赛事名称...")
    
    url = "https://lol.fandom.com/api.php"
    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": "MatchSchedule",
        "fields": "OverviewPage",
        # 核心逻辑：只查名字里带 LPL/LCK 和 2026 的，且必须是正赛（排除资格赛Qualifier，除非你需要）
        "where": "(OverviewPage LIKE '%LPL%2026%' OR OverviewPage LIKE '%LCK%2026%') AND OverviewPage NOT LIKE '%Qualifi%'",
        "group_by": "OverviewPage", # 去重，只看名字
        "limit": 20
    }
    
    try:
        response = requests.get(url, params=params, headers={'User-Agent': 'LeagueFinder/1.0'}, timeout=15)
        data = response.json()
        
        matches = data.get("cargoquery", [])
        if not matches:
            print("❌ 没搜到。这很奇怪，可能是 Wiki 目前还没建立 2026 正赛的条目（或者名字完全变了）。")
            return

        print("✅ 找到了！请直接复制下面的名字：")
        print("=" * 60)
        for item in matches:
            print(f'"{item["title"]["OverviewPage"]}"')
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_exact_league_names()
