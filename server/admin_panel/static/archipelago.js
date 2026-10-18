// Archipelago: the room to connect to, the connection, and the played
// account's progress. The page is Maple's UmamusumeX Archipelago page, on this
// panel's ops (archipelago.get / .set / .say) instead of that dashboard's API.

import { act, call, esc, fmt as num, icon, keepScroll } from "./core.js";
import { empty } from "./widgets.js";

const GL = { region: "global", viewer: "" };  // the room plays Global's last-logged-in account

const FIELDS = [
  ["archipelago_server", "Room", "host:port, e.g. archipelago.gg:38281"],
  ["archipelago_slot", "Slot name", "your player name in the seed"],
  ["archipelago_password", "Room password", "blank when the room has none"],
];

// Archipelago page sections and tracker groups start open; the ones closed are
// remembered in this browser.
export function apClosed() {
  try { return new Set(JSON.parse(localStorage.getItem("ap-closed") || "[]")); } catch (e) { return new Set(); }
}

export function setApClosed(name, closed) {
  const set = apClosed();
  if (closed) set.add(name); else set.delete(name);
  try { localStorage.setItem("ap-closed", JSON.stringify([...set])); } catch (e) { /* per-browser only */ }
}

export function apSec(title, body, extra = "") {
  const open = apClosed().has(title) ? "" : " open";
  return `<details class="ap-sec" data-ap-sec="${esc(title)}"${open}>
    <summary class="ap-sec-title">${esc(title)}${extra}</summary>${body}</details>`;
}

function apPage(settings) {
  return `
    <div id="ap-awaken"></div>
    ${apSec("Connection", `<div class="ap-panel ap-col" id="ap-status"><span class="faint">Press "Check connection".</span></div>`,
      `<span class="grow"></span><a class="btn sm" href="/logs.zip" download="umaps-archipelago-logs.zip"
        title="server.log and the connection status, for a bug report">Download logs</a>
      <button class="btn sm" type="button" data-a="check">Check connection</button>`)}
    ${apSec("Game setup", `<div class="ap-panel ap-col" id="ap-setup"><span class="faint">Checking...</span></div>`,
      `<span class="grow"></span><button class="btn sm" type="button" data-a="setup">Check files</button>`)}
    ${apSec("Room", `<div class="ap-panel">
      ${FIELDS.map(([k, label, help]) => `<div class="ed-row"><label style="flex:1">${esc(label)}<span class="faint" style="font-size:11px">${esc(help)}</span></label>
        <input class="wide" data-k="${k}" type="${k.endsWith("password") ? "password" : "text"}" value="${esc(settings[k] ?? "")}"></div>`).join("")}
      <div class="row"><span class="grow"></span><button class="btn primary sm" type="button" data-a="save">${icon("save")} Save</button></div></div>`)}
    ${apSec("Permanent buffs", `<div class="ap-panel" id="ap-permanent"></div>`)}
    ${apSec("Traps and boons", `
      <div class="faint ap-small ap-gap">Spent when a career gets to its final race (any placing). A career given up or lost before then hands them back for the next one; each kind applies once per career and a duplicate waits.</div>
      <div class="ap-grid" id="ap-effects"></div>`)}
    ${apSec("Hints", `
      <div class="ap-panel">
        <div class="row ap-gap">
          <input type="text" class="grow" id="ap-hint-item" list="ap-item-names" placeholder="Item to find, e.g. Progressive Speed Training" autocomplete="off">
          <datalist id="ap-item-names"></datalist>
          <button class="btn primary sm" type="button" data-a="hint">Ask for a hint</button>
        </div>
        <div class="faint ap-small ap-gap" id="ap-points"></div>
        <div id="ap-hints"></div>
      </div>`)}
    ${apSec("Items", `
      <div class="ap-grid">
        <div class="ap-panel"><div class="ap-sub">Sent: your checks</div><div class="ap-scroll" id="ap-sent"></div></div>
        <div class="ap-panel"><div class="ap-sub">Received</div><div class="ap-scroll" id="ap-received"></div></div>
      </div>`)}
    ${apSec("Tracker", `
      <div class="ap-legend faint ap-small">
        <span><span class="ap-dot ap-logic"></span>available now</span>
        <span><span class="ap-dot ap-hard"></span>possible, but hard for now</span>
        <span><span class="ap-dot ap-locked"></span>locked: needs an item</span>
        <span><span class="ap-dot ap-done"></span>done</span>
      </div>
      <div id="ap-tracker"></div>`)}`;
}

// A Trainee Awakening received: the game shows it only after a new login.
// Counted from the received list; the X hides it until the next one.
function awakenBox(received) {
  const n = (received || []).filter((r) => r.item === "Trainee Awakening").length;
  let seen = 0;
  try { seen = Number(localStorage.getItem("apAwakenSeen")) || 0; } catch (e) { /* storage blocked */ }
  if (!n || n <= seen) return "";
  return `<div class="ap-banner ap-awaken" data-n="${n}"><div class="grow">
      <b>Hey, you got an Awakening!</b> A trainee is now 5 stars and potential 5.
      Restart the game, or go to Menu → To Title Screen and log in again, to see it.
      <div class="faint">If all your trainees were already maxed, it waits for your next new one instead.</div></div>
    <button class="ap-awaken-x btn sm" title="Dismiss" aria-label="Dismiss">✕</button></div>`;
}

function goalBox(g) {
  if (!g) return "";
  const left = Math.max(0, g.target - g.current);
  const status = g.done ? "Goal reached!"
    : `${num(left)} ${g.kind === "rank_score" ? "points" : g.unit} to go · ${g.in_logic ? "in logic now" : "possible, but logic expects more buffs first"}`;
  return `<div class="ap-col ap-goal">
    <div class="row"><span><b>Goal</b> ${esc(g.label)}</span><span class="grow"></span>
      <span><b>${num(g.current)}</b> / ${num(g.target)} ${esc(g.unit)} · ${g.percent}%</span></div>
    <div class="ap-bar${g.done ? " ok" : ""}"><i style="width:${g.percent}%"></i></div>
    <div class="faint">${status}</div></div>`;
}

export const archipelagoWin = {
  title: "Archipelago", icon: "flag", size: [520, 460], place: [0.04, 0.04, 0.92, 0.92], key: "a",
  mount(body, win) {
    const $ = (sel) => body.querySelector(sel);
    let last = "";
    body.classList.add("flush");

    async function load() {
      let d;
      try { d = await call("archipelago.get", {}, GL); } catch (ex) { body.innerHTML = empty(esc(ex.message)); return; }
      body.innerHTML = `<div class="pane-scroll ap-page">${apPage(d.settings)}</div>`;
      last = "";
      render(d);
    }

    // quiet: the 4-second refresh (no "Checking...", no redraw when nothing changed).
    async function checkArchipelago(quiet) {
      const box = $("#ap-status");
      if (!box) return;
      if (!quiet) box.innerHTML = `<span class="faint">Checking...</span>`;
      let r;
      try {
        r = await call("archipelago.get", {}, GL);
      } catch (e) {
        if (!quiet) box.innerHTML = `<span class="faint">Could not ask the server: ${esc(e.message)}</span>`;
        return;
      }
      render(r, quiet);
    }

    function render(r, quiet) {
      const sig = JSON.stringify(r);
      if (quiet && sig === last) return;
      last = sig;
      keepScroll(body.querySelector(".pane-scroll"), () => {
        renderStatus(r);
        renderApTracker(r);
        renderApEffects(r);
        renderApReceived(r);
        renderPermanent(r);
      });
    }

    function renderStatus(r) {
      const c = r.connection || {};
      const label = { connected: "Connected", connecting: "Connecting", error: "Error", off: "Not connected" }[c.state] || c.state;
      const sv = r.save;
      const row = (k, v) => `<div class="row"><span class="faint">${esc(k)}</span><span class="grow"></span><span>${v}</span></div>`;
      $("#ap-status").innerHTML = `
        <div class="ap-state ap-${esc(c.state || "off")}">${esc(label)}${c.detail ? ` <span class="faint">${esc(c.detail)}</span>` : ""}</div>
        ${c.state === "off" && !c.detail ? `<div class="faint">No connection yet: start the game server and fill in the room and slot below.</div>` : ""}
        <div class="faint">If something in the game looks out of date (a hint level, the trainee list, ticket counts), restart the game.</div>
        ${sv ? `<div class="ap-grid ap-kv">
          ${row("Seed", esc(sv.seed || "none yet"))}
          ${row("Items received", sv.items_received)}
          ${row("Checks done", sv.checks_done)}
          ${row("Different races won", sv.different_races_won)}
          ${row("Next career", sv.next_career.length ? esc(sv.next_career.join(", ")) : "nothing pending")}
        </div>
        ${goalBox(r.goal)}
        ${sv.recent_checks.length ? `<div class="faint ap-small"><b>Newest checks:</b> ${sv.recent_checks.map(esc).join(", ")}</div>` : ""}` : ""}`;
      const awaken = $("#ap-awaken");
      awaken.innerHTML = awakenBox(r.received);
      const x = awaken.querySelector(".ap-awaken-x");
      if (x) x.onclick = () => {
        try { localStorage.setItem("apAwakenSeen", x.closest(".ap-awaken").dataset.n); } catch (e) { /* storage blocked */ }
        awaken.innerHTML = "";
      };
    }

    function renderPermanent(r) {
      const perm = r.permanent || [];
      $("#ap-permanent").innerHTML = perm.length
        ? `<table class="ap-fx"><thead><tr><th>Item</th><th>Each</th><th>In total</th></tr></thead><tbody>${perm.map((b) => `<tr>
            <td><b>${esc(b.name)}</b>${b.count > 1 ? ` <span class="ap-count">x${b.count}</span>` : ""}</td>
            <td class="faint">${esc(b.each)}</td><td>${esc(b.effect)}</td></tr>`).join("")}</tbody></table>`
        : `<span class="faint">No permanent buffs yet.</span>`;
    }

    function renderApReceived(r) {
      const room = r.room || {};
      const pts = room.hint_points;
      $("#ap-points").innerHTML = (pts == null ? "" : `Hint points: <b>${esc(pts)}</b>${room.hint_cost ? ` · a hint costs ${esc(room.hint_cost)}` : ""}`)
        + (room.last_reply ? `<div class="faint">${esc(room.last_reply)}</div>` : "");
      const dl = $("#ap-item-names");
      if (dl && !dl.childElementCount) dl.innerHTML = (r.item_names || []).map((n) => `<option value="${esc(n)}">`).join("");
      // AP item flags: 1 progression, 2 useful, 4 trap.
      const kind = (f) => (f & 4 ? `<span class="ap-tag ap-trap">trap</span>` : f & 1 ? `<span class="ap-tag ap-prog">progression</span>`
        : f & 2 ? `<span class="ap-tag ap-boon">useful</span>` : "");
      const got = r.received || [];
      $("#ap-received").innerHTML = got.length
        ? `<ul class="ap-items">${got.map((g) => `<li>${kind(g.flags || 0)}<b>${esc(g.item)}</b>
            ${g.info ? `<div class="ap-info">${esc(g.info)}</div>` : ""}
            <div class="faint">from ${esc(g.from || "the server")}${g.where && !/^#-?\d+$/.test(g.where) ? ` · ${esc(g.where)}` : ""}</div></li>`).join("")}</ul>`
        : `<span class="faint">Nothing received yet.</span>`;
      const sent = r.sent || [];
      $("#ap-sent").innerHTML = sent.length
        ? `<ul class="ap-items">${sent.map((g) => `<li>${kind(g.flags || 0)}<b>${esc(g.item)}</b>${g.to ? ` <span class="faint">for ${esc(g.to)}</span>` : ""}
            ${g.info ? `<div class="ap-info">${esc(g.info)}</div>` : ""}
            <div class="faint">${esc(g.where)}</div></li>`).join("")}</ul>`
        : `<span class="faint">No checks done yet.</span>`;
    }

    // Traps and boons: what this career carries, then the queue grouped by name
    // ("x2 · 1 next career, 1 waits").
    function renderApEffects(r) {
      const box = $("#ap-effects");
      if (!box) return;
      const fx = r.effects || { career: null, next: [] };
      const column = (trap) => {
        const now = (fx.career?.effects || []).filter((e) => e.trap === trap);
        const nowHtml = !fx.career
          ? `<span class="faint">No career running.</span>`
          : now.length
            ? `<table class="ap-fx"><tbody>${now.map((e) => `<tr class="${e.left === "over" ? "ap-over" : ""}">
                <td>${esc(e.name)}</td><td>${esc(e.effect)}</td><td class="faint">${esc(e.left)}</td></tr>`).join("")}</tbody></table>`
            : `<span class="faint">None this career.</span>`;
        const queued = new Map();
        for (const n of fx.next.filter((n) => n.trap === trap)) {
          const q = queued.get(n.name) || { name: n.name, info: n.info, next: 0, later: 0 };
          q[n.later ? "later" : "next"]++;
          queued.set(n.name, q);
        }
        const queuedHtml = queued.size
          ? `<ul class="ap-items">${[...queued.values()].map((q) => {
              const total = q.next + q.later;
              const when = [q.next ? `${q.next} next career` : "", q.later ? `${q.later} wait${q.later > 1 ? "" : "s"} for later ones` : ""].filter(Boolean).join(", ");
              return `<li><b>${esc(q.name)}</b>${total > 1 ? ` <span class="ap-count">x${total}</span>` : ""} <span class="faint">(${esc(when)})</span>
                ${q.info ? `<div class="ap-info">${esc(q.info)}</div>` : ""}</li>`;
            }).join("")}</ul>`
          : `<span class="faint">Nothing queued.</span>`;
        return `<div class="ap-panel">
          <div class="ap-sub"><span class="ap-tag ${trap ? "ap-trap" : "ap-boon"}">${trap ? "Traps" : "Boons"}</span></div>
          <div class="ap-sub">This career${fx.career ? ` · turn ${fx.career.turn}` : ""}</div>${nowHtml}
          <div class="ap-sub">Queued</div>${queuedHtml}</div>`;
      };
      box.innerHTML = column(true) + column(false);
    }

    // Tracker: the seed's checks by group (done / in logic / not yet), and the
    // room's hints that involve this slot.
    function renderApTracker(r) {
      const hints = r.hints || [];
      const todo = hints.filter((h) => h.mine_to_find && !h.found);
      const mine = hints.filter((h) => h.for_me && !h.mine_to_find && !h.found);
      const hintRow = (h, text) => `<li class="${h.found ? "done" : ""}">${text}</li>`;
      $("#ap-hints").innerHTML = hints.length
        ? `${todo.length ? `<div class="ap-sub">To do in your game</div><ul class="ap-list">${todo.map((h) => hintRow(h,
            `<b>${esc(h.location)}</b> has <b>${esc(h.item)}</b> for ${esc(h.receiver)}`)).join("")}</ul>` : ""}
          ${mine.length ? `<div class="ap-sub">Your items in other worlds</div><ul class="ap-list">${mine.map((h) => hintRow(h,
            `<b>${esc(h.item)}</b> is at ${esc(h.finder)}'s <b>${esc(h.location)}</b>`)).join("")}</ul>` : ""}
          ${!todo.length && !mine.length ? `<span class="faint">Every hinted check is done.</span>` : ""}`
        : `<span class="faint">No hints yet. Ask for one above.</span>`;
      const groups = r.tracker || [];
      if (!groups.length) {
        $("#ap-tracker").innerHTML = `<span class="faint">The tracker fills in once the server has connected to the room.</span>`;
        return;
      }
      const mark = (c) => (c.done ? "ap-done" : c.in_logic ? "ap-logic" : c.locked ? "ap-locked" : "ap-hard");
      const title = {
        "ap-done": "done",
        "ap-logic": "in logic: you can get it now",
        "ap-hard": "possible now, but logic expects stronger careers first (more buffs)",
        "ap-locked": "locked: needs an item first (its scenario or trainee)",
      };
      const closed = apClosed();
      $("#ap-tracker").innerHTML = groups.map((g) => {
        const n = g.checks.filter((c) => c.done).length;
        const open = g.checks.filter((c) => !c.done && c.in_logic).length;
        return `<details class="ap-group"${closed.has(`tracker:${g.group}`) ? "" : " open"} data-group="${esc(g.group)}">
          <summary><span>${esc(g.group)}</span><span class="faint">${n}/${g.checks.length}${open ? ` · ${open} available` : ""}</span></summary>
          <ul class="ap-checks">${g.checks.map((c) => `<li class="${mark(c)}" title="${title[mark(c)]}">${esc(c.name)}</li>`).join("")}</ul>
        </details>`;
      }).join("");
    }

    // Game setup: the Hachimi plugins, config.json and master.mdb, with a Fix
    // that installs this release's plugin and lists both in config.json.
    async function checkSetup(btn, fix) {
      const r = await act(btn, fix ? "Fixing the game setup" : "Checking the game setup",
        () => call(fix ? "archipelago.setup_fix" : "archipelago.setup", {}, GL), fix ? "Game setup fixed: restart the game" : null);
      const box = $("#ap-setup");
      if (!r || !box) return;
      box.innerHTML = `<ul class="ap-list">${r.rows.map((x) => `<li><span class="ap-dot ${x.ok ? "ap-logic" : "ap-locked"}"></span>
          <b>${esc(x.name)}</b> <span class="faint">${esc(x.detail)}</span></li>`).join("")}</ul>
        ${r.fixable ? `<div class="row"><span class="faint">Close the game first.</span><span class="grow"></span>
          <button class="btn primary sm" type="button" data-a="setup-fix">Fix</button></div>` : ""}`;
    }

    async function askHint(btn) {
      const item = $("#ap-hint-item").value.trim();
      if (!item) return;
      const r = await act(btn, "Asking for a hint", () => call("archipelago.say", { text: `!hint ${item}` }, GL));
      if (!r) return;
      $("#ap-hint-item").value = "";
      setTimeout(() => checkArchipelago(true), 1500);  // the room answers in a moment
    }

    const values = () => Object.fromEntries([...body.querySelectorAll("[data-k]")].map((i) => [i.dataset.k, i.value]));
    body.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-a]");
      if (!b) return;
      if (b.dataset.a === "check") return checkArchipelago();
      if (b.dataset.a === "setup") return checkSetup(b);
      if (b.dataset.a === "setup-fix") return checkSetup(b, true);
      if (b.dataset.a === "hint") return askHint(b);
      if (b.dataset.a === "save") {
        const r = await act(b, "Saving Archipelago settings", () => call("archipelago.set", { values: values() }, GL), "Archipelago settings saved");
        if (r) render(r);
      }
    });
    body.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.id === "ap-hint-item") askHint(body.querySelector('[data-a="hint"]'));
    });
    // Remember which sections and tracker groups are folded.
    body.addEventListener("toggle", (e) => {
      const d = e.target;
      const name = d.dataset?.apSec || (d.dataset?.group ? `tracker:${d.dataset.group}` : null);
      if (name) setApClosed(name, !d.open);
    }, true);

    win.refresh = load;
    body.innerHTML = empty("Loading…");
    load().then(() => checkSetup());
    const timer = setInterval(() => checkArchipelago(true), 4000);
    return () => clearInterval(timer);
  },
};
