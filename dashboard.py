import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import os

from config import DB_PATH, RRG_CSV_PATH

st.set_page_config(page_title="城门立木龙头战法观察图（仅沪深主板版）", layout="wide")
st.title("🐲 城门立木龙头战法观察图（仅沪深主板版）")

def clean_stock_code(series):
    s = series.astype(str).str.replace(r'\.0$', '', regex=True).str.replace(r'\D', '', regex=True)
    return s.str.zfill(6)


def file_signature(path):
    try:
        return (str(path), os.path.getmtime(path), os.path.getsize(path))
    except OSError:
        return (str(path), None, None)


# ==========================================
# 💾 数据引擎 1：横截面与微观穿透数据
# ==========================================
@st.cache_data
def load_cross_section_data(csv_signature=None, db_signature=None):
    csv_path = RRG_CSV_PATH
    db_path = DB_PATH

    df = pd.DataFrame()
    limit_up_df = pd.DataFrame(columns=['股票名称', '股票代码', '涨跌幅(%)', '所属板块', '成交额'])
    top10_5d_df = pd.DataFrame(columns=['排名', '股票名称', '股票代码', '5日涨幅(%)', '所属板块'])
    debug_log = {}

    # 1. 读 CSV 宏观数据
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
    else:
        debug_log["Error_CSV"] = "找不到 rrg_daily_result.csv"

    # 2. 读 DB 微观数据
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            daily_df = pd.DataFrame()
            ind_df = pd.DataFrame()
            dates_df = pd.read_sql("SELECT DISTINCT 日期 FROM stock_daily ORDER BY 日期 DESC LIMIT 5", conn)
            recent_dates = dates_df['日期'].tolist()

            if len(recent_dates) >= 1:
                placeholders = ','.join(['?'] * len(recent_dates))
                # 🛡️ 防弹衣 1：用 SELECT * 替代写死字段名，避免数据库结构微调报错
                daily_df = pd.read_sql(f"SELECT * FROM stock_daily WHERE 日期 IN ({placeholders})", conn, params=recent_dates)
                ind_df = pd.read_sql("SELECT * FROM stock_industry", conn)
            conn.close()

            if not daily_df.empty and not ind_df.empty:
                # 动态识别列名
                name_col_ind = '名称' if '名称' in ind_df.columns else ('股票名称' if '股票名称' in ind_df.columns else '代码')
                if name_col_ind != '股票名称':
                    ind_df.rename(columns={name_col_ind: '股票名称'}, inplace=True)

                close_col = '收盘' if '收盘' in daily_df.columns else ('最新价' if '最新价' in daily_df.columns else None)
                if close_col and close_col != '收盘':
                    daily_df.rename(columns={close_col: '收盘'}, inplace=True)

                daily_df['代码'], ind_df['代码'] = clean_stock_code(daily_df['代码']), clean_stock_code(ind_df['代码'])
                daily_df, ind_df = daily_df[daily_df['代码'] != '000000'], ind_df[ind_df['代码'] != '000000']

                daily_df['收盘'] = pd.to_numeric(daily_df.get('收盘', 0), errors='coerce')
                daily_df['涨跌幅'] = pd.to_numeric(daily_df.get('涨跌幅', 0), errors='coerce').fillna(0)
                daily_df['成交额'] = pd.to_numeric(daily_df.get('成交额', 0), errors='coerce').fillna(0)

                pivot_close = daily_df.pivot(index='代码', columns='日期', values='收盘')
                t0, t2, t4 = recent_dates[0], recent_dates[min(2, len(recent_dates)-1)], recent_dates[-1]

                ret_3d = ((pivot_close[t0] - pivot_close[t2]) / pivot_close[t2]) * 100
                ret_5d = ((pivot_close[t0] - pivot_close[t4]) / pivot_close[t4]) * 100

                t0_df = daily_df[daily_df['日期'] == t0].copy()
                t0_df['3日涨幅'], t0_df['5日涨幅'] = t0_df['代码'].map(ret_3d).fillna(0), t0_df['代码'].map(ret_5d).fillna(0)

                detail_df = pd.merge(t0_df, ind_df, on='代码', how='inner')
                name_col = '股票名称'

                limit_up_raw = detail_df[detail_df['涨跌幅'] >= 9.8].copy()
                if not limit_up_raw.empty:
                    limit_up_df = limit_up_raw[[name_col, '代码', '涨跌幅', '行业名称', '成交额']]
                    limit_up_df.columns = ['股票名称', '股票代码', '涨跌幅(%)', '所属板块', '成交额']
                    limit_up_df = limit_up_df.sort_values(by=['所属板块', '涨跌幅(%)'], ascending=[True, False]).reset_index(drop=True)

                top10_raw = detail_df.nlargest(10, '5日涨幅').copy()
                if not top10_raw.empty:
                    top10_5d_df = top10_raw[[name_col, '代码', '5日涨幅', '行业名称']]
                    top10_5d_df.columns = ['股票名称', '股票代码', '5日涨幅(%)', '所属板块']
                    top10_5d_df.reset_index(drop=True, inplace=True)
                    top10_5d_df.index = top10_5d_df.index + 1

                sector_info = []
                for sector, group in detail_df.groupby('行业名称'):
                    top1 = group.nlargest(5, '涨跌幅')
                    top3 = group.nlargest(5, '3日涨幅')
                    top5 = group.nlargest(5, '5日涨幅')
                    core3 = group.nlargest(3, '成交额')

                    sector_info.append({
                        '行业名称': sector,
                        '1日龙头': "、".join([f"{r[name_col]}({'+' if r['涨跌幅']>0 else ''}{r['涨跌幅']:.1f}%)" for _, r in top1.iterrows()]) or "-",
                        '3日龙头': "、".join([f"{r[name_col]}({'+' if r['3日涨幅']>0 else ''}{r['3日涨幅']:.1f}%)" for _, r in top3.iterrows()]) or "-",
                        '5日龙头': "、".join([f"{r[name_col]}({'+' if r['5日涨幅']>0 else ''}{r['5日涨幅']:.1f}%)" for _, r in top5.iterrows()]) or "-",
                        '核心中军': "、".join([f"{r[name_col]}" for _, r in core3.iterrows()]) or "-"
                    })

                info_df = pd.DataFrame(sector_info)
                df = pd.merge(df, info_df, on='行业名称', how='left').fillna("-")
        except Exception as e:
            debug_log['Error_DB'] = str(e)
    else:
        debug_log["Error_DB"] = "找不到 sample_data.db"
        
    return df, limit_up_df, top10_5d_df, debug_log

# ==========================================
# 💾 数据引擎 2：轨迹时光机 (自适应雷达版)
# ==========================================
@st.cache_data
def load_trajectory_data(days=45, db_signature=None):
    db_path = DB_PATH
    if not os.path.exists(db_path): return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(db_path)
        dates_query = f"SELECT DISTINCT 日期 FROM stock_daily ORDER BY 日期 DESC LIMIT {days}"
        recent_dates = pd.read_sql(dates_query, conn)['日期'].tolist()
        if not recent_dates: 
            conn.close()
            return pd.DataFrame()
        
        placeholders = ','.join(['?'] * len(recent_dates))
        daily_df = pd.read_sql(f"SELECT * FROM stock_daily WHERE 日期 IN ({placeholders})", conn, params=recent_dates)
        ind_df = pd.read_sql("SELECT * FROM stock_industry", conn)
        conn.close()

        daily_df['代码'] = clean_stock_code(daily_df['代码'])
        ind_df['代码'] = clean_stock_code(ind_df['代码'])
        df = pd.merge(daily_df, ind_df, on='代码', how='inner')
        df['涨跌幅'] = pd.to_numeric(df.get('涨跌幅', 0), errors='coerce').fillna(0)
        
        sector_daily = df.groupby(['日期', '行业名称'])['涨跌幅'].mean().reset_index()
        sector_pivot = sector_daily.pivot(index='日期', columns='行业名称', values='涨跌幅').fillna(0)
        
        sector_index = (1 + sector_pivot / 100).cumprod() * 1000
        bench_index = sector_index.mean(axis=1)
        
        # 🔥 核心魔法：自适应数据长度的动态窗口！
        available_days = len(sector_index)
        if available_days < 5:
            # 数据少于5天，确实无法算出动能，只能返回空
            return pd.DataFrame()
        elif available_days < 20:
            # 冷启动期 (比如只有10天数据)：极速微观窗口
            rs_window = max(1, available_days // 3)
            mom_window = max(1, available_days // 4)
            smooth_window = 1
        elif available_days < 35:
            # 数据中等：过渡期窗口
            rs_window, mom_window, smooth_window = 10, 3, 2
        else:
            # 数据充足：标准 RRG 经典窗口
            rs_window, mom_window, smooth_window = 20, 5, 3
        
        bench_return = (bench_index / bench_index.shift(rs_window)) - 1
        
        traj_results = []
        for sector in sector_index.columns:
            sec_return = (sector_index[sector] / sector_index[sector].shift(rs_window)) - 1
            raw_rs = sec_return - bench_return
            smooth_rs = raw_rs.rolling(window=smooth_window).mean()
            raw_mom = smooth_rs - smooth_rs.shift(mom_window)
            smooth_mom = raw_mom.rolling(window=smooth_window).mean()
            
            temp_df = pd.DataFrame({
                '日期': sector_index.index,
                '行业名称': sector,
                '相对强弱_X': smooth_rs * 100,
                '动量_Y': smooth_mom * 100
            }).dropna()
            traj_results.append(temp_df)
            
        if traj_results:
            return pd.concat(traj_results, ignore_index=True)
    except Exception as e:
        print(f"时光机加载失败: {e}")
        
    return pd.DataFrame()

# ==========================================
# 📊 前端渲染主逻辑
# ==========================================
df, limit_up_df, top10_5d_df, debug_log = load_cross_section_data(
    file_signature(RRG_CSV_PATH),
    file_signature(DB_PATH),
)
traj_all_df = load_trajectory_data(days=45, db_signature=file_signature(DB_PATH))

if not df.empty:
    # 🛡️ 防弹衣 2：强制补齐画图所需的所有列（如果数据库合并失败，图表依然能画出宏观气泡！）
    required_cols = ["1日龙头", "3日龙头", "5日龙头", "核心中军"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = "数据等待同步..."
            
    if "相对强弱_X" not in df.columns: df["相对强弱_X"] = 0.0
    if "动量_Y" not in df.columns: df["动量_Y"] = 0.0
    if "行业名称" not in df.columns: df["行业名称"] = "未知板块"
    if "板块5日平均涨幅" not in df.columns: df["板块5日平均涨幅"] = 0.0

    tab1, tab2 = st.tabs(["🌌 全市场横截面 (今日战况)", "☄️ 单板块轨迹与微观穿透 (时光机)"])
    
    with tab1:
        has_bubble_col = '突破动能得分_气泡大小' in df.columns
        top_bubble_sectors = df.nlargest(15, '突破动能得分_气泡大小')['行业名称'].tolist() if has_bubble_col else df['行业名称'].tolist()[:15]
        
        df['显示名称'] = df.apply(lambda r: r['行业名称'] if r['行业名称'] in top_bubble_sectors or abs(r.get('动量_Y', 0)) > 5 or r.get('相对强弱_X', 0) > 15 else "", axis=1)

        size_col = "突破动能得分_气泡大小" if has_bubble_col else None
        
        fig = px.scatter(
            df, x="相对强弱_X", y="动量_Y", size=size_col, color="板块5日平均涨幅", 
            color_continuous_scale="RdYlGn_r", text="显示名称",
            custom_data=["行业名称", "相对强弱_X", "动量_Y", "板块5日平均涨幅", 
                         "突破动能得分_气泡大小" if has_bubble_col else "动量_Y", "1日龙头", "3日龙头", "5日龙头", "核心中军"],
            size_max=60, height=850
        )

        custom_hover = (
            "<b style='font-size:20px; color:#ffffff;'>%{customdata[0]}</b><br><br>" +
            "📈 <b>动量 (Y轴)：</b>%{customdata[2]:.2f} &nbsp;&nbsp;|&nbsp;&nbsp; 💪 <b>强弱 (X轴)：</b>%{customdata[1]:.2f}<br>" +
            "🔥 <b>活跃得分：</b>%{customdata[4]:.1f} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp; 📊 <b>近5日涨跌：</b>%{customdata[3]:.2f}%<br>" +
            "<br><b style='color:#7f8c8d;'>┈┈┈┈┈┈┈┈┈ 微观个股穿透 ┈┈┈┈┈┈┈┈┈</b><br><br>" + 
            "🥇 <b style='color:#e74c3c;'>今日先锋 (1日 Top 5)：</b><br><i style='font-size:11px;'>%{customdata[5]}</i><br><br>" +
            "🚀 <b style='color:#f39c12;'>短期动能 (3日 Top 5)：</b><br><i style='font-size:11px;'>%{customdata[6]}</i><br><br>" +
            "🔥 <b style='color:#f1c40f;'>中期趋势 (5日 Top 5)：</b><br><i style='font-size:11px;'>%{customdata[7]}</i><br><br>" +
            "⚓ <b style='color:#3498db;'>核心中军 (高流动性抱团)：</b><br><i style='font-size:11px;'>%{customdata[8]}</i><br><extra></extra>"
        )

        fig.update_traces(hovertemplate=custom_hover, textposition='top center', textfont=dict(size=12, color='#2c3e50', family="Arial Black"), marker=dict(line=dict(width=1, color='rgba(255,255,255,0.8)'), opacity=0.8))
        fig.add_hline(y=0, line_color="#34495e", opacity=0.8, line_width=1.5)
        fig.add_vline(x=0, line_color="#34495e", opacity=0.8, line_width=1.5)

        annotations = [
            dict(xref='paper', yref='paper', x=0.98, y=0.98, text="领涨", showarrow=False, font=dict(color="#e74c3c", size=18, family="Arial Black"), bgcolor="rgba(231, 76, 60, 0.08)", borderpad=6),
            dict(xref='paper', yref='paper', x=0.02, y=0.98, text="走强", showarrow=False, font=dict(color="#e67e22", size=18, family="Arial Black"), bgcolor="rgba(230, 126, 34, 0.08)", borderpad=6),
            dict(xref='paper', yref='paper', x=0.02, y=0.02, text="领跌", showarrow=False, font=dict(color="#27ae60", size=18, family="Arial Black"), bgcolor="rgba(39, 174, 96, 0.08)", borderpad=6),
            dict(xref='paper', yref='paper', x=0.98, y=0.02, text="走弱", showarrow=False, font=dict(color="#2980b9", size=18, family="Arial Black"), bgcolor="rgba(41, 128, 185, 0.08)", borderpad=6)
        ]
        
        fig.update_layout(
            annotations=annotations, template="plotly_white", margin=dict(l=20, r=20, t=40, b=20),
            xaxis=dict(title="相对强弱 (大局趋势)", zeroline=False, gridcolor='#ecf0f1'), 
            yaxis=dict(title="动量 (近期加速度)", zeroline=False, gridcolor='#ecf0f1'),
            hoverlabel=dict(bgcolor="rgba(30, 30, 30, 0.95)", bordercolor="rgba(255,255,255,0.2)", font_size=13, font_color="white", align="left")
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        col_table1, col_table2 = st.columns(2)
        with col_table1:
            st.markdown("#### 🚀 今日涨停先锋阵营")
            if not limit_up_df.empty:
                st.dataframe(limit_up_df.style.format({'涨跌幅(%)': '{:.2f}%', '成交额': '{:,.0f}'}).background_gradient(cmap='Reds', subset=['涨跌幅(%)']), use_container_width=True, height=380)
            else:
                st.info("💡 涨停数据同步中或暂无涨停标的")
        with col_table2:
            st.markdown("#### 🔥 全市场 5日连板/主升 Top 10")
            if not top10_5d_df.empty:
                st.dataframe(top10_5d_df.style.format({'5日涨幅(%)': '{:.2f}%'}).background_gradient(cmap='Oranges', subset=['5日涨幅(%)']), use_container_width=True, height=380)
            else:
                st.info("💡 5日涨幅数据同步中")

    with tab2:
        if not traj_all_df.empty:
            col_sel, col_empty = st.columns([1, 3])
            with col_sel:
                default_sector = df.sort_values('相对强弱_X', ascending=False)['行业名称'].iloc[0]
                target_sector = st.selectbox("🔍 选择目标板块", traj_all_df['行业名称'].unique(), index=list(traj_all_df['行业名称'].unique()).index(default_sector))
            
            micro_data = df[df['行业名称'] == target_sector]
            if not micro_data.empty:
                m_row = micro_data.iloc[0]
                st.markdown("##### 🔬 最新资金穿透明细")
                c1, c2, c3, c4 = st.columns(4)
                c1.info(f"**🥇 1日先锋 (今日)**\n\n{m_row['1日龙头']}")
                c2.warning(f"**🚀 3日动能 (短期)**\n\n{m_row['3日龙头']}")
                c3.error(f"**🔥 5日趋势 (中期)**\n\n{m_row['5日龙头']}")
                c4.success(f"**⚓ 核心中军 (大票)**\n\n{m_row['核心中军']}")

            st.markdown("---")
            traj_df = traj_all_df[traj_all_df['行业名称'] == target_sector].copy()
            traj_df['日期'] = pd.to_datetime(traj_df['日期'])
            traj_df = traj_df.sort_values('日期', ascending=True).reset_index(drop=True)
            traj_df['日期_str'] = traj_df['日期'].dt.strftime('%Y-%m-%d')
            
            fig_traj = go.Figure()
            fig_traj.add_trace(go.Scatter(x=traj_df['相对强弱_X'], y=traj_df['动量_Y'], mode='lines', line=dict(color='#3498db', width=3), hoverinfo='skip'))
            fig_traj.add_trace(go.Scatter(x=traj_df['相对强弱_X'][:-1], y=traj_df['动量_Y'][:-1], mode='markers+text', marker=dict(size=10, color=traj_df.index[:-1], colorscale='Blues', line=dict(width=1, color='#2980b9')), text=traj_df['日期_str'][:-1], customdata=traj_df[['日期_str', '相对强弱_X', '动量_Y']][:-1], hovertemplate="<b>%{customdata[0]}</b><br>强弱 (X): %{customdata[1]:.2f}<br>动量 (Y): %{customdata[2]:.2f}<extra></extra>"))

            if len(traj_df) > 0 and not micro_data.empty:
                last_row = traj_df.iloc[-1]
                hover_text_latest = f"<b style='font-size:18px; color:#ffffff;'>🔥 最新位置 ({last_row['日期_str']})</b><br><br>🥇 <b>1日先锋:</b> {m_row['1日龙头']}<br><br>🚀 <b>3日动能:</b> {m_row['3日龙头']}<br><br>🔥 <b>5日趋势:</b> {m_row['5日龙头']}<br><br>⚓ <b>核心中军:</b> {m_row['核心中军']}<extra></extra>"
                fig_traj.add_trace(go.Scatter(x=[last_row['相对强弱_X']], y=[last_row['动量_Y']], mode='markers+text', marker=dict(size=22, color='#e74c3c', symbol='star', line=dict(width=2, color='white')), text=[f"🔥 {last_row['日期_str']}"], textposition='top right', textfont=dict(color="#e74c3c", size=14, family="Arial Black"), hovertemplate=hover_text_latest))
                if len(traj_df) > 1:
                    prev_x, prev_y = traj_df.iloc[-2]['相对强弱_X'], traj_df.iloc[-2]['动量_Y']
                    fig_traj.add_annotation(x=last_row['相对强弱_X'], y=last_row['动量_Y'], ax=prev_x, ay=prev_y, xref='x', yref='y', axref='x', ayref='y', showarrow=True, arrowhead=3, arrowsize=2, arrowwidth=3, arrowcolor='#e74c3c')

            fig_traj.add_hline(y=0, line_color="#7f8c8d", opacity=0.6, line_width=1)
            fig_traj.add_vline(x=0, line_color="#7f8c8d", opacity=0.6, line_width=1)
            fig_traj.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=40, b=20), height=650, xaxis=dict(title="相对强弱 (X)", zeroline=False, gridcolor='#ecf0f1'), yaxis=dict(title="动量 (Y)", zeroline=False, gridcolor='#ecf0f1'), showlegend=False)
            st.plotly_chart(fig_traj, use_container_width=True)
        else:
            st.warning("⚠️ 时光机数据准备中：请检查 K 线历史数据是否足够长。")

    st.markdown("---")
    st.subheader("📋 宏微观异动数据汇总")
    if '突破动能得分_气泡大小' in df.columns:
        st.dataframe(df[['行业名称', '突破动能得分_气泡大小', '相对强弱_X', '动量_Y', '1日龙头', '3日龙头', '5日龙头', '核心中军']].style.background_gradient(cmap='Reds', subset=['突破动能得分_气泡大小']), height=400)
    else:
        st.dataframe(df, height=400)

    # 显示底层的排错日志
    if debug_log:
        st.warning("⚠️ 数据库底层读取提示 (不影响页面呈现)：")
        st.json(debug_log)

else:
    st.error("🚨 致命错误：数据未能成功加载，页面渲染终止！")
    st.write(f"1️⃣ CSV 宏观数据文件是否存在？: **{os.path.exists(RRG_CSV_PATH)}**")
    st.write(f"2️⃣ SQLite 微观数据库是否存在？: **{os.path.exists(DB_PATH)}**")
