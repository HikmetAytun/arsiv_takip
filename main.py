"""
Arşiv Takip Sistemi — Komut satırı arayüzü
Yeni mimari: files + movements tabloları
"""

from pathlib import Path

import pandas as pd

from db import (
    DB_YOLU,
    action_log_ekle,
    acik_movement_var_mi,
    dosya_ve_hareket_ekle,
    file_arsive_al,
    file_gecmisi_getir,
    giris_yap,
    istatistik_ozet,
    tablo_olustur,
    tum_files_ozet,
    varsayilan_kullanicilari_olustur,
    excel_verisini_yukle,
    parse_ilce_detay_from_text,
    migrate_legacy_dosyalar_if_needed,
)

DOSYA_YOLU = Path("data/arsiv_2026.ods")


# -----------------------------------------------------------------------
# Excel yükleme
# -----------------------------------------------------------------------

def ilk_kurulum_excelden_aktar():
    if not DOSYA_YOLU.exists():
        raise FileNotFoundError(f"ODS dosyası bulunamadı: {DOSYA_YOLU}")

    print("\nExcel'den okunuyor...")
    df = pd.read_excel(DOSYA_YOLU, engine="odf", header=1)
    df = df.dropna(axis=1, how="all")
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={
        "ARŞİVE TESLİMTARİHİ":       "ARŞİVE TESLİM TARİHİ",
        "ARŞİVGÖREVLİSİ ADI SOYADI": "ARŞİV GÖREVLİSİ ADI SOYADI",
    })

    for kol in ["VERİLDİĞİ TARİH", "ARŞİVE TESLİM TARİHİ"]:
        if kol in df.columns:
            df[kol] = pd.to_datetime(df[kol], errors="coerce", dayfirst=True)

    for kol in ["DOSYA NO", "ŞEFLİĞİ",
                "TESLİM ALAN PERSONELİN ADI SOYADI",
                "ARŞİV GÖREVLİSİ ADI SOYADI"]:
        if kol in df.columns:
            df[kol] = df[kol].fillna("").astype(str).str.strip()

    satirlar = []
    for _, row in df.iterrows():
        dosya_no = str(row.get("DOSYA NO", "")).strip()
        if not dosya_no or dosya_no == "nan":
            continue

        def _tarih(val):
            if pd.isna(val):
                return None
            if hasattr(val, "strftime"):
                return val.strftime("%Y-%m-%d")
            return str(val)

        satirlar.append({
            "dosya_no":        dosya_no,
            "sefligi":         str(row.get("ŞEFLİĞİ", "")).strip(),
            "teslim_alan":     str(row.get("TESLİM ALAN PERSONELİN ADI SOYADI", "")).strip(),
            "arsiv_gorevlisi": str(row.get("ARŞİV GÖREVLİSİ ADI SOYADI", "")).strip(),
            "teslim_tarihi":   _tarih(row.get("VERİLDİĞİ TARİH")),
            "iade_tarihi":     _tarih(row.get("ARŞİVE TESLİM TARİHİ")),
        })

    excel_verisini_yukle(satirlar)
    print(f"{len(satirlar)} kayıt yüklendi.")


# -----------------------------------------------------------------------
# Yardımcı gösterim
# -----------------------------------------------------------------------

def tablo_yazdir(veriler: list[dict], baslik: str, limit: int = 20):
    print(f"\n--- {baslik} ---")
    if not veriler:
        print("Kayıt bulunamadı.")
        return
    kolonlar = ["file_id", "orijinal_dosya_no", "ilce", "sefligi",
                "teslim_alan_personel", "teslim_tarihi", "durum", "bekleme_gun"]
    df = pd.DataFrame(veriler)[
        [k for k in kolonlar if k in veriler[0]]
    ]
    print(df.head(limit).to_string(index=False))


def ozet_yazdir():
    oz = istatistik_ozet()
    print("\n--- ÖZET ---")
    print(f"Toplam      : {oz['toplam']}")
    print(f"Arşivde     : {oz['arsivde']}")
    print(f"Zimmette    : {oz['zimmette']}")
    print(f"Gecikmiş    : {oz['gecikmis']}")


# -----------------------------------------------------------------------
# Menü
# -----------------------------------------------------------------------

def menu_goster(role: str):
    print("\n===== ARŞİV TAKİP MENÜSÜ =====")
    print("1 - Özet bilgiler")
    print("2 - Gecikmiş dosyalar (ilk 20)")
    print("3 - Aktif zimmetler (ilk 20)")
    print("4 - Dosya no ile ara")
    print("5 - Personel adına göre ara")
    print("6 - Dosya hareket geçmişi")
    if role in ["arsiv", "admin"]:
        print("7 - Excel'den yeniden yükle")
        print("8 - Dosyayı arşive al")
        print("9 - Yeni dosya + zimmet ekle")
    print("0 - Çıkış")


def giris_ekrani() -> dict:
    print("\n===== ARŞİV TAKİP SİSTEMİ =====")
    while True:
        username = input("Kullanıcı adı: ").strip()
        sifre    = input("Şifre: ").strip()
        kullanici = giris_yap(username, sifre)
        if kullanici:
            print(f"\nHoş geldin {kullanici['full_name']} ({kullanici['role']})")
            return kullanici
        print("Hatalı kullanıcı adı veya şifre.\n")


def main():
    tablo_olustur()
    varsayilan_kullanicilari_olustur()

    # İlk çalıştırmada eski dosyalar tablosu varsa taşı
    migrated = migrate_legacy_dosyalar_if_needed()
    if migrated:
        print("Eski veriler yeni yapıya aktarıldı.")

    # DB boşsa Excel'den yükle
    veriler = tum_files_ozet()
    if not veriler:
        print("Veritabanı boş, Excel'den yükleniyor...")
        try:
            ilk_kurulum_excelden_aktar()
        except FileNotFoundError as e:
            print(f"UYARI: {e}")

    kullanici = giris_ekrani()

    while True:
        menu_goster(kullanici["role"])
        secim = input("\nSeçiminiz: ").strip()

        if secim == "1":
            ozet_yazdir()

        elif secim == "2":
            veriler = tum_files_ozet()
            geciken = [r for r in veriler if r["durum"] == "GECİKMİŞ"]
            geciken.sort(key=lambda x: x["bekleme_gun"], reverse=True)
            tablo_yazdir(geciken, "GECİKMİŞ DOSYALAR", 20)

        elif secim == "3":
            veriler = tum_files_ozet()
            aktif = [r for r in veriler if r["durum"] in ("ZİMMETTE", "GECİKMİŞ")]
            aktif.sort(key=lambda x: x["bekleme_gun"], reverse=True)
            tablo_yazdir(aktif, "AKTİF ZİMMETLER", 20)

        elif secim == "4":
            aranan = input("Dosya no: ").strip().lower()
            veriler = tum_files_ozet()
            sonuc = [r for r in veriler
                     if aranan in (r.get("orijinal_dosya_no") or "").lower()]
            tablo_yazdir(sonuc, f"ARAMA: {aranan}", 50)

        elif secim == "5":
            adi = input("Personel adı: ").strip().lower()
            veriler = tum_files_ozet()
            sonuc = [r for r in veriler
                     if adi in (r.get("teslim_alan_personel") or "").lower()]
            tablo_yazdir(sonuc, f"PERSONEL: {adi}", 50)

        elif secim == "6":
            try:
                fid = int(input("Dosya ID: ").strip())
            except ValueError:
                print("Geçersiz ID.")
                continue
            gecmis = file_gecmisi_getir(fid)
            if gecmis:
                df = pd.DataFrame(gecmis)
                print(df.to_string(index=False))
            else:
                print("Kayıt bulunamadı.")

        elif secim == "7" and kullanici["role"] in ["arsiv", "admin"]:
            ilk_kurulum_excelden_aktar()
            action_log_ekle(
                kullanici["id"], kullanici["username"],
                kullanici["full_name"], kullanici["role"],
                "EXCEL_YUKLE", "Excel'den yeniden yüklendi (CLI).",
            )

        elif secim == "8" and kullanici["role"] in ["arsiv", "admin"]:
            try:
                fid = int(input("Arşive alınacak dosya ID: ").strip())
            except ValueError:
                print("Geçersiz ID.")
                continue
            if not acik_movement_var_mi(fid):
                print("Bu dosya zaten arşivde.")
                continue
            from datetime import date as _date
            iade_tarihi = _date.today().strftime("%Y-%m-%d")
            iade_alan   = kullanici["full_name"]
            file_arsive_al(fid, iade_tarihi, iade_alan)
            action_log_ekle(
                kullanici["id"], kullanici["username"],
                kullanici["full_name"], kullanici["role"],
                "ARŞİVE_AL", f"file_id={fid}",
            )
            print("Dosya arşive alındı.")

        elif secim == "9" and kullanici["role"] in ["arsiv", "admin"]:
            dosya_no  = input("Dosya No: ").strip()
            sefligi   = input("Şefliği: ").strip()
            teslim_alan = input("Teslim Alan Personel: ").strip()
            arsiv_gor   = input("Arşiv Görevlisi: ").strip()
            from datetime import date as _date
            teslim_tarihi = _date.today().strftime("%Y-%m-%d")
            fid = dosya_ve_hareket_ekle(
                dosya_no, sefligi, teslim_alan, arsiv_gor, teslim_tarihi
            )
            print(f"Yeni dosya eklendi. ID: {fid}")

        elif secim == "0":
            print("Çıkış yapılıyor...")
            break

        else:
            print("Geçersiz seçim.")


if __name__ == "__main__":
    main()
