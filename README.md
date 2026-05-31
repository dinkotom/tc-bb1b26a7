# Galerie fotopastí (Z lesa)

Statická galerie posledních **7 dní** fotek z fotopastí. **Čte z Google Drive**
(archiv, který plní zpracovávací pipeline `trailcam`) a publikuje na GitHub Pages.
`noindex`, neuhádnutelná URL, obnova v prohlížeči á 15 min + lightbox.

Galerie je **jen pro čtení** – nešahá na e-maily ani na zpracování. Drive zůstává
soukromý; veřejně (na skryté URL) je jen nedávný výřez fotek.

## Potřebné GitHub Secrets
(Settings → Secrets and variables → Actions → New repository secret)

| Secret | Obsah |
|---|---|
| `GOOGLE_TOKEN_JSON` | celý obsah `token.json` (OAuth, z projektu trailcam) |
| `TARGET_DRIVE_FOLDER_ID` | ID kořenové složky na Drive (stejné jako v trailcamu) |

Bez nich se nasadí prázdná galerie; po doplnění a spuštění workflow se zaplní.

## Build / cron
GitHub Actions (`.github/workflows/build.yml`) běží ~každých 20 min: stáhne z Drive
nové fotky posledních 7 dní (přírůstkově, s cache), vyrobí `public/index.html` a nasadí.
Fotky se **necommitují do gitu** – jdou jen do publikovaného artefaktu.

## Lokální náhled
```sh
python3 build_gallery.py --no-fetch   # postaví stránku z public/photos
```

Rozsah dní = `GALLERY_DAYS` (výchozí 7).
