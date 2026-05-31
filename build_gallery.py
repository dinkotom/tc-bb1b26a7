#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Galerie fotopastí – čte fotky z Google Drive (archiv) a generuje statickou
stránku pro GitHub Pages. Zobrazuje posledních N dní, seskupeno podle dne → lokality.

Drive struktura:  <ROOT>/YYYY-MM-DD/<Lokalita>/foto.jpg

Spuštění:
    python3 build_gallery.py                 # stáhne z Drive + postaví stránku
    python3 build_gallery.py --no-fetch       # jen postaví stránku z public/photos (lokální náhled)

Konfigurace přes prostředí:
    GOOGLE_TOKEN_JSON        obsah token.json (OAuth authorized_user)  – nebo soubor token.json
    TARGET_DRIVE_FOLDER_ID   ID kořenové složky na Drive
    GALLERY_DAYS             kolik dní zpět (výchozí 7)
"""

import argparse
import datetime as dt
import html
import json
import os
import sys

OUT_DIR = "public"
PHOTOS_DIR = os.path.join(OUT_DIR, "photos")
DAYS = int(os.getenv("GALLERY_DAYS", "7"))
IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def drive_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    # Scope nepředáváme – použijí se ty, na které byl token vydán
    # (jinak Google při refreshi vrátí invalid_scope). Čteme jen, nezapisujeme.
    token_json = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json:
        info = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(info)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json")
    else:
        sys.exit("Chybí GOOGLE_TOKEN_JSON nebo token.json.")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def list_children(service, parent_id, only_folders=False, only_images=False):
    q = f"'{parent_id}' in parents and trashed=false"
    if only_folders:
        q += " and mimeType='application/vnd.google-apps.folder'"
    if only_images:
        q += " and mimeType contains 'image/'"
    items, token = [], None
    while True:
        resp = service.files().list(
            q=q, spaces="drive", pageSize=1000, pageToken=token,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            orderBy="name").execute()
        items.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return items


def download(service, file_id, dest):
    from googleapiclient.http import MediaIoBaseDownload
    import io
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with io.FileIO(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, service.files().get_media(fileId=file_id))
        done = False
        while not done:
            _, done = downloader.next_chunk()


def fetch_recent(days):
    """Stáhne fotky z posledních `days` dní do public/photos (přírůstkově)."""
    root = os.getenv("TARGET_DRIVE_FOLDER_ID")
    if not root:
        sys.exit("Chybí TARGET_DRIVE_FOLDER_ID.")
    service = drive_service()

    today = dt.date.today()
    povolene = {(today - dt.timedelta(days=i)).isoformat() for i in range(days)}

    den_slozky = [f for f in list_children(service, root, only_folders=True)
                  if f["name"] in povolene]

    stazeno = 0
    for den in sorted(den_slozky, key=lambda f: f["name"]):
        for lok in list_children(service, den["id"], only_folders=True):
            for img in list_children(service, lok["id"], only_images=True):
                dest = os.path.join(PHOTOS_DIR, den["name"], lok["name"], img["name"])
                if os.path.exists(dest):
                    continue
                download(service, img["id"], dest)
                stazeno += 1
    print(f"Staženo nových fotek: {stazeno}", file=sys.stderr)

    # prune dnů mimo okno
    if os.path.isdir(PHOTOS_DIR):
        for d in os.listdir(PHOTOS_DIR):
            p = os.path.join(PHOTOS_DIR, d)
            if os.path.isdir(p) and d not in povolene:
                import shutil
                shutil.rmtree(p)
                print(f"Smazán starý den: {d}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Sestavení HTML
# ---------------------------------------------------------------------------

DNY_CZ = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]
MESICE_CZ = ["", "ledna", "února", "března", "dubna", "května", "června",
             "července", "srpna", "září", "října", "listopadu", "prosince"]


def cesky_datum(iso):
    try:
        d = dt.date.fromisoformat(iso)
        return f"{DNY_CZ[d.weekday()]} {d.day}. {MESICE_CZ[d.month]}"
    except ValueError:
        return iso


def nacti_strukturu():
    """Vrátí {den: {lokalita: [relativní_cesty]}} z public/photos."""
    data = {}
    if not os.path.isdir(PHOTOS_DIR):
        return data
    for den in os.listdir(PHOTOS_DIR):
        dp = os.path.join(PHOTOS_DIR, den)
        if not os.path.isdir(dp):
            continue
        for lok in os.listdir(dp):
            lp = os.path.join(dp, lok)
            if not os.path.isdir(lp):
                continue
            fotky = sorted(f for f in os.listdir(lp) if f.lower().endswith(IMG_EXT))
            if fotky:
                data.setdefault(den, {}).setdefault(lok, []).extend(
                    f"photos/{den}/{lok}/{f}" for f in fotky)
    return data


PAGE = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta http-equiv="refresh" content="900">
<meta name="theme-color" content="#0e120f">
<title>Fotopasti – Tošanovice</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,ital,wght@9..144,1,500..700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
  :root{--bg:#0e120f; --panel:#161c17; --ink:#e9eee7; --muted:#8b988a;
    --line:rgba(255,255,255,.09); --moss:#8bbf5f; --amber:#e0a93f;}
  *{box-sizing:border-box;}
  html{-webkit-text-size-adjust:100%;}
  body{margin:0; color:var(--ink); background:var(--bg); padding:0 16px 60px;
    font-family:"JetBrains Mono",ui-monospace,monospace; line-height:1.4;
    background-image:radial-gradient(120% 50% at 50% -10%, rgba(139,191,95,.10), transparent 60%);
    background-attachment:fixed;}
  .wrap{max-width:1100px; margin:0 auto;}
  header{padding:34px 2px 6px;}
  .kicker{font-size:.7rem; letter-spacing:.32em; text-transform:uppercase; color:var(--muted);}
  h1{font-family:"Fraunces",Georgia,serif; font-style:italic; font-weight:600;
    font-size:clamp(2.4rem,9vw,3.6rem); line-height:.92; margin:.12em 0 .1em; letter-spacing:-.02em;}
  h1 .d{color:var(--moss);}
  .sub{font-size:.78rem; color:var(--muted);}

  .day{margin:34px 0 6px; padding-top:14px; border-top:1px solid var(--line);
    display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;}
  .day h2{font-family:"Fraunces",serif; font-weight:600; font-size:1.5rem; margin:0; letter-spacing:-.01em;}
  .day .iso{font-size:.72rem; color:var(--muted);}

  .loc{margin:16px 0 6px; display:flex; align-items:center; gap:9px;}
  .loc .name{font-size:1.15rem; font-weight:600; color:var(--moss); letter-spacing:.01em;}
  .loc .cnt{font-size:.72rem; color:var(--muted);}
  .loc::after{content:""; flex:1; height:1px; background:var(--line);}

  .grid{display:grid; gap:8px; grid-template-columns:repeat(auto-fill,minmax(150px,1fr));}
  .grid a{display:block; position:relative; aspect-ratio:4/3; border-radius:11px; overflow:hidden;
    background:var(--panel); border:1px solid var(--line);}
  .grid img{width:100%; height:100%; object-fit:cover; display:block; transition:transform .3s ease;}
  @media(hover:hover){ .grid a:hover img{transform:scale(1.05);} }
  .grid .tm{position:absolute; left:0; right:0; bottom:0; padding:14px 8px 5px;
    font-size:.68rem; color:#fff; background:linear-gradient(transparent, rgba(0,0,0,.7));}

  .empty{border:1px dashed var(--line); border-radius:14px; padding:40px 18px; text-align:center;
    color:var(--muted); margin:24px 0;}
  footer{margin-top:34px; text-align:center; font-size:.68rem; color:var(--muted);}
  footer a{color:var(--moss);}

  /* lightbox */
  #lb{position:fixed; inset:0; z-index:50; background:rgba(8,10,8,.94); display:none;
    align-items:center; justify-content:center; padding:20px; cursor:zoom-out;}
  #lb.on{display:flex;}
  #lb img{max-width:100%; max-height:92vh; border-radius:8px; box-shadow:0 20px 60px rgba(0,0,0,.6); cursor:default;}
  #lb .cap{position:fixed; bottom:14px; left:0; right:0; text-align:center; color:#cfd8cb; font-size:.74rem;}
  #lb .nav{position:fixed; top:50%; transform:translateY(-50%); cursor:pointer; padding:0;
    width:48px; height:48px; border-radius:50%; font-size:1.9rem; line-height:1;
    background:rgba(255,255,255,.08); color:#fff; border:1px solid rgba(255,255,255,.18);
    display:flex; align-items:center; justify-content:center; transition:background .2s;}
  #lb .nav:hover{background:rgba(255,255,255,.22);}
  #lb .prev{left:14px;} #lb .next{right:14px;}
  #lb .close{top:14px; right:14px; transform:none; font-size:1.5rem;}
  @media (max-width:520px){ #lb .nav{width:40px; height:40px; font-size:1.5rem;} }
  @media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important;}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="kicker">Posledních __DNI__ dní</div>
    <h1>Fotopasti<span class="d"> – Tošanovice</span></h1>
    <div class="sub">Aktualizováno __CAS__</div>
  </header>
  __TELO__
  <footer><a href="https://dinkotom.github.io/domov-60de93c6/">← Doma</a> · zdroj: Google Drive · obnova á 15 min</footer>
</div>
<div id="lb">
  <button class="nav close" aria-label="Zavřít (Esc)">×</button>
  <button class="nav prev" aria-label="Předchozí (←)">‹</button>
  <img alt="">
  <button class="nav next" aria-label="Další (→)">›</button>
  <div class="cap"></div>
</div>
<script>
  var lb=document.getElementById('lb'), lbimg=lb.querySelector('img'), cap=lb.querySelector('.cap');
  var links=[].slice.call(document.querySelectorAll('.grid a')), idx=-1;
  function show(i){
    if(!links.length) return;
    idx=(i+links.length)%links.length;
    var a=links[idx];
    lbimg.src=a.getAttribute('href'); cap.textContent=a.dataset.cap||'';
    lb.classList.add('on');
  }
  function closeLb(){ lb.classList.remove('on'); }
  links.forEach(function(a,i){ a.addEventListener('click', function(e){ e.preventDefault(); show(i); }); });
  lb.addEventListener('click', function(e){ if(e.target===lb) closeLb(); });   // klik na pozadí zavře
  lb.querySelector('.close').addEventListener('click', function(e){ e.stopPropagation(); closeLb(); });
  lb.querySelector('.prev').addEventListener('click', function(e){ e.stopPropagation(); show(idx-1); });
  lb.querySelector('.next').addEventListener('click', function(e){ e.stopPropagation(); show(idx+1); });
  document.addEventListener('keydown', function(e){
    if(!lb.classList.contains('on')) return;
    if(e.key==='Escape') closeLb();
    else if(e.key==='ArrowRight') show(idx+1);
    else if(e.key==='ArrowLeft') show(idx-1);
  });
</script>
</body>
</html>
"""


def _popisek(rel):
    """Z názvu souboru 'YYYY-MM-DD HH:MM Lokalita.jpg' vytáhne čas (HH:MM)."""
    base = os.path.splitext(os.path.basename(rel))[0]
    import re
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", base)   # jen reálný čas, ne datum
    return f"{m.group(1)}:{m.group(2)}" if m else base


def build_index():
    data = nacti_strukturu()
    if data:
        bloky = []
        for den in sorted(data, reverse=True):
            lokality = data[den]
            celkem = sum(len(v) for v in lokality.values())
            blok = [f'<div class="day"><h2>{html.escape(cesky_datum(den))}</h2>'
                    f'<span class="iso">{html.escape(den)} · {celkem} foto</span></div>']
            for lok in sorted(lokality):
                fotky = lokality[lok]
                blok.append(f'<div class="loc"><span class="name">{html.escape(lok)}</span>'
                            f'<span class="cnt">{len(fotky)}</span></div>')
                blok.append('<div class="grid">')
                for rel in fotky:
                    cap = html.escape(f"{lok} · {_popisek(rel)}")
                    blok.append(
                        f'<a href="{html.escape(rel)}" data-cap="{cap}">'
                        f'<img loading="lazy" src="{html.escape(rel)}" alt="{cap}">'
                        f'<span class="tm">{html.escape(_popisek(rel))}</span></a>')
                blok.append('</div>')
            bloky.append("\n".join(blok))
        telo = "\n".join(bloky)
    else:
        telo = '<div class="empty">Zatím žádné fotky v posledních dnech.</div>'

    cas = dt.datetime.now().strftime("%-d.%-m.%Y %H:%M")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DNI__", str(DAYS))
                    .replace("__CAS__", html.escape(cas))
                    .replace("__TELO__", telo))
    print(f"Stránka hotová ({sum(len(v) for d in data.values() for v in d.values())} fotek).", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="nestahovat z Drive, jen postavit stránku")
    args = ap.parse_args()
    if not args.no_fetch:
        # bez konfigurace fetch přeskočíme a postavíme prázdnou stránku (1. nasazení)
        if not (os.getenv("GOOGLE_TOKEN_JSON") or os.path.exists("token.json")) \
           or not os.getenv("TARGET_DRIVE_FOLDER_ID"):
            print("VAROVÁNÍ: chybí GOOGLE_TOKEN_JSON / TARGET_DRIVE_FOLDER_ID "
                  "– přeskakuji stahování, stavím prázdnou galerii.", file=sys.stderr)
        else:
            fetch_recent(DAYS)
    build_index()


if __name__ == "__main__":
    main()
