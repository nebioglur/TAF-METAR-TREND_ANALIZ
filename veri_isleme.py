# -*- coding: utf-8 -*-
import re
import pandas as pd
from datetime import datetime, timezone

def process_data(lines, station_code, wmo_id, ref_dt=None):
    if ref_dt is None: ref_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    data = []
    current_record = None

    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Ogimet HTML kalıntılarını temizle (TAF sonuna yapışan HTML tagleri)
        if '=' in line:
            line = line.split('=')[0] + '='
        
        # HTML satırlarını atla
        if line.startswith(("<", "&lt;", "&nbsp;", "window.", "var ", "function")):
            continue
        if any(x in line for x in ["índice de calor", "cookieconsent", "humedad relativa", "precipitación"]):
            continue
        
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
                    ref_dt = dt # Referans tarihi güncelle (Bağlamı koru)
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
                        # Referans tarihe en yakın tarihi bul (Ay geçişlerini yönet)
                        m_day, m_hour, m_min = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        candidates = []
                        for offset in [0, -1, 1]:
                            y, m_month = ref_dt.year, ref_dt.month + offset
                            if m_month < 1: m_month += 12; y -= 1
                            elif m_month > 12: m_month -= 12; y += 1
                            try: candidates.append(ref_dt.replace(year=y, month=m_month, day=m_day, hour=m_hour, minute=m_min, second=0, microsecond=0))
                            except: pass
                        dt_sort = min(candidates, key=lambda x: abs(x - ref_dt)) if candidates else ref_dt
                        dt_str = dt_sort.strftime("%d.%m.%Y %H:%M")
                    except: pass
            
            elif len(parts) > 1 and len(parts[0]) == 4 and parts[0].isalpha() and parts[1].endswith('Z'):
                turu = "TAF" if ("TAF" in line or "/" in line) else "METAR"
                content = line
                m = re.search(r'\b(\d{2})(\d{2})(\d{2})Z\b', content)
                if m:
                    try:
                        # Referans tarihe en yakın tarihi bul
                        m_day, m_hour, m_min = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        candidates = []
                        for offset in [0, -1, 1]:
                            y, m_month = ref_dt.year, ref_dt.month + offset
                            if m_month < 1: m_month += 12; y -= 1
                            elif m_month > 12: m_month -= 12; y += 1
                            try: candidates.append(ref_dt.replace(year=y, month=m_month, day=m_day, hour=m_hour, minute=m_min, second=0, microsecond=0))
                            except: pass
                        dt_sort = min(candidates, key=lambda x: abs(x - ref_dt)) if candidates else ref_dt
                        dt_str = dt_sort.strftime("%d.%m.%Y %H:%M")
                    except: pass

            current_record = {"date": dt_str, "Türü": turu, "İstasyon": station_code if turu!="SİNOPTİK" else wmo_id, "Bülten": content, "_dt": dt_sort}
        
        else:
            # continue satırı (TAF vb. for)
            if current_record:
                current_record["Bülten"] += " " + line

    if current_record:
        data.append(current_record)
    
    if not data:
        return pd.DataFrame(columns=["date", "Türü", "İstasyon", "Bülten", "_dt"])
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df[df["date"] != "---"]
        df = df.drop_duplicates(subset=['Türü', 'Bülten'])
        df = df.sort_values(by="_dt", ascending=False)
    return df