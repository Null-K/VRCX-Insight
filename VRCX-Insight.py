import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.ndimage import gaussian_filter1d
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.font_manager as fm

appdata_path = os.environ.get('APPDATA')
DB_PATH = os.path.join(appdata_path, "VRCX", "VRCX.sqlite3")

class VRCXPredictorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VRCX 日志分析")
        self.root.geometry("1060x900")
        self.root.minsize(1060, 600)
        self.root.configure(bg="#f1f5f9")
        
        self.setup_styles()
        self.create_widgets()
        self.auto_discover_tables()
        self.set_chinese_font()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('vista')
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Value.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1e293b", background="#ffffff")
        style.configure("StatTitle.TLabel", font=("Microsoft YaHei UI", 9), foreground="#64748b", background="#ffffff")
        style.configure("Treeview", rowheight=32, font=("Microsoft YaHei UI", 9), relief="flat")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), background="#f8fafc")

    def set_chinese_font(self):
        fonts = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']
        for f in fonts:
            if f in [font.name for font in fm.fontManager.ttflist]:
                plt.rcParams['font.sans-serif'] = [f]
                plt.rcParams['axes.unicode_minus'] = False
                return f
        return None

    def circular_mean(self, hours):
        radians = np.deg2rad(np.array(hours) / 24 * 360)
        sin_mean = np.mean(np.sin(radians))
        cos_mean = np.mean(np.cos(radians))
        mean_angle = np.rad2deg(np.arctan2(sin_mean, cos_mean)) % 360
        return mean_angle / 360 * 24

    def create_widgets(self):
        self.main_container = ttk.Frame(self.root, padding="25 25 25 25")
        self.main_container.pack(fill=tk.BOTH, expand=True)

        search_card = tk.Frame(self.main_container, bg="#ffffff", padx=20, pady=15, 
                                highlightthickness=1, highlightbackground="#e2e8f0")
        search_card.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(search_card, text="数据源:", background="#ffffff").pack(side=tk.LEFT)
        self.table_var = tk.StringVar()
        self.table_combo = ttk.Combobox(search_card, textvariable=self.table_var, width=35, state="readonly")
        self.table_combo.pack(side=tk.LEFT, padx=(10, 20))
        
        ttk.Label(search_card, text="好友名称:", background="#ffffff").pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(search_card, textvariable=self.name_var, width=25)
        self.name_entry.pack(side=tk.LEFT, padx=10)
        self.name_entry.bind('<Return>', lambda e: self.run_analysis())
        
        btn_frame = tk.Frame(search_card, bg="#ffffff")
        btn_frame.pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="运行分析", bg="#3b82f6", fg="white", font=("Microsoft YaHei UI", 9, "bold"), 
                  relief="flat", padx=15, pady=5, command=self.run_analysis, cursor="hand2").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="指定好友热力图", bg="#10b981", fg="white", font=("Microsoft YaHei UI", 9, "bold"), 
                  relief="flat", padx=15, pady=5, command=self.show_heatmap, cursor="hand2").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="全局好友热力图", bg="#6366f1", fg="white", font=("Microsoft YaHei UI", 9, "bold"), 
                  relief="flat", padx=15, pady=5, command=self.show_all_users_heatmap, cursor="hand2").pack(side=tk.LEFT, padx=5)

        self.status_card = tk.Frame(self.main_container, bg="#ffffff", padx=20, pady=20,
                                    highlightthickness=1, highlightbackground="#e2e8f0")
        self.status_card.pack(fill=tk.X, pady=(0, 20))
        self.status_indicator = ttk.Label(self.status_card, text="等待分析...", font=("Microsoft YaHei UI", 12, "bold"), background="#ffffff")
        self.status_indicator.pack(side=tk.LEFT)
        self.status_detail = ttk.Label(self.status_card, text="请输入好友名称后按下回车或点击按钮", foreground="#64748b", background="#ffffff")
        self.status_detail.pack(side=tk.LEFT, padx=30)

        self.metrics_container = ttk.Frame(self.main_container)
        self.metrics_container.pack(fill=tk.X, pady=(0, 20))
        self.metrics = {}
        titles = [("count", "样本数量"), ("prob", "近 2 小时上线概率"), ("dur", "平均在线时长"), ("time", "典型上线时间"), ("stab", "作息稳定性")]
        for i, (key, title) in enumerate(titles):
            f = tk.Frame(self.metrics_container, bg="#ffffff", padx=15, pady=15, highlightthickness=1, highlightbackground="#e2e8f0")
            f.grid(row=0, column=i, sticky="nsew", padx=(0 if i==0 else 10, 0))
            self.metrics_container.columnconfigure(i, weight=1)
            ttk.Label(f, text=title, style="StatTitle.TLabel").pack(anchor=tk.W)
            v = ttk.Label(f, text="--", style="Value.TLabel")
            v.pack(anchor=tk.W, pady=(10, 0))
            self.metrics[key] = v

        table_frame = tk.Frame(self.main_container, bg="#ffffff", padx=2, pady=2, highlightthickness=1, highlightbackground="#e2e8f0")
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("date", "start", "duration", "end")
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode="browse")
        self.tree.heading("date", text="日期"); self.tree.heading("start", text="上线时间")
        self.tree.heading("duration", text="在线时长 (小时)"); self.tree.heading("end", text="下线时间")
        for col in columns: self.tree.column(col, anchor=tk.CENTER, width=100)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

    def auto_discover_tables(self):
        if not os.path.exists(DB_PATH): return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'usr%_feed_online_offline'")
        tables = [row[0] for row in cursor.fetchall()]; self.table_combo['values'] = tables
        if tables: self.table_combo.current(0)
        conn.close()

    def get_raw_data(self):
        name = self.name_var.get().strip()
        table = self.table_var.get()
        if not name: return None
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f"SELECT type, created_at FROM {table} WHERE display_name = ?", conn, params=(name,))
        conn.close(); return df

    def run_analysis(self):
        df = self.get_raw_data()
        if df is None or df.empty:
            self.status_indicator.config(text="未找到用户", foreground="#ef4444"); return

        try:
            df['dt'] = pd.to_datetime(df['created_at']).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
            sessions = []
            last_online = None
            for _, row in df.iterrows():
                if row['type'] == 'Online': last_online = row['dt']
                elif row['type'] == 'Offline' and last_online:
                    dur = (row['dt'] - last_online).total_seconds() / 3600
                    if 0.02 < dur < 24:
                        sessions.append({'start': last_online, 'end': row['dt'], 'dur': dur, 'hour': last_online.hour + last_online.minute/60})
                    last_online = None

            for item in self.tree.get_children(): self.tree.delete(item)
            for s in sessions[::-1]:
                self.tree.insert("", tk.END, values=(s['start'].strftime('%Y-%m-%d'), s['start'].strftime('%H:%M'), f"{s['dur']:.2f}", s['end'].strftime('%H:%M')))

            if not sessions: 
                self.status_indicator.config(text="数据不足", foreground="#f59e0b"); return
            if len(sessions) < 5: 
                self.status_indicator.config(text="数据不足", foreground="#f59e0b"); return

            sdf = pd.DataFrame(sessions)

            self.metrics['count'].config(text=f"{len(sdf)}")
            avg_dur = sdf['dur'].mean()
            self.metrics['dur'].config(text=f"{avg_dur:.2f} 小时")
            
            typical_h = self.circular_mean(sdf['hour'].values)
            self.metrics['time'].config(text=f"{int(typical_h):02d}:{int((typical_h%1)*60):02d}")

            bins = np.zeros(96)
            for h in sdf['hour']: bins[int(h * 4) % 96] += 1
            smoothed = gaussian_filter1d(bins, sigma=1.5, mode='wrap')
            now_bin = int((datetime.now().hour + datetime.now().minute / 60) * 4) % 96
            prob = np.sum(smoothed[(now_bin+1):(now_bin+9)]) / (smoothed.sum() if smoothed.sum() > 0 else 1)
            self.metrics['prob'].config(text=f"{prob * 100:.1f}%")

            std_dev = np.std(sdf['hour'])
            self.metrics['stab'].config(text="极高" if std_dev < 1.5 else "规律" if std_dev < 3 else "随机")

            last_rec = df.iloc[-1]
            if last_rec['type'] == 'Online':
                elapsed = (datetime.now() - last_rec['dt']).total_seconds() / 3600
                self.status_indicator.config(text="● 在线中 (ONLINE)", foreground="#16a34a")
                predict_off = (datetime.now() + timedelta(hours=max(0, avg_dur - elapsed))).strftime('%H:%M')
                self.status_detail.config(text=f"已在线 {elapsed:.1f} 小时 | 预计下线时间为: {predict_off}")
            else:
                self.status_indicator.config(text="○ 离线 (OFFLINE)", foreground="#64748b")
                self.status_detail.config(text=f"最后上线: {last_rec['dt'].strftime('%m-%d %H:%M')}")

        except Exception as e:
            messagebox.showerror("获取错误", str(e))

    def show_heatmap(self):
        df = self.get_raw_data()
        if df is None or df.empty: return
        try:
            self.set_chinese_font()

            df['created_at'] = pd.to_datetime(df['created_at']).dt.tz_convert('Asia/Shanghai')
            online_df = df[df['type'] == 'Online'].copy()
            if online_df.empty: 
                messagebox.showinfo("生成失败", "该数据源中没有在线记录")
                return

            online_df['hour'] = online_df['created_at'].dt.hour
            week_map = {'Monday': '周一', 'Tuesday': '周二', 'Wednesday': '周三', 
                        'Thursday': '周四', 'Friday': '周五', 'Saturday': '周六', 'Sunday': '周日'}
            online_df['weekday'] = online_df['created_at'].dt.day_name().map(week_map)
            days_order = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            online_df['weekday'] = pd.Categorical(online_df['weekday'], categories=days_order, ordered=True)

            heatmap_data = online_df.groupby(['weekday', 'hour'], observed=False).size().unstack(fill_value=0)
            heatmap_data = heatmap_data.reindex(columns=range(24), fill_value=0)

            plt.figure(figsize=(12, 7))
            sns.heatmap(heatmap_data, annot=True, fmt="d", cmap="YlGnBu", cbar_kws={'label': '上线次数'})
            
            plt.title(f"VRChat 好友 [{self.name_var.get()}] 活跃热力图\n数据源: VRCX", fontsize=15, pad=20)
            plt.xlabel("小时 (24小时制)", fontsize=12)
            plt.ylabel("星期", fontsize=12)
            
            plt.xticks(rotation=0)
            plt.yticks(rotation=0)

            plt.tight_layout()
            plt.show()
        except Exception as e: 
            messagebox.showerror("生成失败", str(e))

    def show_all_users_heatmap(self):
        table = self.table_var.get()
        if not table:
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            query = f"SELECT created_at FROM {table} WHERE type = 'Online'"
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                messagebox.showinfo("生成失败", "该数据源中没有在线记录")
                return

            df['created_at'] = pd.to_datetime(df['created_at']).dt.tz_convert('Asia/Shanghai')
            df['hour'] = df['created_at'].dt.hour
            
            week_map = {'Monday': '周一', 'Tuesday': '周二', 'Wednesday': '周三', 'Thursday': '周四', 'Friday': '周五', 'Saturday': '周六', 'Sunday': '周日'}
            df['weekday'] = df['created_at'].dt.day_name().map(week_map)
            days_order = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            df['weekday'] = pd.Categorical(df['weekday'], categories=days_order, ordered=True)

            heatmap_data = df.groupby(['weekday', 'hour'], observed=False).size().unstack(fill_value=0)
            heatmap_data = heatmap_data.reindex(columns=range(24), fill_value=0)

            plt.figure(figsize=(12, 7))
            sns.heatmap(heatmap_data, annot=True, fmt="d", cmap="YlGnBu", cbar_kws={'label': '上线次数'})
            plt.title(f"VRChat 好友活跃热力图\n数据源: VRCX - {table[:12]}...", fontsize=15, pad=20)
            plt.xlabel("小时 (24小时制)", fontsize=12)
            plt.ylabel("星期", fontsize=12)

            plt.xticks(rotation=0)
            plt.yticks(rotation=0)

            plt.tight_layout()
            plt.show()

        except Exception as e:
            messagebox.showerror("生成失败", str(e))

if __name__ == "__main__":
    root = tk.Tk(); app = VRCXPredictorUI(root); root.mainloop()