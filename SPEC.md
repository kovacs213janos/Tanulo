# Tanulóplatform – specifikáció v1.1

A v1 specifikáció megvalósított, pontosított változata. A v1-hez képesti eltérések a 11. pontban vannak összegyűjtve, indoklással.

## 1. Cél

Böngészőből (asztali és mobil) elérhető tanulófelület a gyerekeknek. A tananyagok tartalomcsomagként (JSON) kerülnek fel, a rendszer tárolja őket, és profilonként menti a haladást. A csomagokat Claude generálja a tanári anyagokból a 7. pont szerinti formátumban (kész prompt: `docs/csomagkeszito-prompt.md`).

## 2. Hatókör

Benne van a v1-ben:

- Profilok jelszó nélkül.
- Anyagtár címmel, témával, tantárggyal, címkékkel, és keresés köztük.
- Csomag feltöltése, frissítése, archiválása, végleges törlése.
- Tanulási módok: kártyák, kvíz, forrásos feladatok, idővonal, összefoglaló, csapdák.
- Szerveroldali, tartós tárolás: a haladás másnap és másik eszközön is megvan.
- Teljes export és visszatöltés; napi automatikus adatbázismentés.

Nincs benne a v1-ben:

- Jelszavas bejelentkezés.
- Automatikus generálás PDF-ből.
- Ismétléses tanulási algoritmus (v2). A v1 már naplózza a jelöléseket (`review_log`), hogy a v2 ne üres előzménnyel induljon.
- Képi források.
- Több család vagy szervezet kiszolgálása.

## 3. Felhasználás

### Profilok

- A nyitóképernyő a profilválasztó: név és színes monogram. Kattintásra belép, jelszó nincs.
- A kiválasztott profilt az eszköz megjegyzi (localStorage), és bármikor át lehet váltani (jobb felső monogram).
- Szerep: `parent` vagy `child`. Feltölteni, szerkeszteni, archiválni, törölni, exportálni, visszatölteni és profilt kezelni csak parent profillal lehet. A backend is ellenőrzi (`X-Profile-Id` alapján), de ez kényelmi korlát, nem biztonsági; a védelmet a 8. pont adja.
- Első indításkor (nincs profil) a felület az első, szülői profil létrehozását kéri; itt exportfájlból vissza is lehet tölteni mindent.
- Legalább egy szülői profilnak mindig maradnia kell (nem törölhető, nem minősíthető vissza).

### Anyagtár

- Lista. Minden elemen látszik a cím, a tantárgy, a szint, a téma, a címkék, a frissítés dátuma és a profil haladása („Tudom: 34/160”, kiemelősávval: sárga = tudom, rózsaszín = még nem megy).
- Keresés egy mezőben cím, téma, tantárgy, címkék és szint alapján, kis- és nagybetűre és ékezetre érzéketlenül, **részszóra is**: a „tortenet” megtalálja a „Társadalomtörténet”-et. Több szó esetén mindegyiknek szerepelnie kell.
- Szűrők: tantárgy, címke. Rendezés: legutóbb használt (az adott profil szerint), legutóbb feltöltött, cím szerint.
- Szülőnek: „Archiváltak” kapcsoló (ha van archivált anyag).

### Anyag nézet

Fülek, de csak azok, amelyekhez a csomagban van tartalom.

**Kártyák**
- Fejezetszűrő, keverés, „csak amit még nem tudok” szűrő (a beállítás megmarad az eszközön).
- Megfordítás (kattintás/koppintás), valamint „Tudom” és „Még nem megy” jelölés; jelölés után a következő kártya jön.
- Billentyűk: Szóköz/Enter = fordít, ←/→ = lapoz, 1 = tudom, 2 = még nem megy. Mobilon vízszintes húzással is lehet lapozni.
- A kör végén összesítő, és „Még egyszer, ami nem megy”.

**Kvíz**
- Fejezetszűrő; egy kör 5/10/15/20 vagy az összes kérdés, véletlen sorrendben, az opciók is keverve.
- Válasz után azonnali visszajelzés magyarázattal. Billentyűk: 1–6 válasz, Enter tovább.
- A végén eredmény és a hibás kérdések listája helyes válasszal; „Hibásak újra”. Minden kör eredménye mentődik, a legutóbbi 10 látszik.

**Forrásos feladatok**
- Forrásszöveg vagy -táblázat (mobilon a táblázat soronként kártyává alakul), „Kivonat” jelölés, ha `excerpt: true`.
- Kérdések szövegmezővel; a beírt válasz automatikusan mentődik („Mentve 18:39”).
- Megoldás kérdésenként vagy egyszerre mind kinyitható.

**Idővonal**: dátum és esemény lista `sort_key` szerint, fejezetszűrővel.

**Összefoglaló**: elején a vizsgainformáció (`meta.exam_info`), tartalomjegyzék ugrógombokkal, fejezetenkénti blokkok, a végén a „Csapdák”, legalul a `source_note`.

### Feltöltés (csak parent)

1. JSON-fájl kiválasztása vagy szöveg beillesztése.
2. Ellenőrzés. Hiba esetén mezőszintű, magyar nyelvű lista, például `cards[12].chapter: "9" nem létező fejezet`. A figyelmeztetések (pl. ismeretlen kulcs) nem akadályozzák a mentést.
3. Előnézet a darabszámokkal, és hogy új anyag lesz-e vagy egy meglévő hányadik verziója.
4. Metaadat-űrlap: cím, téma, tantárgy, címkék, évfolyam vagy szint. A mezők a JSON `meta` részéből előtöltődnek, és felülírhatók.
5. Mentés.

**Frissítés**: ha a `meta.id` már létezik, új verzió keletkezik (minden verzió megmarad). Az azonos azonosítójú elemeken a haladás megmarad, akkor is, ha a szövegük változott. Az új csomagból hiányzó elemek elrejtődnek (nem számítanak a haladásba, jelölni sem lehet őket), de a haladási adatuk nem törlődik; ha egy későbbi verzióban visszakerülnek, a régi haladás újra érvényes. Archivált anyag új verziójának feltöltése visszaállítja az archiválást.

**Archiválás**: az anyag eltűnik a listából, de minden adata megmarad; visszaállítható. **Végleges törlés** csak külön megerősítéssel (pipa a párbeszédablakban; az API-ban `confirm=<azonosító>`), és minden profil haladásával együtt törlődik.

## 4. Architektúra

- Backend: Python 3.12, FastAPI, uvicorn.
- Adatbázis: SQLite egyetlen fájlban (`/data/app.db`), WAL módban, idegen kulcsokkal. Séma-verziókezelés: `PRAGMA user_version` + `app/db.py` `MIGRATIONS` lista.
- Keresés: a `packs.search_text` oszlop a cím, téma, tantárgy, címkék és szint normalizált (kisbetű, ékezet nélküli) összefűzése; a lekérdezés szavanként `LIKE '%szó%'`. Családi léptéknél (néhány száz csomagig) ez gyors, és részszót is talál.
- Frontend: vanilla JS egyoldalas alkalmazás (`static/`), build lépés nélkül, a backend szolgálja ki. Hash-alapú útvonalak: `#/`, `#/profilok`, `#/anyag/{id}/{fül}`, `#/feltoltes`, `#/kezeles`.
- Futtatás: docker compose, egyetlen konténer, a `/data` tartós kötetre csatolva; nem root felhasználó (uid 10001), csak olvasható gyökér-fájlrendszer.
- Mentés: naponta egy konzisztens pillanatkép `VACUUM INTO`-val a `/data/backups/app-ÉÉÉÉHHNN.db` fájlba, `BACKUP_KEEP_DAYS` napig megőrizve; plusz export (minden csomag minden verzióval és minden haladás egy JSON-ban) és visszatöltés.
- Felület: magyar nyelvű; mobilra tervezve, 360 px szélességtől; világos és sötét téma (rendszer szerint vagy kézzel); billentyűzettel kezelhető; webfont és külső erőforrás nélkül (helyi hálózaton, net nélkül is működik).

## 5. Adatmodell

```
profiles      (id, name, color, role[parent|child], created_at)
packs         (id TEXT PK = meta.id, title, topic, subject, tags JSON, level,
               current_version INT, archived BOOL, search_text, created_at, updated_at)
pack_versions (pack_id, version, json TEXT, uploaded_by, uploaded_at)       PK(pack_id, version)
pack_items    (pack_id, kind[cards|quiz|tasks|timeline|traps], item_id)     PK(pack_id, kind, item_id)
              -- az aktuális verzió elemei; ebből számol a lista, és ez szűri a jelöléseket
card_progress (profile_id, pack_id, item_id, status[new|learning|known],
               seen_count, last_seen_at)                                     PK(profile_id, pack_id, item_id)
review_log    (id, profile_id, pack_id, item_id, rating, reviewed_at)       -- minden jelölés (v2: FSRS)
quiz_attempts (id, profile_id, pack_id, chapter, score, max, wrong_ids JSON, taken_at)
task_answers  (profile_id, pack_id, task_id, question_id, answer TEXT, updated_at)
last_opened   (profile_id, pack_id, opened_at)
```

Profil vagy csomag törlésekor a hozzá tartozó haladás kaszkáddal törlődik. Időbélyegek: UTC, ISO 8601, ezredmásodperccel.

## 6. API

| Metódus | Útvonal | Funkció | Jog |
|---|---|---|---|
| GET | `/api/health` | Állapot, verzió, sémaverzió | – |
| GET | `/api/config` | Verzió, max. feltöltési méret | – |
| GET | `/api/profiles` | Profilok listája | – |
| POST | `/api/profiles` | Új profil (az első csak parent lehet, és ehhez nem kell fejléc) | parent |
| PATCH | `/api/profiles/{id}` | Név, szín, szerep | parent |
| DELETE | `/api/profiles/{id}?confirm={id}` | Profil törlése a haladással | parent |
| GET | `/api/packs?q=&subject=&tag=&sort=recent\|uploaded\|title&archived=` | Keresés és lista; profilfejléccel haladással; tantárgy- és címkelistával | – |
| GET | `/api/packs/{id}` | Metaadat, aktuális verzió JSON-ja, verziólista; profilfejléccel rögzíti a megnyitást | – |
| POST | `/api/packs/validate` | Validálás mentés nélkül (törzs: a nyers JSON-szöveg) | – |
| POST | `/api/packs` | Feltöltés vagy új verzió: `{"content": "<JSON-szöveg>", "meta": {…felülírás}}` | parent |
| PATCH | `/api/packs/{id}` | Metaadatok, `archived` | parent |
| DELETE | `/api/packs/{id}?confirm={id}` | Végleges törlés | parent |
| GET | `/api/progress/{packId}` | Kártyastátuszok, feladatválaszok, utolsó 10 kvízeredmény | profil |
| PUT | `/api/progress/{packId}` | `{"cards": [{item_id, status}], "answers": [{task_id, question_id, answer}]}` (részleges; üres válasz = törlés) | profil |
| POST | `/api/progress/{packId}/quiz` | `{chapter, score, max, wrong_ids}` | profil |
| GET | `/api/export` | Teljes export (`tanulo-export/1`) letöltésként | parent |
| POST | `/api/import?confirm=replace` | Visszatöltés: minden adat cseréje, egy tranzakcióban | parent, vagy üres adatbázis |

Az aktív profil azonosítója az `X-Profile-Id` fejlécben megy. Hibák formája: `{"detail": "<magyar üzenet>", "code": "<gépi kód>", "errors": [{path, message, text}]?}`. Az interaktív API-leírás: `/api/docs`.

## 7. Tartalomcsomag formátum (`tanulo-csomag/1`)

### Általános szabályok

- A fájl UTF-8 JSON (BOM megengedett). A kulcsok angolul és ékezet nélkül, a tartalom magyarul.
- Azonosítók: minta `^[a-z0-9][a-z0-9-]{0,63}$`, mindig **szöveg** (a `"4"` jó, a `4` nem).
  - A `cards`, `quiz`, `tasks`, `timeline`, `traps` elemei **közös névtérben**, a csomagon belül egyediek.
  - A fejezetek azonosítói külön névtér.
  - A feladatkérdések azonosítói a feladaton belül egyediek (lehet mindegyik feladatban `"1"`, `"2"`, `"3"`).
  - Frissítéskor a változatlan elemek azonosítója marad, mert ehhez kötődik a haladás.
  - Ajánlott előtagok: `c-` kártya, `q-` kvíz, `t-` feladat, `tl-` idővonal, `tr-` csapda.
- Szövegformázás a szöveges mezőkben szűk Markdown-részhalmazzal: `**félkövér**`, `*dőlt*`, sortörés (`\n` a JSON-ban). Más jelölés és HTML nem; a megjelenítő escape-eli.
- Hiányzó opcionális blokk = üres tömb, `null`, vagy a kulcs elhagyható.

### Gyökér

| Mező | Típus | Kötelező | Leírás |
|---|---|---|---|
| schema | string | igen | Pontosan `"tanulo-csomag/1"` |
| meta | object | igen | Lásd lent |
| chapters | array | igen | Legalább 1 fejezet |
| cards | array | nem | Tanulókártyák |
| quiz | array | nem | Feleletválasztós kérdések |
| tasks | array | nem | Forrásos feladatok |
| timeline | array | nem | Idővonal |
| summary | array | nem | Összefoglaló fejezetenként |
| traps | array | nem | Tipikus hibák |

### meta

| Mező | Típus | Kötelező | Leírás |
|---|---|---|---|
| id | id | igen | Stabil csomagazonosító, pl. `tarsadalomtortenet-1-2026osz` |
| title | string ≤120 | igen | Megjelenő cím |
| topic | string ≤200 | igen | Téma, kereshető |
| subject | string ≤60 | igen | Tantárgy, pl. „Történelem” |
| tags | string[] ≤10, egyenként ≤40 | nem | Címkék |
| level | string ≤40 | nem | Pl. „BA 1. félév”, „7. osztály” |
| language | string ≤10 | nem | Alapértelmezés: `"hu"` |
| source_note | string ≤300 | nem | Milyen anyagokból készült; itt kell jelezni az általános tudásból pótolt részeket |
| exam_info | string ≤1500 | nem | Vizsgainformáció, az összefoglaló elején jelenik meg |
| generated_at | ISO dátum vagy időpont | nem | Generálás ideje |

### Elemek

```
chapters[] { "id", "title": string ≤160, "order": int }

cards[]    { "id", "chapter": chapter.id, "front": string ≤300, "back": string ≤1200 }

quiz[]     { "id", "chapter", "question": string ≤400,
             "options": string[2..6] (egyenként ≤300), "correct": int (0-tól, < options.length),
             "explanation": string ≤600 }

tasks[]    { "id", "chapter", "title": string ≤160,
             "source": { "caption": string ≤200,
                         "type": "text" | "table",
                         "text": string ≤1500,                                   // ha type=text
                         "excerpt": bool,                                        // true = tartalmi kivonat
                         "table": { "header": string[], "rows": string[][] } },  // ha type=table; cella ≤500
             "questions": [ { "id", "prompt": string ≤400, "solution": string ≤800 } ]  // 3–8 db
           }

timeline[] { "id", "date": string ≤40 (szabad szöveg), "sort_key": int (pl. 18671000),
             "event": string ≤300, "chapter"?: chapter.id }

summary[]  { "chapter": chapter.id,
             "blocks": [ { "type": "heading",   "text": string ≤120 }
                       | { "type": "paragraph", "text": string ≤2000 }
                       | { "type": "list",      "items": string[] (egyenként ≤1000) } ] }

traps[]    { "id", "title": string ≤160, "explanation": string ≤500 }
```

### Validálási szabályok

Hiba (nem menthető):
- A `schema` értéke nem pontos egyezés; kötelező mező hiányzik; rossz típus; üres kötelező szöveg.
- Fejezethivatkozás nem létező fejezetre.
- Azonosító nem felel meg a mintának, vagy ismétlődik (a fenti névterek szerint).
- `quiz[].correct` érvénytelen index; az opciók száma nem 2–6; két opció azonos (kis-/nagybetű, ékezet és szóköz nélkül összevetve).
- Táblázatnál egy sor hossza eltér a fejléc hosszától; a feladat kérdésszáma nem 3–8.
- Hosszkorlát túllépése; a teljes fájl nagyobb 2 MB-nál (`MAX_UPLOAD_MB`); nem UTF-8; érvénytelen JSON (sor/oszlop megjelöléssel).
- Legfeljebb 200 hibát listáz.

Figyelmeztetés (menthető):
- Ismeretlen kulcs (előre kompatibilitás), duplikált kulcs egy objektumon belül, ismétlődő címke, ismétlődő fejezetsorszám, egy fejezethez több összefoglaló, 100 szónál hosszabb forrásszöveg, üres összefoglaló, tartalom nélküli csomag.

### Minimális példa

Lásd `tests/fixtures/pelda.json`; teljesebb, minden módot használó példa: `examples/bemutato-naprendszer.json`.

### Generálási irányelvek (Claude-nak, csomagkészítéskor)

- **Hűség a forráshoz**: csak a feltöltött anyagban szereplő tény kerüljön be. Ha egy követelményhez nincs adat a forrásban, általános tudásból pótolható, de a `source_note` mezőben jelezni kell.
- **Részletesség**: a vizsgakövetelményekhez igazodjon; ahol a tanár nagyságrendet kér, nagyságrend kerüljön be, ne pontos szám.
- **Ajánlott mennyiség** egy félévnyi tárgynál: 100–180 kártya; 30–50 kvízkérdés hihető, de egyértelműen rossz opciókkal; 5–10 forrásos feladat a vizsgaformátumot követve; 30–50 idővonal-elem.
- **Forrásrészletek**: legfeljebb kb. 80 szó; ami nem szó szerinti, azt `"excerpt": true` jelöli.
- **Frissítés**: meglévő csomag frissítésekor a generáláshoz **a korábbi csomag JSON-ját is be kell adni**, és a változatlan elemek azonosítója megmarad. Új elem új azonosítót kap; törölt elem azonosítóját nem szabad újrahasznosítani másra.
- **Kimenet**: egyetlen érvényes JSON-fájl, kommentek nélkül.

## 8. Üzemeltetés és védelem

- Mivel nincs jelszó, a szolgáltatás nem lehet nyílt a weben. Lehetőségek: csak helyi hálózaton (a compose `BIND_ADDR` a gép LAN-címe), csak VPN-en (pl. a gép Tailscale-címe, Funnel nélkül), vagy reverse proxy mögött basic auth-tal / Cloudflare Access-szel. A tanári vázlatok gyakran nem terjeszthetők, ezért is fontos.
- A compose alapértelmezése `127.0.0.1`: amíg nincs tudatosan beállítva, semmi nem érheti el kívülről.
- Konfiguráció környezeti változókkal: `PORT`, `DATA_DIR`, `MAX_UPLOAD_MB`, `BACKUP_ENABLED`, `BACKUP_KEEP_DAYS`, `LOG_LEVEL`, `TZ`.
- Naplózás a konzolra; healthcheck a `/api/health` végponton (a Docker-kép `HEALTHCHECK`-je is ezt hívja).
- A `/data/backups` ugyanazon a köteten van, mint az adatbázis; a gépen kívülre másolás külön feladat.

## 9. Elfogadási kritériumok

Mindegyikhez automatikus teszt tartozik (`tests/test_api.py` `test_acceptance_*`, illetve `tests/e2e_ui.py`).

1. Két profil létrehozható. Az egyikkel megjelölt kártyák a másik profilnál nem jelennek meg tudottként, és újraindítás után is megvannak.
2. A példa JSON hibátlanul validál és betöltődik. Egy szándékosan hibás változatnál (rossz `correct` index, nem létező fejezet) mezőszintű hibaüzenet jelenik meg.
3. A „dualizmus” és a „tortenet” keresés megtalálja a csomagot.
4. Ugyanazon `meta.id`-vel újra feltöltve az új verzió jelenik meg, és a megmaradt kártyák haladása nem vész el.
5. Mobilon (390 px, és 360 px-en is) minden mód használható vízszintes görgetés nélkül.
6. Az export és a visszatöltés után minden adat megvan.

## 10. v2 ötletek

- Ismétléses tanulás (FSRS) a `review_log` alapján.
- Képi források és térképfeladatok.
- Csomaggenerálás közvetlenül PDF-ből a Claude API-val, átnéző felülettel.
- Statisztika a szülőnek: ki mennyit tanult (az adatok már megvannak: `review_log`, `quiz_attempts`, `last_opened`).

## 11. Eltérések a v1 specifikációtól

| Téma | v1 | v1.1 | Ok |
|---|---|---|---|
| Keresés | FTS5 `unicode61 remove_diacritics 2` | normalizált `search_text` + `LIKE` | Az FTS5 egész tokenre vagy előtagra keres; a „tortenet” nem találná meg a „Társadalomtörténet”-et (magyar összetett szó), így a 3. kritérium nem teljesülne. A `trigram` tokenizáló ékezetlenítéssel SQLite 3.45-öt kér, a `python:3.12-slim` 3.40-et hoz. |
| Visszatöltés | nem volt végpont | `POST /api/import` | A 6. kritérium megköveteli. |
| Napi mentés | fájlmásolat | `VACUUM INTO`, megőrzési idővel | Futó WAL-os adatbázis fájlmásolata inkonzisztens lehet. |
| Jelölésnapló | – | `review_log` | Az FSRS-hez (v2) előzmény kell. |
| Haladásszámláló | – | `pack_items` | A rejtett elemek ne számítsanak, és ne lehessen jelölni őket. |
| Azonosító-névterek | „csomagon belül egyediek” | elemek közösen, fejezetek külön, feladatkérdések feladaton belül | A feladatkérdéseknél a `"1"`, `"2"`, `"3"` természetes, és a haladás (feladat, kérdés) párhoz kötődik. |
| Profilkezelés | csak létrehozás | módosítás, törlés, utolsó szülő védelme | A „profilt kezelni” kitételhez. |
| Export | bárki | csak parent | Minden profil adatát tartalmazza. |
| Frissítés archivált anyagra | – | visszaállítja | Aki új verziót tölt fel, láthatóvá akarja tenni. |
