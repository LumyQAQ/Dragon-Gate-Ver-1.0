import akshare as ak
import pandas as pd
import sqlite3
import datetime


def rolling_update():
    db_path = "./sample_data.db"
    conn = sqlite3.connect(db_path)

    try:
        # 1. 抓取今日行情
        print("🚀 正在抓取今日收盘数据...")
        df_today = ak.stock_zh_a_spot_em()
        today_str = datetime.datetime.now().strftime('%Y-%m-%d')

        # 2. 格式化数据并存入 sample_data.db
        # 这里需要匹配你原有的表结构 (代码, 日期, 收盘, 涨跌幅, 成交额)
        df_to_save = df_today[['代码', '名称', '最新价', '涨跌幅', '成交额']].copy()
        df_to_save['日期'] = today_str
        df_to_save.rename(columns={'最新价': '收盘'}, inplace=True)

        df_to_save.to_sql('stock_daily', conn, if_exists='append', index=False)
        print(f"✅ {today_str} 数据已追加入库")

        # 3. 🔥 核心逻辑：保持“瘦身”，只保留最近 60 天的数据
        # 这样你的数据库永远不会超过 100MB
        print("🧹 正在执行滚动清理...")
        keep_days = 60
        cursor = conn.cursor()
        cursor.execute(f"""
            DELETE FROM stock_daily 
            WHERE 日期 NOT IN (
                SELECT DISTINCT 日期 FROM stock_daily 
                ORDER BY 日期 DESC LIMIT {keep_days}
            )
        """)
        conn.commit()
        print(f"✨ 清理完成，仅保留最近 {keep_days} 个交易日数据。")

    except Exception as e:
        print(f"❌ 更新失败: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    rolling_update()