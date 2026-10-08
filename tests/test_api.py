"""API-tesztek; a test_acceptance_* függvények a specifikáció 9. pontjának kritériumai."""
from __future__ import annotations

import copy
import json
from datetime import date

from fastapi.testclient import TestClient

from app import backup
from app.main import create_app

from .conftest import hdr, make_settings


def upload(client, profile, text_or_obj, meta=None):
    text = text_or_obj if isinstance(text_or_obj, str) else json.dumps(text_or_obj, ensure_ascii=False)
    return client.post("/api/packs", json={"content": text, "meta": meta}, headers=hdr(profile))


def mark(client, profile, pack_id, **statuses):
    r = client.put(f"/api/progress/{pack_id}", headers=hdr(profile),
                   json={"cards": [{"item_id": k.replace("_", "-"), "status": v} for k, v in statuses.items()]})
    assert r.status_code == 200, r.text
    return r.json()


def list_items(client, profile, **params):
    r = client.get("/api/packs", params=params, headers=hdr(profile) if profile else None)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ------------------------------------------------------------ 9. pont
def test_acceptance_1_profiles_progress_isolated_and_persistent(client, parent, child, demo_text, data_dir):
    assert upload(client, parent, demo_text).status_code == 201
    mark(client, parent, "naprendszer-bemutato", c_nap_tipus="known", c_mars="known", c_jupiter="learning")

    mine = client.get("/api/progress/naprendszer-bemutato", headers=hdr(parent)).json()["cards"]
    theirs = client.get("/api/progress/naprendszer-bemutato", headers=hdr(child)).json()["cards"]
    assert mine["c-nap-tipus"]["status"] == "known"
    assert theirs == {}
    assert list_items(client, child)[0]["progress"]["known"] == 0
    assert list_items(client, parent)[0]["progress"] == {"known": 2, "learning": 1, "total": 14}

    # "újraindítás": új alkalmazáspéldány ugyanazon az adatkönyvtáron
    restarted = TestClient(create_app(make_settings(data_dir)))
    again = restarted.get("/api/progress/naprendszer-bemutato", headers=hdr(parent)).json()["cards"]
    assert again["c-nap-tipus"]["status"] == "known"
    assert again["c-jupiter"]["status"] == "learning"
    assert restarted.get("/api/progress/naprendszer-bemutato", headers=hdr(child)).json()["cards"] == {}


def test_acceptance_2_example_loads_and_broken_variant_reports_fields(client, parent, example_text, example):
    v = client.post("/api/packs/validate", content=example_text.encode())
    assert v.json()["ok"] is True and v.json()["errors"] == []
    r = upload(client, parent, example_text)
    assert r.status_code == 201 and r.json()["version"] == 1
    loaded = client.get("/api/packs/tarsadalomtortenet-1-2026osz", headers=hdr(parent)).json()
    assert loaded["content"] == example
    assert loaded["pack"]["title"] == "Társadalomtörténet I."

    bad = copy.deepcopy(example)
    bad["quiz"][0]["correct"] = 4
    bad["cards"][0]["chapter"] = "9"
    v = client.post("/api/packs/validate", content=json.dumps(bad).encode()).json()
    texts = [e["text"] for e in v["errors"]]
    assert v["ok"] is False
    assert 'cards[0].chapter: "9" nem létező fejezet' in texts
    assert "quiz[0].correct: 4 érvénytelen index: 0 és 3 között kell lennie (0-tól számolva)" in texts
    r = upload(client, parent, bad)
    assert r.status_code == 422
    assert {e["path"] for e in r.json()["errors"]} == {"cards[0].chapter", "quiz[0].correct"}


def test_acceptance_3_search_is_accent_and_case_insensitive(client, parent, example_text, demo_text):
    upload(client, parent, example_text)
    upload(client, parent, demo_text)
    for q in ("dualizmus", "tortenet", "TÖRTÉNET", "tarsadalom tortenet", "  Történet  ", "kre"):
        ids = [p["id"] for p in list_items(client, parent, q=q)]
        assert ids == ["tarsadalomtortenet-1-2026osz"], q
    assert [p["id"] for p in list_items(client, parent, q="oriasbolygo")] == ["naprendszer-bemutato"]
    assert list_items(client, parent, q="nincs ilyen") == []
    assert list_items(client, parent, q="100%_") == []  # LIKE-jokerek escape-elve
    assert [p["id"] for p in list_items(client, parent, subject="szociologia")] == ["tarsadalomtortenet-1-2026osz"]
    assert [p["id"] for p in list_items(client, parent, tag="Csillagászat")] == ["naprendszer-bemutato"]


def test_acceptance_4_new_version_keeps_progress(client, parent, child, demo_text):
    upload(client, parent, demo_text)
    mark(client, child, "naprendszer-bemutato", c_mars="known", c_neptunusz="known", c_venusz="learning")
    client.put("/api/progress/naprendszer-bemutato", headers=hdr(child),
               json={"answers": [{"task_id": "t-galilei", "question_id": "1", "answer": "Négy pontot."}]})

    pack = json.loads(demo_text)
    pack["cards"] = [c for c in pack["cards"] if c["id"] != "c-neptunusz"]          # kimarad
    pack["cards"][0]["back"] = "Átírt hátoldal."                                   # változik, id marad
    pack["cards"].append({"id": "c-pluto", "chapter": "3", "front": "Plútó", "back": "Törpebolygó."})
    r = upload(client, parent, pack)
    assert r.status_code == 201 and r.json()["version"] == 2 and r.json()["created"] is False

    loaded = client.get("/api/packs/naprendszer-bemutato", headers=hdr(child)).json()
    assert loaded["pack"]["current_version"] == 2
    assert loaded["content"]["cards"][0]["back"] == "Átírt hátoldal."
    assert [v["version"] for v in loaded["versions"]] == [2, 1]

    prog = client.get("/api/progress/naprendszer-bemutato", headers=hdr(child)).json()
    assert prog["cards"]["c-mars"]["status"] == "known"
    assert prog["cards"]["c-neptunusz"]["status"] == "known"   # a rejtett elem adata megmarad
    assert prog["answers"]["t-galilei"]["1"] == "Négy pontot."
    item = list_items(client, child)[0]
    assert item["progress"] == {"known": 1, "learning": 1, "total": 14}  # a rejtett nem számít

    # a rejtett elemre jelölés nem megy át
    assert mark(client, child, "naprendszer-bemutato", c_neptunusz="learning")["ignored"] == 1

    # visszakerül a csomagba: a régi haladás újra számít
    upload(client, parent, demo_text)
    assert list_items(client, child)[0]["progress"]["known"] == 2


def test_acceptance_6_export_then_import_restores_everything(client, parent, child, demo_text, example_text, data_dir, tmp_path):
    upload(client, parent, demo_text)
    upload(client, parent, example_text)
    upload(client, parent, demo_text)  # 2. verzió
    mark(client, child, "naprendszer-bemutato", c_mars="known", c_venusz="learning")
    client.put("/api/progress/naprendszer-bemutato", headers=hdr(child),
               json={"answers": [{"task_id": "t-galilei", "question_id": "2", "answer": "Holdak."}]})
    client.post("/api/progress/naprendszer-bemutato/quiz", headers=hdr(child),
                json={"chapter": "3", "score": 2, "max": 3, "wrong_ids": ["q-pluto"]})
    client.get("/api/packs/naprendszer-bemutato", headers=hdr(child))
    client.patch("/api/packs/tarsadalomtortenet-1-2026osz", headers=hdr(parent), json={"archived": True})

    exported = client.get("/api/export", headers=hdr(parent))
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    dump = exported.json()

    # teljesen új szerver, üres adatbázis: profil nélkül is visszatölthető
    fresh = TestClient(create_app(make_settings(tmp_path / "fresh")))
    r = fresh.post("/api/import?confirm=replace", content=exported.content)
    assert r.status_code == 200, r.text
    assert r.json()["imported"]["packs"] == 2

    again = fresh.get("/api/export", headers=hdr(parent)).json()
    for d in (dump, again):
        d.pop("exported_at")
    assert again == dump

    assert list_items(fresh, child)[0]["progress"] == {"known": 1, "learning": 1, "total": 14}
    assert [p["id"] for p in list_items(fresh, parent, q="tortenet", archived="true")] == ["tarsadalomtortenet-1-2026osz"]
    prog = fresh.get("/api/progress/naprendszer-bemutato", headers=hdr(child)).json()
    assert prog["answers"]["t-galilei"]["2"] == "Holdak."
    assert prog["quiz_attempts"][0]["wrong_ids"] == ["q-pluto"]


# ------------------------------------------------------------ jogosultság, profilok
def test_first_profile_must_be_parent(client):
    r = client.post("/api/profiles", json={"name": "Bence", "role": "child"})
    assert r.status_code == 422 and r.json()["code"] == "first_parent"


def test_only_parent_can_create_profiles_and_upload(client, parent, child, example_text):
    assert client.post("/api/profiles", json={"name": "X"}).status_code == 403
    assert client.post("/api/profiles", json={"name": "X"}, headers=hdr(child)).status_code == 403
    r = upload(client, child, example_text)
    assert r.status_code == 403 and r.json()["detail"] == "Ehhez szülői profil kell."
    assert client.get("/api/export", headers=hdr(child)).status_code == 403
    assert client.post("/api/import?confirm=replace", content=b"{}", headers=hdr(child)).status_code == 403


def test_unknown_profile_header(client, parent):
    r = client.get("/api/progress/x", headers={"X-Profile-Id": "999"})
    assert r.status_code == 401 and r.json()["code"] == "unknown_profile"
    r = client.get("/api/progress/x", headers={"X-Profile-Id": "abc"})
    assert r.status_code == 401


def test_last_parent_is_protected(client, parent, child):
    r = client.patch(f"/api/profiles/{parent['id']}", json={"role": "child"}, headers=hdr(parent))
    assert r.status_code == 409
    r = client.delete(f"/api/profiles/{parent['id']}?confirm={parent['id']}", headers=hdr(parent))
    assert r.status_code == 409
    r = client.patch(f"/api/profiles/{child['id']}", json={"name": "Bence B.", "color": "#123456"}, headers=hdr(parent))
    assert r.json()["name"] == "Bence B." and r.json()["color"] == "#123456"


def test_delete_profile_needs_confirm_and_cascades(client, parent, child, demo_text):
    upload(client, parent, demo_text)
    mark(client, child, "naprendszer-bemutato", c_mars="known")
    assert client.delete(f"/api/profiles/{child['id']}", headers=hdr(parent)).status_code == 400
    assert client.delete(f"/api/profiles/{child['id']}?confirm={child['id']}", headers=hdr(parent)).status_code == 200
    dump = client.get("/api/export", headers=hdr(parent)).json()
    assert dump["card_progress"] == [] and dump["review_log"] == []


# ------------------------------------------------------------ csomagkezelés
def test_meta_override_on_upload_and_patch(client, parent, example_text):
    r = upload(client, parent, example_text, meta={"title": "Saját cím", "tags": ["egy", "Egy", " kettő "]})
    assert r.status_code == 201
    item = list_items(client, parent)[0]
    assert item["title"] == "Saját cím" and item["tags"] == ["egy", "kettő"]
    assert item["topic"].startswith("Magyar társadalomtörténet")  # a többi a JSON-ból

    r = client.patch("/api/packs/tarsadalomtortenet-1-2026osz", headers=hdr(parent), json={"topic": "Kiegyezés kora"})
    assert r.status_code == 200
    assert list_items(client, parent, q="kiegyezes")[0]["id"] == "tarsadalomtortenet-1-2026osz"
    assert list_items(client, parent, q="dualizmus") == []   # a téma már nem tartalmazza, a címke sem

    r = client.patch("/api/packs/tarsadalomtortenet-1-2026osz", headers=hdr(parent), json={"title": "  "})
    assert r.status_code == 422 and r.json()["errors"][0]["path"] == "title"


def test_archive_hides_and_reupload_unarchives(client, parent, example_text):
    upload(client, parent, example_text)
    client.patch("/api/packs/tarsadalomtortenet-1-2026osz", headers=hdr(parent), json={"archived": True})
    data = client.get("/api/packs", headers=hdr(parent)).json()
    assert data["items"] == [] and data["archived_count"] == 1
    assert len(list_items(client, parent, archived="true")) == 1
    upload(client, parent, example_text)
    assert len(list_items(client, parent)) == 1


def test_delete_pack_requires_confirmation(client, parent, child, demo_text):
    upload(client, parent, demo_text)
    mark(client, child, "naprendszer-bemutato", c_mars="known")
    assert client.delete("/api/packs/naprendszer-bemutato", headers=hdr(parent)).status_code == 400
    assert client.delete("/api/packs/naprendszer-bemutato?confirm=naprendszer-bemutato", headers=hdr(child)).status_code == 403
    r = client.delete("/api/packs/naprendszer-bemutato?confirm=naprendszer-bemutato", headers=hdr(parent))
    assert r.status_code == 200
    assert client.get("/api/packs/naprendszer-bemutato").status_code == 404
    assert client.get("/api/export", headers=hdr(parent)).json()["card_progress"] == []


def test_sorting(client, parent, child, demo_text, example_text):
    upload(client, parent, example_text)
    upload(client, parent, demo_text)
    assert [p["id"] for p in list_items(client, child, sort="title")] == ["naprendszer-bemutato", "tarsadalomtortenet-1-2026osz"]
    client.get("/api/packs/tarsadalomtortenet-1-2026osz", headers=hdr(child))
    assert list_items(client, child, sort="recent")[0]["id"] == "tarsadalomtortenet-1-2026osz"
    assert list_items(client, parent, sort="uploaded")[0]["id"] == "naprendszer-bemutato"


def test_validate_accepts_wrapped_content(client, example_text):
    r = client.post("/api/packs/validate", json={"content": example_text})
    assert r.json()["ok"] is True


def test_validate_reports_existing_pack(client, parent, example_text):
    upload(client, parent, example_text)
    r = client.post("/api/packs/validate", content=example_text.encode()).json()
    assert r["existing"]["next_version"] == 2


# ------------------------------------------------------------ haladás
def test_review_log_records_every_mark(client, parent, demo_text):
    upload(client, parent, demo_text)
    mark(client, parent, "naprendszer-bemutato", c_mars="learning")
    mark(client, parent, "naprendszer-bemutato", c_mars="known")
    prog = client.get("/api/progress/naprendszer-bemutato", headers=hdr(parent)).json()
    assert prog["cards"]["c-mars"]["seen_count"] == 2
    log = client.get("/api/export", headers=hdr(parent)).json()["review_log"]
    assert [x["rating"] for x in log] == ["learning", "known"]


def test_task_answers_update_and_clear(client, parent, demo_text):
    upload(client, parent, demo_text)
    url = "/api/progress/naprendszer-bemutato"
    client.put(url, headers=hdr(parent), json={"answers": [{"task_id": "t-galilei", "question_id": "1", "answer": "a"}]})
    client.put(url, headers=hdr(parent), json={"answers": [{"task_id": "t-galilei", "question_id": "1", "answer": "b"}]})
    assert client.get(url, headers=hdr(parent)).json()["answers"] == {"t-galilei": {"1": "b"}}
    client.put(url, headers=hdr(parent), json={"answers": [{"task_id": "t-galilei", "question_id": "1", "answer": "  "}]})
    assert client.get(url, headers=hdr(parent)).json()["answers"] == {}
    r = client.put(url, headers=hdr(parent), json={"answers": [{"task_id": "t-nincs", "question_id": "1", "answer": "x"}]})
    assert r.json()["ignored"] == 1


def test_quiz_attempts(client, parent, demo_text):
    upload(client, parent, demo_text)
    url = "/api/progress/naprendszer-bemutato/quiz"
    assert client.post(url, headers=hdr(parent), json={"score": 5, "max": 3}).status_code == 422
    assert client.post(url, headers=hdr(parent), json={"chapter": None, "score": 3, "max": 6, "wrong_ids": ["q-pluto"]}).status_code == 201
    attempts = client.get("/api/progress/naprendszer-bemutato", headers=hdr(parent)).json()["quiz_attempts"]
    assert attempts[0]["score"] == 3 and attempts[0]["chapter"] is None


def test_progress_requires_profile(client, parent, demo_text):
    upload(client, parent, demo_text)
    r = client.get("/api/progress/naprendszer-bemutato")
    assert r.status_code == 401 and r.json()["code"] == "no_profile"


# ------------------------------------------------------------ üzemeltetés
def test_health_and_static(client):
    assert client.get("/api/health").json()["status"] == "ok"
    r = client.get("/")
    assert r.status_code == 200 and "Tanuló" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_import_rejects_garbage_and_keeps_data(client, parent, demo_text):
    upload(client, parent, demo_text)
    r = client.post("/api/import?confirm=replace", content=b'{"format": "valami"}', headers=hdr(parent))
    assert r.status_code == 422
    assert client.post("/api/import", content=b"{}", headers=hdr(parent)).status_code == 400
    assert len(list_items(client, parent)) == 1


def test_oversized_request_rejected(client, parent):
    big = b"x" * (5 * 1024 * 1024)
    r = client.post("/api/packs/validate", content=big)
    assert r.status_code == 413


def test_daily_backup_and_prune(client, parent, demo_text, data_dir):
    upload(client, parent, demo_text)
    db = data_dir / "app.db"
    bdir = data_dir / "backups"
    made = backup.make_backup(db, bdir, date(2026, 10, 8))
    old = backup.make_backup(db, bdir, date(2026, 9, 1))
    assert made.exists() and old.exists()
    removed = backup.prune(bdir, keep_days=14, today=date(2026, 10, 8))
    assert removed == [old] and made.exists()
    restored = TestClient(create_app(make_settings(data_dir)))  # a mentés használható adatbázis
    import sqlite3
    with sqlite3.connect(made) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pack_versions").fetchone()[0] == 1
    assert restored.get("/api/health").status_code == 200
