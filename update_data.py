import os

if os.getenv("DRAGON_GATE_CLEAR_PROXY") == "1":
    for proxy_key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ[proxy_key] = ""

import akshare as ak
import pandas as pd
import sqlite3
import datetime
import traceback

from config import DB_PATH, RRG_CSV_PATH


def rolling_update(rebuild_rrg=True):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("🚀 启动终极防弹版：正在通过【新浪财经】接口获取今日收盘数据...")
        df_today = ak.stock_zh_a_spot()

        if df_today is None or df_today.empty:
            print("❌ 获取到的数据为空，请稍后重试。")
            return

        print(f"✅ 成功连通新浪服务器，顺利拉取 {len(df_today)} 只股票数据！")
        today_str = datetime.datetime.now().strftime('%Y-%m-%d')

        # 1. 提取纯 6 位数字代码
        df_today['代码'] = df_today['代码'].astype(str).str.extract(r'(\d{6})')[0]

        # 2. 筛选所需列并重命名，尽量保留策略计算需要的 OHLCV 字段
        df_to_save = df_today[['代码', '今开', '最新价', '最高', '最低', '成交量', '成交额', '涨跌幅', '涨跌额', '昨收']].copy()
        df_to_save.rename(columns={'今开': '开盘', '最新价': '收盘'}, inplace=True)
        df_to_save['日期'] = today_str

        # 3. 强制转换数据类型
        for col in ['开盘', '收盘', '最高', '最低', '成交量', '成交额', '涨跌幅', '涨跌额', '昨收']:
            df_to_save[col] = pd.to_numeric(df_to_save[col], errors='coerce')
        df_to_save['振幅'] = ((df_to_save['最高'] - df_to_save['最低']) / df_to_save['昨收'] * 100).where(
            df_to_save['昨收'] != 0
        )
        df_to_save['换手率'] = pd.NA
        df_to_save = df_to_save[
            ['代码', '日期', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '振幅', '涨跌幅', '涨跌额', '换手率']
        ]
        df_to_save.dropna(subset=['代码', '收盘'], inplace=True)

        # 4. 清理今天可能残留的脏数据
        cursor.execute("DELETE FROM stock_daily WHERE 日期 = ?", (today_str,))
        conn.commit()

        # 5. 写入数据库
        print("⏳ 正在将清洗后的数据写入数据库...")
        df_to_save.to_sql('stock_daily', conn, if_exists='append', index=False)
        print(f"✅ 【{today_str}】行情数据已完美追加入库！")

        # 6. 滚动清理
        print("🧹 正在执行数据库 60 天滚动清理...")
        keep_days = 60
        cursor.execute(f"""
            DELETE FROM stock_daily 
            WHERE 日期 NOT IN (
                SELECT DISTINCT 日期 FROM stock_daily 
                ORDER BY 日期 DESC LIMIT {keep_days}
            )
        """)
        conn.commit()
        print(f"✨ 数据库体检完成，当前仅保留最近 {keep_days} 个交易日的精华数据。")

        if rebuild_rrg:
            print("📈 正在重算板块 RRG 坐标 CSV...")
            from strategy_engine import build_rrg_snapshot

            result_df = build_rrg_snapshot(db_path=DB_PATH, csv_path=RRG_CSV_PATH)
            if result_df.empty:
                print("⚠️ RRG 坐标未生成：数据库历史数据不足或行业映射为空。")
            else:
                latest_date = result_df['日期'].max()
                print(f"✅ RRG 坐标已更新至 {latest_date}，写入 {RRG_CSV_PATH}。")

    except Exception as e:
        print(f"\n❌ 更新失败！遇到了底层错误。详细雷达日志如下：")
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    rolling_update()
