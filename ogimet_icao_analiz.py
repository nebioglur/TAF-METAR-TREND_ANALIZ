# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
from datetime import datetime, timedelta, timezone
import threading
import pandas as pd
import re
import math
import requests
from bs4 import BeautifulSoup
from tkcalendar import DateEntry
import urllib3
import time
import RASATLAR
import TAF_METAR_TREND

# SSL Hatalarını Gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

STATION = "LTAN"
WMO_ID = "17244"

robot = TAF_METAR_TREND.HavacilikRobotModulu()

def process_data(lines, station_code, wmo_id):
    data = []
    current_record = None

    for line in lines:
        line = line.strip()
        if not line: continue
        
        parts = line.split()
        is_start = False
        
        # Yeni kayıt başlangıcı tespiti
        if len(parts) > 0:
            if parts[0].isdigit() and len(parts[0]) == 12:
                is_start = True
            elif parts[0] in ["METAR", "TAF", "SPECI"]:
                is_start = True
            elif len(parts) > 1 and len(parts[0]) == 4 and parts[0].isalpha() and parts[1].endswith('Z'):
                is_start = True
            elif re.match(r'^[A-Z]{4}\d{2}$', parts[0]): # WMO Header (SATT70, FCTT70 vb.)
                is_start = True
            
            # BECMG, TEMPO vb. with başlayan readlinesı kesinlikle continue satırı as işaretle
            if parts[0] in ["BECMG", "TEMPO", "PROB30", "PROB40", "RMK"] or parts[0].startswith("FM") or parts[0].startswith("TX") or parts[0].startswith("TN"):
                is_start = False
        
        if is_start:
            if current_record:
                data.append(current_record)
            
            ts_raw = parts[0]
            dt_str, turu, content = "---", "METAR", line
            dt_sort = datetime.min
            
            if ts_raw.isdigit() and len(ts_raw) == 12:
                try:
                    dt = datetime.strptime(ts_raw, "%Y%m%d%H%M")
                    dt_str = dt.strftime("%d.%m.%Y %H:%M")
                    dt_sort = dt
                except: pass
                
                if len(parts) > 1:
                    p1 = parts[1]
                    if p1 in ["METAR", "TAF", "SPECI"]:
                        turu = p1
                        content = " ".join(parts[2:])
                    elif p1 == "AAXX":
                        turu = "SİNOPTİK"
                        content = " ".join(parts[1:])
                    else:
                        # Detaylı SİNOPTİK Tespiti
                        is_synop = False
                        if wmo_id and wmo_id in line: is_synop = True
                        elif " 333 " in line: is_synop = True
                        elif sum(1 for p in parts if p.isdigit() and len(p) == 5) >= 3: is_synop = True
                        
                        if is_synop:
                            turu = "SİNOPTİK"
                        elif "METAR" in line: turu = "METAR"
                        elif "TAF" in line: turu = "TAF"
                        content = " ".join(parts[1:])
            
            elif parts[0] in ["METAR", "TAF", "SPECI"]:
                turu = parts[0]
                content = " ".join(parts[1:])
                m = re.search(r'\b(\d{2})(\d{2})(\d{2})Z\b', content)
                if m:
                    try:
                        now = datetime.now(timezone.utc).replace(tzinfo=None)
                        dt_est = now.replace(day=int(m.group(1)), hour=int(m.group(2)), minute=int(m.group(3)))
                        if dt_est > now + timedelta(days=1): dt_est -= timedelta(days=28)
                        dt_sort = dt_est
                        dt_str = dt_sort.strftime("%d.%m.%Y %H:%M")
                    except: pass
            
            elif len(parts) > 1 and len(parts[0]) == 4 and parts[0].isalpha() and parts[1].endswith('Z'):
                turu = "TAF" if ("TAF" in line or "/" in line) else "METAR"
                content = line
                m = re.search(r'\b(\d{2})(\d{2})(\d{2})Z\b', content)
                if m:
                    try:
                        now = datetime.now(timezone.utc).replace(tzinfo=None)
                        dt_est = now.replace(day=int(m.group(1)), hour=int(m.group(2)), minute=int(m.group(3)))
                        if dt_est > now + timedelta(days=1): dt_est -= timedelta(days=28)
                        dt_sort = dt_est
                        dt_str = dt_sort.strftime("%d.%m.%Y %H:%M")
                    except: pass

            current_record = {"date": dt_str, "Türü": turu, "İstasyon": station_code if turu!="SİNOPTİK" else wmo_id, "Bülten": content, "_dt": dt_sort}
        
        else:
            # continue satırı (TAF vb. for)
            if current_record:
                current_record["Bülten"] += " " + line

    if current_record:
        data.append(current_record)
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.drop_duplicates(subset=['Türü', 'Bülten'])
        df = df.sort_values(by="_dt", ascending=False)
    return df

# ================== GUI ==================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"OGIMET ICAO ANALİZ - {STATION}")
        self.geometry("1200x700")
        self.state('zoomed')
        self.configure(bg="#2b2b2b")
        self.full_df = None
        self.auto_refresh_var = tk.BooleanVar()
        self.refresh_job = None
        self.tree_tooltips = {}
        self.tooltip_window = None
        self.last_tooltip_item = None
        self.setup_ui()
        
    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", background="#263238", foreground="#eceff1", fieldbackground="#263238", rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#37474f", foreground="white", font=("Segoe UI", 11, "bold"))
        style.map("Treeview", background=[('selected', '#00bcd4')])

        top_frame = tk.Frame(self, bg="#2b2b2b")
        top_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(top_frame, text="ICAO:", bg="#2b2b2b", fg="#aaaaaa").pack(side="left")
        self.ent_station = tk.Entry(top_frame, width=5, bg="#1e1e1e", fg="white", insertbackground="white")
        self.ent_station.insert(0, STATION)
        self.ent_station.pack(side="left", padx=(2, 10))

        tk.Label(top_frame, text="WMO:", bg="#2b2b2b", fg="#aaaaaa").pack(side="left")
        self.ent_wmo = tk.Entry(top_frame, width=6, bg="#1e1e1e", fg="white", insertbackground="white")
        self.ent_wmo.insert(0, WMO_ID)
        self.ent_wmo.pack(side="left", padx=(2, 10))
        
        now = datetime.now()
        self.ent_start = DateEntry(top_frame, width=10, background='#0078D7', foreground='white', borderwidth=2)
        self.ent_start.set_date(now - timedelta(days=1))
        self.ent_start.pack(side="left", padx=5)
        
        self.ent_end = DateEntry(top_frame, width=10, background='#0078D7', foreground='white', borderwidth=2)
        self.ent_end.set_date(now)
        self.ent_end.pack(side="left", padx=5)
        
        tk.Button(top_frame, text="yieldİ ÇEK & ANALİZ ET", command=self.start_process, 
                  bg="#0078D7", fg="white", font=("Segoe UI", 10, "bold"), relief="flat").pack(side="left", padx=10)
        
        tk.Button(top_frame, text="EXCEL RAPOR", command=self.export_to_excel, 
                  bg="#43A047", fg="white", font=("Segoe UI", 10, "bold"), relief="flat").pack(side="left", padx=5)
        
        self.chk_auto = tk.Checkbutton(top_frame, text="Oto. Yenile (5dk)", variable=self.auto_refresh_var, command=self.toggle_auto_refresh, bg="#2b2b2b", fg="white", selectcolor="#2b2b2b", activebackground="#2b2b2b", activeforeground="white", font=("Segoe UI", 10))
        self.chk_auto.pack(side="left", padx=5)

        # Filtreleme Alanı
        filter_frame = tk.Frame(self, bg="#2b2b2b")
        filter_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(filter_frame, text="Filtrele:", bg="#2b2b2b", fg="white").pack(side="left")
        self.cb_filter = ttk.Combobox(filter_frame, state="readonly", values=["HEPSİ", "❌ UYUMSUZ", "⚠️ DİKKAT", "✅ UYUMLU"])
        self.cb_filter.current(0)
        self.cb_filter.pack(side="left", padx=5)
        self.cb_filter.bind("<<ComboboxSelected>>", self.apply_filter)
        
        tk.Label(filter_frame, text="Ara:", bg="#2b2b2b", fg="white").pack(side="left", padx=(10, 5))
        self.entry_search = tk.Entry(filter_frame, bg="#1e1e1e", fg="white", insertbackground="white")
        self.entry_search.pack(side="left", padx=5, fill="x", expand=True)
        self.entry_search.bind("<KeyRelease>", self.apply_filter)

        self.lbl_status = tk.Label(top_frame, text="Hazır", bg="#2b2b2b", fg="#aaaaaa")
        self.lbl_status.pack(side="left", padx=10)

        # Treeview
        cols = ("date", "Türü", "İstasyon", "Uyum", "Bülten")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        self.tree.heading("date", text="date")
        self.tree.heading("Türü", text="Türü")
        self.tree.heading("İstasyon", text="İstasyon")
        self.tree.heading("Uyum", text="TREND UYUM")
        self.tree.heading("Bülten", text="Bülten")
        
        self.tree.column("date", width=100, anchor="center")
        self.tree.column("Türü", width=50, anchor="center")
        self.tree.column("İstasyon", width=60, anchor="center")
        self.tree.column("Uyum", width=200, anchor="center")
        self.tree.column("Bülten", width=800, anchor="w")
        
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tree.tag_configure('UYUMSUZ', background='#D32F2F', foreground='white')
        self.tree.tag_configure('DIKKAT', background='#FFD700', foreground='black')
        self.tree.tag_configure('UYUMLU', foreground='#69F0AE')
        self.tree.tag_configure('SİNOPTİK', foreground='#FFB74D')
        self.tree.tag_configure('METAR', foreground='#4FC3F7')
        self.tree.tag_configure('TAF', background='#3E2723', foreground='#FFAB00', font=("Verdana", 10, "bold"))

        # Detay Paneli
        self.detail_text = tk.Text(self, height=8, bg="#1e1e1e", fg="white", font=("Consolas", 11))
        self.detail_text.pack(fill="x", padx=10, pady=10)
        
        self.detail_text.tag_config("header", foreground="#aaaaaa", font=("Segoe UI", 10, "bold"))
        self.detail_text.tag_config("content", foreground="white")
        self.detail_text.tag_config("red", foreground="#FF5252")
        self.detail_text.tag_config("yellow", foreground="#FFD700")
        self.detail_text.tag_config("green", foreground="#69F0AE")
        
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.bind("<Leave>", self.hide_tooltip)
        self.tree.bind("<Double-1>", self.open_detail_window)
        self.tree.bind("<Button-3>", self.show_tree_context_menu)
        self.detail_text.bind("<Button-3>", self.show_text_context_menu)

    def toggle_auto_refresh(self):
        if self.auto_refresh_var.get():
            self.auto_refresh_loop()
        elif self.refresh_job:
            self.after_cancel(self.refresh_job)
            self.refresh_job = None

    def auto_refresh_loop(self):
        if self.auto_refresh_var.get():
            self.start_process()
            self.refresh_job = self.after(300000, self.auto_refresh_loop)

    def start_process(self):
        st = self.ent_station.get().strip().upper()
        wmo = self.ent_wmo.get().strip()
        d_start = self.ent_start.get_date()
        d_end = self.ent_end.get_date()
        
        s_dt = datetime.combine(d_start, datetime.min.time())
        e_dt = datetime.combine(d_end, datetime.max.time())
        
        self.lbl_status.config(text="Veriler çekiliyor...", fg="#FFD740")
        threading.Thread(target=self.worker, args=(st, wmo, s_dt, e_dt), daemon=True).start()

    def worker(self, st, wmo, s_dt, e_dt):
        try:
            all_lines = []
            curr_end = e_dt
            
            # Ogimet genellikle 30-31 günlük veri verir. Uzun aralıklar for döngü kuruyoruz.
            while curr_end > s_dt:
                curr_start = curr_end - timedelta(days=30)
                if curr_start < s_dt:
                    curr_start = s_dt
                
                self.after(0, lambda s=curr_start, e=curr_end: self.lbl_status.config(text=f"Çekiliyor: {s.strftime('%d.%m.%Y')} - {e.strftime('%d.%m.%Y')}", fg="#FFD740"))
                
                try:
                    chunk_lines = RASATLAR.fetch(curr_start, curr_end, station=st, wmo_id=wmo)
                    if chunk_lines:
                        all_lines.extend(chunk_lines)
                except Exception as e:
                    print(f"Veri parça hatası: {e}")
                
                curr_end = curr_start - timedelta(seconds=1)
                time.sleep(0.5) # Sunucuyu yormamak for bekleme

            if not all_lines:
                self.after(0, lambda: messagebox.showwarning("Uyarı", "Veri bulunamadı."))
                self.after(0, lambda: self.lbl_status.config(text="Veri yok", fg="white"))
                return

            try:
                df = process_data(all_lines, st, wmo)
            except Exception as e:
                raise Exception(f"Veri işleme hatası: {e}")
            
            # ANALİZ
            df["_uyum"] = ""
            df["_detay"] = ""
            df["_ref_taf"] = ""
            
            try:
                tafs = df[df['Türü'] == 'TAF'].sort_values(by='_dt')
                
                if not tafs.empty:
                    # Ardışık Exception takibi for sayaçlar
                    last_taf_text = None
                    consecutive_counts = {"Rüzgar": 0, "Görüş": 0, "ceil": 0}
                    
                    # Kronolojik sıra with işle (Eskiden yeniye)
                    # df.sort_values with sıralı iterasyon yapıyoruz
                    for idx, row in df.sort_values(by='_dt', ascending=True).iterrows():
                        if row['Türü'] in ['METAR', 'SPECI']:
                            metar_dt = row['_dt']
                            
                            # 1. METAR zamanından önce or aynı zamanda yayınlanmış TAF'ları al
                            relevant_tafs = tafs[tafs['_dt'] <= metar_dt]
                            
                            target_row = None
                            
                            # 2. En son yayınlanan TAF'ı seç (passerlilik süresi kontrolü iptal)
                            if not relevant_tafs.empty:
                                target_row = relevant_tafs.iloc[-1]
                            
                            if target_row is not None:
                                last_taf = target_row['Bülten']
                                taf_dt = target_row['_dt']
                                
                                # TAF değiştiyse sayaçları sıfırla
                                if last_taf != last_taf_text:
                                    consecutive_counts = {k: 0 for k in consecutive_counts}
                                    last_taf_text = last_taf
                                
                                # 3 time KURALI: TAF yayınlandıktan sonraki 3 time içindeki rasatlar dikkate alınır.
                                time_diff = metar_dt - taf_dt
                                if time_diff > timedelta(hours=3):
                                    continue

                                print(f"🔍 DENETİM: METAR {metar_dt.strftime('%d/%H:%M')} <--- TAF {target_row['_dt'].strftime('%d/%H:%M')}")

                                df.at[idx, "_ref_taf"] = last_taf
                                try:
                                    # TAF Zamanını bul (Örn: 0412/0512)
                                    # Regex geliştirildi: Gün (01-31) and time (00-24) formatına uygunluk kontrolü. BECMG/TEMPO for de passerli.
                                    regex_period = r'(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-4])/(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-4])'
                                    
                                    t_valid = re.search(r'\b' + regex_period + r'\b', last_taf)
                                    taf_zaman = t_valid.group(0) if t_valid else "0000/0000"
                                    
                                    # FM Gruplarını dikkate alarak aktif splitümü seç
                                    active_taf = last_taf
                                    # FM, BECMG and TEMPO gruplarını dikkate alarak aktif splitümü seç
                                    try:
                                        best_change_start = -1
                                        taf_dt = target_row['_dt']

                                        # Tüm değişim gruplarını (FM, BECMG, TEMPO) yakalayan birleşik regex
                                        change_pattern = r'\b(FM(\d{6})|(?:BECMG|TEMPO)\s+((\d{4})/\d{4}))\b'
                                        
                                        for m in re.finditer(change_pattern, last_taf):
                                            start_dt = None
                                            try:
                                                if m.group(2): # FM grubu matchti (örn: FM081000)
                                                    time_code = m.group(2)
                                                    day, hour, minute = int(time_code[0:2]), int(time_code[2:4]), int(time_code[4:6])
                                                    start_dt = taf_dt.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                                                elif m.group(3): # BECMG/TEMPO grubu matchti (örn: BECMG 0810/0812)
                                                    time_code = m.group(4) # Sadece başlangıç DDHH alınır (örn: 0810)
                                                    day, hour = int(time_code[0:2]), int(time_code[2:4])
                                                    start_dt = taf_dt.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)
                                                
                                                if start_dt:
                                                    # Ay passişi kontrolü
                                                    if start_dt.day < taf_dt.day and (taf_dt.day - start_dt.day) > 15:
                                                        if start_dt.month == 12: start_dt = start_dt.replace(year=start_dt.year+1, month=1)
                                                        else: start_dt = start_dt.replace(month=start_dt.month+1)
                                                    elif start_dt.day > taf_dt.day and (start_dt.day - taf_dt.day) > 15:
                                                        if start_dt.month == 1: start_dt = start_dt.replace(year=start_dt.year-1, month=12)
                                                        else: start_dt = start_dt.replace(month=start_dt.month-1)
                                                    
                                                    if start_dt <= metar_dt:
                                                        best_change_start = max(best_change_start, m.start())
                                            except (ValueError, IndexError): continue

                                        if best_change_start != -1:
                                            active_taf = last_taf[best_change_start:]
                                    except Exception as e:
                                        print(f"Değişim Grubu Analiz Hatası: {e}")

                                    # Trend kısmını ayır
                                    trend_part = ""
                                    tr_m = re.search(r'\b(BECMG|TEMPO|NOSIG)\b', row['Bülten'])
                                    if tr_m: trend_part = row['Bülten'][tr_m.start():]

                                    skor, status_code, reasons = robot.analiz_et(active_taf, row['Bülten'], trend_part, taf_zaman)
                                    
                                    # --- ARDIŞIK Exception KONTROLÜ ---
                                    current_cats = set()
                                    for r in reasons:
                                        if "Rüzgar" in r: current_cats.add("Rüzgar")
                                        if "Görüş" in r: current_cats.add("Görüş")
                                        if "ceil" in r or "Dikey Görüş" in r or "Bulut" in r: current_cats.add("ceil")
                                    
                                    amd_msgs = []
                                    for cat in consecutive_counts:
                                        if cat in current_cats:
                                            consecutive_counts[cat] += 1
                                            if consecutive_counts[cat] >= 3:
                                                amd_msgs.append(f"{cat} ({consecutive_counts[cat]}. kez)")
                                        else:
                                            consecutive_counts[cat] = 0
                                    # -----------------------------

                                    icon = ""
                                    if "UYUMSUZ" in status_code: icon = "❌ UYUMSUZ"
                                    elif "DİKKAT" in status_code: icon = "⚠️ DİKKAT"
                                    elif "UYUMLU" in status_code: icon = "✅ UYUMLU"
                                    
                                    df.at[idx, "_uyum"] = icon
                                    
                                    # Detaylı Açıklama Metni Oluşturma
                                    detay_str = ""
                                    if "UYUMSUZ" in status_code:
                                        detay_str = "1- UYUMSUZLUK NEDENİ:\n" + "\n".join([f"• {r}" for r in reasons])
                                        detay_str += "\n\n2- TREND KONTROLÜ:\n• Trend with de uyum sağlanamadı or Trend yok."
                                        detay_str += "\n\n3- SONUÇ:\n• ❌ UYUMSUZ"
                                    elif "DİKKAT" in status_code:
                                        detay_str = "1- UYUMSUZLUK NEDENİ (Ana METAR):\n" + "\n".join([f"• {r}" for r in reasons])
                                        detay_str += "\n\n2- TREND KONTROLÜ:\n• ✅ METAR Trendi TAF limitlerine giriyor."
                                        detay_str += "\n\n3- SONUÇ:\n• ⚠️ DİKKAT (Trend with uyumlu)"
                                    elif "UYUMLU" in status_code:
                                        detay_str = "1- status_code:\n• TAF limitleri dahilinde."
                                        if "Trend" in status_code:
                                            detay_str += " (TAF Trendi with)"
                                        detay_str += "\n\n3- SONUÇ:\n• ✅ UYUMLU"
                                    
                                    # TAVSİYE EKLE
                                    if amd_msgs:
                                        detay_str += f"\n\n👉 KRİTİK TAVSİYE:\n• TAF AMD YAYINLANMALI!\n  Aynı sapma 3 and üzerinde tekrarlandı: {', '.join(amd_msgs)}"
                                    
                                    df.at[idx, "_detay"] = detay_str
                                except Exception as e: print(f"Analiz satır hatası: {e}")
            except Exception as e:
                print(f"Genel analiz hatası: {e}")

            self.after(0, lambda: self.update_tree(df))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Exception", str(e)))

    def apply_filter(self, event=None):
        if self.full_df is None: return
        choice = self.cb_filter.get()
        search = self.entry_search.get().lower()
        df_show = self.full_df.copy()
        
        if choice == "❌ UYUMSUZ": df_show = df_show[df_show["_uyum"].str.contains("UYUMSUZ", na=False)]
        elif choice == "⚠️ DİKKAT": df_show = df_show[df_show["_uyum"].str.contains("DİKKAT", na=False)]
        elif choice == "✅ UYUMLU": df_show = df_show[df_show["_uyum"].str.contains("UYUMLU", na=False)]
        
        if search: df_show = df_show[df_show["Bülten"].str.lower().str.contains(search, na=False)]
        self.render_tree(df_show)

    def update_tree(self, df):
        self.full_df = df
        self.apply_filter()

    def show_tree_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Satırı copy", command=self.copy_tree_selection)
        menu.tk_popup(event.x_root, event.y_root)

    def copy_tree_selection(self):
        selected = self.tree.selection()
        if not selected: return
        res = []
        for item in selected:
            vals = self.tree.item(item, "values")
            res.append(" | ".join(map(str, vals)))
        self.clipboard_clear()
        self.clipboard_append("\n".join(res))

    def show_text_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="copy", command=self.copy_text_selection)
        menu.add_command(label="Tümünü Seç", command=self.select_all_text)
        menu.tk_popup(event.x_root, event.y_root)

    def copy_text_selection(self):
        try:
            sel = self.detail_text.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(sel)
        except: pass

    def select_all_text(self):
        self.detail_text.tag_add("sel", "1.0", "end")

    def render_tree(self, df):
        self.tree_tooltips.clear()
        self.tree.delete(*self.tree.get_children())
        for _, row in df.iterrows():
            vals = (row["date"], row["Türü"], row["İstasyon"], row["_uyum"], row["Bülten"])
            tag = ""
            if "UYUMSUZ" in row["_uyum"]: tag = "UYUMSUZ"
            elif "DİKKAT" in row["_uyum"]: tag = "DIKKAT"
            elif "UYUMLU" in row["_uyum"]: tag = "UYUMLU"
            elif row["Türü"] == "SİNOPTİK": tag = "SİNOPTİK"
            elif row["Türü"] == "TAF": tag = "TAF"
            elif row["Türü"] in ["METAR", "SPECI"]: tag = "METAR"
            
            item_id = self.tree.insert("", "end", values=vals, tags=(tag,))
            
            if row["_detay"]:
                color = "#eceff1"
                if "UYUMSUZ" in row["_uyum"]: color = "#FF5252"
                elif "DİKKAT" in row["_uyum"]: color = "#FFD700"
                elif "UYUMLU" in row["_uyum"]: color = "#69F0AE"
                self.tree_tooltips[item_id] = (f"Analiz Detayı:\n{row['_detay']}", color)
                
        self.lbl_status.config(text=f"Gösterilen: {len(df)} kayıt", fg="#69F0AE")
        self.adjust_column_widths(df)

    def on_tree_motion(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id == self.last_tooltip_item: return
        self.last_tooltip_item = item_id
        self.hide_tooltip()
        if item_id and item_id in self.tree_tooltips:
            val = self.tree_tooltips[item_id]
            if isinstance(val, tuple): text, color = val
            else: text, color = val, "#eceff1"
            self.show_tooltip(event.x_root, event.y_root, text, color)

    def show_tooltip(self, x, y, text, text_color="#eceff1"):
        self.tooltip_window = tk.Toplevel(self)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.withdraw() 
        bg_color = "#263238" 
        fg_color = text_color 
        border_color = "#FF5252" if "UYUMSUZ" in text or "KRİTİK" in text or "YANLIŞ" in text else "#80cbc4"
        
        frame = tk.Frame(self.tooltip_window, bg=bg_color, highlightbackground=border_color, highlightthickness=2)
        frame.pack(fill="both", expand=True)
        
        # Renkli text for Text widget kullanımı
        txt_widget = tk.Text(frame, width=90, height=len(text.split('\n')) + 4, bg=bg_color, fg=fg_color, font=("Consolas", 10), relief="flat", wrap="word")
        txt_widget.pack(padx=10, pady=8)
        
        txt_widget.tag_config("green", foreground="#00E676")
        txt_widget.tag_config("red", foreground="#FF5252")
        txt_widget.tag_config("yellow", foreground="#FFD700")
        txt_widget.tag_config("default", foreground=fg_color)
        
        for line in text.split('\n'):
            tag = "default"
            if "✅" in line or "UYUMLU" in line: tag = "green"
            elif "❌" in line or "UYUMSUZ" in line: tag = "red"
            elif "⚠️" in line or "DİKKAT" in line: tag = "yellow"
            txt_widget.insert("end", line + "\n", tag)
            
        txt_widget.config(state="disabled")
        
        self.tooltip_window.update_idletasks()
        width = self.tooltip_window.winfo_reqwidth()
        height = self.tooltip_window.winfo_reqheight()
        
        pos_x = x + 15
        pos_y = y + 10
        if pos_x + width > self.tooltip_window.winfo_screenwidth(): pos_x = x - width - 15
        if pos_y + height > self.tooltip_window.winfo_screenheight(): pos_y = y - height - 10
        if pos_x < 0: pos_x = 0
        if pos_y < 0: pos_y = 0
        
        self.tooltip_window.wm_geometry(f"+{pos_x}+{pos_y}")
        self.tooltip_window.deiconify()

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        if event: self.last_tooltip_item = None

    def open_detail_window(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        item = self.tree.item(sel[0])
        vals = item['values']
        
        date = vals[0]
        bulten = vals[4]
        
        if self.full_df is not None:
            row = self.full_df[(self.full_df['date'] == date) & (self.full_df['Bülten'] == bulten)]
            if not row.empty:
                row = row.iloc[0]
                if row['Türü'] not in ['METAR', 'SPECI']:
                    return

                ref_taf = row.get('_ref_taf', '')
                detay = row.get('_detay', '')
                
                top = tk.Toplevel(self)
                top.title(f"Detaylı Analiz: {date}")
                top.geometry("1100x600")
                top.configure(bg="#2b2b2b")
                
                tk.Label(top, text=f"METAR - TAF KARŞILAŞTIRMASI ({STATION})", font=("Segoe UI", 12, "bold"), bg="#2b2b2b", fg="white").pack(pady=10)
                
                # Yan Yana Görünüm for PanedWindow
                paned = tk.PanedWindow(top, orient=tk.HORIZONTAL, bg="#2b2b2b", sashwidth=5)
                paned.pack(fill="both", expand=True, padx=10, pady=5)
                
                # SOL: METAR and Analiz Sonucu
                f_metar = tk.LabelFrame(paned, text="METAR / SPECI & ANALİZ", bg="#2b2b2b", fg="#4FC3F7", font=("Segoe UI", 10, "bold"))
                paned.add(f_metar, minsize=500)
                
                txt_metar = tk.Text(f_metar, bg="#1e1e1e", fg="white", font=("Consolas", 11), relief="flat", wrap="word", padx=10, pady=10)
                txt_metar.pack(fill="both", expand=True)
                txt_metar.insert("1.0", bulten + "\n\n" + "-"*40 + "\n" + detay)
                txt_metar.config(state="disabled")
                
                # SAĞ: Referans TAF
                f_taf = tk.LabelFrame(paned, text="REFERANS TAF", bg="#2b2b2b", fg="#E64A19", font=("Segoe UI", 10, "bold"))
                paned.add(f_taf, minsize=500)
                
                taf_text = ref_taf if ref_taf else "Uygun TAF bulunamadı."
                txt_taf = tk.Text(f_taf, bg="#1e1e1e", fg="#E64A19" if ref_taf else "#FF5252", font=("Consolas", 11, "bold"), relief="flat", wrap="word", padx=10, pady=10)
                txt_taf.pack(fill="both", expand=True)
                txt_taf.insert("1.0", taf_text)
                txt_taf.config(state="disabled")
    def adjust_column_widths(self, df):
        try:
            font = tkfont.Font(family="Segoe UI", size=10)
            header_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
            
            col_map = {
                "date": "date",
                "Türü": "Türü",
                "İstasyon": "İstasyon",
                "Uyum": "_uyum",
                "Bülten": "Bülten"
            }
            
            for col_id in self.tree["columns"]:
                df_col = col_map.get(col_id)
                heading_text = self.tree.heading(col_id, "text")
                max_w = header_font.measure(heading_text) + 25
                
                if df_col and df_col in df.columns:
                    vals = df[df_col].fillna("").astype(str).unique()
                    if len(vals) > 50: vals = sorted(vals, key=len, reverse=True)[:50]
                    for v in vals:
                        w = font.measure(v) + 20
                        if w > max_w: max_w = w
                
                if col_id == "Bülten": 
                    max_w = min(max_w, 1200)
                    max_w = max(max_w, 400)
                
                if col_id == "Uyum":
                    max_w = max(max_w, 150)
                
                self.tree.column(col_id, width=max_w)
        except Exception as e: print(f"Resize error: {e}")

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        item = self.tree.item(sel[0])
        vals = item['values']
        # Detayları bul
        bulten = vals[4]
        date = vals[0]
        
        # DataFrame'den detayı çek
        if self.full_df is not None:
            row = self.full_df[(self.full_df['date'] == date) & (self.full_df['Bülten'] == bulten)]
            if not row.empty:
                row_data = row.iloc[0]
                detay = row_data.get('_detay', '')
                ref_taf = row_data.get('_ref_taf', '')
                
                self.detail_text.config(state="normal")
                self.detail_text.delete("1.0", tk.END)
                
                # METAR
                self.detail_text.insert(tk.END, f"METAR:\n{bulten}\n", "content")
                
                # TAF
                if ref_taf:
                    self.detail_text.insert(tk.END, f"\nİLGİLİ TAF:\n{ref_taf}\n", "content")
                
                # ANALİZ
                if detay:
                    self.detail_text.insert(tk.END, "\nANALİZ DETAYI:\n", "header")
                    for line in detay.split('\n'):
                        tag = "default"
                        if "✅" in line or "UYUMLU" in line: tag = "green"
                        elif "❌" in line or "UYUMSUZ" in line: tag = "red"
                        elif "⚠️" in line or "DİKKAT" in line: tag = "yellow"
                        self.detail_text.insert(tk.END, f"{line}\n", tag)
                
                self.detail_text.config(state="disabled")

    def export_to_excel(self):
        if self.full_df is None or self.full_df.empty:
            messagebox.showwarning("Uyarı", "Dışa aktarılacak veri yok.")
            return
            
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel Dosyası", "*.xlsx")],
                title="Analiz Raporunu Kaydet"
            )
            
            if not file_path: return
            
            export_df = self.full_df.copy()
            
            # Sütunları düzenle
            cols_to_export = ["date", "Türü", "İstasyon", "Bülten", "_uyum", "_detay", "_ref_taf"]
            available_cols = [c for c in cols_to_export if c in export_df.columns]
            export_df = export_df[available_cols]
            
            rename_map = {"_uyum": "Uyum Durumu", "_detay": "Analiz Detayı", "_ref_taf": "Referans TAF"}
            export_df.rename(columns=rename_map, inplace=True)
            
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                export_df.to_excel(writer, sheet_name='Tüm Veriler', index=False)
                if "Uyum Durumu" in export_df.columns:
                    uyumsuz_df = export_df[export_df["Uyum Durumu"].str.contains("UYUMSUZ|DİKKAT", na=False)].copy()
                    if not uyumsuz_df.empty:
                        # Detayları sütunlara ayır
                        if "Analiz Detayı" in uyumsuz_df.columns:
                            split_data = uyumsuz_df["Analiz Detayı"].str.split('\n', expand=True)
                            split_data.columns = [f"Neden {i+1}" for i in range(split_data.shape[1])]
                            uyumsuz_df = pd.concat([uyumsuz_df, split_data], axis=1)
                        
                        uyumsuz_df.to_excel(writer, sheet_name='Uyumsuzluklar', index=False)
                        
            messagebox.showinfo("Başarılı", f"Rapor kaydedildi:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Exception", f"Dışa aktarma hatası: {e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()