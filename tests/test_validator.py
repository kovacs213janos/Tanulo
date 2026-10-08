"""A tanulo-csomag/1 validátor szabályai (7. pont)."""
from __future__ import annotations

import copy
import json

from app.validator import validate_data, validate_text

MAX = 2 * 1024 * 1024


def texts(result) -> list[str]:
    return [e.as_dict()["text"] for e in result.errors]


def test_example_is_valid(example):
    r = validate_data(example)
    assert r.ok, texts(r)
    assert r.warnings == []
    assert r.counts()["cards"] == 1


def test_demo_pack_is_valid(demo_text):
    r = validate_text(demo_text, MAX)
    assert r.ok, texts(r)
    assert r.warnings == []


def test_wrong_correct_index_and_missing_chapter(example):
    bad = copy.deepcopy(example)
    bad["quiz"][0]["correct"] = 7
    bad["cards"][0]["chapter"] = "9"
    r = validate_data(bad)
    assert not r.ok
    assert 'cards[0].chapter: "9" nem létező fejezet' in texts(r)
    assert any(t.startswith("quiz[0].correct: 7 érvénytelen index") for t in texts(r))


def test_schema_must_match_exactly(example):
    bad = dict(example, schema="tanulo-csomag/2")
    assert any(t.startswith("schema:") for t in texts(validate_data(bad)))


def test_ids_pattern_and_uniqueness(example):
    bad = copy.deepcopy(example)
    bad["cards"].append(dict(bad["cards"][0]))                 # duplikált azonosító
    bad["quiz"][0]["id"] = "Q_Rossz"                          # rossz minta
    bad["traps"][0]["id"] = "c-kvota"                         # közös névtér
    t = texts(validate_data(bad))
    assert any(x.startswith('cards[1].id: "c-kvota" azonosító már szerepel') for x in t)
    assert any(x.startswith('quiz[0].id: "Q_Rossz" érvénytelen azonosító') for x in t)
    assert any(x.startswith('traps[0].id: "c-kvota" azonosító már szerepel') for x in t)


def test_numeric_chapter_id_gets_helpful_message(example):
    bad = copy.deepcopy(example)
    bad["cards"][0]["chapter"] = 4
    assert any("írd idézőjelbe" in x for x in texts(validate_data(bad)))


def test_duplicate_options(example):
    bad = copy.deepcopy(example)
    bad["quiz"][0]["options"][3] = "külügy "
    assert "quiz[0].options[3]: azonos a(z) quiz[0].options[0] opcióval" in texts(validate_data(bad))


def test_option_count_bounds(example):
    bad = copy.deepcopy(example)
    bad["quiz"][0]["options"] = ["Egy"]
    bad["quiz"][0]["correct"] = 0
    assert any(x.startswith("quiz[0].options: 1 opció van") for x in texts(validate_data(bad)))


def test_table_row_length(example):
    bad = copy.deepcopy(example)
    bad["tasks"] = [{
        "id": "t-1", "chapter": "4", "title": "Táblázat",
        "source": {"caption": "Adatok", "type": "table",
                   "table": {"header": ["A", "B"], "rows": [["1", "2"], ["3"]]}},
        "questions": [{"id": "a", "prompt": "?", "solution": "!"}] * 1 + [
            {"id": "b", "prompt": "?", "solution": "!"}, {"id": "c", "prompt": "?", "solution": "!"}],
    }]
    assert "tasks[0].source.table.rows[1]: 1 cella van, de a fejlécben 2 oszlop" in texts(validate_data(bad))


def test_task_question_count_and_ids(example):
    bad = copy.deepcopy(example)
    bad["tasks"] = [{
        "id": "t-1", "chapter": "4", "title": "Szöveg",
        "source": {"caption": "Forrás", "type": "text", "text": "Rövid szöveg.", "excerpt": True},
        "questions": [{"id": "1", "prompt": "?", "solution": "!"}, {"id": "1", "prompt": "?", "solution": "!"}],
    }]
    t = texts(validate_data(bad))
    assert "tasks[0].questions: 2 kérdés van, 3 és 8 között kell lennie" in t
    assert any(x.startswith('tasks[0].questions[1].id: "1" kérdésazonosító már szerepel') for x in t)


def test_length_limits(example):
    bad = copy.deepcopy(example)
    bad["cards"][0]["front"] = "x" * 301
    bad["meta"]["title"] = "y" * 121
    t = texts(validate_data(bad))
    assert "cards[0].front: túl hosszú: 301 karakter (legfeljebb 300)" in t
    assert "meta.title: túl hosszú: 121 karakter (legfeljebb 120)" in t


def test_unknown_keys_are_warnings_not_errors(example):
    ok = copy.deepcopy(example)
    ok["future_block"] = []
    ok["cards"][0]["image"] = "x.png"
    r = validate_data(ok)
    assert r.ok
    paths = [w.path for w in r.warnings]
    assert "future_block" in paths and "cards[0].image" in paths


def test_optional_blocks_may_be_missing(example):
    minimal = {k: example[k] for k in ("schema", "meta", "chapters", "cards")}
    assert validate_data(minimal).ok


def test_chapters_required(example):
    bad = copy.deepcopy(example)
    bad["chapters"] = []
    assert "chapters: legalább egy fejezet kell" in texts(validate_data(bad))


def test_file_size_limit():
    r = validate_text(b"{" + b" " * (MAX + 1) + b"}", MAX)
    assert not r.ok and r.errors[0].path == "(fájl)" and "túl nagy" in r.errors[0].message


def test_invalid_json_reports_position():
    r = validate_text('{\n  "schema": "tanulo-csomag/1",\n  "meta": \n}', MAX)
    assert r.errors[0].path == "(fájl)"
    assert "4. sor" in r.errors[0].message


def test_bom_is_accepted(example_text):
    assert validate_text("﻿" + example_text, MAX).ok


def test_generated_at_iso(example):
    ok = copy.deepcopy(example)
    ok["meta"]["generated_at"] = "2026-10-08T18:00:00Z"
    assert validate_data(ok).ok
    ok["meta"]["generated_at"] = "tegnap"
    assert any(x.startswith("meta.generated_at:") for x in texts(validate_data(ok)))


def test_summary_block_types(example):
    bad = copy.deepcopy(example)
    bad["summary"][0]["blocks"].append({"type": "image", "src": "x"})
    assert any(x.startswith("summary[0].blocks[1].type:") for x in texts(validate_data(bad)))


def test_error_list_is_capped():
    data = {"schema": "tanulo-csomag/1", "meta": {"id": "x", "title": "t", "topic": "t", "subject": "s"},
            "chapters": [{"id": "1", "title": "e", "order": 1}],
            "cards": [{"id": f"c-{i}", "chapter": "nincs", "front": "a", "back": "b"} for i in range(500)]}
    r = validate_data(data)
    assert len(r.errors) == 200 and r.truncated
    json.dumps(r.as_dict())  # szerializálható
