"""
arsiv.db düzeltme scripti
Çalıştırma: arsiv_takip klasöründen -> python fix_db.py
"""
import sqlite3
import os

# DB yolunu bul
for yol in ['arsiv.db', '../arsiv.db', 'arsiv_web/../arsiv.db']:
    if os.path.exists(yol):
        DB = yol
        break
else:
    print("HATA: arsiv.db bulunamadi!")
    print("Bu scripti arsiv_takip klasöründen calistirin.")
    input("Devam etmek icin Enter'a basin...")
    exit(1)

print(f"DB bulundu: {os.path.abspath(DB)}")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

eklemeler = [
    ("ALTER TABLE users     ADD COLUMN dahili                TEXT    DEFAULT ''"),
    ("ALTER TABLE files     ADD COLUMN ada                   TEXT    DEFAULT ''"),
    ("ALTER TABLE files     ADD COLUMN parsel                TEXT    DEFAULT ''"),
    ("ALTER TABLE movements ADD COLUMN teslim_alan_user_id   INTEGER"),
    ("ALTER TABLE movements ADD COLUMN arsive_gonderildi     INTEGER DEFAULT 0"),
    ("ALTER TABLE movements ADD COLUMN arsive_gonderen       TEXT    DEFAULT ''"),
    ("ALTER TABLE movements ADD COLUMN arsive_gonderme_tarihi TEXT"),
]

print("\n[1] Eksik kolonlar ekleniyor...")
for sql in eklemeler:
    kolon = sql.split("ADD COLUMN")[1].strip().split()[0]
    tablo = sql.split("ALTER TABLE")[1].strip().split()[0]
    try:
        conn.execute(sql)
        print(f"  ✓ {tablo}.{kolon} eklendi")
    except Exception:
        print(f"  - {tablo}.{kolon} zaten var")

conn.commit()

print("\n[2] Bozuk hareket verileri duzeltiliyor...")
import re
c = conn.cursor()
c.execute("SELECT * FROM movements")
rows = c.fetchall()
duzeltilen = 0
for row in rows:
    d = dict(row)
    ta = d.get('teslim_alan_personel') or ''
    tt = d.get('teslim_tarihi') or ''
    # teslim_tarihi tarih degil, teslim_alan tarih formatindaysa swap et
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', tt) and re.match(r'^\d{4}-\d{2}-\d{2}$', ta):
        conn.execute("UPDATE movements SET teslim_tarihi=?, teslim_alan_personel=? WHERE id=?",
                     (ta, tt, d['id']))
        print(f"  ✓ movement id={d['id']} swap edildi: tarih={ta}, personel={tt}")
        duzeltilen += 1
    # 'ARSIV' veya 'ARŞİV' ise veren_arsiv_gorevlisi ile degistir
    elif ta in ('ARSIV', 'ARŞİV', 'Arsiv', 'Arşiv'):
        yeni = d.get('veren_arsiv_gorevlisi') or ta
        conn.execute("UPDATE movements SET teslim_alan_personel=? WHERE id=?", (yeni, d['id']))
        print(f"  ✓ movement id={d['id']} 'ARŞİV' -> '{yeni}' duzeltildi")
        duzeltilen += 1

conn.commit()

if duzeltilen == 0:
    print("  Duzeltilecek kayit bulunamadi (zaten temiz).")

print("\n[3] Sonuc kontrol:")
c.execute("SELECT COUNT(*) as sayi FROM files")
print(f"  Dosya sayisi: {c.fetchone()['sayi']}")
c.execute("SELECT COUNT(*) as sayi FROM movements")
print(f"  Hareket sayisi: {c.fetchone()['sayi']}")
c.execute("SELECT COUNT(*) as sayi FROM users")
print(f"  Kullanici sayisi: {c.fetchone()['sayi']}")

conn.close()
print("\n✓ Tamamlandi! Sunucuyu yeniden baslatabilirsiniz.")
input("Cikis icin Enter'a basin...")
