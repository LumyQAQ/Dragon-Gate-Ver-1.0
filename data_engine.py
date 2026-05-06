import akshare as ak
import pandas as pd
import sqlite3
import os
from datetime import datetime, timedelta
from tqdm import tqdm


# 数据库文件路径（会自动在当前目录生成）
DB_PATH = "A_share_data.db"


def get_db_connection():
    """获取数据库连接并初始化表结构"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 创建股票日线数据表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_daily (
            代码 TEXT,
            日期 TEXT,
            开盘 REAL,
            收盘 REAL,
            最高 REAL,
            最低 REAL,
            成交量 REAL,
            成交额 REAL,
            振幅 REAL,
            涨跌幅 REAL,
            涨跌额 REAL,
            换手率 REAL,
            PRIMARY KEY (代码, 日期)
        )
    ''')
    # 创建行业映射表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_industry (
            行业名称 TEXT,
            代码 TEXT,
            名称 TEXT,
            PRIMARY KEY (行业名称, 代码)
        )
    ''')
    conn.commit()
    return conn


def update_industry_mapping(conn):
    """更新：东方财富一级行业与股票的映射关系"""
    print("正在更新行业映射表...")
    # 获取所有行业板块
    industry_df = ak.stock_board_industry_name_em()
    industry_names = industry_df['板块名称'].tolist()

    all_cons = []
    for name in tqdm(industry_names, desc="抓取行业成分股"):
        try:
            # 获取该行业下的所有成分股
            cons_df = ak.stock_board_industry_cons_em(symbol=name)
            cons_df = cons_df[['代码', '名称']].copy()
            cons_df['行业名称'] = name
            all_cons.append(cons_df)
        except Exception as e:
            continue

    final_df = pd.concat(all_cons, ignore_index=True)

    # 写入数据库 (replace 覆盖旧映射)
    final_df.to_sql('stock_industry_temp', conn, if_exists='replace', index=False)
    conn.execute("INSERT OR REPLACE INTO stock_industry SELECT * FROM stock_industry_temp")
    conn.execute("DROP TABLE stock_industry_temp")
    conn.commit()
    print("✅ 行业映射表更新完成！")


def update_daily_kline(conn, init_start_date="20240101"):
    """增量更新：全市场 A 股日线数据 (前复权)"""
    print("正在获取全市场有效股票代码...")
    # 获取实时行情表（仅用作获取最新的有效代码列表）
    spot_df = ak.stock_zh_a_spot_em()
    codes = spot_df['代码'].astype(str)
    # 过滤：只保留沪深主板 (60, 00) 和 创业板/科创板 (300, 688)
    valid_codes = codes[codes.str.match(r'^(00|300|60|688)\d{4}$')]

    today_str = datetime.now().strftime("%Y%m%d")

    for code in tqdm(valid_codes, desc="更新日线数据"):
        # 查询该股票在数据库中最新的一天
        query = f"SELECT MAX(日期) FROM stock_daily WHERE 代码='{code}'"
        max_date_df = pd.read_sql(query, conn)
        max_date = max_date_df.iloc[0, 0]

        # 决定抓取的起始日期
        fetch_start = init_start_date
        if max_date:
            # 如果数据库已有记录，从最新日期的下一天开始抓（增量更新）
            # 格式转换: "2024-05-01" -> "20240502"
            next_day = datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)
            fetch_start = next_day.strftime("%Y%m%d")

        if fetch_start > today_str:
            continue  # 如果最新日期已经是今天或未来，跳过

        try:
            # 核心：使用 qfq(前复权) 获取数据，保证量化计算的连续性
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=fetch_start, end_date=today_str,
                                    adjust="qfq")
            if not df.empty:
                df['代码'] = code
                # 将数据写入临时表，然后使用 INSERT OR IGNORE 避免主键冲突
                df.to_sql('temp_daily', conn, if_exists='replace', index=False)
                conn.execute("""
                    INSERT OR IGNORE INTO stock_daily (日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率, 代码)
                    SELECT 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率, 代码 FROM temp_daily
                """)
                conn.commit()
        except Exception as e:
            # 某些停牌或退市股票可能会报错，直接跳过
            pass


if __name__ == "__main__":
    connection = get_db_connection()

    # 1. 更新行业映射（成分股变化不大，平时可注释掉，每月跑一次即可）
    update_industry_mapping(connection)

    # 2. 更新全市场日线（首次运行需要大概半小时到一小时，以后每天只需几分钟）
    print("开始更新全市场K线数据...")
    update_daily_kline(connection, init_start_date="20240101")  # 默认回溯到2024年初

    print("🎉 你的本地金融数据池已就绪！")
    connection.close()