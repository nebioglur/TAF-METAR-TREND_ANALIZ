import re
from datetime import datetime, timedelta, timezone

# =============================================================================
# HAVACILIK ROBOT MODÜLÜ (ANALİZ MOTORU)
# =============================================================================
class HavacilikRobotModulu:
    """
    TAF ve METAR raporlarını ayrıştıran ve ICAO kurallarına göre
    uyumluluk analizi yapan ana sınıf.
    """
    def __init__(self):
        self.esikler_ruyet = [150, 350, 600, 800, 1500, 3000, 5000]
        self.esikler_tavan = [100, 200, 500, 1000, 1500]
        self.esikler_vv = [100, 200, 500, 1000]
        self.kritik_hadiseler = [r'TS', r'FZ', r'SQ', r'FC', r'FG', r'SS', r'DS', r'(?<!-)RA', r'(?<!-)SN', r'GR']

    def zaman_uygun_mu(self, taf_header, metar_time_code, ref_date=None):
        """
        TAF geçerlilik aralığı ile METAR saatini kıyaslar.
        UTC zaman dilimi ve gün geçişlerini (ay sonu dahil) dikkate alır.
        """
        try:
            # TAF: DDHH/DDHH
            t_match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', taf_header)
            if not t_match: return False
            
            ts_d, ts_h = int(t_match.group(1)), int(t_match.group(2))
            te_d, te_h = int(t_match.group(3)), int(t_match.group(4))
            
            # METAR: DDHHMMZ
            m_match = re.search(r'(\d{2})(\d{2})(\d{2})Z', metar_time_code)
            if not m_match: return False
            
            m_d, m_h, m_m = int(m_match.group(1)), int(m_match.group(2)), int(m_match.group(3))
            
            now = ref_date if ref_date else datetime.utcnow()
            now = ref_date if ref_date else datetime.now(timezone.utc).replace(tzinfo=None)
            
            def safe_dt(y, m, d, h, minute=0):
                # Ayın 1'inden başlayıp gün ekleyerek tarih oluştur (Ay sonu taşmalarını önler)
                base = datetime(y, m, 1)
                return base + timedelta(days=d-1, hours=h, minutes=minute)

            # TAF Başlangıç (En yakın tarih tahmini)
            candidates = []
            for offset in [-1, 0, 1]:
                y, m = now.year, now.month + offset
                if m < 1: m += 12; y -= 1
                elif m > 12: m -= 12; y += 1
                try:
                    candidates.append(safe_dt(y, m, ts_d, ts_h))
                except: continue
            
            if not candidates: return False
            t_start = min(candidates, key=lambda x: abs(x - now))
            
            # TAF Bitiş
            y_end, m_end = t_start.year, t_start.month
            if te_d < ts_d: # Gün devri (Ay sonu)
                m_end += 1
                if m_end > 12: m_end = 1; y_end += 1
            
            t_end = safe_dt(y_end, m_end, te_d, te_h)
            
            # METAR (TAF aralığına giren aday)
            m_candidates = []
            for offset in [-1, 0, 1]:
                y, m = t_start.year, t_start.month + offset
                if m < 1: m += 12; y -= 1
                elif m > 12: m -= 12; y += 1
                try:
                    m_candidates.append(safe_dt(y, m, m_d, m_h, m_m))
                except: continue
                
            for m_dt in m_candidates:
                if t_start <= m_dt <= t_end:
                    return True
                    
            return False
        except Exception:
            return False

    def _is_trend_active(self, trend_header, metar_time_code, trend_type, ref_date=None):
        """Trendin (BECMG/TEMPO) belirtilen METAR saati için aktif olup olmadığını kontrol eder."""
        try:
            # Trend Header: DDHH/DDHH
            t_match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', trend_header)
            if not t_match: return True 
            
            ts_d, ts_h = int(t_match.group(1)), int(t_match.group(2))
            te_d, te_h = int(t_match.group(3)), int(t_match.group(4))
            
            # METAR: DDHHMMZ
            m_match = re.search(r'(\d{2})(\d{2})(\d{2})Z', metar_time_code)
            if not m_match: return True
            
            m_d, m_h, m_m = int(m_match.group(1)), int(m_match.group(2)), int(m_match.group(3))
            
            now = ref_date if ref_date else datetime.utcnow()
            now = ref_date if ref_date else datetime.now(timezone.utc).replace(tzinfo=None)
            
            def safe_dt(y, m, d, h, minute=0):
                base = datetime(y, m, 1)
                return base + timedelta(days=d-1, hours=h, minutes=minute)

            # Trend Başlangıç
            candidates = []
            for offset in [-1, 0, 1]:
                y, m = now.year, now.month + offset
                if m < 1: m += 12; y -= 1
                elif m > 12: m -= 12; y += 1
                try:
                    candidates.append(safe_dt(y, m, ts_d, ts_h))
                except: continue
            
            if not candidates: return True
            t_start = min(candidates, key=lambda x: abs(x - now))
            
            # Trend Bitiş
            y_end, m_end = t_start.year, t_start.month
            if te_d < ts_d: 
                m_end += 1
                if m_end > 12: m_end = 1; y_end += 1
            
            t_end = safe_dt(y_end, m_end, te_d, te_h)
            
            # METAR Zamanı
            m_candidates = []
            for offset in [-1, 0, 1]:
                y, m = t_start.year, t_start.month + offset
                if m < 1: m += 12; y -= 1
                elif m > 12: m -= 12; y += 1
                try:
                    m_candidates.append(safe_dt(y, m, m_d, m_h, m_m))
                except: continue
            
            if not m_candidates: return True
            m_dt = min(m_candidates, key=lambda x: abs(x - t_start))

            if trend_type == 'TEMPO':
                return t_start <= m_dt <= t_end
            elif trend_type == 'BECMG':
                return m_dt >= t_start
            
            return True
        except:
            return True

    def check_threshold(self, v1, v2, thresholds):
        """İki değer arasında (örn. Görüş) limit geçişi olup olmadığını kontrol eder."""
        low, high = min(v1, v2), max(v1, v2)
        for t in thresholds:
            if low < t <= high: return True
        return False

    def _parse_wind(self, code):
        """Metin içinden rüzgar yönü, hızı ve hamlesini (gust) ayıklar."""
        # Önce Gust ve KT içeren tam formatı dene
        match = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b', code)
        if match:
            yon = 0 if match.group(1) == "VRB" else int(match.group(1))
            hiz = int(match.group(2))
            gust = int(match.group(3)) if match.group(3) else 0
            return yon, hiz, gust
            
        # Fallback: Eski basit format (Gust yok varsayılır)
        match = re.search(r'\b(\d{3}|VRB)(\d{2,3})KT\b', code)
        if match:
            yon = 0 if match.group(1) == "VRB" else int(match.group(1))
            hiz = int(match.group(2))
            return yon, hiz, 0
            
        return None

    def _parse_ceiling(self, code):
        """Metin içinden bulut tavanını (Ceiling) veya Dikey Görüşü (VV) ayıklar."""
        if any(x in code for x in ['CAVOK', 'SKC', 'NSC', 'CLR']):
            return 9999, False
        
        vv = re.search(r'VV(\d{3})', code)
        if vv: return int(vv.group(1)) * 100, True
        
        clouds = re.findall(r'(BKN|OVC)(\d{3})', code)
        if clouds:
            return min([int(c[1]) * 100 for c in clouds]), False
            
        return None

    def _parse_cloud_layers(self, code):
        """Tüm bulut katmanlarını (Tip, Yükseklik) listesi olarak döner."""
        layers = []
        matches = re.findall(r'\b(FEW|SCT|BKN|OVC|VV)(\d{3})\b', code)
        for m in matches:
            layers.append((m[0], int(m[1])*100))
        return layers

    def _parse_visibility(self, code):
        """Metin içinden görüş mesafesini (Visibility) ayıklar."""
        if 'CAVOK' in code:
            return 10000
            
        match = re.search(r'\b(\d{4})\b', code)
        if match:
            return int(match.group(1))
            
        return None

    def _extract_body(self, text):
        """Rapor metnini rüzgar grubundan itibaren alır (Başlıkları ve zamanı atlar)."""
        # Rüzgar deseni: 3 hane yön (veya VRB) + 2/3 hane hız + (opsiyonel G + hamle) + KT
        match = re.search(r'\b(\d{3}|VRB)\d{2,3}(?:G\d{2,3})?KT\b', text)
        if match:
            return text[match.start():]
        return text

    def _compare_values(self, t_vals, m_vals):
        """TAF/Trend değerleri ile METAR değerlerini karşılaştırır ve hataları listeler."""
        t_wind, t_vis, t_cig = t_vals
        m_wind, m_vis, m_cig = m_vals
        errors = []

        # Rüzgar
        t_yon, t_hiz, t_gust = t_wind
        m_yon, m_hiz, m_gust = m_wind
        
        if abs(t_hiz - m_hiz) >= 10:
            errors.append(f"Rüzgar hızı farkı >= 10KT (Beklenen:{t_hiz} vs METAR:{m_hiz})")
        
        yon_f = abs(t_yon - m_yon)
        if yon_f > 180: yon_f = 360 - yon_f
        if yon_f >= 60 and (t_hiz >= 10 or m_hiz >= 10):
            errors.append("Rüzgar yön farkı >= 60 derece")

        # Görüş
        low_v = min(t_vis, m_vis)
        high_v = max(t_vis, m_vis)
        for th in self.esikler_ruyet:
            if low_v < th <= high_v:
                errors.append(f"Görüş değişimi limit dışı (Beklenen:{t_vis}m vs METAR:{m_vis}m)")
                break

        # Tavan
        t_c_h, t_is_vv = t_cig
        m_c_h, m_is_vv = m_cig
        low = min(t_c_h, m_c_h)
        high = max(t_c_h, m_c_h)
        for th in self.esikler_tavan:
            if low < th <= high:
                label = "Dikey Görüş" if (t_is_vv or m_is_vv) else "Tavan"
                errors.append(f"{label} değişimi limit dışı (Beklenen:{t_c_h} vs METAR:{m_c_h})")
                break
                
        return errors

    def _parse_all_taf_trends(self, text):
        """TAF metni içindeki tüm BECMG ve TEMPO gruplarını ayıklar."""
        trends = []
        # BECMG veya TEMPO kelimelerine göre böl
        parts = re.split(r'\b(BECMG|TEMPO)\b', text)
        # parts[0] ana metin, sonraki her ikili (Tip, İçerik) şeklindedir
        for i in range(1, len(parts), 2):
            trend_type = parts[i]
            content = parts[i+1]
            
            # Zaman grubunu ayıkla (DDHH/DDHH)
            time_str = None
            time_match = re.search(r'\b\d{4}/\d{4}\b', content)
            if time_match:
                time_str = time_match.group(0)
                # Zaman grubunu içerikten sil ki Görüş (Visibility) ile karışmasın
                content = content.replace(time_str, "")
            
            w = self._parse_wind(content)
            v = self._parse_visibility(content)
            c = self._parse_ceiling(content)
            trends.append({'type': trend_type, 'time': time_str, 'wind': w, 'vis': v, 'cig': c})
        return trends

    def analiz_et(self, taf_raw, metar_raw, trend_raw, taf_zaman="0412/0512", ref_date=None):
        """Modülün ana denetleme fonksiyonu. TAF ve METAR'ı karşılaştırır."""
        
        if ref_date is None: ref_date = datetime.utcnow()

        if not taf_raw or not metar_raw:
            return 0, "VERİ BULUNAMADI", ["TAF veya METAR verisi eksik."]

        # Başlıkları temizle (Rüzgar grubundan başlat)
        taf_body = self._extract_body(taf_raw)
        metar_body = self._extract_body(metar_raw)
        
        # 1. ZAMAN KONTROLÜ
        metar_time_match = re.search(r'\b\d{6}Z\b', metar_raw)
        # if metar_time_match:
        #     # Kullanıcı isteği: TAF geçerlilik periyoduna bakılmaksızın analiz yap.
        #     if not self.zaman_uygun_mu(taf_zaman, metar_time_match.group(0), ref_date):
        #         msg = f"METAR saati ({metar_time_match.group(0)}) TAF aralığı ({taf_zaman}) dışında."
        #         print(f"ZAMAN HATASI: {msg}")
        #         # return 0, "ZAMAN UYUMSUZLUĞU", [msg]

        # --- PARSE METAR ---
        m_wind = self._parse_wind(metar_body)
        if m_wind is None: 
            return 0, "VERİ BULUNAMADI", ["METAR rüzgar verisi okunamadı."]
        
        m_vis = self._parse_visibility(metar_body)
        if m_vis is None: m_vis = 10000
        
        m_cig = self._parse_ceiling(metar_body)
        if m_cig is None: m_cig = (9999, False)
        
        metar_vals = (m_wind, m_vis, m_cig)

        # --- PARSE TAF ---
        t_wind = self._parse_wind(taf_body)
        if t_wind is None: 
            return 0, "VERİ BULUNAMADI", ["TAF rüzgar verisi okunamadı."]
        
        t_vis = self._parse_visibility(taf_body)
        if t_vis is None: t_vis = 10000
        
        t_cig = self._parse_ceiling(taf_body)
        if t_cig is None: t_cig = (9999, False)
        
        taf_vals = (t_wind, t_vis, t_cig)
        
        # --- COMPARE TAF vs METAR ---
        errors = self._compare_values(taf_vals, metar_vals)
        
        if not errors:
            return 100, "UYUMLU", []
        
        # --- TAF İÇİNDEKİ TRENDLERİ (BECMG/TEMPO) KONTROL ET ---
        # Eğer ana TAF ile uyuşmazlık varsa, belki TAF içindeki bir BECMG/TEMPO ile uyumludur.
        taf_trends = self._parse_all_taf_trends(taf_body)
        for tr in taf_trends:
            # Zaman kontrolü
            if tr['time'] and metar_time_match:
                if not self._is_trend_active(tr['time'], metar_time_match.group(0), tr['type'], ref_date):
                    continue

            # Trend içinde değer varsa onu kullan, yoksa ana TAF değerini koru (Persistence)
            eff_wind = tr['wind'] if tr['wind'] is not None else t_wind
            eff_vis = tr['vis'] if tr['vis'] is not None else t_vis
            eff_cig = tr['cig'] if tr['cig'] is not None else t_cig
            
            # Bu kombinasyonla tekrar karşılaştır
            tr_errors = self._compare_values((eff_wind, eff_vis, eff_cig), metar_vals)
            if not tr_errors:
                return 100, "UYUMLU (TAF Trend)", []

        # Hala hata varsa, METAR Trendine bak (Aşağıdaki mevcut kod)
        if not errors:
            return 100, "UYUMLU", []
        

        # --- ANALYZE METAR TREND ---
        if trend_raw:
            # Parse METAR Trend
            # Use METAR main values as fallback (Persistence)
            w = self._parse_wind(trend_raw)
            mt_wind = w if w is not None else m_wind
            
            v = self._parse_visibility(trend_raw)
            mt_vis = v if v is not None else m_vis
            
            c = self._parse_ceiling(trend_raw)
            mt_cig = c if c is not None else m_cig
            
            metar_trend_vals = (mt_wind, mt_vis, mt_cig)
            
            # Compare TAF (Expected) vs METAR Trend (Forecasted Observation)
            trend_errors = self._compare_values(taf_vals, metar_trend_vals)
            
            if not trend_errors:
                return 50, "DİKKAT", errors

            return 0, "UYUMSUZ", errors + trend_errors
            
        return 0, "UYUMSUZ", errors

# --- MODÜL KULLANIMI ---
if __name__ == "__main__":
    robot = HavacilikRobotModulu()
    # Örnek: TAF 4. gün 12:00-05:00 arası geçerli. METAR 4. gün 13:30.
    
    print("--- ZAMAN KONTROL TESTLERİ (BECMG/TEMPO) ---")
    # Test Senaryoları: (Trend Header, METAR Time, Type, Ref Date, Beklenen Sonuç)
    test_cases = [
        ("1012/1014", "101300Z", "TEMPO", datetime(2024,10,10,13,0), True),  # İçinde
        ("1012/1014", "101100Z", "TEMPO", datetime(2024,10,10,11,0), False), # Önce
        ("1012/1014", "101500Z", "TEMPO", datetime(2024,10,10,15,0), False), # Sonra
        ("1012/1014", "101300Z", "BECMG", datetime(2024,10,10,13,0), True),  # Değişim sırasında
        ("1012/1014", "101500Z", "BECMG", datetime(2024,10,10,15,0), True),  # Değişimden sonra (Kalıcı)
        ("1012/1014", "101100Z", "BECMG", datetime(2024,10,10,11,0), False), # Değişimden önce
        # Ay Geçişi
        ("3123/0101", "312330Z", "TEMPO", datetime(2023,12,31,23,30), True), # Yılbaşı gecesi
        ("3123/0101", "010030Z", "TEMPO", datetime(2024,1,1,0,30), True),    # Yeni yıl sabahı
    ]
    
    for t_head, m_time, t_type, ref, exp in test_cases:
        res = robot._is_trend_active(t_head, m_time, t_type, ref_date=ref)
        status = "✅ GEÇTİ" if res == exp else f"❌ KALDI (Beklenen: {exp})"
        print(f"{status} | {t_type} {t_head} vs {m_time} | Ref: {ref} -> Sonuç: {res}")

    print("\n--- TAM ANALİZ TESTİ ---")
    skor, durum, neden = robot.analiz_et(
        "TAF 0412/0512 20010KT", 
        "METAR 041330Z 20022KT", 
        "BECMG 20010KT"
        "BECMG 20010KT",
        ref_date=datetime(2024,10,4,13,30)
    )
    print(f"Robot Skoru: %{skor} | Durum: {durum}")