# CLAUDE.md – Tanuló

Családi tanulóplatform: FastAPI + SQLite backend, vanilla JS SPA, egy Docker-konténer. A teljes specifikáció a `SPEC.md`-ben van; viselkedést érintő változtatásnál azt is frissítsd.

## Parancsok

```bash
pip install -r requirements-dev.txt                       # egyszer
pytest                                                    # 44 teszt, ~3 mp; minden változtatás után
DATA_DIR=./data-dev uvicorn --factory app.main:create_app --reload --port 8000
# böngészős teszt (360/390 px, sötét téma, billentyűzet) – ÜRES adatbázisú szerver kell:
rm -rf ./data-e2e && DATA_DIR=./data-e2e uvicorn --factory app.main:create_app --port 8765 &
python tests/e2e_ui.py http://127.0.0.1:8765 ./shots      # képernyőképek a ./shots-ba
docker compose up -d --build                              # éles futtatás
```

Felületi változtatás után futtasd az e2e tesztet is, és nézd meg a képernyőképeket.

## Felépítés

- `app/main.py` – végpontok, jogosultság (`X-Profile-Id` fejléc → `get_profile` / `require_profile` / `require_parent`), hibakezelés. Az app factory-val jön létre (`create_app(settings)`), modulszintű `app` nincs.
- `app/validator.py` – a `tanulo-csomag/1` formátum ellenőrzése. Hibák és figyelmeztetések `path: message` alakban, magyarul.
- `app/packs.py` – mentés/verziózás, lista, keresés, haladásszámlálás.
- `app/transfer.py` – export (`tanulo-export/1`) és import (egy tranzakcióban mindent cserél).
- `app/backup.py` – napi `VACUUM INTO` mentés háttérszálon, megőrzési idővel.
- `app/db.py` – kapcsolat, séma, migrációk (`MIGRATIONS` lista + `PRAGMA user_version`).
- `static/app.js` – az egész felület egy IIFE-ben: `h()` elemkészítő, `md()` szűk Markdown, `api()`, `saver` (kötegelt haladásmentés), hash-router, nézetek (`view*`) és tanulási módok (`mode*`).

## Invariánsok – ezeket ne törd el

- **A haladás az elemazonosítóhoz kötődik** (`card_progress.item_id`, `task_answers.task_id/question_id`), nem a verzióhoz. Új verzió feltöltése soha nem töröl haladást.
- A `pack_items` mindig az **aktuális** verzió elemeit tartalmazza; ebből számol a lista, és ez szűri a jelöléseket. Ha a csomag tartalma változik (feltöltés, import), `rebuild_items()` kell.
- `search_text` = `normalize(cím, téma, tantárgy, címkék, szint)`; minden metaadat-változáskor újraszámolandó (`make_search_text`). Keresés: szavanként `LIKE '%…%' ESCAPE '\'`. Ne cseréld FTS5-re (részszó-keresés kell a magyar összetett szavak miatt; lásd SPEC 11. pont).
- **Migráció csak hozzáfűzéssel**: új séma = új elem a `MIGRATIONS` végére. Meglévőt ne módosíts. Ha új tábla jön, a `transfer.TABLES` és `DELETE_ORDER` is bővítendő, különben az export/import elveszti.
- A célkörnyezet `python:3.12-slim` (bookworm), **SQLite 3.40**: ne használj újabb SQLite-funkciót (pl. `->>`, `unixepoch()`, STRICT táblák, FTS5 trigram ékezetlenítéssel). Python: 3.12-kompatibilis szintaxis.
- Időbélyeg: `db.now_iso()` (UTC, ezredmásodperc) – a rendezés erre épül.
- A felület **nem tölt be külső erőforrást** (CDN, webfont): helyi hálózaton net nélkül is mennie kell.
- Felhasználói szövegben a tartalom mindig `md()`-n vagy `textContent`-en megy át; `innerHTML`-t csak `md()`/`esc()` kimenetével szabad. A `h()` `html` attribútuma is csak ilyet kaphat.
- `fill(parent, ...)` / `add(parent, ...)` a `replaceChildren` / `append` helyett: kiszűri a `null`-t és kibontja a tömböket (különben „null” vagy „[object HTMLElement]” kerül a képernyőre).
- CSS egyéni tulajdonság (`--c`, `--s`) a `h()` `style` objektumán át megy (`setProperty`); `Object.assign(el.style, …)` ezt csendben elnyeli.

## Stílus és nyelv

- Minden felhasználói szöveg és API-hibaüzenet **magyar**; a kód, az azonosítók és a JSON-kulcsok angolok. Kódkommentek magyarul.
- API-hiba: `err(status, "magyar üzenet", "gepi_kod", errors=[...])` → `{"detail", "code", "errors"?}`.
- Felület: mobil először (360 px), sötét téma tokenekkel (`:root` + `prefers-color-scheme` + `data-theme`), minden interaktív elem legalább 44 px magas, látható fókusz.
- Vizuális irány: tanulóasztal – indexkártya (piros felső vonal, kék sorvonalak), szövegkiemelő-sárga (tudom) és -rózsaszín (még nem megy), tintakék kiemelés, a tananyag serif, a kezelőfelület rendszer-sans. Új elemnél ehhez igazodj, ne hozz be új díszítést.

## Állapot

- v1 kész: minden elfogadási kritériumhoz van automatikus teszt (`tests/test_api.py::test_acceptance_*`, `tests/e2e_ui.py`).
- **A Docker-képet a fejlesztői környezetben nem lehetett megépíteni** (a regisztri nem volt elérhető): az első `docker compose up --build` az éles gépen az első valódi próba. A Python 3.12-szintaxis és az SQLite 3.40-kompatibilitás ellenőrizve van.
- v2 ötletek: SPEC 10. pont (FSRS a `review_log`-ra építve, szülői statisztika, képi források, PDF→csomag generálás).
