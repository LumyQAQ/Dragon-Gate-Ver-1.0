import sqlite3
import pandas as pd
import os


def create_sample_db():
    # ⚠️ 请确保这里的大数据库文件名与你本地的文件名完全一致
    source_db_path = "A_share_data.db"

    # 将要生成的小数据库名称
    target_db_path = "sample_data.db"

    if not os.path.exists(source_db_path):
        print(f"❌ 找不到源数据库，请检查路径或文件名: {source_db_path}")
        return

    print("🔌 正在连接实盘大数据库...")
    conn_src = sqlite3.connect(source_db_path)

    try:
        # 1. 抓取最近的 10 个交易日
        print("📅 正在定位最近的 10 个交易日...")
        dates_df = pd.read_sql("SELECT DISTINCT 日期 FROM stock_daily ORDER BY 日期 DESC LIMIT 45", conn_src)
        recent_dates = dates_df['日期'].tolist()

        if not recent_dates:
            print("❌ 源数据库中没有找到任何日期数据！")
            return

        print(f"   => 成功截取日期范围: {recent_dates[-1]} 至 {recent_dates[0]}")

        # 2. 提取这 10 天的全市场 K 线数据
        print("⏳ 正在抽取这 10 天的日线切片数据...")
        placeholders = ','.join(['?'] * len(recent_dates))
        daily_query = f"SELECT * FROM stock_daily WHERE 日期 IN ({placeholders})"
        daily_df = pd.read_sql(daily_query, conn_src, params=recent_dates)
        print(f"   => 成功抽取 {len(daily_df)} 条 K线数据。")

        # 3. 提取完整的行业映射表
        print("🏷️ 正在抽取全市场行业映射数据...")
        ind_df = pd.read_sql("SELECT * FROM stock_industry", conn_src)
        print(f"   => 成功抽取 {len(ind_df)} 条行业记录。")

    except Exception as e:
        print(f"❌ 读取数据时发生错误: {e}")
        return
    finally:
        conn_src.close()

    # 4. 写入全新的开源迷你数据库
    print(f"💾 正在生成云端专用迷你数据库 {target_db_path} ...")
    try:
        conn_tgt = sqlite3.connect(target_db_path)
        daily_df.to_sql('stock_daily', conn_tgt, if_exists='replace', index=False)
        ind_df.to_sql('stock_industry', conn_tgt, if_exists='replace', index=False)
        conn_tgt.close()

        file_size = os.path.getsize(target_db_path) / (1024 * 1024)
        print("=========================================")
        print(f"✅ 瘦身完美收官！迷你数据库生成成功！")
        print(f"📦 文件大小约为: {file_size:.2f} MB")
        print("🎉 接下来请把这个 sample_data.db 拖进 GitHub 网页进行覆盖！")
        print("=========================================")
    except Exception as e:
        print(f"❌ 写入新数据库时发生错误: {e}")


if __name__ == "__main__":
    create_sample_db()
