"""Böngészős végigjátszás headless Chromiummal (Playwright).

Ellenőrzi az 5. elfogadási kritériumot: 360 és 390 px szélességen minden mód
vízszintes görgetés nélkül használható; és közben végigkattintja a fő folyamatokat.

Futtatás (futó szerver ellen):
    python tests/e2e_ui.py http://127.0.0.1:8000 [képernyőkép-könyvtár]
Az adatbázis legyen üres (első indítás), mert az első profilt is ez hozza létre.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DEMO = (ROOT / "examples" / "bemutato-naprendszer.json").read_text(encoding="utf-8")


def no_hscroll(page: Page, where: str) -> None:
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw, f"vízszintes görgetés: {where} ({sw}px > {iw}px)"


def shot(page: Page, out: Path | None, name: str) -> None:
    if out:
        page.screenshot(path=str(out / f"{name}.png"), full_page=True)


def run(base: str, out: Path | None) -> None:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, locale="hu-HU")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        # --- első indítás: szülői profil
        page.goto(base + "/")
        expect(page.get_by_role("heading", name="Üdv a Tanulóban!")).to_be_visible()
        no_hscroll(page, "első indítás")
        shot(page, out, "01-elso-inditas")
        page.get_by_label("Név").fill("Anya")
        page.get_by_role("button", name="Profil létrehozása").click()
        expect(page.get_by_role("heading", name="Anyagok")).to_be_visible()
        expect(page.get_by_text("Még nincs anyag")).to_be_visible()
        no_hscroll(page, "üres anyagtár")

        # --- gyerek profil a kezelésben
        page.get_by_role("link", name="Kezelés").click()
        page.get_by_role("button", name="Új profil").click()
        dlg = page.locator("dialog[open]")
        dlg.get_by_label("Név").fill("Bence")
        dlg.get_by_role("button", name="Létrehozás").click()
        expect(page.get_by_text("Bence", exact=True)).to_be_visible()
        no_hscroll(page, "kezelés")
        shot(page, out, "02-kezeles")

        # --- hibás csomag: mezőszintű hibák
        page.goto(base + "/#/feltoltes")
        bad = DEMO.replace('"correct": 1, "explanation": "A **Jupiter**', '"correct": 9, "explanation": "A **Jupiter**') \
                  .replace('"id": "c-nap-tipus", "chapter": "1"', '"id": "c-nap-tipus", "chapter": "9"')
        page.get_by_label("vagy szöveg").fill(bad)
        page.get_by_role("button", name="Ellenőrzés").click()
        expect(page.get_by_text("cards[0].chapter")).to_be_visible()
        expect(page.get_by_text("quiz[0].correct")).to_be_visible()
        expect(page.get_by_text('"9" nem létező fejezet')).to_be_visible()
        no_hscroll(page, "hibás feltöltés")
        shot(page, out, "03-hibas-csomag")

        # --- jó csomag feltöltése
        page.get_by_label("vagy szöveg").fill(DEMO)
        page.get_by_role("button", name="Ellenőrzés").click()
        expect(page.get_by_text("A csomag rendben van")).to_be_visible()
        expect(page.get_by_text("Új anyag lesz.")).to_be_visible()
        shot(page, out, "04-feltoltes-rendben")
        page.get_by_role("button", name="Mentés").click()
        expect(page.locator("h1.pack-title")).to_have_text("A Naprendszer – bemutató csomag")

        # --- módok
        for tab in ["Kártyák", "Kvíz", "Feladatok", "Idővonal", "Összefoglaló"]:
            page.get_by_role("tab", name=tab).click()
            page.wait_for_timeout(150)
            no_hscroll(page, f"mód: {tab}")

        # kártyák: fordítás és jelölés
        page.get_by_role("tab", name="Kártyák").click()
        shot(page, out, "05-kartya-elol")
        page.locator(".flash-inner").click()
        page.wait_for_timeout(500)
        shot(page, out, "06-kartya-hatul")
        page.get_by_role("button", name="Tudom").click()
        page.get_by_role("button", name="Tudom").click()
        page.get_by_role("button", name="Még nem megy").click()
        expect(page.locator(".deck-status")).to_contain_text("4 / 14")
        no_hscroll(page, "kártyák jelölés után")

        # kvíz: egy teljes kör
        page.get_by_role("tab", name="Kvíz").click()
        page.get_by_role("button", name="Kör indítása").click()
        for _ in range(6):
            page.locator(".options button").first.click()
            shot(page, out, "07-kviz-valasz") if _ == 0 else None
            no_hscroll(page, "kvíz visszajelzés")
            page.locator("button.btn-primary:not([hidden])").filter(has_text="Következő").or_(
                page.get_by_role("button", name="Eredmény")).first.click()
        expect(page.locator(".score")).to_be_visible()
        shot(page, out, "08-kviz-eredmeny")
        no_hscroll(page, "kvíz eredmény")

        # feladatok: válasz írása, táblázat mobilon
        page.get_by_role("tab", name="Feladatok").click()
        page.locator("textarea").first.fill("Négy fénypontot látott.")
        expect(page.get_by_text("Mentve")).to_be_visible(timeout=5000)
        page.get_by_role("button", name="Összes megoldás mutatása").click()
        no_hscroll(page, "feladatok megoldásokkal")
        shot(page, out, "09-feladatok")

        page.get_by_role("tab", name="Idővonal").click()
        shot(page, out, "10-idovonal")
        page.get_by_role("tab", name="Összefoglaló").click()
        expect(page.locator("#tab-panel")).not_to_contain_text("[object")
        expect(page.locator(".traps dt")).to_have_count(3)
        shot(page, out, "11-osszefoglalo")

        # --- anyagtár: haladás és ékezet nélküli keresés
        page.goto(base + "/#/")
        expect(page.get_by_text("Tudom: 2/14")).to_be_visible()
        page.get_by_role("searchbox").fill("oriasbolygo")
        expect(page.locator(".pack h2")).to_have_count(1)
        page.get_by_role("searchbox").fill("nincsilyen")
        expect(page.get_by_text("Nincs találat")).to_be_visible()
        page.get_by_role("searchbox").fill("")
        page.wait_for_timeout(400)
        shot(page, out, "12-anyagtar")
        no_hscroll(page, "anyagtár")

        # --- profilváltás: a gyerek nem látja az anya haladását
        page.get_by_role("button", name="Profil: Anya. Váltás").click()
        page.get_by_role("button", name="Bence").click()
        expect(page.get_by_text("Tudom: 0/14")).to_be_visible()
        expect(page.get_by_role("link", name="Feltöltés")).to_have_count(0)
        mono_colors = page.evaluate("getComputedStyle(document.querySelector('#profile-btn .mono')).backgroundColor")
        assert mono_colors != "rgb(39, 71, 201)", "a profil színe nem érvényesült"

        # --- 360 px, sötét téma
        page.set_viewport_size({"width": 360, "height": 740})
        page.emulate_media(color_scheme="dark")
        page.locator(".pack").first.click()
        expect(page.locator("main")).not_to_contain_text("null")
        for tab in ["Kártyák", "Kvíz", "Feladatok", "Idővonal", "Összefoglaló"]:
            page.get_by_role("tab", name=tab).click()
            page.wait_for_timeout(150)
            no_hscroll(page, f"360 px, sötét: {tab}")
        page.get_by_role("tab", name="Kártyák").click()
        shot(page, out, "13-kartya-360-sotet")
        page.get_by_role("tab", name="Feladatok").click()
        shot(page, out, "14-feladatok-360-sotet")

        # --- asztali nézet, billentyűzet
        page.set_viewport_size({"width": 1280, "height": 860})
        page.emulate_media(color_scheme="light")
        page.get_by_role("tab", name="Kártyák").click()
        page.locator("body").click(position={"x": 5, "y": 400})
        page.keyboard.press("Space")
        page.wait_for_timeout(500)
        expect(page.locator(".flash")).to_have_class("flash flipped")
        page.keyboard.press("1")
        expect(page.locator(".deck-status")).to_contain_text("2 / 14")
        shot(page, out, "15-asztali")

        browser.close()

    real = [e for e in errors if "favicon" not in e]
    assert not real, "konzolhibák:\n" + "\n".join(real)
    print("E2E rendben: minden mód 360 és 390 px-en vízszintes görgetés nélkül, konzolhiba nincs.")


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    run(base_url.rstrip("/"), out_dir)
