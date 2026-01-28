import requests
import json
from datetime import datetime

def probe_global_latest():
    print("🌍 正在扫描 Leaguepedia 最近录入的比赛数据 (不分战队)...")
    
    url = "https://lol.fandom.com/api.php"
    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": "MatchSchedule",
        "fields": "OverviewPage, Team1, Team2, Score1, Score2, DateTime_UTC, Winner",
        # 只要是 2026-01-10 之后的比赛都拿出来看看
        "where": "DateTime_UTC >= '2026-01-10' AND Score1 IS NOT NULL", 
        "order_by": "DateTime_UTC DESC",
        "limit": 10
    }
    
    try:
        response = requests.get(url, params=params, headers={'User-Agent': 'ProbeBot/1.0'}, timeout=15)
        data = response.json()
        
        matches = data.get("cargoquery", [])
        if not matches:
            print("❌ 依然没有抓到数据。这说明可能是 where 条件的时间或者字段名有问题。")
            print("尝试移除 'Score1 IS NOT NULL' 再试一次...")
            return

        print(f"✅ 成功抓取到 {len(matches)} 条最近比赛记录！")
        print("请仔细对比下表中的【OverviewPage】和【Team Name】：")
        print("=" * 100)
        print(f"{'Time (UTC)':<18} | {'OverviewPage (复制这个到配置里)':<40} | {'Team1'}")
        print("-" * 100)
        
        for item in matches:
            m = item["title"]
            print(f"{m.get('DateTime_UTC', '')[:16]:<18} | {m.get('OverviewPage', ''):<40} | {m.get('Team1', '')}")
            
        print("=" * 100)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_global_latest()
