import sqlite3
import pandas as pd

# 连接数据库
conn = sqlite3.connect("A_share_data.db")
df = pd.read_sql("SELECT * FROM stock_industry", conn)

print("🕵️ 案发现场还原：")
print(f"原本应该装数字的'代码'列，现在装的竟然是 -> 【{df['代码'].iloc[0]}】")

# 核心魔法：直接把表头顺序拨乱反正！
df.columns = ['代码', '名称', '行业名称']

print("\n🩹 修复之后：")
print(f"现在的'代码'列，装的是 -> 【{df['代码'].iloc[0]}】")
print(f"现在的'行业名称'列，装的是 -> 【{df['行业名称'].iloc[0]}】")

# 写回数据库，彻底覆盖掉那个错位的表
df.to_sql('stock_industry', conn, if_exists='replace', index=False)
print("\n✅ 行业表错位已永久修复！")

conn.close()