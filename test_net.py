import os
import sys
# 清空幽灵代理
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['all_proxy'] = ''

print(f"🐍 当前使用的 Python 路径: {sys.executable}")
print("====================================")

try:
    import requests
    print("⏳ 1. 正在测试 Python 访问基础互联网 (百度)...")
    res = requests.get("https://www.baidu.com", timeout=5)
    print(f"✅ 基础网络通畅！(状态码: {res.status_code})")
except Exception as e:
    print(f"❌ 基础网络彻底瘫痪，报错信息: {e}")

print("====================================")

try:
    import akshare as ak
    print("⏳ 2. 正在测试【新浪财经】(全网最不封IP的接口)...")
    df = ak.stock_zh_a_spot() # 这是新浪的接口，极其稳定
    print(f"✅ 新浪财经连通！成功获取到 {len(df)} 只股票数据。")
except Exception as e:
    print(f"❌ 新浪财经连接失败，报错信息: {e}")

print("====================================")