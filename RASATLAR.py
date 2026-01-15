# -*- coding: utf-8 -*-
"""
RASATLAR.py
Ogimet.com üzerinden METAR/TAF verilerini çeker.
Requests + BeautifulSoup kullanır.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime

def fetch(start_dt, end_dt, station="LTAN", wmo_id=None, timeout=30):
    """
    Ogimet.com üzerinden tarih aralığına göre verileri çeker.
    """
    
    # Hedef istasyon (ICAO öncelikli)
    target = station if station else wmo_id
    if not target: return []
    
    # Ogimet URL yapısı (display_metars2.php daha güvenilirdir)
    url = "https://www.ogimet.com/display_metars2.php"
    
    # Parametreler
    params = {
        "lang": "en",
        "lugar": target,
        "tipo": "ALL",  # METAR ve TAF
        "ord": "REV",   # Yeniden eskiye sırala
        "nil": "NO",    # Boş kayıtları gösterme
        "fmt": "html",  # HTML formatı (Daha güvenilir parsing için)
        "ano": start_dt.year,
        "mes": f"{start_dt.month:02d}",
        "day": f"{start_dt.day:02d}",
        "hora": f"{start_dt.hour:02d}",
        "min": f"{start_dt.minute:02d}",
        "anof": end_dt.year,
        "mesf": f"{end_dt.month:02d}",
        "dayf": f"{end_dt.day:02d}",
        "horaf": f"{end_dt.hour:02d}",
        "minf": f"{end_dt.minute:02d}",
        "send": "send"
    }
    
    print(f"DEBUG: Ogimet İsteği Başlatılıyor -> {target} ({start_dt.strftime('%d.%m.%Y')} - {end_dt.strftime('%d.%m.%Y')})")
    
    # Tarayıcı gibi görünmek için Header ekle
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout, verify=False)
        print(f"DEBUG: Sunucu Yanıt Kodu: {response.status_code} | İçerik Boyutu: {len(response.text)} byte")
        
        if response.status_code != 200:
            print(f"HATA: Ogimet sunucusu {response.status_code} kodu döndü.")
            return []
            
        # HTML yanıtını ayrıştır
        soup = BeautifulSoup(response.text, "html.parser")
        
        lines = []
        pres = soup.find_all("pre")
        
        if not pres:
            print("DEBUG: UYARI - HTML içinde <pre> etiketi bulunamadı (Veri yok veya format değişmiş).")
            # Hata ayıklama için yanıtın başını yazdır
            print(f"DEBUG: Yanıt Başlangıcı: {response.text[:200]}...")
            
        for pre in pres:
            lines.extend(pre.get_text().splitlines())

        print(f"DEBUG: Toplam {len(lines)} satır veri çekildi.")
        data = []
        for l in lines:
            l = l.strip()
            if l and not l.startswith("#"):
                data.append(l)
            
        # --- SYNOP VERİLERİ (Eksik Kısım Eklendi) ---
        if wmo_id:
            try:
                url_synop = "https://www.ogimet.com/display_synops2.php"
                params_synop = params.copy()
                params_synop["lugar"] = wmo_id
                params_synop["fmt"] = "txt"
                r2 = requests.get(url_synop, params=params_synop, headers=headers, timeout=timeout, verify=False)
                
                if r2.ok:
                    for line in r2.text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            data.append(line)
            except Exception as e:
                print(f"Ogimet SYNOP çekme hatası: {e}")

        return data

    except Exception as e:
        print(f"Ogimet veri çekme hatası: {e}")
        return []
