# -*- coding: utf-8 -*-
"""
OGIMET ICAO ANALİZ - WEB ARAYÜZÜ (Streamlit)
Bu dosya, masaüstü uygulamasının web versiyonudur.
Çalıştırmak için terminale: streamlit run ogimet_webapp.py
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta, timezone
import RASATLAR
import TAF_METAR_TREND
import io
import plotly.express as px
from veri_isleme import process_data
from ayarlar import TURKEY_STATIONS

# Sayfa Ayarları
st.set_page_config(
    page_title="OGIMET ICAO ANALİZ",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Robot Modülünü Başlat
@st.cache_resource
def get_robot():
    return TAF_METAR_TREND.HavacilikRobotModulu()

robot = get_robot()

def analyze_dataframe(df):
    """DataFrame üzerindeki METAR ve TAF'ları analiz eder."""
    df["_uyum"] = ""
    df["_detay"] = ""
    df["_ref_taf"] = ""
    
    tafs = df[df['Türü'] == 'TAF'].sort_values(by='_dt')
    if tafs.empty: return df

    last_taf_text = None
    consecutive_counts = {"Rüzgar": 0, "Görüş": 0, "ceil": 0}

    # Kronolojik sıra (Eskiden yeniye)
    for idx, row in df.sort_values(by='_dt', ascending=True).iterrows():
        if row['Türü'] in ['METAR', 'SPECI']:
            metar_dt = row['_dt']
            relevant_tafs = tafs[tafs['_dt'] <= metar_dt]
            
            if not relevant_tafs.empty:
                target_row = relevant_tafs.iloc[-1]
                last_taf = target_row['Bülten']
                taf_dt = target_row['_dt']

                if last_taf != last_taf_text:
                    consecutive_counts = {k: 0 for k in consecutive_counts}
                    last_taf_text = last_taf

                if (metar_dt - taf_dt) > timedelta(hours=3): continue

                df.at[idx, "_ref_taf"] = last_taf
                
                # TAF Zamanı
                regex_period = r'(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-4])/(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-4])'
                t_valid = re.search(r'\b' + regex_period + r'\b', last_taf)
                taf_zaman = t_valid.group(0) if t_valid else "0000/0000"

                # FM Gruplarını dikkate alarak aktif bölümü seç
                active_taf = last_taf
                try:
                    best_change_start = -1
                    
                    # Sadece FM grupları ana TAF'ı sıfırlar. BECMG/TEMPO trend olarak işlenir.
                    change_pattern = r'\bFM(?P<fm>\d{6})\b'
                    
                    for m in re.finditer(change_pattern, last_taf):
                        start_dt = None
                        try:
                            if m.group('fm'):
                                time_code = m.group('fm')
                                day, hour, minute = int(time_code[0:2]), int(time_code[2:4]), int(time_code[4:6])
                                start_dt = taf_dt.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                            
                            if start_dt:
                                # Ay geçişi kontrolü
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
                except Exception as e: pass

                # Trend
                trend_part = ""
                tr_m = re.search(r'\b(BECMG|TEMPO|NOSIG)\b', row['Bülten'])
                if tr_m: trend_part = row['Bülten'][tr_m.start():]

                skor, status_code, reasons = robot.analiz_et(active_taf, row['Bülten'], trend_part, taf_zaman)

                # Ardışık Hata Kontrolü
                current_cats = set()
                for r in reasons:
                    if "Rüzgar" in r: current_cats.add("Rüzgar")
                    if "Görüş" in r: current_cats.add("Görüş")
                    if "ceil" in r or "Dikey" in r or "Bulut" in r: current_cats.add("ceil")
                
                amd_msgs = []
                for cat in consecutive_counts:
                    if cat in current_cats:
                        consecutive_counts[cat] += 1
                        if consecutive_counts[cat] >= 3:
                            amd_msgs.append(f"{cat} ({consecutive_counts[cat]}. kez)")
                    else:
                        consecutive_counts[cat] = 0

                icon = ""
                if "UYUMSUZ" in status_code: icon = "❌ UYUMSUZ"
                elif "DİKKAT" in status_code: icon = "⚠️ DİKKAT"
                elif "UYUMLU" in status_code: icon = "✅ UYUMLU"
                
                df.at[idx, "_uyum"] = icon
                
                detay_str = ""
                if "UYUMSUZ" in status_code:
                    detay_str = "**1- UYUMSUZLUK NEDENİ:**\n" + "\n".join([f"- {r}" for r in reasons])
                    detay_str += "\n\n**2- TREND KONTROLÜ:**\n- Trend ile de uyum sağlanamadı veya Trend yok."
                    detay_str += "\n\n**3- SONUÇ:**\n- ❌ **UYUMSUZ**"
                elif "DİKKAT" in status_code:
                    detay_str = "**1- UYUMSUZLUK NEDENİ (Ana METAR):**\n" + "\n".join([f"- {r}" for r in reasons])
                    if any("TAF Trend" in r for r in reasons):
                        detay_str += "\n\n**2- TREND KONTROLÜ:**\n- ✅ TAF Trendi ile erken uyum (Buffer)."
                        detay_str += "\n\n**3- SONUÇ:**\n- ⚠️ **DİKKAT** (TAF Trendi ile uyumlu)"
                    else:
                        detay_str += "\n\n**2- TREND KONTROLÜ:**\n- ✅ METAR Trendi TAF limitlerine giriyor."
                        detay_str += "\n\n**3- SONUÇ:**\n- ⚠️ **DİKKAT** (METAR Trendi ile uyumlu)"
                elif "UYUMLU" in status_code:
                    detay_str = "✅ **UYUMLU**"

                if amd_msgs:
                    detay_str += f"\n\n👉 KRİTİK TAVSİYE:\n• TAF AMD YAYINLANMALI!\n  Aynı sapma 3+ kez tekrarlandı: {', '.join(amd_msgs)}"
                
                df.at[idx, "_detay"] = detay_str

    return df

# --- ARAYÜZ ---
st.sidebar.title("Ayarlar")
station = st.sidebar.text_input("ICAO Kodu", "LTAN")
wmo = st.sidebar.text_input("WMO Kodu", "17244")

today = datetime.now()
start_date = st.sidebar.date_input("Başlangıç", today - timedelta(days=1))
end_date = st.sidebar.date_input("Bitiş", today)

filter_opt = st.sidebar.selectbox("Filtrele", ["HEPSİ", "❌ UYUMSUZ", "⚠️ DİKKAT", "✅ UYUMLU"])

# Session State (Veri Kalıcılığı)
if "analiz_sonucu" not in st.session_state:
    st.session_state.analiz_sonucu = None

if st.sidebar.button("VERİ ÇEK & ANALİZ ET", type="primary"):
    with st.spinner('Veriler Ogimet üzerinden çekiliyor...'):
        s_dt = datetime.combine(start_date, datetime.min.time())
        e_dt = datetime.combine(end_date, datetime.max.time())
        
        try:
            lines = RASATLAR.fetch(s_dt, e_dt, station=station, wmo_id=wmo)
            if not lines:
                st.error("Veri bulunamadı.")
                st.session_state.analiz_sonucu = None
            else:
                df = process_data(lines, station, wmo, ref_dt=e_dt)
                df = analyze_dataframe(df)
                st.session_state.analiz_sonucu = df
                            
        except Exception as e:
            st.error(f"Bir hata oluştu: {e}")
            st.session_state.analiz_sonucu = None

if st.session_state.analiz_sonucu is not None:
    df = st.session_state.analiz_sonucu.copy()
    
    # Filtreleme
    if filter_opt != "HEPSİ":
        df = df[df["_uyum"].str.contains(filter_opt.split()[1], na=False)]
    
    st.success(f"Toplam {len(df)} kayıt listeleniyor.")
    
    # --- PASTA GRAFİĞİ ---
    if not df.empty:
        st.subheader("Analiz Dağılımı")
        
        # Grafik için etiketleri temizle (Emojileri kaldır)
        df_chart = df.copy()
        df_chart["Durum_Temiz"] = df_chart["_uyum"].apply(lambda x: "UYUMSUZ" if "UYUMSUZ" in str(x) else ("DİKKAT" if "DİKKAT" in str(x) else ("UYUMLU" if "UYUMLU" in str(x) else None)))
        df_chart = df_chart.dropna(subset=["Durum_Temiz"])
        
        uyum_counts = df_chart["Durum_Temiz"].value_counts().reset_index()
        uyum_counts.columns = ["Durum", "Adet"]
        
        color_map = {
            "UYUMLU": "#66BB6A",
            "DİKKAT": "#FFEE58",
            "UYUMSUZ": "#EF5350"
        }
        
        col_chart, col_stats = st.columns([2, 1])
        with col_chart:
            fig = px.pie(uyum_counts, values='Adet', names='Durum', 
                         color='Durum', color_discrete_map=color_map,
                         hole=0.4, title="Analiz Sonuç Dağılımı")
            fig.update_traces(textinfo='value+percent', textfont_size=12)
            fig.update_layout(height=350, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        with col_stats:
            st.dataframe(uyum_counts, hide_index=True, use_container_width=True)
    # ---------------------
    
    # --- EXCEL İNDİRME BUTONU ---
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Analiz Raporu')
    
    st.download_button(
        label="📥 Excel Olarak İndir",
        data=buffer.getvalue(),
        file_name=f"ogimet_analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    # ---------------------------
    
    # Tablo Gösterimi
    st.dataframe(
        df[["date", "Türü", "_uyum", "Bülten"]],
        column_config={
            "date": "Tarih",
            "Türü": "Tip",
            "_uyum": "Trend Uyum",
            "Bülten": st.column_config.TextColumn("Bülten", width="large")
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Detaylar
    st.subheader("Detaylı Analiz Raporu")
    for _, row in df.iterrows():
        if row["_detay"]:
            label = f"{row['_uyum']} | {row['date']} | {row['Türü']}"
            with st.expander(label, expanded=("UYUMSUZ" in row["_uyum"])):
                c1, c2 = st.columns(2)
                with c1:
                    st.caption("METAR / SPECI")
                    st.code(row['Bülten'], language="text")
                with c2:
                    st.caption("REFERANS TAF")
                    st.code(row.get('_ref_taf', 'TAF Bulunamadı'), language="text")
                
                if "UYUMSUZ" in row["_uyum"]:
                    st.error(row["_detay"], icon="❌")
                elif "DİKKAT" in row["_uyum"]:
                    st.warning(row["_detay"], icon="⚠️")
                elif "UYUMLU" in row["_uyum"]:
                    st.success(row["_detay"], icon="✅")
                else:
                    st.info(row["_detay"])