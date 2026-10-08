# Csomagkészítő prompt

Így készül a tananyagból feltölthető csomag. Egy Claude-beszélgetésben:

1. Csatold a tanári anyagokat (jegyzet, diák, vizsgakövetelmény).
2. **Frissítésnél** csatold a jelenlegi csomag JSON-ját is (a Tanulóban: anyag megnyitása → **JSON letöltése**, szülői profillal).
3. Másold be az alábbi szöveget, a szögletes zárójeles részeket kitöltve.
4. A kapott JSON-t a Tanuló **Feltöltés** oldalán ellenőrizd; ha hibát jelez, a hibalistát másold vissza Claude-nak javításra.

---

```text
Készíts tanulócsomagot a csatolt anyagokból a lent leírt "tanulo-csomag/1" formátumban.

Tárgy: [pl. Történelem]
Szint: [pl. 7. osztály / BA 1. félév]
Vizsga: [formátum, időtartam, mire kell figyelni – ha tudod]
Csomagazonosító (meta.id): [pl. tortenelem-7-dualizmus-2026osz; frissítésnél a régi!]
[Frissítésnél: A csatolt korábbi csomag frissítése. A változatlan elemek azonosítója
maradjon ugyanaz; új elem új azonosítót kapjon; törölt elem azonosítóját ne használd újra.]

Szabályok:
- Csak a csatolt anyagban szereplő tény kerüljön be. Ha egy követelményhez nincs adat, pótolhatod
  általános tudásból, de a meta.source_note mezőben írd le, mit pótoltál.
- A vizsgakövetelményekhez igazodj; ahol a tanár nagyságrendet kér, nagyságrendet írj, ne pontos számot.
- Mennyiség egy félévnyi anyagnál: 100–180 kártya, 30–50 kvízkérdés (hihető, de egyértelműen rossz
  opciókkal), 5–10 forrásos feladat a vizsgaformátum szerint, 30–50 idővonal-elem. Kisebb anyagnál arányosan.
- Forrásrészlet legfeljebb kb. 80 szó; ami nem szó szerinti idézet, annál "excerpt": true.
- Kimenet: egyetlen érvényes JSON-fájl, kommentek nélkül.

Formátum:
- UTF-8 JSON. Kulcsok angolul, tartalom magyarul.
- Azonosító: ^[a-z0-9][a-z0-9-]{0,63}$, mindig szöveg ("4", nem 4). A cards, quiz, tasks, timeline,
  traps elemeinek azonosítói együtt is egyediek; előtagok: c-, q-, t-, tl-, tr-. A fejezetazonosítók
  külön névtér. A feladatkérdések azonosítói a feladaton belül egyediek ("1", "2", "3" jó).
- Szövegformázás: **félkövér**, *dőlt*, \n sortörés. Más jelölés és HTML tilos.

{
  "schema": "tanulo-csomag/1",
  "meta": { "id", "title" (≤120), "topic" (≤200), "subject" (≤60), "tags" (≤10 db, egyenként ≤40),
            "level" (≤40), "language": "hu", "source_note" (≤300), "exam_info" (≤1500),
            "generated_at": "ÉÉÉÉ-HH-NN" },
  "chapters": [ { "id", "title" (≤160), "order": egész } ],                       // legalább 1
  "cards":    [ { "id", "chapter", "front" (≤300), "back" (≤1200) } ],
  "quiz":     [ { "id", "chapter", "question" (≤400), "options": [2–6 különböző szöveg],
                  "correct": a helyes opció indexe 0-tól, "explanation" (≤600) } ],
  "tasks":    [ { "id", "chapter", "title" (≤160),
                  "source": { "caption" (≤200), "type": "text" vagy "table",
                              "text" (≤1500, ha text), "excerpt": true/false,
                              "table": { "header": [..], "rows": [[..], ..] } (ha table; minden
                              sor pontosan annyi cella, ahány fejléc) },
                  "questions": [ 3–8 db { "id", "prompt" (≤400), "solution" (≤800) } ] } ],
  "timeline": [ { "id", "date" (≤40, szabad szöveg, pl. "1918. október 30–31."),
                  "sort_key": egész (ÉÉÉÉHHNN, ismeretlen hónap/nap = 00), "event" (≤300),
                  "chapter" (nem kötelező) } ],
  "summary":  [ { "chapter", "blocks": [ { "type": "heading", "text" (≤120) }
                                       | { "type": "paragraph", "text" (≤2000) }
                                       | { "type": "list", "items": [..] } ] } ],
  "traps":    [ { "id", "title" (≤160), "explanation" (≤500) } ]                  // tipikus hibák
}
```

---

Tippek:

- Nagy anyagnál kérheted fejezetenként is („először az 1–3. fejezet kártyáit és kvízét”), majd a végén egy fájlba fésülve.
- A `meta.id` a haladás kulcsa: **ugyanaz a tárgy mindig ugyanazzal az azonosítóval** menjen fel, különben új anyag lesz, és a haladás nem jön át.
- A Feltöltés oldal a figyelmeztetéseket (pl. ismeretlen kulcs, túl hosszú forrásrészlet) nem tekinti hibának; mentés előtt érdemes rájuk nézni.
