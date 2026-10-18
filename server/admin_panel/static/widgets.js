// Shared UI pieces for the admin windows.

import { REGION_NAME, esc, gameIcon, icon, store, userName } from "./core.js";

// ------------------------------------------------------------ game constants
export const APT_KEYS = ["turf", "dirt", "short", "mile", "middle", "long", "front", "pace", "late", "end"];
export const APT_LABELS = ["Turf", "Dirt", "Sprint", "Mile", "Medium", "Long", "Front", "Pace", "Late", "End"];
export const APT_FIELDS = ["proper_ground_turf", "proper_ground_dirt", "proper_distance_short", "proper_distance_mile",
  "proper_distance_middle", "proper_distance_long", "proper_running_style_nige", "proper_running_style_senko",
  "proper_running_style_sashi", "proper_running_style_oikomi"];
export const GRADE = ["", "G", "F", "E", "D", "C", "B", "A", "S"];
export const STYLES = { 1: "Front", 2: "Pace", 3: "Late", 4: "End" };
export const MOODS = { 1: "Awful", 2: "Bad", 3: "Normal", 4: "Good", 5: "Great" };
export const STATS = [["speed", "Speed"], ["stamina", "Stamina"], ["power", "Power"], ["guts", "Guts"], ["wiz", "Wit"]];
export const SUPPORT_TYPES = [["speed", "Speed"], ["stamina", "Stamina"], ["power", "Power"], ["guts", "Guts"], ["wiz", "Wit"],
  ["friend", "Friend"], ["group", "Group"]];
export const RARITY = { 1: "R", 2: "SR", 3: "SSR" };

export const aptBadge = (v) => `<span class="apt g${v || 1}">${GRADE[v || 1] || "?"}</span>`;
export const aptRow = (apt) => `<span class="apts">${apt.map((v, i) => `<span title="${APT_LABELS[i]}">${aptBadge(v)}</span>`).join("")}</span>`;
export const gradeOptions = (sel, withAny = false) => (withAny ? `<option value="">Any</option>` : "")
  + [8, 7, 6, 5, 4, 3, 2, 1].map((v) => `<option value="${v}" ${+sel === v ? "selected" : ""}>${GRADE[v]}${withAny ? "+" : ""}</option>`).join("");
export const stars = (n, max = 5) => `<span class="stars">${"★".repeat(Math.max(0, n || 0))}<span class="off">${"★".repeat(Math.max(0, max - (n || 0)))}</span></span>`;
export const lbDiamonds = (lb) => `<span class="lb">${[0, 1, 2, 3].map((i) => `<i class="${i < lb ? "on" : ""}"></i>`).join("")}</span>`;
export const opts = (pairs, sel) => pairs.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(sel) ? "selected" : ""}>${esc(t)}</option>`).join("");

// ------------------------------------------------------------ target picker
// The account <select> in a window's title bar. It follows (and sets) the
// global target, so every window always edits the same account.
export function targetPicker(win) {
  const sel = document.createElement("select");
  sel.className = "compact";
  sel.title = "Account to edit";
  const fill = () => {
    const list = store.users[store.region]?.users || [];
    const cur = store.viewer;
    const known = list.some((u) => u.id === cur);
    sel.innerHTML = (known ? "" : `<option value="${esc(cur)}">${esc(cur || "…")}</option>`)
      + list.map((u) => `<option value="${esc(u.id)}">${esc(userName(u))} · ${esc(u.id)}${u.default ? " ★" : ""}</option>`).join("");
    sel.value = cur;
  };
  sel.addEventListener("change", () => store.setTarget(store.region, sel.value));
  const off = store.on((kind) => { if (kind === "users" || kind === "target") fill(); });
  fill();
  win.offs = [...(win.offs || []), off];
  return sel;
}

export const regionTag = () => `<span class="pill">${REGION_NAME[store.region]}</span>`;

// ------------------------------------------------------------ modal
export function modal(win, html, { wide = false, onClose } = {}) {
  const el = document.createElement("div");
  el.className = "modal";
  el.innerHTML = `<div class="modal-box ${wide ? "wide" : ""}">${html}</div>`;
  const close = () => { el.remove(); onClose?.(); };
  el.addEventListener("pointerdown", (e) => { if (e.target === el) close(); });
  el.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } });
  win.body.append(el);
  return { el, box: el.firstElementChild, close };
}

// A confirm / prompt in the window. Resolves the typed value (or true), or null.
export function ask(win, { title, text = "", ok = "OK", danger = false, input = null, value = "", placeholder = "" }) {
  return new Promise((resolve) => {
    let done = false;
    const m = modal(win, `<h3>${esc(title)}</h3>${text ? `<p>${text}</p>` : ""}
      ${input ? `<input type="${input}" class="ask-in" value="${esc(value)}" placeholder="${esc(placeholder)}" spellcheck="false">` : ""}
      <div class="modal-foot"><button class="btn" data-x>Cancel</button>
        <button class="btn ${danger ? "danger-fill" : "primary"}" data-ok>${esc(ok)}</button></div>`,
      { onClose: () => { if (!done) resolve(null); } });
    const inp = m.box.querySelector(".ask-in");
    const finish = (v) => { done = true; m.close(); resolve(v); };
    m.box.querySelector("[data-x]").onclick = () => m.close();
    m.box.querySelector("[data-ok]").onclick = () => finish(inp ? inp.value : true);
    inp?.addEventListener("keydown", (e) => { if (e.key === "Enter") finish(inp.value); });
    (inp || m.box.querySelector("[data-ok]")).focus();
  });
}

// ------------------------------------------------------------ search picker
// <div class="pick"> with an input and a dropdown of matches.
// search(q) -> [{...}], row(item) -> html, pick(item).
export function picker({ placeholder = "Search…", search, row, pick, width }) {
  const el = document.createElement("div");
  el.className = "pick";
  el.innerHTML = `<input type="text" placeholder="${esc(placeholder)}" spellcheck="false" ${width ? `style="width:${width}px"` : ""}><div class="pick-res"></div>`;
  const inp = el.firstElementChild, res = el.lastElementChild;
  let items = [], hi = 0;
  const draw = () => {
    res.innerHTML = items.map((it, i) => `<button type="button" class="${i === hi ? "hi" : ""}" data-i="${i}">${row(it)}</button>`).join("");
  };
  const update = () => {
    const q = inp.value.trim();
    items = q ? search(q.toLowerCase()).slice(0, 40) : [];
    hi = 0;
    draw();
  };
  inp.addEventListener("input", update);
  inp.addEventListener("focus", update);
  inp.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { hi = Math.min(items.length - 1, hi + 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { hi = Math.max(0, hi - 1); draw(); e.preventDefault(); }
    else if (e.key === "Enter" && items[hi]) { choose(items[hi]); e.preventDefault(); }
    else if (e.key === "Escape") { items = []; draw(); }
  });
  const choose = (it) => { pick(it); inp.value = ""; items = []; draw(); };
  res.addEventListener("mousedown", (e) => {
    const b = e.target.closest("[data-i]");
    if (b) { e.preventDefault(); choose(items[+b.dataset.i]); }
  });
  inp.addEventListener("blur", () => setTimeout(() => { items = []; draw(); }, 150));
  return el;
}

// Matchers over the region's catalogues.
const has = (q, ...fields) => fields.some((f) => String(f ?? "").toLowerCase().includes(q));
export const skillSearch = (skills) => (q) => skills.filter((s) => has(q, s.name, s.id));
export const skillRow = (s) => `${gameIcon("skill", s.icon, "xs")}<span class="${s.rarity >= 2 ? "r2" : ""}">${esc(s.name)}</span>
  <span class="faint">${s.rarity >= 3 ? "unique" : s.rarity === 2 ? "gold" : "white"} · ${s.id}</span>`;
export const umaSearch = (cat) => (q) => cat.umas.cards.filter((c) => has(q, c.name, c.title, c.id));
export const umaRow = (c) => `${gameIcon("card", c.id, "xs")}<span>${esc(c.name)}</span><span class="faint">${esc(c.title)} · ${c.id}</span>`;
export const supportSearch = (cat) => (q) => cat.supports.cards.filter((c) => has(q, c.name, c.title, c.id));
export const supportRow = (c) => `${gameIcon("support", c.id, "xs")}<span class="rar rar-${c.rarity}">${RARITY[c.rarity]}</span><span>${esc(c.name)}</span><span class="faint">${esc(c.title)} · ${c.id}</span>`;
export const itemSearch = (cat) => (q) => cat.items.filter((i) => has(q, i.name, i.id));
export const itemRow = (i) => `${gameIcon("item", i.id, "xs")}<span>${esc(i.name)}</span><span class="faint">${esc(i.group)} · ${i.id}</span>`;
export const factorSearch = (factors) => (q) => {
  const seen = new Set();
  return factors.filter((f) => has(q, f.name, f.id) && !seen.has(f.group) && seen.add(f.group));
};
export const factorRow = (f) => `<span class="spark kind-${f.kind}">${esc(f.name)}</span><span class="faint">${f.kind}</span>`;

// ------------------------------------------------------------ selection
// A Set of ids plus click / shift-click range selection over the shown order.
export function selection() {
  const sel = new Set();
  let anchor = null;
  return {
    set: sel,
    click(id, order, e) {
      if (e.shiftKey && anchor !== null) {
        const a = order.indexOf(anchor), b = order.indexOf(id);
        if (a >= 0 && b >= 0) {          // shift-click: select the whole range
          for (let i = Math.min(a, b); i <= Math.max(a, b); i++) sel.add(order[i]);
          return;
        }
      }
      sel.has(id) ? sel.delete(id) : sel.add(id);
      anchor = id;
    },
    all(order) { for (const id of order) sel.add(id); },
    none() { sel.clear(); anchor = null; },
    invert(order) { for (const id of order) sel.has(id) ? sel.delete(id) : sel.add(id); },
    only(id) { sel.clear(); sel.add(id); anchor = id; },
  };
}

export function selectionBar(n, shown, total) {
  return `<span><b>${shown.toLocaleString()}</b> shown of ${total.toLocaleString()}</span>
    <span>· <b>${n.toLocaleString()}</b> selected</span>
    <button class="linkish" data-sel="all">Select shown</button>
    <button class="linkish" data-sel="none">Clear</button>
    <button class="linkish" data-sel="invert">Invert</button>`;
}

// ------------------------------------------------------------ files
export function download(name, data) {
  const blob = new Blob([typeof data === "string" ? data : JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export function pickFile(accept = ".json,application/json") {
  return new Promise((resolve) => {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = accept;
    inp.onchange = () => {
      const f = inp.files[0];
      if (!f) return resolve(null);
      const r = new FileReader();
      r.onload = () => resolve({ name: f.name, text: String(r.result) });
      r.readAsText(f);
    };
    inp.click();
  });
}

export const empty = (text, extra = "") => `<div class="empty empty-pad"><div>${text}</div>${extra}</div>`;
export const noTarget = () => empty("Pick an account first.", `<button class="btn primary" data-open="users">${icon("users")} Users</button>`);
