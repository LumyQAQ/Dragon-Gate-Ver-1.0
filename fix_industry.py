import akshare as ak
import pandas as pd
import sqlite3
import time
from tqdm import tqdm

DB_PATH = "A_share_data.db"


def fix_industry():
    conn = sqlite3.connect(DB_PATH)
    print("开始连接东方财富服务器获取行业板块...")

    try:
        industry_df = ak.stock_board_industry_name_em()
        industry_names = industry_df['板块名称'].tolist()
        print(f"✅ 成功获取到 {len(industry_names)} 个行业板块目录。")
    except Exception as e:
        print(f"❌ 获取行业目录失败，可能是网络或接口问题: {e}")
        return

    all_cons = []
    # 遍历每个行业抓取成分股，加上进度条
    for name in tqdm(industry_names, desc="正在温柔地抓取成分股 (防封禁)"):
        try:
            cons_df = ak.stock_board_industry_cons_em(symbol=name)
            cons_df = cons_df[['代码', '名称']].copy()
            cons_df['行业名称'] = name
            all_cons.append(cons_df)

            # 核心魔法：每次抓取完停顿 0.5 秒，模拟真人点击，防止被东方财富拉黑 IP
            time.sleep(0.5)
        except Exception as e:
            print(f"\n⚠️ 抓取 [{name}] 板块报错被拦截: {e}")

    if all_cons:
        final_df = pd.concat(all_cons, ignore_index=True)
        # 写入数据库
        final_df.to_sql('stock_industry_temp', conn, if_exists='replace', index=False)
        conn.execute("INSERT OR REPLACE INTO stock_industry SELECT * FROM stock_industry_temp")
        conn.execute("DROP TABLE stock_industry_temp")
        conn.commit()
        print(f"\n🎉 完美修复！成功将 {len(final_df)} 条行业与股票的映射关系写入数据库！")
    else:
        print("\n❌ 抓取全部失败，如果全屏报错，可能需要更换网络或连接手机热点重试。")

    conn.close()


if __name__ == "__main__":
    fix_industry()