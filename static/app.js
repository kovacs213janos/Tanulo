/* Tanulóplatform – egyoldalas felület (vanilla JS, build lépés nélkül). */
"use strict";
(() => {
  // ================================================================ alapok
  const $app = document.getElementById("app");
  const $topbar = document.getElementById("topbar");
  const $toasts = document.getElementById("toasts");

  const LS = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, String(v)); } catch { /* privát mód */ } },
  };

  const state = {
    profile: null,
    profiles: [],
    config: { max_upload_bytes: 2 * 1024 * 1024 },
    cleanup: null,
    keyHandler: null,
    renderSeq: 0,
  };

  const PALETTE = ["#e4572e", "#2e86ab", "#3bb273", "#7768ae", "#f2a541", "#d1495b", "#00a6a6", "#8c6a5d"];
  const SUBJECT_COLORS = ["#2747c9", "#c2410c", "#15803d", "#7e22ce", "#b45309", "#be123c", "#0e7490", "#4d7c0f"];
  const COUNT_LABELS = {
    chapters: "fejezet", cards: "kártya", quiz: "kvízkérdés", tasks: "feladat",
    task_questions: "feladatkérdés", timeline: "idővonal-elem", summary: "összefoglaló-fejezet", traps: "csapda",
  };

  // Elemkészítő: h("div", {class: "x", onclick: fn}, "szöveg", h(...))
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "html") el.innerHTML = v; // csak md()/esc() kimenetével hívjuk
        else if (k === "text") el.textContent = v;
        else if (k === "style" && typeof v === "object") {
          for (const [sk, sv] of Object.entries(v)) {
            if (sk.startsWith("--")) el.style.setProperty(sk, sv); else el.style[sk] = sv;
          }
        }
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (v === true) el.setAttribute(k, "");
        else el.setAttribute(k, v);
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  // replaceChildren/append, de a null/false elemeket kihagyja és a tömböket kibontja.
  const clean = (kids) => kids.flat(Infinity).filter((k) => k != null && k !== false);
  const fill = (parent, ...kids) => parent.replaceChildren(...clean(kids));
  const add = (parent, ...kids) => parent.append(...clean(kids));

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Szűk Markdown: **félkövér**, *dőlt*, sortörés. Minden más escape-elve.
  function md(s) {
    return esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*\s](?:[^*]*[^*\s])?)\*/g, "<em>$1</em>")
      .replace(/\r?\n/g, "<br>");
  }
  const mdEl = (tag, text, attrs = {}) => h(tag, { ...attrs, html: md(text) });

  function norm(s) {
    return String(s ?? "").toLocaleLowerCase("hu").normalize("NFKD").replace(/[̀-ͯ]/g, "").trim();
  }

  function hashColor(s, palette) {
    let x = 0;
    for (const ch of norm(s)) x = (x * 31 + ch.codePointAt(0)) >>> 0;
    return palette[x % palette.length];
  }

  function monogram(name) {
    const parts = String(name).trim().split(/\s+/).filter(Boolean);
    const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] || "?").slice(0, 2);
    return letters.toLocaleUpperCase("hu");
  }

  function monoEl(p, big = false) {
    return h("span", { class: "mono" + (big ? " big" : ""), style: { "--c": p.color }, "aria-hidden": "true" }, monogram(p.name));
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleDateString("hu-HU", { year: "numeric", month: "short", day: "numeric" });
  }
  function fmtDateTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString("hu-HU", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  function countsText(counts, keys = ["cards", "quiz", "tasks", "timeline", "traps"]) {
    return keys.filter((k) => counts[k]).map((k) => `${counts[k]} ${COUNT_LABELS[k]}`).join(", ");
  }

  function toast(msg, bad = false) {
    const el = h("div", { class: "toast" + (bad ? " bad" : "") }, msg);
    $toasts.append(el);
    setTimeout(() => el.remove(), bad ? 6000 : 3200);
  }

  function isTyping(el) {
    return el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
  }

  // ================================================================ párbeszédablakok
  function openDialog(build) {
    return new Promise((resolve) => {
      const dlg = h("dialog");
      let done = false;
      const close = (value) => {
        if (done) return;
        done = true;
        dlg.close();
        dlg.remove();
        resolve(value);
      };
      dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(null); });
      build(dlg, close);
      document.body.append(dlg);
      dlg.showModal();
      const first = dlg.querySelector("[autofocus], input, textarea, select, button");
      if (first) first.focus();
    });
  }

  function confirmDialog({ title, text, ok = "Rendben", danger = false, check = null }) {
    return openDialog((dlg, close) => {
      const okBtn = h("button", { type: "button", class: danger ? "btn-danger" : "btn-primary", onclick: () => close(true) }, ok);
      let cb = null;
      if (check) {
        cb = h("input", { type: "checkbox", onchange: () => { okBtn.disabled = !cb.checked; } });
        okBtn.disabled = true;
      }
      add(dlg, 
        h("h2", null, title),
        text ? mdEl("p", text) : null,
        check ? h("label", { class: "check" }, cb, check) : null,
        h("div", { class: "btn-row" },
          h("button", { type: "button", onclick: () => close(false), autofocus: true }, "Mégse"),
          okBtn),
      );
    });
  }

  // Űrlapos ablak: onSubmit(form) dobhat ApiError-t, ekkor a hiba az ablakban jelenik meg.
  function formDialog({ title, fields, submit = "Mentés", onSubmit }) {
    return openDialog((dlg, close) => {
      const errBox = h("div", { class: "alert alert-bad", hidden: true, role: "alert" });
      const form = h("form", { method: "dialog", novalidate: true });
      const submitBtn = h("button", { type: "submit", class: "btn-primary" }, submit);
      add(form, h("h2", null, title), errBox, ...fields,
        h("div", { class: "btn-row" }, h("button", { type: "button", onclick: () => close(null) }, "Mégse"), submitBtn));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        submitBtn.disabled = true;
        errBox.hidden = true;
        try {
          close(await onSubmit(form));
        } catch (err) {
          fill(errBox, ...issueNodes(err));
          errBox.hidden = false;
        } finally {
          submitBtn.disabled = false;
        }
      });
      add(dlg, form);
    });
  }

  function issueNodes(err) {
    const msg = err instanceof Error ? err.message : String(err);
    const list = err && err.data && Array.isArray(err.data.errors) ? err.data.errors : [];
    return [h("strong", null, msg), list.length ? h("ul", { class: "issues" }, list.map((e) => h("li", null, h("code", null, e.path), " ", e.message))) : null];
  }

  function field(labelText, input, hint) {
    const id = input.id || "f-" + Math.random().toString(36).slice(2, 9);
    input.id = id;
    return h("div", { class: "field" }, h("label", { for: id }, labelText, hint ? h("span", { class: "hint" }, " – " + hint) : null), input);
  }

  function colorSwatches(name, current) {
    return h("div", { class: "field" },
      h("span", { class: "sr-only", id: name + "-lbl" }, "Szín"),
      h("div", { class: "swatches", role: "radiogroup", "aria-labelledby": name + "-lbl" },
        PALETTE.map((c, i) => h("label", { title: c },
          h("input", { type: "radio", name, value: c, checked: (current || PALETTE[0]) === c, "aria-label": `${i + 1}. szín` }),
          h("span", { style: { "--c": c } })))));
  }

  // ================================================================ API
  class ApiError extends Error {
    constructor(message, status, data) {
      super(message);
      this.status = status;
      this.data = data || {};
      this.code = this.data.code;
    }
  }

  async function api(path, { method = "GET", body, raw, contentType, keepalive = false } = {}) {
    const headers = {};
    if (state.profile) headers["X-Profile-Id"] = String(state.profile.id);
    let payload;
    if (raw !== undefined) {
      payload = raw;
      headers["Content-Type"] = contentType || "text/plain; charset=utf-8";
    } else if (body !== undefined) {
      payload = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
    let res;
    try {
      res = await fetch(path, { method, headers, body: payload, keepalive });
    } catch {
      throw new ApiError("Nem érem el a szervert. Ellenőrizd a hálózatot.", 0);
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = null; }
    if (!res.ok) {
      const msg = (data && data.detail) || `Hiba történt (${res.status}).`;
      if (res.status === 401 && data && (data.code === "unknown_profile" || data.code === "no_profile")) {
        setProfile(null);
        location.hash = "#/profilok";
      }
      throw new ApiError(typeof msg === "string" ? msg : "Hibás kérés.", res.status, data);
    }
    return data;
  }

  function setProfile(p) {
    state.profile = p;
    LS.set("profileId", p ? p.id : null);
    renderTopbar();
  }

  const isParent = () => state.profile && state.profile.role === "parent";

  // ================================================================ haladás mentése (kötegelve)
  const saver = {
    packId: null,
    cards: new Map(),
    answers: new Map(),
    waiters: [],
    timer: null,
    retryTimer: null,
    failedOnce: false,

    queueCard(packId, itemId, status) {
      this.switchPack(packId);
      this.cards.set(itemId, status);
      this.schedule(500);
    },
    queueAnswer(packId, taskId, questionId, answer) {
      this.switchPack(packId);
      this.answers.set(taskId + "\u0000" + questionId, { task_id: taskId, question_id: questionId, answer });
      this.schedule(900);
      return new Promise((resolve, reject) => this.waiters.push({ resolve, reject }));
    },
    switchPack(packId) {
      if (this.packId && this.packId !== packId && this.pending()) this.flush();
      this.packId = packId;
    },
    pending() { return this.cards.size > 0 || this.answers.size > 0; },
    schedule(ms) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.flush(), ms);
    },
    async flush({ keepalive = false } = {}) {
      clearTimeout(this.timer);
      if (!this.pending() || !this.packId) return;
      const packId = this.packId;
      const cards = [...this.cards].map(([item_id, status]) => ({ item_id, status }));
      const answers = [...this.answers.values()];
      const waiters = this.waiters;
      this.cards = new Map();
      this.answers = new Map();
      this.waiters = [];
      try {
        await api(`/api/progress/${encodeURIComponent(packId)}`, { method: "PUT", body: { cards, answers }, keepalive });
        this.failedOnce = false;
        waiters.forEach((w) => w.resolve());
      } catch (err) {
        if (err.status === 401 || err.status === 404) { waiters.forEach((w) => w.reject(err)); return; }
        // visszatesszük, ami közben nem íródott felül, és később újrapróbáljuk
        for (const c of cards) if (!this.cards.has(c.item_id)) this.cards.set(c.item_id, c.status);
        for (const a of answers) {
          const k = a.task_id + "\u0000" + a.question_id;
          if (!this.answers.has(k)) this.answers.set(k, a);
        }
        this.packId = this.packId || packId;
        waiters.forEach((w) => w.reject(err));
        if (!this.failedOnce) toast("Nem sikerült menteni a haladást, újrapróbálom.", true);
        this.failedOnce = true;
        clearTimeout(this.retryTimer);
        this.retryTimer = setTimeout(() => this.flush(), 5000);
      }
    },
  };
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saver.flush({ keepalive: true }); });
  window.addEventListener("pagehide", () => saver.flush({ keepalive: true }));

  // ================================================================ felső sáv, téma
  const THEMES = [["auto", "Téma: auto"], ["light", "Téma: világos"], ["dark", "Téma: sötét"]];
  function applyTheme(t) {
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  }
  function renderTopbar() {
    const t = LS.get("theme") || "auto";
    const btn = document.getElementById("theme-btn");
    btn.textContent = (THEMES.find((x) => x[0] === t) || THEMES[0])[1];
    const pb = document.getElementById("profile-btn");
    fill(pb);
    if (state.profile) {
      pb.append(monoEl(state.profile));
      pb.setAttribute("aria-label", `Profil: ${state.profile.name}. Váltás`);
      pb.title = `${state.profile.name} – profil váltása`;
    }
    $topbar.hidden = !state.profile;
  }
  document.getElementById("theme-btn").addEventListener("click", () => {
    const cur = LS.get("theme") || "auto";
    const next = THEMES[(THEMES.findIndex((x) => x[0] === cur) + 1) % THEMES.length][0];
    LS.set("theme", next === "auto" ? null : next);
    applyTheme(next);
    renderTopbar();
  });
  document.getElementById("profile-btn").addEventListener("click", () => { location.hash = "#/profilok"; });

  document.addEventListener("keydown", (e) => {
    if (!state.keyHandler || e.ctrlKey || e.metaKey || e.altKey) return;
    if (isTyping(e.target) || document.querySelector("dialog[open]")) return;
    // Fókuszált gombon a Szóköz/Enter a gomb saját kattintása legyen, ne fusson le kétszer.
    if ((e.key === " " || e.key === "Enter") && e.target.closest && e.target.closest("button, a, summary")) return;
    state.keyHandler(e);
  });

  // ================================================================ útvonalak
  function parseHash() {
    const raw = location.hash.replace(/^#\/?/, "");
    const parts = raw.split("/").filter(Boolean).map(decodeURIComponent);
    return parts;
  }

  async function route() {
    const seq = ++state.renderSeq;
    if (state.cleanup) { try { state.cleanup(); } catch { /* */ } }
    state.cleanup = null;
    state.keyHandler = null;
    await saver.flush();
    const parts = parseHash();
    const name = parts[0] || "";

    if (!state.profile && name !== "profilok") {
      location.replace("#/profilok");
      return;
    }
    const view = {
      "": viewLibrary,
      profilok: viewProfiles,
      anyag: viewPack,
      feltoltes: viewUpload,
      kezeles: viewManage,
    }[name];
    if (!view) { location.replace("#/"); return; }
    if ((name === "feltoltes" || name === "kezeles") && !isParent()) {
      toast("Ehhez szülői profil kell.", true);
      location.replace("#/");
      return;
    }
    fill($app, h("p", { class: "loading" }, "Betöltés…"));
    try {
      await view(parts.slice(1), () => seq === state.renderSeq);
    } catch (err) {
      if (seq !== state.renderSeq) return;
      fill($app, h("div", { class: "empty" },
        h("p", null, err.message || "Hiba történt."),
        h("button", { type: "button", onclick: () => route() }, "Újra")));
    }
    if (seq === state.renderSeq) window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  // ================================================================ profilválasztó
  async function viewProfiles(_args, alive) {
    state.profiles = await api("/api/profiles");
    if (!alive()) return;
    if (state.profile && !state.profiles.some((p) => p.id === state.profile.id)) setProfile(null);
    renderTopbar();

    if (state.profiles.length === 0) return renderFirstRun();

    const grid = h("div", { class: "picker-grid" }, state.profiles.map((p) =>
      h("button", {
        type: "button",
        "aria-current": state.profile && state.profile.id === p.id ? "true" : null,
        onclick: () => { setProfile(p); location.hash = "#/"; },
      }, monoEl(p, true), h("span", { class: "name" }, p.name), h("span", { class: "role" }, p.role === "parent" ? "szülő" : "tanuló"))));

    fill($app, h("section", { class: "picker" },
      h("h1", null, "Ki tanul most?"),
      grid,
      isParent() ? h("div", { class: "btn-row", style: { justifyContent: "center" } },
        h("button", { type: "button", onclick: () => newProfileDialog().then((p) => p && route()) }, "Új profil"),
        h("a", { class: "btn btn-quiet", href: "#/kezeles" }, "Profilok kezelése")) : null,
      state.profile ? h("p", { class: "mt" }, h("a", { href: "#/" }, "Vissza az anyagokhoz")) : null,
    ));
  }

  function renderFirstRun() {
    const name = h("input", { type: "text", maxlength: 40, autocomplete: "off", required: true });
    const errBox = h("div", { class: "alert alert-bad", hidden: true, role: "alert" });
    const form = h("form", { novalidate: true },
      errBox,
      field("Név", name),
      colorSwatches("first-color", PALETTE[0]),
      h("button", { type: "submit", class: "btn-primary" }, "Profil létrehozása"));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const color = form.querySelector("input[name=first-color]:checked")?.value;
        const p = await api("/api/profiles", { method: "POST", body: { name: name.value.trim(), color, role: "parent" } });
        setProfile(p);
        location.hash = "#/";
      } catch (err) {
        fill(errBox, ...issueNodes(err));
        errBox.hidden = false;
      }
    });
    const importInput = h("input", { type: "file", accept: ".json,application/json" });
    importInput.addEventListener("change", async () => {
      const f = importInput.files[0];
      if (!f) return;
      if (await doImport(f)) route();
      importInput.value = "";
    });
    fill($app, h("section", { class: "picker" },
      h("h1", null, "Üdv a Tanulóban!"),
      h("div", { class: "narrow" },
        h("p", null, "Hozd létre az első profilt. Ez szülői profil lesz: ezzel lehet anyagot feltölteni és a többi profilt kezelni."),
        form,
        h("div", { class: "panel mt" },
          h("h2", null, "Van mentésed?"),
          h("p", { class: "hint" }, "Egy korábbi exportfájlból mindent visszatölthetsz: profilokat, anyagokat, haladást."),
          h("div", { class: "file-pick" }, importInput)))));
    name.focus();
  }

  function newProfileDialog() {
    const name = h("input", { type: "text", maxlength: 40, autocomplete: "off" });
    const role = h("select", null, h("option", { value: "child" }, "Tanuló"), h("option", { value: "parent" }, "Szülő"));
    return formDialog({
      title: "Új profil",
      submit: "Létrehozás",
      fields: [field("Név", name), field("Szerep", role, "szülő tölthet fel anyagot"), colorSwatches("np-color", PALETTE[state.profiles.length % PALETTE.length])],
      onSubmit: async (form) => {
        const color = form.querySelector("input[name=np-color]:checked")?.value;
        const p = await api("/api/profiles", { method: "POST", body: { name: name.value.trim(), role: role.value, color } });
        toast(`Létrehozva: ${p.name}`);
        return p;
      },
    });
  }

  // ================================================================ anyagtár
  const lib = { q: "", subject: "", tag: "", sort: LS.get("lib.sort") || "recent", archived: false };

  async function viewLibrary(_args, alive) {
    const search = h("input", {
      type: "search", value: lib.q, placeholder: "Keresés: cím, téma, tantárgy, címke",
      "aria-label": "Keresés az anyagok között", autocomplete: "off", enterkeyhint: "search",
    });
    const subjectSel = h("select", { "aria-label": "Tantárgy" });
    const tagSel = h("select", { "aria-label": "Címke" });
    const sortSel = h("select", { "aria-label": "Rendezés" },
      h("option", { value: "recent" }, "Legutóbb használt"),
      h("option", { value: "uploaded" }, "Legutóbb feltöltött"),
      h("option", { value: "title" }, "Cím szerint"));
    sortSel.value = lib.sort;
    const archToggle = h("label", { class: "check", hidden: true }, h("input", { type: "checkbox", checked: lib.archived }), h("span"));
    const results = h("div", { "aria-live": "polite" });

    const headButtons = isParent() ? h("div", { class: "btn-row" },
      h("a", { class: "btn btn-primary btn-small", href: "#/feltoltes" }, "Feltöltés"),
      h("a", { class: "btn btn-small", href: "#/kezeles" }, "Kezelés")) : null;

    fill($app, 
      h("div", { class: "lib-head" }, h("h1", null, lib.archived ? "Archivált anyagok" : "Anyagok"), headButtons),
      h("div", { class: "searchbox" },
        h("span", { html: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>' }),
        search),
      h("div", { class: "controls" }, subjectSel, tagSel, h("div", { class: "sort-cell" }, sortSel), isParent() ? archToggle : null),
      results);

    const fillSelect = (sel, items, current, allLabel) => {
      fill(sel, h("option", { value: "" }, allLabel), ...items.map((x) => h("option", { value: x }, x)));
      sel.value = items.includes(current) ? current : "";
    };

    async function load() {
      const params = new URLSearchParams({ q: lib.q, subject: lib.subject, tag: lib.tag, sort: lib.sort });
      if (lib.archived) params.set("archived", "true");
      const data = await api("/api/packs?" + params);
      if (!alive()) return;
      fillSelect(subjectSel, data.subjects, lib.subject, "Minden tantárgy");
      fillSelect(tagSel, data.tags, lib.tag, "Minden címke");
      archToggle.hidden = !(data.archived_count > 0 || lib.archived);
      archToggle.querySelector("span").textContent = `Archiváltak (${data.archived_count})`;
      $app.querySelector(".lib-head h1").textContent = lib.archived ? "Archivált anyagok" : "Anyagok";
      renderResults(data);
    }

    function renderResults(data) {
      if (data.items.length === 0) {
        const filtered = lib.q || lib.subject || lib.tag;
        let content;
        if (filtered) {
          content = [h("p", null, lib.q ? `Nincs találat erre: „${lib.q}”.` : "Ezekkel a szűrőkkel nincs találat."),
            h("button", { type: "button", onclick: () => { lib.q = ""; lib.subject = ""; lib.tag = ""; search.value = ""; load(); } }, "Szűrők törlése")];
        } else if (lib.archived) {
          content = [h("p", null, "Nincs archivált anyag.")];
        } else if (isParent()) {
          content = [h("p", null, "Még nincs anyag. Tölts fel egy tartalomcsomagot (JSON)."), h("a", { class: "btn btn-primary", href: "#/feltoltes" }, "Csomag feltöltése")];
        } else {
          content = [h("p", null, "Még nincs anyag. Kérd meg a szülőt, hogy töltsön fel egyet.")];
        }
        fill(results, h("div", { class: "empty" }, content));
        return;
      }
      fill(results, h("ul", { class: "packlist" }, data.items.map(packItem)));
    }

    search.addEventListener("input", debounce(() => { lib.q = search.value.trim(); load().catch(showErr); }, 220));
    subjectSel.addEventListener("change", () => { lib.subject = subjectSel.value; load().catch(showErr); });
    tagSel.addEventListener("change", () => { lib.tag = tagSel.value; load().catch(showErr); });
    sortSel.addEventListener("change", () => { lib.sort = sortSel.value; LS.set("lib.sort", lib.sort); load().catch(showErr); });
    archToggle.querySelector("input").addEventListener("change", (e) => { lib.archived = e.target.checked; load().catch(showErr); });

    await load();
  }

  function showErr(err) { toast(err.message || "Hiba történt.", true); }

  function packItem(p) {
    const prog = p.progress;
    const total = prog ? prog.total : 0;
    const knownPct = total ? (prog.known / total) * 100 : 0;
    const learnPct = total ? (prog.learning / total) * 100 : 0;
    return h("li", null, h("a", { class: "pack", href: `#/anyag/${encodeURIComponent(p.id)}`, style: { "--s": hashColor(p.subject, SUBJECT_COLORS) } },
      h("h2", null, p.title),
      h("div", { class: "subject" }, h("span", null, p.subject), p.level ? h("span", null, p.level) : null),
      h("p", { class: "topic" }, p.topic),
      p.tags.length ? h("ul", { class: "tags", "aria-label": "Címkék" }, p.tags.map((t) => h("li", { class: "tag" }, t))) : null,
      total ? h("div", { class: "meter meter-stack", role: "img", "aria-label": `Tudom: ${prog.known} / ${total}, tanulás alatt: ${prog.learning}` },
        h("span", { style: { width: knownPct + "%" } }), h("span", { style: { width: learnPct + "%" } })) : null,
      h("div", { class: "pack-foot" },
        total ? h("span", { class: "known" }, `Tudom: ${prog.known}/${total}`) : h("span", null, countsText(p.counts) || "Üres csomag"),
        h("span", null, `Frissítve: ${fmtDate(p.updated_at)}`))));
  }

  // ================================================================ anyag nézet
  const TABS = [
    { key: "kartyak", label: "Kártyák", has: (c) => (c.cards || []).length > 0, render: modeCards },
    { key: "kviz", label: "Kvíz", has: (c) => (c.quiz || []).length > 0, render: modeQuiz },
    { key: "feladatok", label: "Feladatok", has: (c) => (c.tasks || []).length > 0, render: modeTasks },
    { key: "idovonal", label: "Idővonal", has: (c) => (c.timeline || []).length > 0, render: modeTimeline },
    { key: "osszefoglalo", label: "Összefoglaló", has: (c) => (c.summary || []).length > 0 || (c.traps || []).length > 0 || !!(c.meta && c.meta.exam_info), render: modeSummary },
  ];

  async function viewPack(args, alive) {
    const packId = args[0];
    const [data, progress] = await Promise.all([
      api(`/api/packs/${encodeURIComponent(packId)}`),
      api(`/api/progress/${encodeURIComponent(packId)}`),
    ]);
    if (!alive()) return;
    const content = data.content;
    const pack = data.pack;
    const chapters = (content.chapters || []).slice().sort((a, b) => a.order - b.order);
    const chTitle = Object.fromEntries(chapters.map((c) => [c.id, c.title]));
    const chOrder = Object.fromEntries(chapters.map((c, i) => [c.id, i]));
    const ctx = { packId, pack, content, chapters, chTitle, chOrder, progress, panel: null, data };

    const tabs = TABS.filter((t) => t.has(content));
    const wanted = args[1] || LS.get(`tab.${packId}`);
    let current = tabs.find((t) => t.key === wanted) || tabs[0];

    const panel = h("section", { id: "tab-panel", role: "tabpanel" });
    ctx.panel = panel;
    const tabBar = h("div", { class: "tabs", role: "tablist", "aria-label": "Tanulási módok" });

    let modeCleanup = null;
    function select(tab, focus = false) {
      if (modeCleanup) { try { modeCleanup(); } catch { /* */ } }
      modeCleanup = null;
      state.keyHandler = null;
      current = tab;
      LS.set(`tab.${packId}`, tab.key);
      history.replaceState(null, "", `#/anyag/${encodeURIComponent(packId)}/${tab.key}`);
      for (const b of tabBar.children) {
        const on = b.dataset.key === tab.key;
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        if (on && focus) b.focus();
      }
      panel.setAttribute("aria-labelledby", "tab-" + tab.key);
      fill(panel);
      modeCleanup = tab.render(ctx) || null;
    }
    tabs.forEach((t, i) => tabBar.append(h("button", {
      type: "button", role: "tab", id: "tab-" + t.key, "aria-controls": "tab-panel", dataset: { key: t.key },
      onclick: () => select(t),
      onkeydown: (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        e.stopPropagation();
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        select(n, true);
      },
    }, t.label)));

    const parentTools = isParent() ? h("div", { class: "btn-row" },
      h("button", { type: "button", class: "btn-small", onclick: () => editPackDialog(pack) }, "Adatok szerkesztése"),
      h("a", { class: "btn btn-small", href: "#/feltoltes" }, "Új verzió feltöltése"),
      h("button", { type: "button", class: "btn-small", onclick: () => downloadJson(content, `${packId}-v${pack.current_version}.json`) }, "JSON letöltése")) : null;

    fill($app, 
      h("nav", { class: "crumbs" }, h("a", { href: "#/" }, "Anyagok")),
      h("h1", { class: "pack-title" }, pack.title),
      h("div", { class: "pack-sub" },
        h("span", null, pack.subject), pack.level ? h("span", null, pack.level) : null,
        h("span", null, `${pack.current_version}. verzió, ${fmtDate(pack.updated_at)}`),
        pack.archived ? h("span", { class: "badge" }, "Archivált") : null),
      parentTools,
      tabs.length ? tabBar : null,
      tabs.length ? panel : h("div", { class: "empty" }, h("p", null, "Ebben a csomagban nincs megjeleníthető tartalom.")));

    state.cleanup = () => { if (modeCleanup) modeCleanup(); };
    if (current) select(current);
  }

  function editPackDialog(pack) {
    const title = h("input", { type: "text", value: pack.title, maxlength: 120 });
    const topic = h("textarea", { maxlength: 200, rows: 2 }, pack.topic);
    const subject = h("input", { type: "text", value: pack.subject, maxlength: 60 });
    const tags = h("input", { type: "text", value: pack.tags.join(", ") });
    const level = h("input", { type: "text", value: pack.level || "", maxlength: 40 });
    return openDialog((dlg, close) => {
      const errBox = h("div", { class: "alert alert-bad", hidden: true, role: "alert" });
      const form = h("form", { novalidate: true },
        h("h2", null, "Anyag adatai"), errBox,
        field("Cím", title), field("Téma", topic), field("Tantárgy", subject),
        field("Címkék", tags, "vesszővel elválasztva"), field("Évfolyam vagy szint", level),
        h("div", { class: "btn-row" },
          h("button", { type: "button", onclick: () => close(null) }, "Mégse"),
          h("button", { type: "submit", class: "btn-primary" }, "Mentés")),
        h("hr", { style: { border: "none", borderTop: "1px solid var(--line)", margin: "18px 0" } }),
        h("div", { class: "btn-row", style: { justifyContent: "flex-start" } },
          h("button", { type: "button", onclick: async () => {
            try {
              await api(`/api/packs/${encodeURIComponent(pack.id)}`, { method: "PATCH", body: { archived: !pack.archived } });
              toast(pack.archived ? "Visszaállítva" : "Archiválva: már nem látszik a listában");
              close(true);
              if (pack.archived) route(); else location.hash = "#/";
            } catch (err) { showErr(err); }
          } }, pack.archived ? "Visszaállítás" : "Archiválás"),
          h("button", { type: "button", class: "btn-danger", onclick: async () => {
            close(null);
            if (await deletePack(pack)) location.hash = "#/";
          } }, "Végleges törlés")));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await api(`/api/packs/${encodeURIComponent(pack.id)}`, {
            method: "PATCH",
            body: { title: title.value, topic: topic.value, subject: subject.value, level: level.value,
              tags: tags.value.split(",").map((t) => t.trim()).filter(Boolean) },
          });
          toast("Mentve");
          close(true);
          route();
        } catch (err) {
          fill(errBox, ...issueNodes(err));
          errBox.hidden = false;
        }
      });
      add(dlg, form);
    });
  }

  async function deletePack(pack) {
    const ok = await confirmDialog({
      title: "Végleges törlés",
      text: `A(z) **${pack.title}** anyag minden verziójával és **minden profil haladásával** együtt törlődik. Ez nem vonható vissza.`,
      ok: "Végleges törlés", danger: true,
      check: "Értem, hogy ez nem vonható vissza",
    });
    if (!ok) return false;
    try {
      await api(`/api/packs/${encodeURIComponent(pack.id)}?confirm=${encodeURIComponent(pack.id)}`, { method: "DELETE" });
      toast("Törölve");
      return true;
    } catch (err) { showErr(err); return false; }
  }

  function chapterSelect(ctx, items, key, onChange) {
    const ids = new Set(items.map((x) => x.chapter).filter(Boolean));
    const avail = ctx.chapters.filter((c) => ids.has(c.id));
    const sel = h("select", { "aria-label": "Fejezet" },
      h("option", { value: "" }, "Összes fejezet"),
      avail.map((c) => h("option", { value: c.id }, c.title)));
    const saved = LS.get(`${key}.${ctx.packId}`) || "";
    sel.value = avail.some((c) => c.id === saved) ? saved : "";
    sel.addEventListener("change", () => { LS.set(`${key}.${ctx.packId}`, sel.value || null); onChange(sel.value); });
    return { sel, value: () => sel.value, count: avail.length };
  }

  // ---------------------------------------------------------------- kártyák
  function modeCards(ctx) {
    const all = ctx.content.cards.map((c, i) => ({ ...c, _i: i }))
      .sort((a, b) => (ctx.chOrder[a.chapter] ?? 999) - (ctx.chOrder[b.chapter] ?? 999) || a._i - b._i);
    const status = (id) => (ctx.progress.cards[id] && ctx.progress.cards[id].status) || "new";

    const opts = { shuffle: LS.get("cards.shuffle") === "1", onlyNew: LS.get("cards.onlyNew") === "1" };
    const chSel = chapterSelect(ctx, all, "cards.ch", () => restart());
    const shuffleCb = h("input", { type: "checkbox", checked: opts.shuffle });
    const onlyNewCb = h("input", { type: "checkbox", checked: opts.onlyNew });
    shuffleCb.addEventListener("change", () => { opts.shuffle = shuffleCb.checked; LS.set("cards.shuffle", opts.shuffle ? "1" : null); restart(); });
    onlyNewCb.addEventListener("change", () => { opts.onlyNew = onlyNewCb.checked; LS.set("cards.onlyNew", opts.onlyNew ? "1" : null); restart(); });

    const stage = h("div");
    add(ctx.panel, 
      h("div", { class: "toolbar" }, chSel.count > 1 ? chSel.sel : null,
        h("label", { class: "check" }, shuffleCb, "Keverés"),
        h("label", { class: "check" }, onlyNewCb, "Csak amit még nem tudok")),
      stage);

    let deck = [];
    let i = 0;
    let flipped = false;
    let session = { known: 0, learning: 0 };
    let flashEl = null;

    function build(subset) {
      let d = subset || all.filter((c) => !chSel.value() || c.chapter === chSel.value());
      if (!subset && opts.onlyNew) d = d.filter((c) => status(c.id) !== "known");
      return opts.shuffle ? shuffle(d) : d;
    }
    function restart(subset) {
      deck = build(subset);
      i = 0;
      flipped = false;
      session = { known: 0, learning: 0 };
      render();
    }

    function render() {
      flashEl = null;
      if (deck.length === 0) {
        fill(stage, h("div", { class: "empty" },
          h("p", null, opts.onlyNew ? "Ebben a válogatásban minden kártyát tudsz." : "Ebben a fejezetben nincs kártya."),
          opts.onlyNew ? h("button", { type: "button", onclick: () => { onlyNewCb.checked = false; onlyNewCb.dispatchEvent(new Event("change")); } }, "Az összes kártya mutatása") : null));
        return;
      }
      if (i >= deck.length) {
        const notYet = deck.filter((c) => status(c.id) !== "known");
        fill(stage, h("div", { class: "done-panel" },
          h("p", null, "Végére értél ennek a körnek."),
          h("p", { class: "big" }, `${session.known} tudom, ${session.learning} még nem megy`),
          h("p", { class: "muted" }, `A csomagban összesen ${ctx.content.cards.filter((c) => status(c.id) === "known").length} / ${ctx.content.cards.length} kártyát tudsz.`),
          h("div", { class: "btn-row" },
            notYet.length ? h("button", { type: "button", class: "btn-primary", onclick: () => restart(notYet) }, `Még egyszer, ami nem megy (${notYet.length})`) : null,
            h("button", { type: "button", onclick: () => restart() }, "Újrakezdés"))));
        stage.querySelector("button")?.focus();
        return;
      }
      const card = deck[i];
      const st = status(card.id);
      const stLabel = st === "known" ? "Tudom" : st === "learning" ? "Még nem megy" : "";
      const corner = () => h("span", { class: "corner" + (stLabel ? " status-" + st : "") }, stLabel || "");
      const inner = h("button", {
        type: "button", class: "flash-inner",
        "aria-label": flipped ? "Kártya hátoldala. Kattints a megfordításhoz." : "Kártya előoldala. Kattints a megfordításhoz.",
        onclick: () => flip(),
      },
        h("div", { class: "face front", "aria-hidden": flipped ? "true" : "false" }, corner(), h("div", { html: md(card.front) })),
        h("div", { class: "face back", "aria-hidden": flipped ? "false" : "true" }, corner(), h("div", { html: md(card.back) })));
      flashEl = h("div", { class: "flash" + (flipped ? " flipped" : "") }, inner);
      addSwipe(flashEl);
      fill(stage, 
        h("div", { class: "deck-status" },
          h("span", { class: "chapter" }, ctx.chTitle[card.chapter] || ""),
          h("span", null, `${i + 1} / ${deck.length}`)),
        flashEl,
        h("div", { class: "mark-row" },
          h("button", { type: "button", class: "btn-learning", onclick: () => mark("learning") }, "Még nem megy"),
          h("button", { type: "button", class: "btn-known", onclick: () => mark("known") }, "Tudom")),
        h("div", { class: "nav-row" },
          h("button", { type: "button", class: "btn-quiet", disabled: i === 0, onclick: () => go(-1) }, "‹ Előző"),
          h("button", { type: "button", class: "btn-quiet", onclick: () => go(1) }, "Kihagyom ›")),
        h("p", { class: "keys" }, h("kbd", null, "Szóköz"), " fordít  ", h("kbd", null, "←"), h("kbd", null, "→"), " lapoz  ",
          h("kbd", null, "1"), " tudom  ", h("kbd", null, "2"), " még nem megy"));
    }

    function flip() {
      if (!flashEl) return;
      flipped = !flipped;
      flashEl.classList.toggle("flipped", flipped);
      const [f, b] = flashEl.querySelectorAll(".face");
      f.setAttribute("aria-hidden", flipped ? "true" : "false");
      b.setAttribute("aria-hidden", flipped ? "false" : "true");
    }
    function go(d) {
      const n = i + d;
      if (n < 0 || n > deck.length) return;
      i = n;
      flipped = false;
      render();
    }
    function mark(st) {
      const card = deck[i];
      if (!card) return;
      const prev = ctx.progress.cards[card.id] || { seen_count: 0 };
      ctx.progress.cards[card.id] = { ...prev, status: st, seen_count: (prev.seen_count || 0) + 1, last_seen_at: new Date().toISOString() };
      session[st === "known" ? "known" : "learning"]++;
      saver.queueCard(ctx.packId, card.id, st);
      go(1);
    }
    function addSwipe(el) {
      let x0 = null, y0 = null;
      el.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
      el.addEventListener("touchend", (e) => {
        if (x0 == null) return;
        const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
        x0 = null;
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) go(dx < 0 ? 1 : -1);
      });
    }

    state.keyHandler = (e) => {
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); flip(); } else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
      else if (e.key === "1") { e.preventDefault(); mark("known"); }
      else if (e.key === "2") { e.preventDefault(); mark("learning"); }
    };

    restart();
    return () => saver.flush();
  }

  // ---------------------------------------------------------------- kvíz
  function modeQuiz(ctx) {
    const all = ctx.content.quiz;
    const chSel = chapterSelect(ctx, all, "quiz.ch", () => {});
    const sizeSel = h("select", { "aria-label": "Kérdések száma egy körben" },
      [5, 10, 15, 20].map((n) => h("option", { value: n }, `${n} kérdés`)), h("option", { value: "all" }, "Az összes"));
    sizeSel.value = LS.get("quiz.size") || "10";
    sizeSel.addEventListener("change", () => LS.set("quiz.size", sizeSel.value));

    function setup() {
      state.keyHandler = null;
      const attempts = ctx.progress.quiz_attempts || [];
      const startBtn = h("button", { type: "button", class: "btn-primary", onclick: () => start() }, "Kör indítása");
      fill(ctx.panel, 
        h("p", { class: "muted" }, `${all.length} kérdés a csomagban. Egy körben véletlenszerűen válogatunk.`),
        h("div", { class: "toolbar" }, chSel.count > 1 ? chSel.sel : null, sizeSel, startBtn),
        attempts.length ? h("div", { class: "mt" }, h("h2", null, "Legutóbbi eredmények"),
          h("ul", { class: "attempts" }, attempts.map((a) => h("li", null,
            h("span", null, a.chapter ? (ctx.chTitle[a.chapter] || a.chapter) : "Összes fejezet"),
            h("span", null, h("b", null, `${a.score}/${a.max}`), "  ", fmtDateTime(a.taken_at)))))) : null);
      state.keyHandler = (e) => { if (e.key === "Enter") { e.preventDefault(); start(); } };
    }

    function start(list) {
      let pool = list || all.filter((q) => !chSel.value() || q.chapter === chSel.value());
      const size = sizeSel.value === "all" ? pool.length : parseInt(sizeSel.value, 10);
      pool = shuffle(pool).slice(0, list ? pool.length : size);
      if (pool.length === 0) { toast("Ebben a fejezetben nincs kvízkérdés."); return; }
      run(pool, list ? "retry" : "round");
    }

    function run(questions, kind) {
      let idx = 0;
      const wrong = [];
      let answered = false;
      let nextBtn = null;
      let optionBtns = [];

      function show() {
        answered = false;
        const q = questions[idx];
        const order = shuffle(q.options.map((_, k) => k));
        const fb = h("div", { "aria-live": "polite" });
        nextBtn = h("button", { type: "button", class: "btn-primary", hidden: true, onclick: () => next() }, idx + 1 < questions.length ? "Következő" : "Eredmény");
        optionBtns = order.map((k, n) => h("button", { type: "button", onclick: () => answer(k) },
          h("span", { class: "num" }, String(n + 1)), h("span", { html: md(q.options[k]) })));
        optionBtns.forEach((b, n) => { b.dataset.k = order[n]; });

        function answer(k) {
          if (answered) return;
          answered = true;
          const ok = k === q.correct;
          if (!ok) wrong.push(q);
          optionBtns.forEach((b) => {
            const bk = Number(b.dataset.k);
            b.disabled = true;
            if (bk === q.correct) b.classList.add("correct");
            else if (bk === k) b.classList.add("wrong");
          });
          fill(fb, h("div", { class: "feedback" + (ok ? "" : " bad") },
            h("strong", null, ok ? "Helyes!" : "Nem ez a helyes válasz."),
            q.explanation ? h("span", { html: md(q.explanation) }) : null));
          nextBtn.hidden = false;
          nextBtn.focus();
        }

        fill(ctx.panel, 
          h("div", { class: "deck-status" },
            h("span", { class: "chapter" }, ctx.chTitle[q.chapter] || ""),
            h("span", null, `${idx + 1} / ${questions.length}`)),
          h("p", { class: "quiz-q", html: md(q.question) }),
          h("div", { class: "options", role: "group", "aria-label": "Válaszlehetőségek" }, optionBtns),
          fb,
          h("div", { class: "btn-row" }, nextBtn,
            h("button", { type: "button", class: "btn-quiet", onclick: () => setup() }, "Kör megszakítása")));

        state.keyHandler = (e) => {
          const n = parseInt(e.key, 10);
          if (!answered && n >= 1 && n <= optionBtns.length) { e.preventDefault(); optionBtns[n - 1].click(); }
          else if (answered && (e.key === "Enter" || e.key === "ArrowRight")) { e.preventDefault(); next(); }
        };
      }

      function next() {
        idx++;
        if (idx < questions.length) show();
        else finish();
      }

      async function finish() {
        state.keyHandler = null;
        const score = questions.length - wrong.length;
        const chapter = kind === "round" ? (chSel.value() || null) : null;
        const pct = Math.round((score / questions.length) * 100);
        fill(ctx.panel, h("div", { class: "done-panel" },
          h("p", null, kind === "retry" ? "A hibás kérdések újra:" : "A kör eredménye:"),
          h("p", { class: "score" }, `${score} / ${questions.length}`),
          h("p", { class: "muted" }, `${pct}%`),
          wrong.length ? h("div", null, h("h2", { class: "mt" }, "Ezeket érdemes átnézni"),
            h("ol", { class: "wronglist" }, wrong.map((q) => h("li", null,
              h("div", { html: md(q.question) }),
              h("div", null, "Helyes válasz: ", h("strong", { html: md(q.options[q.correct]) })))))) : h("p", null, "Mindegyik helyes volt."),
          h("div", { class: "btn-row" },
            wrong.length ? h("button", { type: "button", class: "btn-primary", onclick: () => start(wrong.slice()) }, `Hibásak újra (${wrong.length})`) : null,
            h("button", { type: "button", onclick: () => setup() }, "Új kör"))));
        ctx.panel.querySelector(".done-panel button")?.focus();
        try {
          const res = await api(`/api/progress/${encodeURIComponent(ctx.packId)}/quiz`, {
            method: "POST", body: { chapter, score, max: questions.length, wrong_ids: wrong.map((q) => q.id) },
          });
          (ctx.progress.quiz_attempts = ctx.progress.quiz_attempts || []).unshift({
            id: res.id, chapter, score, max: questions.length, wrong_ids: wrong.map((q) => q.id), taken_at: new Date().toISOString(),
          });
        } catch (err) { showErr(err); }
      }

      show();
    }

    setup();
    return null;
  }

  // ---------------------------------------------------------------- forrásos feladatok
  function modeTasks(ctx) {
    const tasks = ctx.content.tasks;
    const list = h("div");
    let allOpen = false;
    const toggleAll = h("button", { type: "button", class: "btn-small", onclick: () => {
      allOpen = !allOpen;
      list.querySelectorAll("details").forEach((d) => { d.open = allOpen; });
      toggleAll.textContent = allOpen ? "Megoldások elrejtése" : "Összes megoldás mutatása";
    } }, "Összes megoldás mutatása");
    const chSel = chapterSelect(ctx, tasks, "tasks.ch", () => render());
    add(ctx.panel, h("div", { class: "toolbar" }, chSel.count > 1 ? chSel.sel : null, toggleAll), list);

    function render() {
      allOpen = false;
      toggleAll.textContent = "Összes megoldás mutatása";
      const shown = tasks.filter((t) => !chSel.value() || t.chapter === chSel.value());
      fill(list, ...shown.map(taskEl));
    }

    function taskEl(t) {
      const saved = (ctx.progress.answers || {})[t.id] || {};
      const note = h("p", { class: "saved-note", "aria-live": "polite" });
      const src = t.source || {};
      let body;
      if (src.type === "table" && src.table) {
        const head = src.table.header || [];
        body = h("table", null,
          h("thead", null, h("tr", null, head.map((x) => h("th", { scope: "col", html: md(x) })))),
          h("tbody", null, (src.table.rows || []).map((r) => h("tr", null, r.map((cell, ci) => h("td", { "data-label": head[ci] || "", html: md(cell) }))))));
      } else {
        body = h("div", { class: "text", html: md(src.text || "") });
      }
      return h("article", { class: "task" },
        h("h2", null, t.title),
        ctx.chTitle[t.chapter] ? h("p", { class: "muted", style: { marginTop: "-6px" } }, ctx.chTitle[t.chapter]) : null,
        h("figure", { class: "source", style: { margin: "10px 0 16px" } },
          h("figcaption", null, h("span", { html: md(src.caption || "Forrás") }), src.excerpt ? h("span", { class: "badge", title: "Tartalmi kivonat, nem szó szerinti idézet" }, "Kivonat") : null),
          body),
        (t.questions || []).map((q, qi) => {
          const ta = h("textarea", { id: `ans-${t.id}-${q.id}`, rows: 3, placeholder: "Írd ide a válaszod…" });
          ta.value = saved[q.id] || "";
          ta.addEventListener("input", () => {
            (ctx.progress.answers[t.id] = ctx.progress.answers[t.id] || {})[q.id] = ta.value;
            note.textContent = "Mentés…";
            saver.queueAnswer(ctx.packId, t.id, q.id, ta.value)
              .then(() => { note.textContent = "Mentve " + new Date().toLocaleTimeString("hu-HU", { hour: "2-digit", minute: "2-digit" }); })
              .catch(() => { note.textContent = "Nincs mentve, újrapróbálom…"; });
          });
          return h("div", { class: "question" },
            h("label", { for: ta.id }, h("span", null, `${qi + 1}. `), h("span", { html: md(q.prompt) })),
            ta,
            h("details", null, h("summary", null, "Megoldás"), h("div", { class: "solution", html: md(q.solution) })));
        }),
        note);
    }

    ctx.progress.answers = ctx.progress.answers || {};
    render();
    return () => saver.flush();
  }

  // ---------------------------------------------------------------- idővonal
  function modeTimeline(ctx) {
    const items = ctx.content.timeline.slice().sort((a, b) => a.sort_key - b.sort_key);
    const list = h("ol", { class: "timeline" });
    const chSel = chapterSelect(ctx, items, "tl.ch", () => render());
    if (chSel.count > 1) add(ctx.panel, h("div", { class: "toolbar" }, chSel.sel));
    add(ctx.panel, list);
    function render() {
      const shown = items.filter((x) => !chSel.value() || x.chapter === chSel.value());
      fill(list, ...shown.map((x) => h("li", null,
        h("div", { class: "date" }, x.date),
        h("div", { class: "event", html: md(x.event) }),
        x.chapter && ctx.chTitle[x.chapter] && !chSel.value() ? h("div", { class: "ch" }, ctx.chTitle[x.chapter]) : null)));
    }
    render();
    return null;
  }

  // ---------------------------------------------------------------- összefoglaló
  function modeSummary(ctx) {
    const meta = ctx.content.meta || {};
    const summary = (ctx.content.summary || []).slice().sort((a, b) => (ctx.chOrder[a.chapter] ?? 999) - (ctx.chOrder[b.chapter] ?? 999));
    const traps = ctx.content.traps || [];
    const jump = (id) => {
      const el = document.getElementById(id);
      if (el) { el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); el.focus({ preventScroll: true }); }
    };
    const toc = [...summary.map((s) => ({ id: "sum-" + s.chapter, label: ctx.chTitle[s.chapter] || s.chapter })),
      ...(traps.length ? [{ id: "sum-traps", label: "Csapdák" }] : [])];

    add(ctx.panel, 
      meta.exam_info ? h("div", { class: "exam-info" }, h("h2", null, "A vizsgáról"), h("div", { html: md(meta.exam_info) })) : null,
      toc.length > 1 ? h("nav", { "aria-label": "Tartalom" }, h("ol", { class: "toc" },
        toc.map((t) => h("li", null, h("button", { type: "button", onclick: () => jump(t.id) }, t.label))))) : null,
      summary.map((s) => h("section", { class: "summary-ch", id: "sum-" + s.chapter, tabindex: "-1" },
        h("h2", null, ctx.chTitle[s.chapter] || s.chapter),
        (s.blocks || []).map((b) => {
          if (b.type === "heading") return h("h3", { html: md(b.text) });
          if (b.type === "list") return h("ul", null, (b.items || []).map((it) => h("li", { html: md(it) })));
          return h("p", { html: md(b.text) });
        }))),
      traps.length ? h("section", { class: "traps", id: "sum-traps", tabindex: "-1" },
        h("h2", null, "Csapdák"),
        h("p", { class: "muted" }, "Tipikus hibák, amelyekbe könnyű belefutni."),
        h("dl", null, traps.map((t) => [h("dt", { html: md(t.title) }), h("dd", { html: md(t.explanation) })]))) : null,
      meta.source_note ? h("p", { class: "muted mt" }, h("small", { html: md("Forrás: " + meta.source_note) })) : null);
    return null;
  }

  // ================================================================ feltöltés
  async function viewUpload(_args, alive) {
    const max = state.config.max_upload_bytes;
    const fileInput = h("input", { type: "file", accept: ".json,application/json,text/plain", id: "pack-file" });
    const ta = h("textarea", { class: "code", spellcheck: "false", placeholder: '{ "schema": "tanulo-csomag/1", … }', id: "pack-text", rows: 8 });
    const checkBtn = h("button", { type: "button", class: "btn-primary" }, "Ellenőrzés");
    const out = h("div", { "aria-live": "polite" });

    fill($app, 
      h("nav", { class: "crumbs" }, h("a", { href: "#/" }, "Anyagok")),
      h("h1", null, "Csomag feltöltése"),
      h("p", { class: "muted" }, "Válaszd ki a tartalomcsomag JSON-fájlját, vagy illeszd be a szövegét. Ha az azonosító (meta.id) már létezik, új verzió lesz belőle, és a haladás megmarad."),
      h("div", { class: "panel" },
        h("div", { class: "field" }, h("label", { for: "pack-file" }, "Fájl"), fileInput),
        h("div", { class: "field" }, h("label", { for: "pack-text" }, "vagy szöveg"), ta),
        checkBtn),
      out);

    fileInput.addEventListener("change", async () => {
      const f = fileInput.files[0];
      if (!f) return;
      if (f.size > max) {
        fill(out, h("div", { class: "alert alert-bad" }, `A fájl túl nagy: ${(f.size / 1048576).toFixed(2)} MB (legfeljebb ${Math.round(max / 1048576)} MB).`));
        return;
      }
      ta.value = await f.text();
      check();
    });
    checkBtn.addEventListener("click", () => check());

    async function check() {
      const text = ta.value;
      if (!text.trim()) { fill(out, h("div", { class: "alert alert-warn" }, "Válassz fájlt, vagy illeszd be a csomag szövegét.")); return; }
      checkBtn.disabled = true;
      fill(out, h("p", { class: "loading" }, "Ellenőrzés…"));
      try {
        const res = await api("/api/packs/validate", { method: "POST", raw: text, contentType: "application/json; charset=utf-8" });
        if (!alive()) return;
        renderResult(res, text);
      } catch (err) {
        fill(out, h("div", { class: "alert alert-bad" }, ...issueNodes(err)));
      } finally { checkBtn.disabled = false; }
    }

    function issueList(items) {
      return h("ul", { class: "issues" }, items.map((e) => h("li", null, h("code", null, e.path), " ", e.message)));
    }

    function renderResult(res, text) {
      const parts = [];
      if (res.errors.length) {
        parts.push(h("div", { class: "alert alert-bad", role: "alert" },
          h("h3", null, `${res.errors.length}${res.truncated ? "+" : ""} hiba miatt nem menthető`),
          issueList(res.errors),
          res.truncated ? h("p", { class: "hint mt" }, "További hibák is lehetnek; javítsd ezeket, és ellenőrizd újra.") : null));
      }
      if (res.warnings.length) {
        parts.push(h("div", { class: "alert alert-warn" },
          h("h3", null, `${res.warnings.length} figyelmeztetés`),
          h("p", { class: "hint" }, "Ezek nem akadályozzák a mentést."),
          issueList(res.warnings)));
      }
      if (res.ok) {
        const c = res.counts;
        const counts = ["chapters", "cards", "quiz", "tasks", "timeline", "summary", "traps"].filter((k) => c[k])
          .map((k) => h("li", null, h("b", null, c[k]), " ", COUNT_LABELS[k]));
        parts.push(h("div", { class: "alert alert-ok" },
          h("h3", null, "A csomag rendben van"),
          h("ul", { class: "counts" }, counts),
          res.existing ? h("p", { class: "mt", style: { marginBottom: 0 } },
            "Ez a(z) ", h("strong", null, res.existing.title), ` anyag ${res.existing.next_version}. verziója lesz. A változatlan azonosítójú elemeken a haladás megmarad; a kimaradó elemek elrejtődnek.`)
            : h("p", { class: "mt", style: { marginBottom: 0 } }, "Új anyag lesz.")));
        parts.push(metaForm(res, text));
      }
      fill(out, ...parts);
      out.firstChild?.scrollIntoView({ block: "nearest" });
    }

    function metaForm(res, text) {
      const m = res.meta;
      const title = h("input", { type: "text", value: m.title || "", maxlength: 120 });
      const topic = h("textarea", { maxlength: 200, rows: 2 }, m.topic || "");
      const subject = h("input", { type: "text", value: m.subject || "", maxlength: 60 });
      const tags = h("input", { type: "text", value: (m.tags || []).join(", ") });
      const level = h("input", { type: "text", value: m.level || "", maxlength: 40 });
      const errBox = h("div", { class: "alert alert-bad", hidden: true, role: "alert" });
      const saveBtn = h("button", { type: "submit", class: "btn-primary" }, "Mentés");
      const form = h("form", { class: "panel", novalidate: true },
        h("h2", null, "Adatok"),
        h("p", { class: "hint" }, "A csomagból töltöttük ki; itt átírhatod."),
        errBox,
        field("Cím", title), field("Téma", topic), field("Tantárgy", subject),
        field("Címkék", tags, "vesszővel elválasztva"), field("Évfolyam vagy szint", level),
        saveBtn);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        saveBtn.disabled = true;
        errBox.hidden = true;
        try {
          const saved = await api("/api/packs", {
            method: "POST",
            body: {
              content: text,
              meta: { title: title.value, topic: topic.value, subject: subject.value, level: level.value,
                tags: tags.value.split(",").map((t) => t.trim()).filter(Boolean) },
            },
          });
          toast(saved.created ? `Mentve: ${title.value}` : `Mentve: ${title.value}, ${saved.version}. verzió`);
          location.hash = `#/anyag/${encodeURIComponent(saved.id)}`;
        } catch (err) {
          fill(errBox, ...issueNodes(err));
          errBox.hidden = false;
          errBox.scrollIntoView({ block: "nearest" });
        } finally { saveBtn.disabled = false; }
      });
      return form;
    }
  }

  // ================================================================ kezelés (szülő)
  async function viewManage(_args, alive) {
    const [profiles, archived, health] = await Promise.all([
      api("/api/profiles"),
      api("/api/packs?archived=true&sort=title"),
      api("/api/health"),
    ]);
    if (!alive()) return;
    state.profiles = profiles;

    const profList = h("ul", { class: "rowlist" }, profiles.map((p) => h("li", null,
      monoEl(p),
      h("div", { class: "grow" }, h("strong", null, p.name), h("small", null, (p.role === "parent" ? "Szülő" : "Tanuló") + (state.profile.id === p.id ? ", most ez van kiválasztva" : ""))),
      h("div", { class: "btn-row" },
        h("button", { type: "button", class: "btn-small", onclick: () => editProfile(p) }, "Szerkesztés"),
        h("button", { type: "button", class: "btn-small btn-danger", onclick: () => removeProfile(p) }, "Törlés")))));

    const archList = archived.items.length ? h("ul", { class: "rowlist" }, archived.items.map((p) => h("li", null,
      h("div", { class: "grow" }, h("a", { href: `#/anyag/${encodeURIComponent(p.id)}` }, p.title), h("small", null, p.subject)),
      h("div", { class: "btn-row" },
        h("button", { type: "button", class: "btn-small", onclick: async () => {
          try { await api(`/api/packs/${encodeURIComponent(p.id)}`, { method: "PATCH", body: { archived: false } }); toast("Visszaállítva"); route(); } catch (err) { showErr(err); }
        } }, "Visszaállítás"),
        h("button", { type: "button", class: "btn-small btn-danger", onclick: async () => { if (await deletePack(p)) route(); } }, "Végleges törlés")))))
      : h("p", { class: "muted" }, "Nincs archivált anyag.");

    const importInput = h("input", { type: "file", accept: ".json,application/json", id: "import-file" });
    importInput.addEventListener("change", async () => {
      const f = importInput.files[0];
      if (!f) return;
      if (await doImport(f)) {
        const ps = await api("/api/profiles").catch(() => []);
        const me = ps.find((p) => p.id === state.profile?.id);
        setProfile(me || null);
        location.hash = me ? "#/" : "#/profilok";
      }
      importInput.value = "";
    });

    fill($app, 
      h("nav", { class: "crumbs" }, h("a", { href: "#/" }, "Anyagok")),
      h("h1", null, "Kezelés"),
      h("section", { class: "panel" },
        h("h2", null, "Profilok"),
        profList,
        h("div", { class: "btn-row mt" }, h("button", { type: "button", onclick: () => newProfileDialog().then((p) => p && route()) }, "Új profil"))),
      h("section", { class: "panel" },
        h("h2", null, "Archivált anyagok"),
        h("p", { class: "hint" }, "Az archivált anyag nem látszik a listában, de a haladással együtt megmarad."),
        archList),
      h("section", { class: "panel" },
        h("h2", null, "Mentés és visszatöltés"),
        h("p", { class: "hint" }, "Az export egyetlen JSON-fájl: minden profil, anyag (összes verzióval) és haladás. A szerver ezen felül naponta automatikus adatbázismentést is készít."),
        h("div", { class: "btn-row" }, h("button", { type: "button", onclick: doExport }, "Exportálás")),
        h("div", { class: "field mt" },
          h("label", { for: "import-file" }, "Visszatöltés exportfájlból", h("span", { class: "hint" }, " – minden jelenlegi adatot lecserél")),
          importInput)),
      h("p", { class: "muted" }, h("small", null, `Verzió: ${health.version}`)));

    async function editProfile(p) {
      const name = h("input", { type: "text", value: p.name, maxlength: 40 });
      const role = h("select", null, h("option", { value: "child" }, "Tanuló"), h("option", { value: "parent" }, "Szülő"));
      role.value = p.role;
      const res = await formDialog({
        title: "Profil szerkesztése",
        fields: [field("Név", name), field("Szerep", role), colorSwatches("ep-color", p.color)],
        onSubmit: async (form) => api(`/api/profiles/${p.id}`, {
          method: "PATCH",
          body: { name: name.value.trim(), role: role.value, color: form.querySelector("input[name=ep-color]:checked")?.value },
        }),
      });
      if (res) {
        if (res.id === state.profile.id) setProfile(res);
        toast("Mentve");
        if (res.id === state.profile.id && res.role !== "parent") { location.hash = "#/"; return; }
        route();
      }
    }

    async function removeProfile(p) {
      const ok = await confirmDialog({
        title: "Profil törlése",
        text: `**${p.name}** profilja és a teljes haladása törlődik.`,
        ok: "Törlés", danger: true, check: "Értem, hogy a haladás is elvész",
      });
      if (!ok) return;
      try {
        await api(`/api/profiles/${p.id}?confirm=${p.id}`, { method: "DELETE" });
        toast("Törölve");
        if (p.id === state.profile.id) { setProfile(null); location.hash = "#/profilok"; return; }
        route();
      } catch (err) { showErr(err); }
    }
  }

  function downloadJson(obj, name) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2) + "\n"], { type: "application/json" }));
    const a = h("a", { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  async function doExport() {
    try {
      const res = await fetch("/api/export", { headers: { "X-Profile-Id": String(state.profile.id) } });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Az exportálás nem sikerült.");
      }
      const blob = await res.blob();
      const name = (res.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "tanulo-export.json";
      const url = URL.createObjectURL(blob);
      const a = h("a", { href: url, download: name });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast("Exportálva: " + name);
    } catch (err) { showErr(err); }
  }

  async function doImport(file) {
    const ok = await confirmDialog({
      title: "Visszatöltés",
      text: `A(z) **${file.name}** tartalma **lecserél minden jelenlegi adatot**: profilokat, anyagokat és haladást.`,
      ok: "Visszatöltés", danger: true, check: "Értem, hogy a jelenlegi adatok elvesznek",
    });
    if (!ok) return false;
    try {
      const text = await file.text();
      const res = await api("/api/import?confirm=replace", { method: "POST", raw: text, contentType: "application/json; charset=utf-8" });
      const c = res.imported;
      toast(`Visszatöltve: ${c.profiles} profil, ${c.packs} anyag.`);
      return true;
    } catch (err) { showErr(err); return false; }
  }

  // ================================================================ indulás
  async function boot() {
    renderTopbar();
    try {
      const [cfg, profiles] = await Promise.all([api("/api/config"), api("/api/profiles")]);
      state.config = cfg;
      state.profiles = profiles;
      const savedId = Number(LS.get("profileId"));
      state.profile = profiles.find((p) => p.id === savedId) || null;
      if (!state.profile) LS.set("profileId", null);
    } catch (err) {
      fill($app, h("div", { class: "empty" }, h("p", null, err.message), h("button", { type: "button", onclick: boot }, "Újra")));
      return;
    }
    renderTopbar();
    route();
  }
  boot();
})();
