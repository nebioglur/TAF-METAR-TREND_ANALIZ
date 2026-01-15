"""
OGIMET PROJE BİLGİ VE YARDIM MODÜLÜ
Bu dosya, Ogimet analiz projesindeki dosyaların durumunu ve
gerekli kütüphanelerin yüklü olup olmadığını kontrol eder.
"""
import os
import sys

def proje_yapisi():
    print("="*70)
    print("OGIMET ICAO ANALİZ PROJESİ - DOSYA YAPISI")
    print("="*70)
    
    files = {
        "ogimet_icao_analiz.py": {
            "desc": "🔴 ANA PROGRAM\n    -> Ogimet verilerini çeker, analiz eder ve arayüzü yönetir.",
            "status": "required"
        },
        "RASATLAR.py": {
            "desc": "🌐 VERİ ÇEKME MODÜLÜ\n    -> Ogimet sitesinden ham verileri indiren modül.",
            "status": "required"
        },
        "TAF_METAR_TREND.py": {
            "desc": "🧠 ANALİZ MOTORU\n    -> ICAO kurallarına göre raporları denetleyen modül.",
            "status": "required"
        },
        "veri_isleme.py": {
            "desc": "⚙️ VERİ İŞLEME\n    -> Ham metin verilerini tabloya dönüştüren yardımcı modül.",
            "status": "required"
        },
        "ayarlar.py": {
            "desc": "🛠️ AYARLAR\n    -> İstasyon listesi ve harita koordinatlarını içeren dosya.",
            "status": "required"
        },
        "exe_olustur.py": {
            "desc": "📦 EXE OLUŞTURUCU\n    -> Projeyi tek tıklamayla .exe dosyasına çeviren araç.",
            "status": "utility"
        },
        "bilgi.py": {
            "desc": "ℹ️ BİLGİ EKRANI\n    -> Bu dosya. Sistem kontrollerini yapar.",
            "status": "utility"
        },
        "ANDROID_BILGI.txt": {
            "desc": "📱 ANDROID NOTLARI\n    -> APK oluşturma ve mobil kullanım hakkında bilgi.",
            "status": "info"
        },
        "requirements.txt": {
            "desc": "📋 GEREKSİNİMLER\n    -> Streamlit Cloud ve web arayüzü için kütüphane listesi.",
            "status": "required"
        }
    }
    
    mevcut_dizin = os.path.dirname(os.path.abspath(__file__))
    
    print(f"{'DOSYA ADI':<25} | {'DURUM':<10} | {'AÇIKLAMA'}")
    print("-" * 70)
    
    for f, info in files.items():
        path = os.path.join(mevcut_dizin, f)
        exists = os.path.exists(path)
        
        durum_ikon = "✅ MEVCUT" if exists else "❌ EKSİK"
        
        print(f"{f:<25} | {durum_ikon:<10}")
        print(f"{info['desc']}")
        print("-" * 70)

def kutuphane_kontrolu():
    print("\n" + "="*70)
    print("KÜTÜPHANE (IMPORT) KONTROLÜ")
    print("="*70)
    
    libs = [
        ("requests", "Veri çekmek için gerekli"),
        ("bs4", "HTML ayrıştırma (BeautifulSoup) için gerekli"),
        ("tkinter", "Arayüz (GUI) için gerekli"),
        ("pandas", "Veri işleme ve Excel için gerekli"),
        ("tkcalendar", "Tarih seçici takvim için gerekli"),
        ("openpyxl", "Excel çıktısı (xlsx) için gerekli"),
        ("pyinstaller", "EXE oluşturmak için gerekli")
    ]
    
    missing = []
    
    for lib, desc in libs:
        try:
            if lib == "bs4": 
                import bs4
            elif lib == "tkinter": 
                import tkinter
            elif lib == "tkcalendar":
                import tkcalendar
            elif lib == "pyinstaller":
                import PyInstaller
            else:
                __import__(lib)
            print(f"✅ {lib:<15} : Yüklü ({desc})")
        except ImportError:
            print(f"❌ {lib:<15} : YÜKLÜ DEĞİL! ({desc})")
            missing.append(lib)
            
    if missing:
        print("\n" + "!"*70)
        print("⚠️ EKSİK KÜTÜPHANELER TESPİT EDİLDİ")
        print("Aşağıdaki komutu terminalde çalıştırarak yükleyebilirsiniz:")
        print("-" * 70)
        
        install_list = [m for m in missing]
            
        install_str = " ".join(install_list)
        print(f"pip install {install_str}")
        print("!"*70)
    else:
        print("\n✅ Tüm gerekli kütüphaneler yüklü.")

if __name__ == "__main__":
    proje_yapisi()
    kutuphane_kontrolu()
    input("\nÇıkmak için Enter'a basın...")