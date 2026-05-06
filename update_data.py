import os

os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['all_proxy'] = ''

import akshare as ak
import pandas as pd
import sqlite3
import datetime
import traceback


def rolling_update():
    db_path = "./sample_data.db"
    conn = sqlite3.connect(db_path)
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

        # 2. 筛选所需列并重命名（🚨 关键修复：去掉了 '名称' 列，完美适配你的数据库）
        df_to_save = df_today[['代码', '最新价', '涨跌幅', '成交额']].copy()
        df_to_save.rename(columns={'最新价': '收盘'}, inplace=True)
        df_to_save['日期'] = today_str

        # 3. 强制转换数据类型
        df_to_save['收盘'] = pd.to_numeric(df_to_save['收盘'], errors='coerce')
        df_to_save['涨跌幅'] = pd.to_numeric(df_to_save['涨跌幅'], errors='coerce')
        df_to_save['成交额'] = pd.to_numeric(df_to_save['成交额'], errors='coerce')
        df_to_save.dropna(subset=['代码', '收盘'], inplace=True)

        # 4. 清理今天可能残留的脏数据
        cursor.execute(f"DELETE FROM stock_daily WHERE 日期 = '{today_str}'")
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

    except Exception as e:
        print(f"\n❌ 更新失败！遇到了底层错误。详细雷达日志如下：")
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    rolling_update()