import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')  # 屏蔽 pandas 的一些无关警告

# 数据库路径
DB_PATH = "A_share_data.db"


def clean_stock_code(series):
    """最强股票代码清洗器：对付整数、浮点数、带后缀的乱码"""
    s = series.astype(str)
    s = s.str.replace(r'\.0$', '', regex=True)  # 干掉浮点数的 .0 (例如 1.0 -> 1)
    s = s.str.replace(r'\D', '', regex=True)  # 干掉所有英文字母和符号
    return s.str.zfill(6)  # 补齐 6 位 (1 -> 000001)


def load_and_merge_data(days_lookback=60):
    conn = sqlite3.connect(DB_PATH)
    print("🔍 正在启动数据体检与清洗...")

    daily_count = pd.read_sql("SELECT COUNT(*) FROM stock_daily", conn).iloc[0, 0]
    ind_count = pd.read_sql("SELECT COUNT(*) FROM stock_industry", conn).iloc[0, 0]
    print(f"👉 诊断1: 数据库拥有 K线 [{daily_count}] 条, 行业 [{ind_count}] 条")

    if daily_count == 0 or ind_count == 0:
        print("❌ 数据库缺失，请重新运行数据引擎。")
        conn.close()
        return pd.DataFrame()

    print("正在提取最近的日线数据...")
    # 取出最近数据
    daily_df = pd.read_sql(f"SELECT * FROM stock_daily ORDER BY 日期 DESC LIMIT 600000", conn)
    daily_df['日期'] = pd.to_datetime(daily_df['日期'])
    recent_dates = daily_df['日期'].sort_values().unique()[-days_lookback:]
    daily_df = daily_df[daily_df['日期'].isin(recent_dates)]

    industry_df = pd.read_sql("SELECT * FROM stock_industry", conn)
    conn.close()

    # 强制将数值列转换为数值类型，防止字符串计算报错
    for col in ['收盘', '成交量', '换手率', '涨跌幅']:
        daily_df[col] = pd.to_numeric(daily_df[col], errors='coerce')

    # ==========================================
    # 🔥 核心物理清洗 🔥
    # ==========================================
    daily_df['代码'] = clean_stock_code(daily_df['代码'])
    industry_df['代码'] = clean_stock_code(industry_df['代码'])

    # 过滤掉依然是空壳的数据
    daily_df = daily_df[daily_df['代码'] != '000000']
    industry_df = industry_df[industry_df['代码'] != '000000']

    print(f"👉 抽查 K线代码洗后样本: {daily_df['代码'].unique()[:3].tolist()}")
    print(f"👉 抽查 行业代码洗后样本: {industry_df['代码'].unique()[:3].tolist()}")

    # 合并数据
    merged_df = pd.merge(daily_df, industry_df, on='代码', how='inner')
    print(f"👉 诊断2: 完美匹配合并出 [{len(merged_df)}] 条有效日线数据！")

    if len(merged_df) == 0:
        print("❌ 致命错误: 还是没有匹配上，请检查上面的抽查样本。")

    return merged_df


def calculate_custom_factors(df):
    if df.empty: return df
    print("正在计算个股技术形态因子 (量价突破与缩量)...")
    df = df.sort_values(['代码', '日期'])

    # 核心形态量化逻辑
    df['is_breakout'] = df['涨跌幅'] >= 8.0
    df['vol_shrink'] = df.groupby('代码')['成交量'].diff() < 0
    df['recent_breakout'] = df.groupby('代码')['is_breakout'].rolling(window=5, min_periods=1).max().reset_index(
        level=0, drop=True)
    df['breakout_and_shrink'] = (df['recent_breakout'] == 1) & (df['vol_shrink'])
    df['5d_return'] = df.groupby('代码')['收盘'].pct_change(periods=5) * 100
    df['5d_turnover'] = df.groupby('代码')['换手率'].rolling(window=5, min_periods=1).mean().reset_index(level=0,
                                                                                                         drop=True)
    return df


def build_sector_rrg_data(df, rs_window=20, mom_window=5, smooth_window=3):
    if df.empty: return pd.DataFrame()
    print("正在聚合板块轮动坐标 (计算 X轴相对强弱 和 Y轴动量)...")
    sector_daily = df.groupby(['日期', '行业名称'])['涨跌幅'].mean().reset_index()
    sector_pivot = sector_daily.pivot(index='日期', columns='行业名称', values='涨跌幅').fillna(0)
    sector_index = (1 + sector_pivot / 100).cumprod() * 1000
    benchmark_index = sector_index.mean(axis=1)
    bench_return = (benchmark_index / benchmark_index.shift(rs_window)) - 1

    rrg_results = []
    for sector in sector_index.columns:
        sec_return = (sector_index[sector] / sector_index[sector].shift(rs_window)) - 1
        raw_rs = sec_return - bench_return
        smooth_rs = raw_rs.rolling(window=smooth_window).mean()
        raw_mom = smooth_rs - smooth_rs.shift(mom_window)
        smooth_mom = raw_mom.rolling(window=smooth_window).mean()

        latest_date = df['日期'].max()
        today_stocks = df[(df['行业名称'] == sector) & (df['日期'] == latest_date)]

        if len(today_stocks) > 0:
            # 放宽一点限制：板块内满足“近期突破缩量”并且“5日均换手率>2%”的个股占比
            active_breakout_count = len(
                today_stocks[(today_stocks['breakout_and_shrink'] == True) & (today_stocks['5d_turnover'] > 2.0)])
            breakout_score = (active_breakout_count / len(today_stocks)) * 100
            avg_5d_gain = today_stocks['5d_return'].mean()
        else:
            breakout_score = 0
            avg_5d_gain = 0

        rs_val = smooth_rs.iloc[-1] if not pd.isna(smooth_rs.iloc[-1]) else 0
        mom_val = smooth_mom.iloc[-1] if not pd.isna(smooth_mom.iloc[-1]) else 0

        rrg_results.append({
            '行业名称': sector,
            '日期': latest_date.date() if pd.notnull(latest_date) else None,
            '相对强弱_X': round(rs_val * 100, 2),
            '动量_Y': round(mom_val * 100, 2),
            '突破动能得分_气泡大小': round(breakout_score, 2),
            '板块5日平均涨幅': round(avg_5d_gain, 2)
        })
    return pd.DataFrame(rrg_results).dropna()


if __name__ == "__main__":
    df = load_and_merge_data(days_lookback=60)

    if df.empty:
        print("\n🛑 程序终止。")
    else:
        df = calculate_custom_factors(df)
        result_df = build_sector_rrg_data(df)

        if result_df.empty:
            print("\n🛑 数据量太少，请检查历史天数。")
        else:
            # 排序：优先看动量大且包含强力异动个股的板块
            result_df = result_df.sort_values(by=['突破动能得分_气泡大小', '动量_Y'], ascending=[False, False])
            print("\n✅ 策略计算完成！今日【量价齐升突破】板块追踪榜单 (前 10 名):")
            print("-" * 75)
            print(result_df.head(10).to_string(index=False))
            print("-" * 75)
            result_df.to_csv("rrg_daily_result.csv", index=False)
            print("\n💾 最终坐标数据已保存至 rrg_daily_result.csv！")