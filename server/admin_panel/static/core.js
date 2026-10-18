// Shared state, the server API and small helpers (VivloToolkit's core.js, adapted).

export const icons = {
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  cards: '<rect x="3" y="6" width="13" height="16" rx="2"/><path d="M8 2h11a2 2 0 0 1 2 2v14"/>',
  uma: '<circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/><path d="m8 4-2-2M16 4l2-2"/>',
  medal: '<circle cx="12" cy="15" r="6"/><path d="M8.5 10.2 6 2h4l2 5 2-5h4l-2.5 8.2"/><path d="m12 12.5 1 2 2 .3-1.5 1.4.4 2-1.9-1-1.9 1 .4-2-1.5-1.4 2-.3z"/>',
  flag: '<path d="M4 22V4"/><path d="M4 4h12l-2 4 2 4H4"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/>',
  sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6 6 2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  maximize: '<rect x="5" y="5" width="14" height="14" rx="3"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
  upload: '<path d="M12 21V9"/><path d="m7 14 5-5 5 5"/><path d="M5 3h14"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m22 7-10 6L2 7"/>',
  save: '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v6h8"/><path d="M7 21v-7h10v7"/>',
  play: '<path d="M7 4v16l13-8z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  restart: '<path d="M5 5v14"/><path d="M19 5 9 12l10 7z"/>',
  map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
};
export const icon = (name) => `<svg class="i" viewBox="0 0 24 24">${icons[name] || ""}</svg>`;

// Bump to skip icon 404s browsers cached under the old one-day policy.
export const ICON_VERSION = 2;
const FALLBACK = { supportart: "support", card: "chara" };
export const gameIcon = (kind, id, cls = "") => {
  if (!id) return `<span class="gicon ${cls} missing"></span>`;
  const fb = FALLBACK[kind];
  const fbId = kind === "card" ? Math.floor(id / 100) : id;
  const onerr = fb ? `this.onerror=()=>this.classList.add('missing');this.src='/icons/${fb}/${fbId}?v=${ICON_VERSION}'` : "this.classList.add('missing')";
  const custom = ["support", "supportart"].includes(kind) && store.catalogs[store.region]?.supportById?.get(+id)?.custom;
  const src = custom ? `/custom-icons/${store.region}/${kind}/${id}?v=${ICON_VERSION}` : `/icons/${kind}/${id}?v=${ICON_VERSION}`;
  return `<img class="gicon ${cls}" src="${src}" loading="lazy" alt="" onerror="${onerr}">`;
};

export const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const fmt = (n) => (n === null || n === undefined ? "–" : typeof n === "number" ? n.toLocaleString() : String(n));
export const bytes = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n || 0} B`;
export function ago(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
export const dateTime = (ts) => ts ? new Date(ts * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "–";

// Keep scroll positions and the focused text field across a re-render.
export function keepScroll(el, fn) {
  const key = (n) => n.tagName + [...n.classList].map((c) => "." + c).join("");
  const scrolled = [...el.querySelectorAll("*")].filter((n) => n.scrollTop > 0).map((n) => [key(n), n.scrollTop]);
  const fields = () => [...el.querySelectorAll("input[type=text], input[type=search], textarea")];
  const f = document.activeElement, fi = el.contains(f) ? fields().indexOf(f) : -1;
  const caret = fi >= 0 ? [f.selectionStart, f.selectionEnd] : null;
  fn();
  for (const [k, top] of scrolled) {
    const n = [...el.querySelectorAll("*")].find((x) => key(x) === k);
    if (n) n.scrollTop = top;
  }
  const nf = fi >= 0 && fields()[fi];
  if (nf) { nf.focus(); try { nf.setSelectionRange(...caret); } catch { /* number etc. */ } }
}

export const prefs = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem("umaps." + key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem("umaps." + key, JSON.stringify(value)); } catch { /* private mode */ } },
};

// ------------------------------------------------------------ colours
const PALETTE = ["#d8b98a", "#8fb7c9", "#a99bd1", "#8fc9a4", "#e0a39a", "#c9c08f"];
export function color(id) {
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
export const REGION_NAME = { global: "Global", jp: "JP" };

// ------------------------------------------------------------ store
// The target (region + viewer) every window edits, the users of each region,
// and each region's master-data catalogue.
const saved = prefs.get("target", {});
export const store = {
  preferEnglish: prefs.get("preferEnglish", true),
  region: saved.region || "global",
  viewers: saved.viewers || {},           // region -> viewer id
  users: {},                              // region -> {default, users: [...]}
  catalogs: {},                           // region -> catalog.core
  extra: {},                              // region -> {skills, factors, programs}
  connected: true,
  errors: [],
  listeners: new Set(),
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); },
  emit(kind, detail) { for (const fn of this.listeners) { try { fn(kind, detail); } catch (e) { console.error(e); } } },
  get viewer() { return this.viewers[this.region] || this.users[this.region]?.default || ""; },
  user(id = this.viewer, region = this.region) { return this.users[region]?.users.find((u) => u.id === id); },
  setTarget(region, viewer) {
    const changed = region !== this.region || (viewer && viewer !== this.viewers[region]);
    this.region = region;
    if (viewer) this.viewers[region] = viewer;
    prefs.set("target", { region: this.region, viewers: this.viewers });
    if (changed) this.emit("target");
    if (!this.users[region]) loadUsers(region);
    if (!this.catalogs[region]) loadCatalog(region);
  },
};

export const userName = (u) => u ? (u.name || `Viewer ${u.id}`) : "–";

// ------------------------------------------------------------ api
// call(op, args) runs one worker operation for the current target.
export async function call(op, args = {}, target = {}) {
  return (await callFull(op, args, target)).result;
}

// The same, returning {result, log} (log = what admin.py / career.py printed).
export async function callFull(op, args = {}, { region = store.region, viewer = store.viewer } = {}) {
  let res;
  try {
    res = await fetch(`/api/${region}/${op}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ viewer, args: { ...args, _prefer_english: store.preferEnglish } }),
    });
  } catch (ex) {
    setConn(false);
    const err = new Error("Lost the admin panel server.");
    err.detail = String(ex);
    throw err;
  }
  setConn(true);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `HTTP ${res.status}`);
    err.detail = data.detail || `${op} -> HTTP ${res.status}`;
    throw err;
  }
  if (data.history?.length) store.emit("history", { region, viewer, ids: data.history, op });
  return { result: data.result ?? null, log: data.log || "" };
}

function setConn(ok) {
  if (store.connected === ok) return;
  store.connected = ok;
  store.emit("conn");
}

export async function loadUsers(region = store.region) {
  try {
    store.users[region] = await call("users.list", {}, { region, viewer: null });
    store.emit("users", { region });
  } catch (ex) { reportError(`Loading ${REGION_NAME[region]} users`, ex); }
  return store.users[region];
}

const catalogLoading = {};
export function refreshCatalog(region = store.region) {
  delete store.catalogs[region];
  delete catalogLoading[region];
  return loadCatalog(region);
}
export function loadCatalog(region = store.region) {
  if (store.catalogs[region]) return Promise.resolve(store.catalogs[region]);
  catalogLoading[region] ||= call("catalog.core", {}, { region, viewer: null }).then((c) => {
    store.catalogs[region] = c;
    c.supportById = new Map(c.supports.cards.map((x) => [x.id, x]));
    c.umaById = new Map(c.umas.cards.map((x) => [x.id, x]));
    c.itemById = new Map(c.items.map((x) => [x.id, x]));
    store.emit("catalog", { region });
    return c;
  }).catch((ex) => { catalogLoading[region] = null; reportError("Loading master data", ex); throw ex; });
  return catalogLoading[region];
}

// Bigger catalogues, fetched the first time a window needs them.
const extraLoading = {};
export function loadExtra(kind, region = store.region) {
  const key = `${region}:${kind}`;
  store.extra[region] ||= {};
  if (store.extra[region][kind]) return Promise.resolve(store.extra[region][kind]);
  extraLoading[key] ||= call(`catalog.${kind}`, {}, { region, viewer: null }).then((list) => {
    store.extra[region][kind] = list;
    list.byId = new Map(list.map((x) => [x.id, x]));
    return list;
  }).catch((ex) => { extraLoading[key] = null; throw ex; });
  return extraLoading[key];
}

// ------------------------------------------------------------ notifications
export function toast(text) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = text;
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), 4000);
}

export function reportError(title, ex) {
  const err = { id: `e${Date.now()}${Math.random()}`, t: Date.now() / 1000, title,
                message: ex?.message || String(ex), detail: ex?.detail || ex?.stack || "" };
  store.errors.push(err);
  if (store.errors.length > 100) store.errors.shift();
  store.emit("errors");
  const el = document.createElement("div");
  el.className = "toast error";
  el.innerHTML = `<div class="grow"><b>${esc(title)}</b><div class="toast-msg">${esc(err.message)}</div></div>
    <button class="wbtn" title="Dismiss">${icon("close")}</button>`;
  el.querySelector("button").onclick = (e) => { e.stopPropagation(); el.remove(); };
  el.onclick = () => { el.remove(); ui.open("errors", { error: err.id }); };
  document.getElementById("toasts").append(el);
}

// Run an action with a busy button and error reporting; returns the result or undefined.
export async function act(btn, title, fn, done) {
  if (btn) btn.disabled = true;
  try {
    const r = await fn();
    if (done) toast(typeof done === "function" ? done(r) : done);
    return r;
  } catch (ex) { reportError(title, ex); }
  finally { if (btn && btn.isConnected) btn.disabled = false; }
}

export const ui = { open: (_kind, _opts) => {} };
