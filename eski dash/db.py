import sqlite3
from pathlib import Path
from datetime import datetime

import bcrypt


DB_YOLU = Path("arsiv.db")


def veritabani_baglantisi():
    conn = sqlite3.connect(DB_YOLU)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def parse_ilce_detay_from_text(text: str):
    if not text:
        return "", ""
    temiz = str(text).strip()
    parcalar = temiz.split(maxsplit=1)
    if len(parcalar) == 1:
        return parcalar[0].strip(), ""
    return parcalar[0].strip(), parcalar[1].strip()


# ---------------------------------------------------------------------------
# Tablo oluşturma
# ---------------------------------------------------------------------------

def tablo_olustur():
    conn = veritabani_baglantisi()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orijinal_dosya_no TEXT NOT NULL,
        ilce TEXT,
        detay_no TEXT,
        sefligi TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER NOT NULL,
        teslim_tarihi TEXT NOT NULL,
        teslim_alan_personel TEXT NOT NULL,
        veren_arsiv_gorevlisi TEXT NOT NULL,
        iade_tarihi TEXT,
        iade_alan_gorevli TEXT,
        notlar TEXT,
        FOREIGN KEY (file_id) REFERENCES files(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash BLOB NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS login_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        full_name TEXT,
        role TEXT,
        login_time TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        full_name TEXT,
        role TEXT,
        action_type TEXT NOT NULL,
        detail TEXT,
        action_time TEXT NOT NULL
    )
    """)

    # movements tablosuna notlar kolonu yoksa ekle (eski DB uyumu)
    try:
        c.execute("ALTER TABLE movements ADD COLUMN notlar TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Şifre
# ---------------------------------------------------------------------------

def sifre_hashle(sifre: str) -> bytes:
    return bcrypt.hashpw(sifre.encode("utf-8"), bcrypt.gensalt())


def sifre_dogrula(sifre: str, password_hash: bytes) -> bool:
    return bcrypt.checkpw(sifre.encode("utf-8"), password_hash)


# ---------------------------------------------------------------------------
# Kullanıcı işlemleri
# ---------------------------------------------------------------------------

def kullanici_var_mi(username: str) -> bool:
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    sonuc = c.fetchone()
    conn.close()
    return sonuc is not None


def kullanici_ekle(username: str, sifre: str, full_name: str, role: str):
    conn = veritabani_baglantisi()
    c = conn.cursor()
    pw = sifre_hashle(sifre)
    c.execute(
        "INSERT INTO users (username, password_hash, full_name, role, active) VALUES (?, ?, ?, ?, 1)",
        (username, pw, full_name, role),
    )
    conn.commit()
    conn.close()


def kullanici_guncelle(user_id: int, full_name: str, role: str):
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET full_name = ?, role = ? WHERE id = ?",
        (full_name, role, user_id),
    )
    conn.commit()
    conn.close()


def tum_kullanicilari_getir():
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, active FROM users ORDER BY id")
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def kullanici_durum_degistir(user_id: int, active: int):
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("UPDATE users SET active = ? WHERE id = ?", (active, user_id))
    conn.commit()
    conn.close()


def kullanici_sifre_sifirla(user_id: int, yeni_sifre: str):
    conn = veritabani_baglantisi()
    c = conn.cursor()
    pw = sifre_hashle(yeni_sifre)
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw, user_id))
    conn.commit()
    conn.close()


def giris_yap(username: str, sifre: str):
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        "SELECT id, username, password_hash, full_name, role, active FROM users WHERE username = ?",
        (username,),
    )
    kullanici = c.fetchone()
    conn.close()

    if not kullanici:
        return None
    if kullanici["active"] != 1:
        return None
    if not sifre_dogrula(sifre, kullanici["password_hash"]):
        return None

    login_log_ekle(
        kullanici["id"], kullanici["username"],
        kullanici["full_name"], kullanici["role"],
    )
    return {
        "id": kullanici["id"],
        "username": kullanici["username"],
        "full_name": kullanici["full_name"],
        "role": kullanici["role"],
        "active": kullanici["active"],
    }


def varsayilan_kullanicilari_olustur():
    varsayilanlar = [
        ("admin",     "12345", "Hikmet Aytun",    "admin"),
        ("arsiv",     "12345", "Arşiv Görevlisi", "arsiv"),
        ("kullanici", "12345", "Normal Kullanıcı", "viewer"),
    ]
    for username, sifre, full_name, role in varsayilanlar:
        if not kullanici_var_mi(username):
            kullanici_ekle(username, sifre, full_name, role)


# ---------------------------------------------------------------------------
# Log işlemleri
# ---------------------------------------------------------------------------

def _simdi() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def login_log_ekle(user_id, username, full_name, role):
    conn = veritabani_baglantisi()
    conn.execute(
        "INSERT INTO login_logs (user_id, username, full_name, role, login_time) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, full_name, role, _simdi()),
    )
    conn.commit()
    conn.close()


def login_loglarini_getir():
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        "SELECT id, username, full_name, role, login_time FROM login_logs ORDER BY id DESC"
    )
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def action_log_ekle(user_id, username, full_name, role, action_type, detail):
    conn = veritabani_baglantisi()
    conn.execute(
        """INSERT INTO action_logs
           (user_id, username, full_name, role, action_type, detail, action_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, username, full_name, role, action_type, detail, _simdi()),
    )
    conn.commit()
    conn.close()


def action_loglarini_getir():
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        """SELECT id, username, full_name, role, action_type, detail, action_time
           FROM action_logs ORDER BY id DESC"""
    )
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


# ---------------------------------------------------------------------------
# Dosya (files) işlemleri
# ---------------------------------------------------------------------------

def file_ekle(orijinal_dosya_no: str, ilce: str, detay_no: str, sefligi: str) -> int:
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        """INSERT INTO files (orijinal_dosya_no, ilce, detay_no, sefligi, active, created_at)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (orijinal_dosya_no.strip(), ilce.strip(), detay_no.strip(), sefligi.strip(), _simdi()),
    )
    conn.commit()
    yeni_id = c.lastrowid
    conn.close()
    return yeni_id


def file_guncelle(file_id: int, orijinal_dosya_no: str, sefligi: str):
    ilce, detay_no = parse_ilce_detay_from_text(orijinal_dosya_no)
    conn = veritabani_baglantisi()
    conn.execute(
        """UPDATE files SET orijinal_dosya_no=?, ilce=?, detay_no=?, sefligi=?
           WHERE id=?""",
        (orijinal_dosya_no.strip(), ilce, detay_no, sefligi.strip(), file_id),
    )
    conn.commit()
    conn.close()


def file_sil(file_id: int):
    """Soft delete — active=0 yapar."""
    conn = veritabani_baglantisi()
    conn.execute("UPDATE files SET active=0 WHERE id=?", (file_id,))
    conn.commit()
    conn.close()


def tum_files_ozet():
    """Ana liste için özetlenmiş sorgu."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
    SELECT
        f.id          AS file_id,
        f.orijinal_dosya_no,
        f.ilce,
        f.detay_no,
        f.sefligi,
        f.created_at,
        m.id          AS movement_id,
        m.teslim_alan_personel,
        m.veren_arsiv_gorevlisi,
        m.teslim_tarihi,
        CASE
            WHEN m.id IS NOT NULL AND
                 CAST(julianday('now') - julianday(m.teslim_tarihi) AS INTEGER) >= 10
                THEN 'GECİKMİŞ'
            WHEN m.id IS NOT NULL
                THEN 'ZİMMETTE'
            ELSE 'ARŞİVDE'
        END AS durum,
        CASE
            WHEN m.id IS NOT NULL
                THEN CAST(julianday('now') - julianday(m.teslim_tarihi) AS INTEGER)
            ELSE 0
        END AS bekleme_gun,
        (SELECT COUNT(*) FROM movements m2 WHERE m2.file_id = f.id) AS hareket_sayisi
    FROM files f
    LEFT JOIN movements m
        ON m.file_id = f.id AND m.iade_tarihi IS NULL
    WHERE f.active = 1
    ORDER BY f.id
    """)
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


# ---------------------------------------------------------------------------
# Hareket (movements) işlemleri
# ---------------------------------------------------------------------------

def movement_ekle(file_id: int, teslim_tarihi: str, teslim_alan_personel: str,
                  veren_arsiv_gorevlisi: str, notlar: str = "") -> int:
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        """INSERT INTO movements
           (file_id, teslim_tarihi, teslim_alan_personel, veren_arsiv_gorevlisi,
            iade_tarihi, iade_alan_gorevli, notlar)
           VALUES (?, ?, ?, ?, NULL, NULL, ?)""",
        (file_id, teslim_tarihi, teslim_alan_personel.strip(),
         veren_arsiv_gorevlisi.strip(), notlar.strip()),
    )
    conn.commit()
    yeni_id = c.lastrowid
    conn.close()
    return yeni_id


def acik_movement_var_mi(file_id: int) -> bool:
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM movements WHERE file_id=? AND iade_tarihi IS NULL", (file_id,)
    )
    sonuc = c.fetchone()
    conn.close()
    return sonuc is not None


def file_arsive_al(file_id: int, iade_tarihi: str, iade_alan_gorevli: str):
    conn = veritabani_baglantisi()
    conn.execute(
        """UPDATE movements SET iade_tarihi=?, iade_alan_gorevli=?
           WHERE file_id=? AND iade_tarihi IS NULL""",
        (iade_tarihi, iade_alan_gorevli.strip(), file_id),
    )
    conn.commit()
    conn.close()


def file_gecmisi_getir(file_id: int):
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
    SELECT
        id,
        teslim_tarihi,
        teslim_alan_personel,
        veren_arsiv_gorevlisi,
        iade_tarihi,
        iade_alan_gorevli,
        notlar
    FROM movements
    WHERE file_id = ?
    ORDER BY teslim_tarihi DESC, id DESC
    """, (file_id,))
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def dosya_ve_hareket_ekle(orijinal_dosya_no: str, sefligi: str,
                           teslim_alan_personel: str, veren_arsiv_gorevlisi: str,
                           teslim_tarihi: str, notlar: str = "") -> int:
    ilce, detay_no = parse_ilce_detay_from_text(orijinal_dosya_no)
    file_id = file_ekle(orijinal_dosya_no, ilce, detay_no, sefligi)
    movement_ekle(file_id, teslim_tarihi, teslim_alan_personel,
                  veren_arsiv_gorevlisi, notlar)
    return file_id


# ---------------------------------------------------------------------------
# İstatistik sorguları
# ---------------------------------------------------------------------------

def istatistik_ozet() -> dict:
    conn = veritabani_baglantisi()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM files WHERE active=1")
    toplam = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM files f
        LEFT JOIN movements m ON m.file_id=f.id AND m.iade_tarihi IS NULL
        WHERE f.active=1 AND m.id IS NULL
    """)
    arsivde = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM files f
        JOIN movements m ON m.file_id=f.id AND m.iade_tarihi IS NULL
        WHERE f.active=1 AND
              CAST(julianday('now') - julianday(m.teslim_tarihi) AS INTEGER) < 10
    """)
    zimmette = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM files f
        JOIN movements m ON m.file_id=f.id AND m.iade_tarihi IS NULL
        WHERE f.active=1 AND
              CAST(julianday('now') - julianday(m.teslim_tarihi) AS INTEGER) >= 10
    """)
    gecikmis = c.fetchone()[0]

    conn.close()
    return {
        "toplam": toplam,
        "arsivde": arsivde,
        "zimmette": zimmette,
        "gecikmis": gecikmis,
    }


def ilce_bazli_istatistik():
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
    SELECT
        f.ilce,
        COUNT(*) AS toplam,
        SUM(CASE WHEN m.id IS NOT NULL THEN 1 ELSE 0 END) AS zimmette,
        SUM(CASE WHEN m.id IS NOT NULL AND
                      CAST(julianday('now')-julianday(m.teslim_tarihi) AS INTEGER)>=10
                 THEN 1 ELSE 0 END) AS gecikmis
    FROM files f
    LEFT JOIN movements m ON m.file_id=f.id AND m.iade_tarihi IS NULL
    WHERE f.active=1
    GROUP BY f.ilce
    ORDER BY toplam DESC
    """)
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def personel_bazli_istatistik():
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
    SELECT
        m.teslim_alan_personel AS personel,
        COUNT(*) AS zimmette,
        SUM(CASE WHEN CAST(julianday('now')-julianday(m.teslim_tarihi) AS INTEGER)>=10
                 THEN 1 ELSE 0 END) AS gecikmis,
        MAX(CAST(julianday('now')-julianday(m.teslim_tarihi) AS INTEGER)) AS max_gun
    FROM movements m
    JOIN files f ON f.id=m.file_id
    WHERE m.iade_tarihi IS NULL AND f.active=1
    GROUP BY m.teslim_alan_personel
    ORDER BY zimmette DESC
    """)
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


# ---------------------------------------------------------------------------
# Eski 'dosyalar' tablosundan yeni modele taşıma
# ---------------------------------------------------------------------------

def migrate_legacy_dosyalar_if_needed() -> bool:
    conn = veritabani_baglantisi()
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dosyalar'")
    legacy_exists = c.fetchone() is not None

    c.execute("SELECT COUNT(*) FROM files")
    files_count = c.fetchone()[0]

    if not legacy_exists or files_count > 0:
        conn.close()
        return False

    c.execute("""
    SELECT
        COALESCE(dosya_no,'')          AS dosya_no,
        COALESCE(sefligi,'')           AS sefligi,
        verildigi_tarih,
        COALESCE(teslim_alan_personel,'') AS teslim_alan_personel,
        COALESCE(arsiv_gorevlisi,'')   AS arsiv_gorevlisi,
        arsive_teslim_tarihi
    FROM dosyalar ORDER BY sira_no
    """)
    legacy_rows = [dict(r) for r in c.fetchall()]

    for row in legacy_rows:
        dosya_no = row["dosya_no"].strip()
        sefligi  = row["sefligi"].strip()
        if not dosya_no:
            continue

        ilce, detay = parse_ilce_detay_from_text(dosya_no)
        c.execute(
            """INSERT INTO files (orijinal_dosya_no,ilce,detay_no,sefligi,active,created_at)
               VALUES (?,?,?,?,1,?)""",
            (dosya_no, ilce, detay, sefligi, _simdi()),
        )
        file_id = c.lastrowid

        teslim_tarihi = row["verildigi_tarih"]
        teslim_alan   = row["teslim_alan_personel"]
        arsiv_gor     = row["arsiv_gorevlisi"]
        iade_tarihi   = row["arsive_teslim_tarihi"]

        if teslim_tarihi and teslim_alan:
            c.execute(
                """INSERT INTO movements
                   (file_id,teslim_tarihi,teslim_alan_personel,veren_arsiv_gorevlisi,
                    iade_tarihi,iade_alan_gorevli,notlar)
                   VALUES (?,?,?,?,?,?,?)""",
                (file_id, teslim_tarihi, teslim_alan, arsiv_gor,
                 iade_tarihi, arsiv_gor if iade_tarihi else None, ""),
            )

    conn.commit()
    conn.close()
    return True


# ---------------------------------------------------------------------------
# Excel'den ilk yükleme (gui_app / main tarafından çağrılır)
# ---------------------------------------------------------------------------

def excel_verisini_yukle(df_rows: list[dict]):
    """
    gui_app'ten gelen temizlenmiş satırları files+movements'a yazar.
    df_rows: her eleman {dosya_no, sefligi, teslim_alan, arsiv_gorevlisi,
                          teslim_tarihi, iade_tarihi} dict'i
    """
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("DELETE FROM movements")
    c.execute("DELETE FROM files")

    for row in df_rows:
        dosya_no = (row.get("dosya_no") or "").strip()
        sefligi  = (row.get("sefligi")  or "").strip()
        if not dosya_no:
            continue

        ilce, detay = parse_ilce_detay_from_text(dosya_no)
        c.execute(
            """INSERT INTO files (orijinal_dosya_no,ilce,detay_no,sefligi,active,created_at)
               VALUES (?,?,?,?,1,?)""",
            (dosya_no, ilce, detay, sefligi, _simdi()),
        )
        file_id = c.lastrowid

        teslim_tarihi = row.get("teslim_tarihi")
        teslim_alan   = (row.get("teslim_alan") or "").strip()
        arsiv_gor     = (row.get("arsiv_gorevlisi") or "").strip()
        iade_tarihi   = row.get("iade_tarihi")

        if teslim_tarihi and teslim_alan:
            c.execute(
                """INSERT INTO movements
                   (file_id,teslim_tarihi,teslim_alan_personel,veren_arsiv_gorevlisi,
                    iade_tarihi,iade_alan_gorevli,notlar)
                   VALUES (?,?,?,?,?,?,?)""",
                (file_id, teslim_tarihi, teslim_alan, arsiv_gor,
                 iade_tarihi, arsiv_gor if iade_tarihi else None, ""),
            )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Otomatik yedekleme
# ---------------------------------------------------------------------------

def veritabani_yedekle() -> str | None:
    """
    arsiv.db dosyasını backups/arsiv_YYYYMMDD_HHMMSS.db olarak kopyalar.
    Başarılıysa yedek yolunu, hata olursa None döner.
    7 günden eski yedekleri siler.
    """
    import shutil
    from datetime import datetime, timedelta

    if not DB_YOLU.exists():
        return None

    yedek_klasor = DB_YOLU.parent / "backups"
    yedek_klasor.mkdir(exist_ok=True)

    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek_yolu = yedek_klasor / f"arsiv_{zaman}.db"

    try:
        shutil.copy2(DB_YOLU, yedek_yolu)
    except Exception:
        return None

    # 7 günden eski yedekleri temizle
    sinir = datetime.now() - timedelta(days=7)
    for f in yedek_klasor.glob("arsiv_*.db"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < sinir:
                f.unlink()
        except Exception:
            pass

    return str(yedek_yolu)


def son_yedek_bilgisi() -> dict:
    """En son yedek dosyasının adını ve boyutunu döner."""
    yedek_klasor = DB_YOLU.parent / "backups"
    if not yedek_klasor.exists():
        return {"adet": 0, "son": None, "boyut_kb": 0}

    yedekler = sorted(yedek_klasor.glob("arsiv_*.db"),
                      key=lambda f: f.stat().st_mtime, reverse=True)
    if not yedekler:
        return {"adet": 0, "son": None, "boyut_kb": 0}

    son = yedekler[0]
    return {
        "adet": len(yedekler),
        "son": son.name,
        "boyut_kb": round(son.stat().st_size / 1024, 1),
    }


# ---------------------------------------------------------------------------
# Mesajlaşma sistemi
# ---------------------------------------------------------------------------

def mesaj_tablolari_olustur():
    """messages ve message_reads tablolarını oluşturur."""
    conn = veritabani_baglantisi()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        gonderen_id INTEGER NOT NULL,
        gonderen    TEXT    NOT NULL,
        alici_id    INTEGER,
        alici       TEXT,
        konu        TEXT,
        icerik      TEXT    NOT NULL,
        genel       INTEGER NOT NULL DEFAULT 0,
        olusturma   TEXT    NOT NULL,
        FOREIGN KEY (gonderen_id) REFERENCES users(id)
    )
    """)
    # genel=1 → herkese duyuru, genel=0 → özel mesaj (alici_id dolu)

    c.execute("""
    CREATE TABLE IF NOT EXISTS message_reads (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        okunma     TEXT    NOT NULL,
        UNIQUE(message_id, user_id),
        FOREIGN KEY (message_id) REFERENCES messages(id),
        FOREIGN KEY (user_id)    REFERENCES users(id)
    )
    """)

    # message_deletes: soft-delete — sadece silen kişiden gizlenir
    c.execute("""
    CREATE TABLE IF NOT EXISTS message_deletes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        silme      TEXT    NOT NULL,
        UNIQUE(message_id, user_id),
        FOREIGN KEY (message_id) REFERENCES messages(id),
        FOREIGN KEY (user_id)    REFERENCES users(id)
    )
    """)

    # Eski DB'ye sütun ekle (uyumluluk)
    for kolon, tip in [
        ("dosya_ref_id", "INTEGER"),
        ("dosya_ref_no", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE messages ADD COLUMN {kolon} {tip}")
        except Exception:
            pass

    conn.commit()
    conn.close()


def mesaj_sil(message_id: int, user_id: int, user_name: str,
               user_role: str, icerik_log: str):
    """Soft-delete: mesajı silen kişiden gizler, DB'de tutar. Admin loglar."""
    conn = veritabani_baglantisi()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO message_deletes (message_id, user_id, silme)
            VALUES (?, ?, ?)
        """, (message_id, user_id, _simdi()))
        conn.commit()
    finally:
        conn.close()
    action_log_ekle(
        user_id, user_name, user_name, user_role,
        "MESAJ_SİL",
        f"message_id={message_id} icerik={icerik_log[:80]}",
    )


def toplu_mesaj_sil(message_ids: list[int], user_id: int,
                     user_name: str, user_role: str):
    """
    Birden fazla mesajı aynı anda silen kişiden gizler.
    Admin action_logs'a toplu kayıt atar.
    """
    if not message_ids:
        return
    conn = veritabani_baglantisi()
    zaman = _simdi()
    try:
        for mid in message_ids:
            conn.execute("""
                INSERT OR IGNORE INTO message_deletes (message_id, user_id, silme)
                VALUES (?, ?, ?)
            """, (mid, user_id, zaman))
        conn.commit()
    finally:
        conn.close()
    action_log_ekle(
        user_id, user_name, user_name, user_role,
        "MESAJ_TOPLU_SİL",
        f"silinen={len(message_ids)} ids={message_ids[:10]}",
    )


def konusma_sil(user_id: int, diger_id: int,
                user_name: str, user_role: str):
    """
    Bir kullanıcıyla olan tüm konuşmayı silen kişiden gizler.
    Karşı taraf hâlâ görebilir. Admin loglar.
    """
    conn = veritabani_baglantisi()
    c = conn.cursor()
    # Bu kullanıcının bu konuşmadaki tüm mesaj id'lerini al
    c.execute("""
        SELECT id FROM messages
        WHERE genel = 0
          AND (
              (gonderen_id = ? AND alici_id = ?)
              OR
              (gonderen_id = ? AND alici_id = ?)
          )
    """, (user_id, diger_id, diger_id, user_id))
    ids = [r[0] for r in c.fetchall()]
    zaman = _simdi()
    for mid in ids:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO message_deletes (message_id, user_id, silme)
                VALUES (?, ?, ?)
            """, (mid, user_id, zaman))
        except Exception:
            pass
    conn.commit()
    conn.close()
    action_log_ekle(
        user_id, user_name, user_name, user_role,
        "KONUŞMA_SİL",
        f"diger_id={diger_id} silinen_mesaj={len(ids)}",
    )


def konusma_listesi_getir(user_id: int) -> list[dict]:
    """
    Sadece gerçek yazışma olan kullanıcıları döner.
    Her kullanıcı için: son mesaj, zaman, okunmamış sayısı, karşı taraf bilgisi.
    """
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        WITH son_mesajlar AS (
            SELECT
                CASE
                    WHEN gonderen_id = ? THEN alici_id
                    ELSE gonderen_id
                END AS diger_id,
                MAX(id) AS son_id
            FROM messages
            WHERE genel = 0
              AND (gonderen_id = ? OR alici_id = ?)
            GROUP BY diger_id
        )
        SELECT
            u.id         AS diger_id,
            u.full_name  AS diger_isim,
            u.role       AS diger_rol,
            m.icerik     AS son_mesaj,
            m.olusturma  AS son_zaman,
            m.gonderen_id AS son_gonderen_id,
            (
                SELECT COUNT(*) FROM messages mm
                LEFT JOIN message_reads mr ON mr.message_id=mm.id AND mr.user_id=?
                LEFT JOIN message_deletes md ON md.message_id=mm.id AND md.user_id=?
                WHERE mm.gonderen_id = u.id
                  AND mm.alici_id = ?
                  AND mm.genel = 0
                  AND mr.id IS NULL
                  AND md.id IS NULL
            ) AS okunmamis
        FROM son_mesajlar sm
        JOIN users u ON u.id = sm.diger_id
        JOIN messages m ON m.id = sm.son_id
        ORDER BY m.olusturma DESC
    """, (user_id, user_id, user_id, user_id, user_id, user_id))
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def duyuru_listesi_getir(user_id: int) -> list[dict]:
    """Genel duyuruları, okunmamış sayısıyla döner."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*) AS toplam,
            SUM(CASE WHEN mr.id IS NULL AND md.id IS NULL
                     AND m.gonderen_id != ?
                THEN 1 ELSE 0 END) AS okunmamis,
            MAX(m.olusturma) AS son_zaman,
            (SELECT icerik FROM messages
             WHERE genel=1 ORDER BY id DESC LIMIT 1) AS son_mesaj
        FROM messages m
        LEFT JOIN message_reads mr ON mr.message_id=m.id AND mr.user_id=?
        LEFT JOIN message_deletes md ON md.message_id=m.id AND md.user_id=?
        WHERE m.genel = 1
    """, (user_id, user_id, user_id))
    row = c.fetchone()
    conn.close()
    if row and row["toplam"]:
        return [dict(row)]
    return []


def mesaj_gonder(gonderen_id: int, gonderen: str,
                  icerik: str, konu: str = "",
                  alici_id: int = None, alici: str = None,
                  genel: bool = False) -> int:
    """Yeni mesaj gönderir. genel=True ise tüm kullanıcılara duyuru."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        INSERT INTO messages
            (gonderen_id, gonderen, alici_id, alici, konu, icerik, genel, olusturma)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        gonderen_id, gonderen,
        alici_id, alici or "",
        konu.strip(), icerik.strip(),
        1 if genel else 0,
        _simdi(),
    ))
    conn.commit()
    mid = c.lastrowid
    conn.close()

    # Admin logu
    if genel:
        detay = f"DUYURU konu={konu[:40]} icerik={icerik[:80]}"
        tip   = "MESAJ_DUYURU"
    else:
        detay = f"alici={alici} icerik={icerik[:80]}"
        tip   = "MESAJ_GONDER"
    action_log_ekle(
        gonderen_id, gonderen, gonderen, "",
        tip, detay,
    )
    return mid


def mesajlari_getir(user_id: int) -> list[dict]:
    """
    Kullanıcıya ait tüm mesajları getirir:
    - Genel duyurular
    - Kullanıcıya özel gelen mesajlar
    - Kullanıcının gönderdiği mesajlar
    Okunma durumu ve yön (gelen/giden/duyuru) bilgisiyle birlikte.
    """
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        SELECT
            m.id,
            m.gonderen_id,
            m.gonderen,
            m.alici_id,
            m.alici,
            m.konu,
            m.icerik,
            m.genel,
            m.olusturma,
            CASE WHEN mr.id IS NOT NULL THEN 1 ELSE 0 END AS okundu,
            CASE
                WHEN m.genel = 1 THEN 'duyuru'
                WHEN m.gonderen_id = ? THEN 'giden'
                ELSE 'gelen'
            END AS yon
        FROM messages m
        LEFT JOIN message_reads mr
            ON mr.message_id = m.id AND mr.user_id = ?
        WHERE
            m.genel = 1
            OR m.alici_id = ?
            OR m.gonderen_id = ?
        ORDER BY m.olusturma DESC
    """, (user_id, user_id, user_id, user_id))
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def mesaj_oku(message_id: int, user_id: int):
    """Mesajı okundu olarak işaretle."""
    conn = veritabani_baglantisi()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO message_reads (message_id, user_id, okunma)
            VALUES (?, ?, ?)
        """, (message_id, user_id, _simdi()))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def tum_mesajlari_oku(user_id: int):
    """Kullanıcının tüm okunmamış mesajlarını okundu yap."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    # Okunmamış mesajların id'lerini al
    c.execute("""
        SELECT m.id FROM messages m
        LEFT JOIN message_reads mr ON mr.message_id=m.id AND mr.user_id=?
        WHERE (m.genel=1 OR m.alici_id=?) AND mr.id IS NULL
    """, (user_id, user_id))
    ids = [r[0] for r in c.fetchall()]
    zaman = _simdi()
    for mid in ids:
        try:
            c.execute("""
                INSERT OR IGNORE INTO message_reads (message_id, user_id, okunma)
                VALUES (?, ?, ?)
            """, (mid, user_id, zaman))
        except Exception:
            pass
    conn.commit()
    conn.close()


def okunmamis_mesaj_sayisi(user_id: int) -> int:
    """Kullanıcının okunmamış mesaj sayısını döner."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM messages m
        LEFT JOIN message_reads mr
            ON mr.message_id = m.id AND mr.user_id = ?
        WHERE (m.genel = 1 OR m.alici_id = ?)
          AND m.gonderen_id != ?
          AND mr.id IS NULL
    """, (user_id, user_id, user_id))
    sayi = c.fetchone()[0]
    conn.close()
    return sayi


def son_mesajlari_getir(user_id: int, limit: int = 50) -> list[dict]:
    """
    Belirli bir kullanıcının konuşma listesi —
    her kişiyle en son mesajı döner.
    """
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        SELECT
            m.id, m.gonderen_id, m.gonderen,
            m.alici_id, m.alici, m.konu, m.icerik,
            m.genel, m.olusturma,
            CASE WHEN mr.id IS NOT NULL THEN 1 ELSE 0 END AS okundu,
            CASE
                WHEN m.genel = 1 THEN 'duyuru'
                WHEN m.gonderen_id = ? THEN 'giden'
                ELSE 'gelen'
            END AS yon
        FROM messages m
        LEFT JOIN message_reads mr
            ON mr.message_id = m.id AND mr.user_id = ?
        WHERE m.genel = 1 OR m.alici_id = ? OR m.gonderen_id = ?
        ORDER BY m.olusturma DESC
        LIMIT ?
    """, (user_id, user_id, user_id, user_id, limit))
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


def konusma_gecmisi(user_id: int, diger_id: int) -> list[dict]:
    """İki kullanıcı arasındaki mesajları döner (silinenleri hariç tutar)."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        SELECT
            m.id,
            m.gonderen_id,
            m.gonderen,
            m.alici_id,
            m.alici,
            m.icerik,
            m.olusturma,
            COALESCE(m.dosya_ref_id,  0)  AS dosya_ref_id,
            COALESCE(m.dosya_ref_no,  '') AS dosya_ref_no,
            CASE WHEN mr_ben.id   IS NOT NULL THEN 1 ELSE 0 END AS okundu,
            CASE WHEN mr_diger.id IS NOT NULL THEN 1 ELSE 0 END AS karsisi_okudu
        FROM messages m
        LEFT JOIN message_reads mr_ben
            ON mr_ben.message_id = m.id AND mr_ben.user_id = ?
        LEFT JOIN message_reads mr_diger
            ON mr_diger.message_id = m.id AND mr_diger.user_id = ?
        LEFT JOIN message_deletes md
            ON md.message_id = m.id AND md.user_id = ?
        WHERE m.genel = 0
          AND md.id IS NULL
          AND (
              (m.gonderen_id = ? AND m.alici_id = ?)
              OR
              (m.gonderen_id = ? AND m.alici_id = ?)
          )
        ORDER BY m.olusturma ASC
    """, (user_id, diger_id, user_id,
          user_id, diger_id, diger_id, user_id))
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler
# ---------------------------------------------------------------------------
# Online durum sistemi
# ---------------------------------------------------------------------------

def online_tablolari_olustur():
    """user_presence tablosunu oluşturur."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_presence (
        user_id    INTEGER PRIMARY KEY,
        son_aktif  TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    # messages tablosuna dosya_ref ve okundu sütunları ekle
    for kolon, tip in [
        ("dosya_ref_id",  "INTEGER"),
        ("dosya_ref_no",  "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE messages ADD COLUMN {kolon} {tip}")
        except Exception:
            pass
    conn.commit()
    conn.close()


def presence_guncelle(user_id: int):
    """Kullanıcının son aktif zamanını güncelle (her 30 sn bir çağrılmalı)."""
    conn = veritabani_baglantisi()
    conn.execute("""
        INSERT INTO user_presence (user_id, son_aktif)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET son_aktif = excluded.son_aktif
    """, (user_id, _simdi()))
    conn.commit()
    conn.close()


def online_kullanicilari_getir(dakika: int = 2) -> list[int]:
    """Son N dakika içinde aktif olan user_id listesini döner."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        SELECT user_id FROM user_presence
        WHERE son_aktif >= datetime('now', ?, 'localtime')
    """, (f"-{dakika} minutes",))
    ids = [r[0] for r in c.fetchall()]
    conn.close()
    return ids


def online_kullanici_bilgileri(dakika: int = 2) -> list[dict]:
    """Online kullanıcıların id, full_name, role bilgilerini döner."""
    ids = online_kullanicilari_getir(dakika)
    if not ids:
        return []
    conn = veritabani_baglantisi()
    c = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    c.execute(f"""
        SELECT id, full_name, role FROM users
        WHERE id IN ({placeholders}) AND active=1
    """, ids)
    veriler = [dict(r) for r in c.fetchall()]
    conn.close()
    return veriler


# ---------------------------------------------------------------------------
# Dosya referanslı mesaj
# ---------------------------------------------------------------------------

def mesaj_gonder_dosya_ref(gonderen_id: int, gonderen: str,
                             icerik: str, alici_id: int, alici: str,
                             dosya_ref_id: int, dosya_ref_no: str) -> int:
    """Dosya referansı içeren özel mesaj gönderir."""
    conn = veritabani_baglantisi()
    c = conn.cursor()
    c.execute("""
        INSERT INTO messages
            (gonderen_id, gonderen, alici_id, alici, konu,
             icerik, genel, olusturma, dosya_ref_id, dosya_ref_no)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
    """, (
        gonderen_id, gonderen, alici_id, alici,
        f"Dosya: {dosya_ref_no}",
        icerik.strip(), _simdi(),
        dosya_ref_id, dosya_ref_no,
    ))
    conn.commit()
    mid = c.lastrowid
    conn.close()

    # Admin logu
    action_log_ekle(
        gonderen_id, gonderen, gonderen, "",
        "MESAJ_DOSYA_REF",
        f"alici={alici} dosya={dosya_ref_no}(id={dosya_ref_id}) not={icerik[:60]}",
    )
    return mid


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tablo_olustur()
    varsayilan_kullanicilari_olustur()
    migrated = migrate_legacy_dosyalar_if_needed()
    if migrated:
        print("Eski dosyalar tablosu yeni yapıya aktarıldı.")
    else:
        print("Veritabanı hazır.")

