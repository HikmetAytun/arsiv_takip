"""
Arşiv Takip Sistemi — Web Backend
FastAPI + Jinja2 + SQLite
"""
from fastapi import FastAPI, Request, Depends, HTTPException, Form, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import sys, os

# db.py'yi bul (üst klasörde)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from db import (
    giris_yap, tum_files_ozet, tum_kullanicilari_getir,
    istatistik_ozet, dosya_ve_hareket_ekle, file_sil,
    arsive_gonder, arsive_gonder_iptal, file_arsive_al,
    arsive_gonderilen_dosyalar, bende_zimmetli_dosyalar,
    action_log_ekle, action_loglarini_getir, login_loglarini_getir,
    mesaj_gonder, mesajlari_getir, mesaj_sil,
    konusma_sil as db_konusma_sil,
    konusma_listesi_getir, konusma_gecmisi, mesaj_oku,
    tum_arsiv_gorevlileri, movement_user_id_guncelle,
    tablo_olustur, varsayilan_kullanicilari_olustur,
    mesaj_tablolari_olustur, online_tablolari_olustur,
    presence_guncelle, online_kullanici_bilgileri,
    zimmet_guncelle, dosya_iade_et,
    personel_bazli_istatistik, ilce_bazli_istatistik,
    kullanici_ekle, kullanici_guncelle, kullanici_durum_degistir,
    kullanici_sifre_sifirla, kullanici_sil as db_kullanici_sil,
    file_gecmisi_getir, son_hareketleri_getir, trend_verisi_getir,
    arsiv_gorevlisini_getir, movement_ekle, acik_movement_var_mi,
)

def okunmamis_sayisi(user_id: int, user_role: str = "") -> int:
    """Kullanıcının okunmamış mesaj sayısını döner. Admin için 0."""
    if user_role == "admin":
        return 0
    try:
        from db import mesajlari_getir
        msgs = mesajlari_getir(user_id)
        return sum(1 for m in msgs if m.get("yon") == "gelen" and not m.get("okundu"))
    except:
        return 0

# Sabitler (gui_app'ten bağımsız)
ILCE_LISTESI = [
    "ALİAĞA", "BALÇOVA", "BAYRAKLI", "BERGAMA", "BEYDAĞ", "BORNOVA",
    "BUCA", "ÇEŞME", "ÇİĞLİ", "DİKİLİ", "FOÇA", "GAZİEMİR", "GÜZELBAHÇE",
    "KARABAĞLAR", "KARŞIYAKA", "KEMALPAŞA", "KINIK", "KİRAZ", "KONAK",
    "MENDERES", "MENEMEN", "NARLIDERE", "ÖDEMİŞ", "SEFERİHİSAR", "SELÇUK",
    "TİRE", "TORBALI", "URLA",
]
MUDÜRLUK_LISTESI = [
    "EMLAK ŞB. MÜD.",
    "KAMULAŞTIRMA ŞB. MÜD.",
    "KİRALAMA VE TAKİP ŞB.MÜD.",
    "GAYRİ. GEL. VE YÖN. ŞB. MÜD.",
]

# ── AYARLAR ──────────────────────────────────────────────────
SECRET_KEY    = "arsiv-takip-gizli-anahtar-2024"  # Prod'da değiştir!
ALGORITHM     = "HS256"
TOKEN_EXPIRE  = 480  # dakika (8 saat)
APP_TITLE     = "Arşiv Takip Sistemi"
APP_VERSIYON  = "v3.0"

# ── FASTAPI ──────────────────────────────────────────────────
app = FastAPI(title=APP_TITLE, version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE   = Path(__file__).parent.parent
TMPL   = BASE / "frontend" / "templates"
STATIC = BASE / "frontend" / "static"

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
templates = Jinja2Templates(directory=str(TMPL))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── JWT ──────────────────────────────────────────────────────
def token_olustur(data: dict) -> str:
    exp = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE)
    return jwt.encode({**data, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def token_coz(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def aktif_kullanici(request: Request) -> Optional[dict]:
    token = request.cookies.get("token")
    if not token:
        return None
    payload = token_coz(token)
    if not payload:
        return None
    return payload


def giris_gerekli(request: Request) -> dict:
    kullanici = aktif_kullanici(request)
    if not kullanici:
        raise HTTPException(status_code=303,
                            headers={"Location": "/giris"})
    return kullanici


# ── YARDIMCILAR ──────────────────────────────────────────────
def render(request, template, ctx={}):
    kullanici = aktif_kullanici(request)
    okunmamis = 0
    if kullanici:
        try:
            okunmamis = okunmamis_sayisi(kullanici["id"], kullanici.get("role",""))
        except:
            pass
        # Dahili bilgisini her seferinde DB'den taze çek (token'dan değil)
        try:
            from db import veritabani_baglantisi as _vb
            _conn = _vb()
            _row = _conn.execute(
                "SELECT COALESCE(dahili,'') as dahili FROM users WHERE id=?",
                (kullanici["id"],)
            ).fetchone()
            _conn.close()
            if _row:
                kullanici = dict(kullanici)
                kullanici["dahili"] = _row["dahili"] or ""
        except:
            pass
    context = {
        "request":      request,
        "kullanici":    kullanici,
        "app_title":    APP_TITLE,
        "app_versiyon": APP_VERSIYON,
        "okunmamis_mesaj": okunmamis,
        **ctx
    }
    return templates.TemplateResponse(request=request, name=template, context=context)


# ═══════════════════════════════════════════════════════════
# ROTALAR
# ═══════════════════════════════════════════════════════════

# ── GİRİŞ ────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def ana(request: Request):
    if aktif_kullanici(request):
        return RedirectResponse("/panel", 302)
    return RedirectResponse("/giris", 302)


@app.get("/giris", response_class=HTMLResponse)
async def giris_form(request: Request):
    if aktif_kullanici(request):
        return RedirectResponse("/panel", 302)
    return render(request, "giris.html")


@app.post("/giris")
async def giris_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    kullanici = giris_yap(username, password)
    if not kullanici:
        return render(request, "giris.html", {"hata": "Kullanıcı adı veya şifre hatalı."})

    token = token_olustur({
        "id":        kullanici["id"],
        "username":  kullanici["username"],
        "full_name": kullanici["full_name"],
        "role":      kullanici["role"],
        "dahili":    kullanici.get("dahili", "") or "",
    })
    # Presence güncelle (online göster)
    try:
        presence_guncelle(kullanici["id"])
    except:
        pass
    yanit = RedirectResponse("/panel", status_code=302)
    yanit.set_cookie("token", token, httponly=True, max_age=TOKEN_EXPIRE * 60)
    return yanit


@app.get("/cikis")
async def cikis():
    yanit = RedirectResponse("/giris", 302)
    yanit.delete_cookie("token")
    return yanit


# ── ANA PANEL ────────────────────────────────────────────────
@app.get("/panel", response_class=HTMLResponse)
async def panel(request: Request):
    k = giris_gerekli(request)
    oz = istatistik_ozet()
    per = personel_bazli_istatistik()[:5]
    # Son 15 hareket - gerçek hareket verileri
    try:
        son_hareketler = son_hareketleri_getir(15)
    except Exception as _e:
        print(f"son_hareketler hata: {_e}")
        son_hareketler = []
    # Yeni mesaj var mı?
    try:
        mesajlar = mesajlari_getir(k["id"])
        yeni_mesaj_var = any(not m.get("okundu") and m.get("yon") == "gelen" for m in mesajlar)
    except:
        yeni_mesaj_var = False
    return render(request, "panel.html", {
        "ozet": oz,
        "personel": per,
        "son_hareketler": son_hareketler,
        "yeni_mesaj_var": yeni_mesaj_var,
        "now_hour": datetime.now().hour,
    })


# ── DOSYA KAYITLARI ──────────────────────────────────────────
@app.get("/dosyalar", response_class=HTMLResponse)
async def dosyalar(
    request: Request,
    ara: str = "",
    ilce: str = "",
    durum: str = "",
):
    giris_gerekli(request)
    veriler = tum_files_ozet()

    if ara:
        ara_l = ara.lower()
        veriler = [r for r in veriler if
            ara_l in (r.get("orijinal_dosya_no") or "").lower() or
            ara_l in (r.get("ilce") or "").lower() or
            ara_l in (r.get("teslim_alan_personel") or "").lower() or
            ara_l in (r.get("ada") or "").lower() or
            ara_l in (r.get("parsel") or "").lower()
        ]
    if ilce:
        veriler = [r for r in veriler if r.get("ilce") == ilce]
    if durum:
        # Türkçe karakter normalize ederek karşılaştır
        def tr_upper(s):
            return s.upper().replace('İ','I').replace('I','I').replace('Ğ','G').replace('Ü','U').replace('Ş','S').replace('Ö','O').replace('Ç','C')
        veriler = [r for r in veriler if tr_upper(durum) in tr_upper(r.get("durum") or "")]

    ilceler = sorted({r.get("ilce","") for r in tum_files_ozet() if r.get("ilce")})
    # Pagination
    sayfa_boyutu = 50
    try:
        sayfa_no = int(request.query_params.get("sayfa", 1))
    except:
        sayfa_no = 1
    toplam = len(veriler)
    toplam_sayfa = max(1, (toplam + sayfa_boyutu - 1) // sayfa_boyutu)
    sayfa_no = max(1, min(sayfa_no, toplam_sayfa))
    bas = (sayfa_no - 1) * sayfa_boyutu
    veriler_sayfa = veriler[bas:bas + sayfa_boyutu]
    return render(request, "dosyalar.html", {
        "dosyalar":     veriler_sayfa,
        "ilceler":      ilceler,
        "ara":          ara,
        "ilce_sec":     ilce,
        "durum_sec":    durum,
        "toplam":       toplam,
        "sayfa_no":     sayfa_no,
        "toplam_sayfa": toplam_sayfa,
        "sayfa_boyutu": sayfa_boyutu,
        "kullanicilar": [u for u in tum_kullanicilari_getir() if u["active"] and u["role"] != "admin"],
    })


# ── YENİ DOSYA ────────────────────────────────────────────────
@app.get("/dosya/yeni", response_class=HTMLResponse)
async def yeni_dosya_form(request: Request):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403, "Yetkisiz")
    kullanicilar = [u for u in tum_kullanicilari_getir()
                    if u["active"] and u["role"] != "admin"]
    return render(request, "yeni_dosya.html", {
        "kullanicilar": kullanicilar,
        "ilceler": ILCE_LISTESI,
        "mudürlükler": MUDÜRLUK_LISTESI,
        "today": datetime.now().strftime("%Y-%m-%d"),
    })


@app.post("/dosya/yeni")
async def yeni_dosya_kaydet(
    request: Request,
    dosya_no: str = Form(...),
    ilce: str = Form(...),
    sefligi: str = Form(""),
    ada: str = Form(...),
    parsel: str = Form(...),
    teslim_alan: str = Form(...),
    arsiv_gorevlisi: str = Form(...),
    teslim_tarihi: str = Form(...),
    teslim_saat: str = Form(""),
    notlar: str = Form(""),
    teslim_alan_user_id: int = Form(None),
):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    try:
        # Tarih + saat birleştir
        tarih_saat = teslim_tarihi
        if teslim_saat:
            tarih_saat = f"{teslim_tarihi} {teslim_saat}"
        fid = dosya_ve_hareket_ekle(
            orijinal_dosya_no=dosya_no, sefligi=sefligi,
            teslim_alan_personel=teslim_alan,
            veren_arsiv_gorevlisi=arsiv_gorevlisi,
            teslim_tarihi=tarih_saat, notlar=notlar,
            ada=ada, parsel=parsel, ilce=ilce,
        )
        if teslim_alan_user_id:
            movement_user_id_guncelle(fid, teslim_alan_user_id)
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "YENİ_DOSYA", f"Dosya No: {dosya_no}")
        return RedirectResponse("/dosyalar?mesaj=eklendi", 302)
    except Exception as e:
        kullanicilar = [u for u in tum_kullanicilari_getir()
                        if u["active"] and u["role"] != "admin"]
        return render(request, "yeni_dosya.html", {
            "hata": str(e),
            "kullanicilar": kullanicilar,
            "ilceler": ILCE_LISTESI,
            "mudürlükler": MUDÜRLUK_LISTESI,
            "today": datetime.now().strftime("%Y-%m-%d"),
        })


# ── ÜZERİMDEKİLER ────────────────────────────────────────────
@app.get("/uzerimdekiler", response_class=HTMLResponse)
async def uzerimdekiler(request: Request):
    k = giris_gerekli(request)
    role = k["role"]

    # Kendi zimmetleri (herkes)
    kendi_dosyalar = bende_zimmetli_dosyalar(k["id"], k["full_name"])

    # Arşiv görevlisi ve admin: arşive gönderilmiş dosyalar da görünsün
    arsive_gonderilen = []
    if role in ("arsiv", "admin"):
        try:
            arsive_gonderilen = arsive_gonderilen_dosyalar()
        except:
            arsive_gonderilen = []

    kullanicilar = [u for u in tum_kullanicilari_getir()
                    if u["active"] and u["role"] != "admin"]
    return render(request, "uzerimdekiler.html", {
        "dosyalar":          kendi_dosyalar,
        "arsive_gonderilen": arsive_gonderilen,
        "rol":               role,
        "kullanicilar":      kullanicilar,
    })


# ── MESAJLAR ─────────────────────────────────────────────────
@app.get("/mesajlar", response_class=HTMLResponse)
async def mesajlar(request: Request):
    k = giris_gerekli(request)
    konusmalar = konusma_listesi_getir(k["id"])
    # Admin hariç aktif kullanıcılar (gönderim listesi için)
    # NOT: Admin listede görünmez ama admin kendisi mesaj gönderebilir
    kullanicilar = [u for u in tum_kullanicilari_getir()
                    if u["active"] and u["id"] != k["id"] and u["role"] != "admin"]
    try:
        online = [u for u in online_kullanici_bilgileri(dakika=3) if u.get("role") != "admin"]
    except:
        online = []
    return render(request, "mesajlar.html", {
        "konusmalar":          konusmalar,
        "kullanicilar":        kullanicilar,
        "online_kullanicilar": online,
        "aktif_id":            None,
        "aktif_isim":          "",
        "mesajlar":            [],
        "benim_id":            k["id"],
    })


@app.get("/mesajlar/{diger_id}", response_class=HTMLResponse)
async def mesaj_gecmis(request: Request, diger_id: int):
    k = giris_gerekli(request)
    mesajlar_list = konusma_gecmisi(k["id"], diger_id)
    for m in mesajlar_list:
        if m["gonderen_id"] != k["id"] and not m.get("okundu"):
            mesaj_oku(m["id"], k["id"])
    tum_k = {u["id"]: u["full_name"] for u in tum_kullanicilari_getir()}
    konusmalar = konusma_listesi_getir(k["id"])
    kullanicilar = [u for u in tum_kullanicilari_getir()
                    if u["active"] and u["id"] != k["id"] and u["role"] != "admin"]
    try:
        online = [u for u in online_kullanici_bilgileri(dakika=3) if u.get("role") != "admin"]
    except:
        online = []
    return render(request, "mesajlar.html", {
        "konusmalar":          konusmalar,
        "kullanicilar":        kullanicilar,
        "online_kullanicilar": online,
        "aktif_id":            diger_id,
        "aktif_isim":          tum_k.get(diger_id, ""),
        "mesajlar":            mesajlar_list,
        "benim_id":            k["id"],
    })


# ── API: MESAJLAR (AJAX polling) ───────────────────────────────────────────
@app.get("/api/mesajlar/{diger_id}")
async def api_mesajlar(request: Request, diger_id: int):
    k = aktif_kullanici(request)
    if not k:
        return JSONResponse({"html": ""})
    mesajlar_list = konusma_gecmisi(k["id"], diger_id)
    for m in mesajlar_list:
        if m["gonderen_id"] != k["id"] and not m.get("okundu"):
            mesaj_oku(m["id"], k["id"])
    # HTML fragment döndür - olusturma formatı: "2026-04-03 09:52:00"
    html = ""
    for m in mesajlar_list:
        is_ben = m["gonderen_id"] == k["id"]
        okundu = "✓✓" if m.get("karsisi_okudu") else "✓"
        # Saat: "2026-04-03 09:52:00" -> "09:52"
        olusturma = m.get("olusturma") or ""
        if " " in olusturma:
            zaman = olusturma.split(" ")[1][:5]
        else:
            zaman = olusturma[-5:]
        # Fotoğraf mesajı mı?
        raw = m.get("icerik", "")
        if raw.startswith("[FOTO:"):
            try:
                inner = raw[6:-1]
                mime, b64 = inner.split(";", 1)
                icerik = (
                    "<img src=\"data:" + mime + ";base64," + b64 + "\" "
                    "style=\"max-width:220px;max-height:180px;border-radius:8px;display:block;cursor:pointer;\" "
                    "onclick=\"this.style.maxWidth=this.style.maxWidth===\'220px\'?\'100%\':\'220px\'\">"
                )
            except Exception:
                icerik = raw.replace("<","&lt;").replace(">","&gt;")
        else:
            icerik = raw.replace("<","&lt;").replace(">","&gt;")
        align = "flex-end" if is_ben else "flex-start"
        cls = "ben" if is_ben else "karsi"
        sil_btn = f'<button onclick="mesajSil({m["id"]})" style="margin-top:2px;font-size:10px;color:var(--txt4);background:none;border:none;cursor:pointer;padding:0 2px;">🗑</button>' if is_ben else ""
        tik = okundu if is_ben else ""
        html += f'<div style="display:flex;flex-direction:column;align-items:{align};" id="msg-{m["id"]}"><div class="bubble {cls}">{icerik}<div class="zaman" style="display:flex;align-items:center;justify-content:flex-end;gap:3px;"><span>{zaman}</span><span>{tik}</span></div></div>{sil_btn}</div>\n'
    if not mesajlar_list:
        html = '<div style="flex:1;display:flex;align-items:center;justify-content:center;color:var(--txt4);padding:40px;">Henüz mesaj yok.</div>'
    return JSONResponse({"html": html})


@app.post("/mesaj/gonder")
async def mesaj_gonder_post(
    request: Request,
    alici_id: int = Form(...),
    icerik: str = Form(...),
):
    k = giris_gerekli(request)
    tum_k = {u["id"]: u["full_name"] for u in tum_kullanicilari_getir()}
    mesaj_gonder(
        gonderen_id=k["id"], gonderen=k["full_name"],
        icerik=icerik, alici_id=alici_id,
        alici=tum_k.get(alici_id, ""),
    )
    return RedirectResponse(f"/mesajlar/{alici_id}", 302)


# ── İSTATİSTİKLER ─────────────────────────────────────────────
@app.get("/istatistikler", response_class=HTMLResponse)
async def istatistikler(request: Request):
    giris_gerekli(request)
    oz   = istatistik_ozet()
    ilce = ilce_bazli_istatistik()
    per  = personel_bazli_istatistik()
    try:
        trend = trend_verisi_getir(30)
    except:
        trend = []
    return render(request, "istatistikler.html", {
        "ozet": oz, "ilce": ilce, "personel": per, "trend": trend,
    })


# ── API ENDPOINTS (AJAX için) ─────────────────────────────────
@app.get("/api/ozet")
async def api_ozet(request: Request):
    giris_gerekli(request)
    return istatistik_ozet()


@app.post("/api/arsive-gonder/{file_id}")
async def api_arsive_gonder(request: Request, file_id: int):
    k = giris_gerekli(request)
    arsiv = tum_arsiv_gorevlileri()
    if not arsiv:
        raise HTTPException(400, "Arşiv görevlisi bulunamadı")
    arsive_gonder(file_id, k["id"], k["full_name"],
                  arsiv[0]["id"], arsiv[0]["full_name"])
    return {"ok": True}


@app.post("/api/toplu-sil")
async def api_toplu_sil(request: Request, ids: str = Form(...), neden: str = Form("")):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    try:
        id_listesi = [int(i) for i in ids.split(",") if i.strip()]
        from db import toplu_hard_delete  # noqa
        silinen = toplu_hard_delete(id_listesi)
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "TOPLU_SİL",
                        f"{silinen} dosya silindi. Neden: {neden or 'Belirtilmedi'}")
        return JSONResponse({"ok": True, "silinen": silinen})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


@app.post("/api/arsive-al/{file_id}")
async def api_arsive_al(request: Request, file_id: int):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    from datetime import date
    file_arsive_al(file_id, datetime.now().strftime("%Y-%m-%d %H:%M"), k["full_name"])
    return {"ok": True}


@app.post("/api/arsive-gonder-iptal/{file_id}")
async def api_arsive_gonder_iptal(request: Request, file_id: int):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    try:
        arsive_gonder_iptal(file_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


@app.post("/api/iade/{file_id}")
async def api_iade(request: Request, file_id: int, not_metni: str = Form("")):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    sonuc = dosya_iade_et(file_id, k["id"], k["full_name"], not_metni)
    return {"ok": True, **sonuc}


# ── BAŞLAT ────────────────────────────────────────────────────

# ── KULLANICILAR ─────────────────────────────────────────────
@app.get("/kullanicilar", response_class=HTMLResponse)
async def kullanicilar(request: Request):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403, "Sadece admin erişebilir")
    kullanicilar_list = tum_kullanicilari_getir()
    return render(request, "kullanicilar.html", {
        "kullanicilar": kullanicilar_list
    })

@app.post("/kullanici/ekle")
async def kullanici_ekle_post(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    dahili: str = Form(""),
):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403)
    try:
        kullanici_ekle(username=username, sifre=password,
                       full_name=full_name, role=role, dahili=dahili)
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "KULLANICI_EKLE", f"{username} eklendi")
        return RedirectResponse("/kullanicilar?mesaj=eklendi", 302)
    except Exception as e:
        kullanicilar_list = tum_kullanicilari_getir()
        return render(request, "kullanicilar.html", {
            "kullanicilar": kullanicilar_list,
            "hata": str(e)
        })

@app.post("/kullanici/{uid}/durum")
async def kullanici_durum(request: Request, uid: int, aktif: int = Form(...)):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403)
    kullanici_durum_degistir(uid, bool(aktif))
    return RedirectResponse("/kullanicilar", 302)

@app.post("/kullanici/{uid}/duzenle")
async def kullanici_duzenle_post(
    request: Request, uid: int,
    full_name: str = Form(...),
    role: str = Form(...),
    dahili: str = Form(""),
    username: str = Form(""),
):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403)
    try:
        kullanici_guncelle(user_id=uid, full_name=full_name, role=role, dahili=dahili)
        # Username değiştir (isteğe bağlı)
        if username and username.strip():
            from db import veritabani_baglantisi as _vb
            conn = _vb()
            conn.execute("UPDATE users SET username=? WHERE id=?", (username.strip(), uid))
            conn.commit(); conn.close()
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "KULLANICI_GÜNCELLE", f"uid={uid}")
        return RedirectResponse("/kullanicilar?mesaj=guncellendi", 302)
    except Exception as e:
        kullanicilar_list = tum_kullanicilari_getir()
        return render(request, "kullanicilar.html", {
            "kullanicilar": kullanicilar_list, "hata": str(e)
        })

@app.post("/kullanici/{uid}/sil")
async def kullanici_sil_post(request: Request, uid: int):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403)
    try:
        db_kullanici_sil(uid)
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "KULLANICI_SİL", f"uid={uid}")
        return RedirectResponse("/kullanicilar?mesaj=silindi", 302)
    except Exception as e:
        kullanicilar_list = tum_kullanicilari_getir()
        return render(request, "kullanicilar.html", {
            "kullanicilar": kullanicilar_list, "hata": str(e)
        })

@app.post("/kullanici/{uid}/sifre")
async def kullanici_sifre(request: Request, uid: int, yeni_sifre: str = Form(...)):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403)
    kullanici_sifre_sifirla(uid, yeni_sifre)
    action_log_ekle(k["id"], k["username"], k["full_name"],
                    k["role"], "SİFRE_SIFIRLA", f"uid={uid}")
    return RedirectResponse("/kullanicilar", 302)


# ── LOGLAR ───────────────────────────────────────────────────
@app.get("/loglar", response_class=HTMLResponse)
async def loglar(request: Request, tip: str = "action", filtre: str = ""):
    k = giris_gerekli(request)
    if k["role"] != "admin":
        raise HTTPException(403, "Sadece admin erişebilir")
    action_logs = action_loglarini_getir()[:500]
    login_logs  = login_loglarini_getir()[:200]
    # Filtre uygula
    if filtre:
        action_logs = [l for l in action_logs
                       if filtre.upper() in (l.get("action_type") or "").upper()
                       or filtre.lower() in (l.get("full_name") or "").lower()
                       or filtre.lower() in (l.get("detail") or "").lower()]
    return render(request, "loglar.html", {
        "action_logs": action_logs,
        "login_logs":  login_logs,
        "aktif_tip":   tip,
        "filtre":      filtre,
    })



# ── RAPORLAR ─────────────────────────────────────────────────
@app.get("/raporlar", response_class=HTMLResponse)
async def raporlar(request: Request):
    giris_gerekli(request)
    kullanicilar_list = [u for u in tum_kullanicilari_getir()
                         if u["active"] and u["role"] != "admin"]
    return render(request, "raporlar.html", {
        "kullanicilar": kullanicilar_list,
        "today": datetime.now().strftime("%Y-%m-%d"),
        "son_rapor": None,
    })

from fastapi.responses import FileResponse
import tempfile, os as _os

def _pdf_olustur(baslik, icerik_satirlari, dosya_adi):
    """Basit PDF oluşturur, yolu döner."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        import datetime as _dt

        tmp = tempfile.mktemp(suffix=".pdf")
        doc = SimpleDocTemplate(tmp, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=2*cm, bottomMargin=1.5*cm)
        stiller = getSampleStyleSheet()
        s_baslik = ParagraphStyle("B", parent=stiller["Heading1"], fontSize=16,
                                   textColor=colors.HexColor("#1C2434"), fontName="Helvetica-Bold")
        s_alt    = ParagraphStyle("A", parent=stiller["Normal"], fontSize=9,
                                   textColor=colors.HexColor("#536478"))
        s_nor    = ParagraphStyle("N", parent=stiller["Normal"], fontSize=10,
                                   textColor=colors.HexColor("#1A2332"))
        els = [
            Paragraph("İzmir Büyükşehir Belediyesi – Gayrimenkul Geliştirme ve Yönetim Dairesi", s_alt),
            HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1A6FBF")),
            Spacer(1, 0.3*cm),
            Paragraph(baslik, s_baslik),
            Paragraph(f"Rapor Tarihi: {_dt.datetime.now().strftime('%d.%m.%Y %H:%M')}", s_alt),
            Spacer(1, 0.4*cm),
        ]
        for satir in icerik_satirlari:
            if isinstance(satir, str):
                els.append(Paragraph(satir, s_nor))
                els.append(Spacer(1, 0.1*cm))
            else:
                els.append(satir)
        doc.build(els)
        return tmp
    except ImportError:
        return None

@app.post("/rapor/tarih")
async def rapor_tarih(request: Request, bas: str = Form(...), bit: str = Form(...)):
    k = giris_gerekli(request)
    try:
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        veriler = [r for r in tum_files_ozet()
                   if bas <= (r.get("teslim_tarihi") or "")[:10] <= bit]
        baslik = f"Tarih Aralığı Raporu: {bas} – {bit}"
        satirlar = [f"Toplam {len(veriler)} kayıt bulundu.", ""]
        tablo_veri = [["Dosya No","İlçe","Ada","Parsel","Teslim Alan","Tarih","Durum"]]
        for r in veriler:
            tablo_veri.append([
                r.get("orijinal_dosya_no",""), r.get("ilce",""),
                r.get("ada",""), r.get("parsel",""),
                (r.get("teslim_alan_personel") or "")[:18],
                (r.get("teslim_tarihi") or "")[:10],
                r.get("durum","")
            ])
        from reportlab.lib.units import cm
        t = Table(tablo_veri, colWidths=[3*cm,3.5*cm,2*cm,2*cm,4.5*cm,3*cm,4*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1C2434")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),8),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F7F8FA"),colors.white]),
            ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#DDE1E7")),
            ("ROWHEIGHT",(0,0),(-1,-1),16),
        ]))
        yol = _pdf_olustur(baslik, [t], "tarih_raporu")
        if yol:
            return FileResponse(yol, media_type="application/pdf",
                                filename=f"tarih_raporu_{bas}_{bit}.pdf")
    except Exception as e:
        pass
    return RedirectResponse("/raporlar?hata=pdf_hatasi", 302)

@app.post("/rapor/personel")
async def rapor_personel(request: Request, personel: str = Form(""), bas: str = Form(...), bit: str = Form(...)):
    k = giris_gerekli(request)
    try:
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        veriler = [r for r in tum_files_ozet()
                   if (not personel or r.get("teslim_alan_personel","") == personel)
                   and bas <= (r.get("teslim_tarihi") or "")[:10] <= bit]
        per_lbl = personel if personel else "Tüm Personel"
        baslik = f"Personel Raporu: {per_lbl}"
        from reportlab.lib.units import cm
        tablo_veri = [["Dosya No","İlçe","Ada","Parsel","Teslim Alan","Tarih","Durum"]]
        for r in veriler:
            tablo_veri.append([
                r.get("orijinal_dosya_no",""), r.get("ilce",""),
                r.get("ada",""), r.get("parsel",""),
                (r.get("teslim_alan_personel") or "")[:18],
                (r.get("teslim_tarihi") or "")[:10],
                r.get("durum","")
            ])
        t = Table(tablo_veri, colWidths=[3*cm,3.5*cm,2*cm,2*cm,4.5*cm,3*cm,4*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0A7C4E")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),8),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F7F8FA"),colors.white]),
            ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#DDE1E7")),
            ("ROWHEIGHT",(0,0),(-1,-1),16),
        ]))
        yol = _pdf_olustur(baslik, [f"Toplam {len(veriler)} kayıt  ·  {bas} – {bit}", "", t], "personel")
        if yol:
            return FileResponse(yol, media_type="application/pdf",
                                filename=f"personel_raporu.pdf")
    except Exception as e:
        pass
    return RedirectResponse("/raporlar?hata=pdf_hatasi", 302)

@app.post("/rapor/ozet")
async def rapor_ozet(request: Request):
    k = giris_gerekli(request)
    try:
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        oz  = istatistik_ozet()
        ilc = ilce_bazli_istatistik()[:12]
        per = personel_bazli_istatistik()[:10]
        top = oz.get("toplam",0)
        satirlar = [
            f"<b>Genel Özet</b>",
            f"Toplam Dosya: {top}  |  Arşivde: {oz.get('arsivde',0)}  |  Zimmette: {oz.get('zimmette',0)}  |  Gecikmiş: {oz.get('gecikmis',0)}",
            "",
            "<b>İlçe Dağılımı (Top 12)</b>",
        ]
        t1 = Table([["İlçe","Toplam","Gecikmiş"]] + [[i["ilce"],i["toplam"],i.get("gecikmis",0)] for i in ilc],
                   colWidths=[8*cm,4*cm,4*cm], repeatRows=1)
        t1.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1A6FBF")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),9),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F7F8FA"),colors.white]),
            ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#DDE1E7")),
        ]))
        t2 = Table([["Personel","Zimmette","Gecikmiş"]] + [[p["personel"],p["zimmette"],p.get("gecikmis",0)] for p in per],
                   colWidths=[8*cm,4*cm,4*cm], repeatRows=1)
        t2.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0A7C4E")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),9),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F7F8FA"),colors.white]),
            ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#DDE1E7")),
        ]))
        from reportlab.platypus import Spacer
        yol = _pdf_olustur("Arşiv Durum Özet Raporu",
                           satirlar + [t1, Spacer(1,0.4*cm), "<b>Personel Bazlı (Top 10)</b>", t2],
                           "ozet")
        if yol:
            return FileResponse(yol, media_type="application/pdf", filename="ozet_raporu.pdf")
    except Exception as e:
        pass
    return RedirectResponse("/raporlar?hata=pdf_hatasi", 302)


# ── ONLINE KULLANICILAR API ──────────────────────────────────
@app.get("/api/online-kullanicilar")
async def api_online_kullanicilar(request: Request):
    k = aktif_kullanici(request)
    if not k:
        return JSONResponse({"ok": False, "kullanicilar": []})
    try:
        presence_guncelle(k["id"])  # Bu isteği yapan da online
        online = online_kullanici_bilgileri(dakika=3)
        # Admin gizle
        online = [u for u in online if u.get("role") != "admin"]
        return JSONResponse({"ok": True, "kullanicilar": online})
    except Exception as e:
        return JSONResponse({"ok": False, "kullanicilar": []})


# ── EN ÇOK BEKLEYEN ──────────────────────────────────────────
@app.get("/en-cok-bekleyen", response_class=HTMLResponse)
async def en_cok_bekleyen(request: Request):
    giris_gerekli(request)
    veriler = tum_files_ozet()
    geciken = sorted(
        [r for r in veriler if "GEC" in (r.get("durum") or "").upper()],
        key=lambda x: x.get("bekleme_gun", 0), reverse=True
    )
    return render(request, "en_cok_bekleyen.html", {"dosyalar": geciken})



# ── PROFİL ──────────────────────────────────────────────────
@app.get("/profil", response_class=HTMLResponse)
async def profil(request: Request):
    k = giris_gerekli(request)
    return render(request, "profil.html", {})

@app.post("/profil/sifre")
async def profil_sifre(
    request: Request,
    mevcut_sifre: str = Form(...),
    yeni_sifre: str = Form(...),
    yeni_sifre2: str = Form(...),
):
    k = giris_gerekli(request)
    if yeni_sifre != yeni_sifre2:
        return render(request, "profil.html", {"sifre_hata": "Yeni şifreler eşleşmiyor."})
    # Mevcut şifre kontrol
    test = giris_yap(k["username"], mevcut_sifre)
    if not test:
        return render(request, "profil.html", {"sifre_hata": "Mevcut şifre hatalı."})
    kullanici_sifre_sifirla(k["id"], yeni_sifre)
    action_log_ekle(k["id"], k["username"], k["full_name"], k["role"], "SİFRE_DEĞİŞTİR", "Kendi şifresini değiştirdi")
    return render(request, "profil.html", {"sifre_basari": "Şifreniz başarıyla değiştirildi."})


# ── MESAJ SİL ────────────────────────────────────────────────
@app.post("/mesaj/sil/{mesaj_id}")
async def mesaj_sil_post(request: Request, mesaj_id: int):
    k = giris_gerekli(request)
    try:
        mesaj_sil(mesaj_id, k["id"], k["full_name"], k["role"], "web-silindi")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


# ── SOHBETİ TEMİZLE ──────────────────────────────────────────
@app.post("/sohbet/temizle/{diger_id}")
async def sohbet_temizle(request: Request, diger_id: int):
    k = giris_gerekli(request)
    try:
        from db import konusma_sil
        konusma_sil(k["id"], diger_id, k["full_name"], k["role"])
        return JSONResponse({"ok": True})
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "hata": str(e), "detail": traceback.format_exc()})


# ── DUYURU GÖNDER ────────────────────────────────────────────
@app.post("/duyuru/gonder")
async def duyuru_gonder_post(
    request: Request,
    konu: str = Form(""),
    icerik: str = Form(...),
):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    mesaj_gonder(
        gonderen_id=k["id"], gonderen=k["full_name"],
        icerik=icerik, konu=konu, genel=True
    )
    return RedirectResponse("/mesajlar", 302)

# ── DOSYA DÜZENLE API ────────────────────────────────────────
@app.post("/api/dosya-duzenle")
async def api_dosya_duzenle(
    request: Request,
    file_id: int = Form(...),
    teslim_alan: str = Form(""),
    teslim_alan_serbest: str = Form(""),
    notlar: str = Form(""),
):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    try:
        isim = teslim_alan if teslim_alan and teslim_alan != "_ignore" else teslim_alan_serbest
        if not isim:
            return JSONResponse({"ok": False, "hata": "Teslim alan boş olamaz"})
        basari = zimmet_guncelle(
            file_id=file_id, teslim_alan=isim,
            notlar=notlar
        )
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "DOSYA_DÜZENLE", f"file_id={file_id}")
        return JSONResponse({"ok": basari})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


# ── YENİDEN ZİMMETLE ─────────────────────────────────────────
@app.post("/api/yeniden-zimmetle/{file_id}")
async def api_yeniden_zimmetle(
    request: Request, file_id: int,
    teslim_alan: str = Form(...),
    teslim_alan_user_id: int = Form(None),
    notlar: str = Form(""),
):
    k = giris_gerekli(request)
    if k["role"] not in ("admin", "arsiv"):
        raise HTTPException(403)
    try:
        import datetime as _dt
        from db import veritabani_baglantisi as _vb
        # Önce açık zimmet varsa kapat (iade et)
        if acik_movement_var_mi(file_id):
            conn = _vb()
            simdi = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("""
                UPDATE movements SET iade_tarihi=?, iade_alan_gorevli=?
                WHERE file_id=? AND iade_tarihi IS NULL
            """, (simdi, k["full_name"], file_id))
            conn.commit(); conn.close()
        # Yeni zimmet oluştur
        simdi = datetime.now().strftime("%Y-%m-%d %H:%M")
        mid = movement_ekle(
            file_id=file_id,
            teslim_tarihi=simdi,
            teslim_alan_personel=teslim_alan,
            veren_arsiv_gorevlisi=k["full_name"],
            notlar=notlar,
            teslim_alan_user_id=teslim_alan_user_id,
        )
        action_log_ekle(k["id"], k["username"], k["full_name"],
                        k["role"], "YENİDEN_ZİMMET",
                        f"file_id={file_id} teslim_alan={teslim_alan}")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


# ── DOSYA GEÇMİŞİ API ────────────────────────────────────────
@app.get("/api/dosya-gecmis/{file_id}")
async def api_dosya_gecmis(request: Request, file_id: int):
    # Cookie olmasa bile çalışsın - sadece giriş yapmış olsun yeterli
    try:
        gecmis = file_gecmisi_getir(file_id)
        return JSONResponse({"ok": True, "gecmis": gecmis})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


# ── MESAJ FOTO GÖNDER ────────────────────────────────────────
@app.post("/mesaj/foto")
async def mesaj_foto(
    request: Request,
    alici_id: int = Form(...),
    foto: UploadFile = None,
):
    k = giris_gerekli(request)
    if not foto:
        return JSONResponse({"ok": False, "hata": "Dosya seçilmedi"})
    try:
        import base64, mimetypes
        icerik_bytes = await foto.read()
        if len(icerik_bytes) > 5 * 1024 * 1024:
            return JSONResponse({"ok": False, "hata": "Maksimum 5MB"})
        b64 = base64.b64encode(icerik_bytes).decode()
        mime = foto.content_type or "image/jpeg"
        icerik = f"[FOTO:{mime};{b64}]"
        tum_k = {u["id"]: u["full_name"] for u in tum_kullanicilari_getir()}
        mesaj_gonder(
            gonderen_id=k["id"], gonderen=k["full_name"],
            icerik=icerik, alici_id=alici_id,
            alici=tum_k.get(alici_id, ""),
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "hata": str(e)})


# ── TELEFON REHBERİ ──────────────────────────────────────────
@app.get("/rehber", response_class=HTMLResponse)
async def rehber(request: Request):
    giris_gerekli(request)
    # Admin hariç aktif kullanıcılar
    kullanicilar = [u for u in tum_kullanicilari_getir()
                    if u["active"] and u["role"] != "admin"]
    return render(request, "rehber.html", {"kullanicilar": kullanicilar})


from fastapi import Request as _Req
from fastapi.responses import HTMLResponse as _HTML
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: _Req, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(request=request, name="hata.html",
            context={"request":request,"kullanici":aktif_kullanici(request),
                     "app_title":APP_TITLE,"app_versiyon":APP_VERSIYON,
                     "okunmamis_mesaj":0,
                     "kod":"404","ikon":"🔍",
                     "baslik":"Sayfa Bulunamadı",
                     "aciklama":"Aradığınız sayfa mevcut değil veya taşınmış olabilir."},
            status_code=404)
    if exc.status_code == 403:
        return templates.TemplateResponse(request=request, name="hata.html",
            context={"request":request,"kullanici":aktif_kullanici(request),
                     "app_title":APP_TITLE,"app_versiyon":APP_VERSIYON,
                     "okunmamis_mesaj":0,
                     "kod":"403","ikon":"🚫",
                     "baslik":"Erişim Reddedildi",
                     "aciklama":"Bu sayfaya erişim yetkiniz bulunmuyor."},
            status_code=403)
    return templates.TemplateResponse(request=request, name="hata.html",
        context={"request":request,"kullanici":aktif_kullanici(request),
                 "app_title":APP_TITLE,"app_versiyon":APP_VERSIYON,
                 "okunmamis_mesaj":0,
                 "kod":str(exc.status_code),"ikon":"⚠️",
                 "baslik":"Hata","aciklama":str(exc.detail)},
        status_code=exc.status_code)

@app.on_event("startup")
async def startup():
    tablo_olustur()
    varsayilan_kullanicilari_olustur()
    mesaj_tablolari_olustur()
    online_tablolari_olustur()
    print(f"✓ {APP_TITLE} {APP_VERSIYON} başlatıldı")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
