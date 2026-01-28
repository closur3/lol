import requests
import json

def probe_correct_names():
    print("🚀 开始探测 Leaguepedia 真实数据 (修正字段版)...")
    
    url = "https://lol.fandom.com/api.php"
    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": "MatchSchedule",
        # 修正点：使用正确的字段名 Team1Score, Team2Score
        "fields": "OverviewPage, DateTime_UTC, Team1, Team2, Team1Score, Team2Score",
        # 只要是今年起的比赛，不管打没打完都显示出来
        "where": "DateTime_UTC >= '2026-01-01'",
        "order_by": "DateTime_UTC DESC",
        "limit": 30
    }
    
    try:
        response = requests.get(url, params=params, headers={'User-Agent': 'FixBot/1.0'}, timeout=15)
        data = response.json()
        
        # 调试：如果返回错误信息，直接打印出来
        if "error" in data:
            print(f"❌ API 报错: {data['error']}")
            return

        matches = data.get("cargoquery", [])
        if not matches:
            print("❌ 依然没数据。请检查你的网络能否访问 lol.fandom.com")
            return

        print(f"✅ 成功连接！抓到了 {len(matches)} 条记录。")
        print("请直接复制下表中【OverviewPage】列的内容到你的配置文件里：")
        print("=" * 100)
        print(f"{'Time (UTC)':<18} | {'OverviewPage (复制这个!)':<40} | {'Match'}")
        print("-" * 100)
        
        unique_pages = set()
        for item in matches:
            m = item["title"]
            time_str = m.get('DateTime_UTC', '')[:16]
            page = m.get('OverviewPage', 'N/A')
            t1 = m.get('Team1', '?')
            t2 = m.get('Team2', '?')
            print(f"{time_str:<18} | {page:<40} | {t1} vs {t2}")
            unique_pages.add(page)
            
        print("=" * 100)
        print("\n💡 你的 TOURNAMENTS 配置应该长这样：")
        print("TOURNAMENTS = [")
        for p in unique_pages:
            if "LPL" in p or "LCK" in p:
                slug = p.lower().replace("/", "-").replace(" ", "-")
                print(f'    {{ "slug": "{slug}", "title": "{p}", "overview_page": "{p}" }},')
        print("]")

    except Exception as e:
        print(f"❌ Python 报错: {e}")

if __name__ == "__main__":
    probe_correct_names()
