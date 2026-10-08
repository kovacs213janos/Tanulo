# Tanuló

Böngészőből (mobilról is) használható tanulófelület. A tananyag JSON-tartalomcsomagként kerül fel; a gyerekek kártyákkal, kvízzel, forrásos feladatokkal, idővonallal és összefoglalóval tanulnak, a haladás profilonként a szerveren tárolódik.

- Specifikáció: [`SPEC.md`](SPEC.md) (a csomagformátum a 7. pontban)
- Csomag készítése Claude-dal: [`docs/csomagkeszito-prompt.md`](docs/csomagkeszito-prompt.md)
- Bemutató csomag kipróbáláshoz: [`examples/bemutato-naprendszer.json`](examples/bemutato-naprendszer.json)

## Telepítés Dockerrel

```bash
# a repó gyökerében
sudo install -d -o 10001 -g 10001 data     # a konténer a 10001-es felhasználóként fut
cp .env.example .env                       # BIND_ADDR beállítása, lásd lent
docker compose up -d --build
docker compose logs -f                     # "Uvicorn running on http://0.0.0.0:8000"
curl -s http://127.0.0.1:8000/api/health   # {"status":"ok",...}
```

Első megnyitáskor a felület a szülői profil létrehozását kéri. Utána: **Feltöltés** → a bemutató csomag → **Mentés**.

Frissítés: `git pull && docker compose up -d --build`. Az adatbázis-séma magától frissül (`PRAGMA user_version`).

## Elérés és védelem

Nincs jelszó, ezért a szolgáltatás **nem lehet nyílt a weben**. A compose alapból csak a `127.0.0.1`-en figyel. A `.env`-ben a `BIND_ADDR` dönti el, honnan érhető el:

| Cél | `BIND_ADDR` | Megjegyzés |
|---|---|---|
| Otthoni wifiről (telefonok, laptopok) | a szerver LAN-címe, pl. `192.168.1.10` | A legegyszerűbb. Házon kívülről nem megy. |
| Csak a tailnetről | a szerver Tailscale-címe (`tailscale ip -4`) | A gyerekek eszközein is kell a Tailscale app. **Funnel nélkül.** |
| Reverse proxy mögött (Caddy, nginx) | `127.0.0.1` | A proxy adjon basic auth-ot vagy Cloudflare Access-t. |

Caddy példa basic auth-tal (`caddy hash-password` adja a hash-t):

```
tanulo.example.hu {
    basic_auth {
        csalad $2a$14$...
    }
    reverse_proxy 127.0.0.1:8000
}
```

## Adatok és mentés

- Minden adat a `./data` könyvtárban: `app.db` (SQLite, WAL) és `backups/`.
- **Napi automatikus mentés**: `data/backups/app-ÉÉÉÉHHNN.db`, konzisztens pillanatkép (`VACUUM INTO`), `BACKUP_KEEP_DAYS` (alapból 14) napig. Ugyanazon a lemezen van, mint az adatbázis, ezért érdemes a gépen kívülre is másolni, pl. cronból: `rsync -a /srv/tanulo/data/backups/ nas:/backup/tanulo/`.
- **Export / visszatöltés** a felületen (Kezelés): egyetlen JSON-fájl, minden profillal, csomaggal (minden verzióval) és haladással. Új gépre költözéskor: üres telepítés → az első képernyőn „Van mentésed?” → exportfájl.
- Visszaállítás napi mentésből: `docker compose stop && cp data/backups/app-20261008.db data/app.db && rm -f data/app.db-wal data/app.db-shm && docker compose start`.

## Beállítások (környezeti változók)

| Változó | Alapérték | Leírás |
|---|---|---|
| `BIND_ADDR` | `127.0.0.1` | (compose) melyik gépcímen figyeljen |
| `HOST_PORT` | `8000` | (compose) gépoldali port |
| `PORT` | `8000` | port a konténerben |
| `DATA_DIR` | `/data` | adatkönyvtár |
| `MAX_UPLOAD_MB` | `2` | maximális csomagméret |
| `BACKUP_ENABLED` | `1` | napi mentés be/ki |
| `BACKUP_KEEP_DAYS` | `14` | hány napi mentés maradjon |
| `LOG_LEVEL` | `INFO` | naplózási szint (konzolra) |
| `TZ` | `Europe/Budapest` | a napi mentés ennek a napjai szerint készül |

## Fejlesztés

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
DATA_DIR=./data-dev uvicorn --factory app.main:create_app --reload --port 8000
```

Tesztek:

```bash
pytest                                   # API és validátor, köztük az elfogadási kritériumok
python -m playwright install chromium    # egyszer
# böngészős végigjátszás üres adatbázisú szerver ellen (360/390 px, sötét téma, billentyűzet):
rm -rf ./data-e2e && DATA_DIR=./data-e2e uvicorn --factory app.main:create_app --port 8765 &
python tests/e2e_ui.py http://127.0.0.1:8765 ./shots
```

Szerkezet:

```
app/          FastAPI backend (main.py: végpontok, validator.py: csomagformátum,
              packs.py: tárolás és lista, transfer.py: export/import, backup.py, db.py: séma)
static/       felület: index.html, app.css, app.js (vanilla JS, build nélkül)
examples/     bemutató csomag
tests/        pytest + Playwright
docs/         csomagkészítő prompt
```

Interaktív API-leírás: `http://<szerver>:8000/api/docs`.
