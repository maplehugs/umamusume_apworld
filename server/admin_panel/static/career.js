// Career: the account's in-progress career. Turn moves, races, events and
// park / resume run career.py's / admin.py's own commands (so goals, class,
// the event ledger and the training screen stay consistent); property edits
// are followed by the same reconcile.

import { act, call, callFull, esc, gameIcon, icon, keepScroll, loadCatalog, loadExtra, store, toast, ui } from "./core.js";
import { APT_FIELDS, APT_LABELS, MOODS, STATS, STYLES, ask, empty, gradeOptions, opts, picker, skillRow, skillSearch, targetPicker }
  from "./widgets.js";

export const careerWin = {
  title: "Career", icon: "flag", size: [760, 540], place: [0.06, 0.02, 0.92, 0.96], key: "6",
  tools(win) { return [targetPicker(win)]; },
  mount(body, win) {
    let s = null, cat = null, skills = null, programs = null, lastLog = "", edits = {};
    win.state.turnOpts ??= { fill_races: true, with_rewards: false, rank: 1, keep_races: false, keep_events: false, reset_fired: false, mark_past: true };
    const to = win.state.turnOpts;

    async function load() {
      try {
        [cat, skills, programs] = await Promise.all([loadCatalog(), loadExtra("skills"), loadExtra("programs")]);
        s = await call("career.state");
      } catch (ex) { body.innerHTML = empty(esc(ex.message)); return; }
      edits = {};
      render();
    }

    async function cmd(name, opts = {}, btn, okText) {
      const r = await act(btn, `Career: ${name}`, () => callFull("career.cmd", { cmd: name, opts }));
      if (r) { lastLog = r.log.trim(); if (okText) toast(okText); load(); }
    }
    async function patch(fields, btn, extra = {}) {
      const r = await act(btn, "Career edit", () => call("career.patch", { fields, ...extra }), "Career updated");
      if (r) { lastLog = (r.notes || []).join("\n"); load(); }
    }

    const card = (title, inner, cls = "") => `<div class="c-card ${cls}"><div class="section">${title}</div>${inner}</div>`;
    const parkedHtml = () => s.parked.length ? `<div class="list-scroll">${s.parked.map((p) => `<div class="row">
        ${gameIcon("card", p.card_id, "sm")}<div class="grow"><b>${esc(p.name)}</b><div class="faint">${esc(p.card)} · turn ${p.turn}</div></div>
        <button class="btn sm" data-resume="${esc(p.name)}" ${s.active ? "disabled title='Park the active career first'" : ""}>Resume</button>
        <button class="btn icon-btn danger" data-dropslot="${esc(p.name)}" title="Delete slot">${icon("trash")}</button></div>`).join("")}</div>`
      : `<div class="faint">No parked careers.</div>`;

    function render() {
      if (!s) return;
      if (!s.active) {
        body.innerHTML = `<div class="c-grid">${empty("No career in progress on this account.", "<div class='faint'>Start one in the game, or resume a parked one.</div>")}
          ${card("Parked careers", parkedHtml())}${lastLog ? `<pre class="log-out">${esc(lastLog)}</pre>` : ""}</div>`;
        return;
      }
      const ci = s.chara_info;
      const skillByGroup = new Map();
      for (const x of skills) skillByGroup.set(`${x.group}:${x.rarity}`, skillByGroup.get(`${x.group}:${x.rarity}`) || x);
      const condName = new Map(cat.misc.conditions.map((c) => [c.id, c.name]));
      const capKey = (k) => (k === "wiz" ? "max_wiz" : `max_${k}`);
      const nextGoal = s.goals.find((g) => !g.cleared);

      keepScroll(body, () => {
        body.innerHTML = `<div class="c-grid">
        <div class="c-status">${gameIcon("card", ci.card_id)}<div class="grow"><b>${esc(s.card)}</b>
            <div class="faint">${esc(s.scenario_name)} · ${esc(s.turn_label)} · <span class="${ci.state === 2 ? "neg" : ""}">${esc(s.state_name)}</span>
            · goals ${s.goals_cleared}/${s.goals.length} · ${s.camp ? "summer camp · " : ""}playing_state ${ci.playing_state}</div></div>
          <div class="row wrap"><button class="btn sm" data-c="reconcile" title="Recompute class, goals and the training screen">${icon("refresh")} Reconcile</button>
            <button class="btn sm" data-c="park">Park…</button>
            <button class="btn sm" data-c="idle_complete" title="Max everything and mark the run complete (finish it in the game)">${icon("bolt")} Complete</button>
            <button class="btn danger sm" data-c="abandon">${icon("trash")} Abandon</button></div></div>
        ${lastLog ? `<pre class="log-out">${esc(lastLog)}</pre>` : ""}
        <div class="faint">The client caches its career: after a change here, reload it in the game (title screen → Continue) before acting.</div>
        <div class="cgrid2">

        ${card("Turn", `<div class="ed-row"><label>Turn<input type="number" class="num" data-turn min="1" max="${s.end_turn}" value="${ci.turn}"></label>
            <input type="range" class="single" data-turnr min="1" max="${s.end_turn}" value="${ci.turn}" style="flex:1;--p:${(ci.turn - 1) / (s.end_turn - 1) * 100}%"></div>
          <div class="checks">
            <label class="check"><input type="checkbox" data-to="fill_races" ${to.fill_races ? "checked" : ""}> count earlier goal races as run</label>
            <label class="check"><input type="checkbox" data-to="with_rewards" ${to.with_rewards ? "checked" : ""}> …and pay their rewards</label>
            <label class="check">placing <input type="number" class="num xs" data-to="rank" value="${to.rank}" min="1" max="18"></label>
            <label class="check"><input type="checkbox" data-to="mark_past" ${to.mark_past ? "checked" : ""}> mark skipped story beats fired</label>
            <label class="check"><input type="checkbox" data-to="keep_races" ${to.keep_races ? "checked" : ""}> rewinding: keep later races</label>
            <label class="check"><input type="checkbox" data-to="keep_events" ${to.keep_events ? "checked" : ""}> keep queued events</label>
            <label class="check"><input type="checkbox" data-to="reset_fired" ${to.reset_fired ? "checked" : ""}> also wipe non-turn fired sets</label></div>
          <div class="row"><button class="btn primary sm" data-c="set_turn">Set turn</button>
            <span class="faint">Next mandatory races: ${s.forced_turns.slice(0, 6).join(", ") || "none"}</span></div>`)}

        ${card("Stats", `<div class="stat-edit">${STATS.map(([k, t]) => `<label>${t}<input type="number" class="num" data-f="${k}" value="${ci[k]}"></label>`).join("")}</div>
          <div class="stat-edit">${STATS.map(([k]) => `<label class="faint">cap<input type="number" class="num" data-f="${capKey(k)}" value="${ci[capKey(k)]}"></label>`).join("")}</div>
          <div class="ed-row"><label>Skill points<input type="number" class="num wide" data-f="skill_point" value="${ci.skill_point}"></label>
            <label>Fans<input type="number" class="num wide" data-f="fans" value="${ci.fans}"></label>
            <label>Energy<input type="number" class="num xs" data-f="vital" value="${ci.vital}"></label>
            <label>max<input type="number" class="num xs" data-f="max_vital" value="${ci.max_vital}"></label>
            <label>Class<input type="number" class="num xs" data-f="chara_grade" value="${ci.chara_grade}"></label></div>
          <div class="ed-row"><label>Mood<span class="seg mood-seg">${Object.entries(MOODS).map(([v, t]) => `<button data-mood="${v}" class="${+v === ci.motivation ? "on" : ""}">${t}</button>`).join("")}</span></label>
            <label>Race style<span class="seg mood-seg">${Object.entries(STYLES).map(([v, t]) => `<button data-style="${v}" class="${+v === ci.race_running_style ? "on" : ""}">${t}</button>`).join("")}</span></label></div>
          <div class="row"><button class="btn primary sm" data-save="stats">${icon("save")} Save stats</button>
            <button class="btn sm" data-quick="max">Max all</button><label class="check"><input type="checkbox" data-regrade> recompute class</label></div>`)}

        ${card("Aptitudes", `<div class="apt-grid">${APT_FIELDS.map((k, i) => `<label>${APT_LABELS[i]}<select data-f="${k}">${gradeOptions(ci[k])}</select></label>`).join("")}</div>
          <div class="row"><button class="btn primary sm" data-save="apt">${icon("save")} Save aptitudes</button><button class="btn sm" data-quick="apt">All S</button></div>`)}

        ${card(`Skills · ${(ci.skill_array || []).length}`, `<div class="skill-chips">${(ci.skill_array || []).map((x, i) => {
            const sk = skills.byId.get(x.skill_id);
            return `<span class="skill-chip ${sk?.rarity >= 2 ? "r2" : ""}">${esc(sk?.name || x.skill_id)}
              <input type="number" class="num xs" data-sklv="${i}" value="${x.level}" style="width:44px;padding:1px 4px">
              <button class="wbtn" data-skrm="${i}">${icon("close")}</button></span>`;
          }).join("")}<span data-skpick></span></div>
          <div class="section" style="margin-top:6px">Hints · ${(ci.skill_tips_array || []).length}</div>
          <div class="skill-chips">${(ci.skill_tips_array || []).map((h, i) => {
            const sk = skillByGroup.get(`${h.group_id}:${h.rarity}`);
            return `<span class="skill-chip ${h.rarity >= 2 ? "r2" : ""}">${esc(sk?.name || `group ${h.group_id}`)}
              <input type="number" class="num xs" data-hlv="${i}" value="${h.level}" min="1" max="5" style="width:44px;padding:1px 4px" title="Hint level">
              <button class="wbtn" data-hrm="${i}">${icon("close")}</button></span>`;
          }).join("")}<span data-hpick></span></div>
          <div class="row"><button class="btn primary sm" data-save="skills">${icon("save")} Save skills &amp; hints</button></div>`)}

        ${card("Conditions", `<div class="skill-chips">${(ci.chara_effect_id_array || []).map((id, i) =>
            `<span class="skill-chip">${esc(condName.get(id) || `#${id}`)}<button class="wbtn" data-cdrm="${i}">${icon("close")}</button></span>`).join("") || `<span class="faint">none</span>`}</div>
          <div class="row"><select class="sm" data-cdadd>${opts([["", "Add a condition…"], ...cat.misc.conditions.map((c) => [c.id, `${c.name} · ${c.id}`])], "")}</select>
            <button class="btn primary sm" data-save="conditions">${icon("save")} Save</button></div>`)}

        ${card("Bonds", `<div class="list-scroll">${s.bonds.map((b, i) => `<div class="bond-row"><span class="ellipsis">${b.support_card_id ? gameIcon("support", b.support_card_id, "xs") : ""} ${esc(b.name)}</span>
            <input type="range" class="single" data-bondr="${i}" min="0" max="100" value="${b.evaluation}" style="--p:${b.evaluation}%">
            <input type="number" class="num xs" data-bond="${i}" min="0" max="100" value="${b.evaluation}"></div>`).join("")}</div>
          <div class="row"><button class="btn primary sm" data-save="bonds">${icon("save")} Save bonds</button><button class="btn sm" data-quick="bonds">All 100</button></div>`)}

        ${card(`Goals · ${s.goals_cleared}/${s.goals.length}`, `<div class="list-scroll">${s.goals.map((g) => `<div class="goal ${g.cleared ? "done" : ""} ${g === nextGoal ? "next" : ""}">
            <span class="faint">T${g.turn}</span><span>${esc(g.what)}</span><span>${g.cleared ? `<span class="ok-t">${icon("check")}</span>` : g.due ? `<span class="warn-t">due</span>` : ""}</span></div>`).join("") || `<div class="faint">No route goals.</div>`}</div>`)}

        ${card(`Race history · ${s.races.length}`, `<div class="list-scroll">${s.races.map((r) => `<div class="race-row"><span class="faint">T${r.turn}</span>
            <span class="ellipsis">${esc(r.name)}</span><span>${r.result_rank === 1 ? `<span class="badge is-win sm">1st</span>` : `#${r.result_rank}`}</span>
            <button class="wbtn" data-racedel="${r.turn}" title="Remove (refund fans)">${icon("close")}</button></div>`).join("") || `<div class="faint">No races yet.</div>`}</div>
          <div class="ed-row"><span data-progpick></span><label>Turn<input type="number" class="num xs" data-rt value="${ci.turn}"></label>
            <label>Place<input type="number" class="num xs" data-rr value="1" min="1"></label>
            <label class="check"><input type="checkbox" data-rw> rewards</label></div>
          <div class="faint" data-progsel>Pick a race to add.</div>`)}

        ${card("Events", `<div class="kv"><span>Active</span><span>${s.events.active ? `${s.events.active.event_id} · story ${s.events.active.story_id} <span class="faint">${esc(s.events.active.source || "")}</span>` : "none"}</span>
            <span>In flight</span><span class="faint">${esc(s.in_flight.join(", ") || "nothing")}</span></div>
          <div class="list-scroll">${s.events.queue.map((e) => `<div class="row"><span class="grow">${e.event_id} · story ${e.story_id} <span class="faint">${esc(e.source || "")} ${esc(e.once_key || "")}</span></span>
            <button class="wbtn" data-evdrop="${e.event_id}" title="Drop">${icon("close")}</button></div>`).join("") || `<div class="faint">Queue empty.</div>`}</div>
          <div class="row wrap"><button class="btn sm" data-c="event_drop_all">Drop queue + active</button>
            <label class="check">un-fire from turn <input type="number" class="num xs" data-uft value="${ci.turn}"></label><button class="btn sm" data-c="event_undo_turn">Un-fire</button></div>
          <details><summary class="faint" style="cursor:pointer">Fired ledger · ${s.events.fired.length}</summary>
            <div class="list-scroll">${s.events.fired.map((x) => `<div class="row"><span class="grow mono ellipsis">${esc(x.key)}</span><span class="faint">${x.turn ?? ""}</span>
              <button class="wbtn" data-unfire="${esc(x.key)}" title="Un-fire">${icon("undo")}</button></div>`).join("")}</div></details>
          <details><summary class="faint" style="cursor:pointer">Queue an event</summary><div class="ed-row">
            <label>Event<input type="number" class="num" data-qe></label><label>Story<input type="number" class="num wide" data-qs></label>
            <label>Choices<input type="number" class="num xs" data-qc value="1"></label><button class="btn sm" data-c="event_queue">Queue</button></div></details>`)}

        ${card("Training screen", `<div class="cmd-chips">${s.commands.map((c) => `<span class="cmd-chip ${c.enabled ? "on" : "off"}">${c.id}${c.level ? ` · Lv${c.level}` : ""}</span>`).join("") || `<span class="faint">none</span>`}</div>
          <div class="faint">Facility levels ${esc(JSON.stringify(s.facility_levels))} · race entry restriction ${s.race_entry_restriction ?? "–"}</div>
          <div class="row"><button class="btn sm" data-c="unlock">Unlock all</button><button class="btn sm" data-c="lock">Lock all</button>
            <span class="faint">until the next turn advance rebuilds it</span></div>`)}

        ${card("Scenario & raw", `<div class="faint">Scenario state: ${s.scenario_keys.map((k) => `<button class="linkish" data-rawkey="${esc(k)}">${esc(k)}</button>`).join(", ") || "none"}
            · <button class="linkish" data-rawkey="single_mode_team">single_mode_team</button></div>
          <div class="ed-row"><input type="text" class="sm mono" data-pp placeholder="chara_info.short_cut_state" style="flex:1;min-width:180px">
            <input type="text" class="sm mono" data-pv placeholder="JSON value" style="width:140px"></div>
          <div class="row"><label class="check"><input type="checkbox" data-pc> create</label><label class="check"><input type="checkbox" data-pf> whole viewer state</label>
            <button class="btn sm" data-c="data_patch">Set path</button></div>`)}

        ${card("Parked careers", parkedHtml())}
        </div></div>`;
      });

      body.querySelector("[data-skpick]").replaceWith(picker({ placeholder: "Add skill…", width: 180, search: skillSearch(skills), row: skillRow,
        pick: (x) => { const arr = ci.skill_array ||= []; if (!arr.some((y) => y.skill_id === x.id)) arr.push({ skill_id: x.id, level: x.rarity >= 3 ? 1 : 1 }); edits.skills = true; render(); } }));
      body.querySelector("[data-hpick]").replaceWith(picker({ placeholder: "Add hint…", width: 180, search: skillSearch(skills), row: skillRow,
        pick: (x) => {
          const arr = ci.skill_tips_array ||= [];
          const h = arr.find((y) => y.group_id === x.group && y.rarity === x.rarity);
          if (h) h.level = Math.min(5, h.level + 1); else arr.push({ group_id: x.group, rarity: x.rarity, level: 1 });
          edits.skills = true; render();
        } }));
      body.querySelector("[data-progpick]").replaceWith(picker({ placeholder: "Add race…", width: 180,
        search: (q) => programs.filter((p) => p.name.toLowerCase().includes(q) || String(p.id) === q),
        row: (p) => `<span class="badge sm sc-${esc(p.grade)}">${esc(p.grade)}</span><span>${esc(p.name)}</span><span class="faint">#${p.id} · month ${p.month}${p.half === 1 ? " early" : " late"}</span>`,
        pick: (p) => { body.querySelector("[data-progsel]").innerHTML = `${esc(p.name)} <button class="btn primary sm" data-c="race_add" data-prog="${p.id}">Add race</button>`; } }));
    }

    const val = (sel) => body.querySelector(sel)?.value;
    body.addEventListener("input", (e) => {
      const t = e.target;
      if (!s?.active) return;
      const ci = s.chara_info;
      if (t.matches("[data-turnr]")) { body.querySelector("[data-turn]").value = t.value; t.style.setProperty("--p", `${(t.value - 1) / (s.end_turn - 1) * 100}%`); }
      else if (t.matches("[data-turn]")) { const r = body.querySelector("[data-turnr]"); r.value = t.value; }
      else if (t.dataset.f) { ci[t.dataset.f] = +t.value; }
      else if (t.dataset.to !== undefined) { to[t.dataset.to] = t.type === "checkbox" ? t.checked : +t.value; win.save(); }
      else if (t.dataset.sklv !== undefined) { ci.skill_array[+t.dataset.sklv].level = +t.value; }
      else if (t.dataset.hlv !== undefined) { ci.skill_tips_array[+t.dataset.hlv].level = +t.value; }
      else if (t.dataset.bondr !== undefined || t.dataset.bond !== undefined) {
        const i = +(t.dataset.bondr ?? t.dataset.bond);
        s.bonds[i].evaluation = +t.value;
        const row = t.closest(".bond-row");
        row.querySelector("[data-bond]").value = t.value;
        const r = row.querySelector("[data-bondr]"); r.value = t.value; r.style.setProperty("--p", `${t.value}%`);
      } else if (t.matches("[data-cdadd]") && t.value) { (ci.chara_effect_id_array ||= []).push(+t.value); render(); }
    });

    body.addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (!b || !s) return;
      const d = b.dataset;
      const ci = s.chara_info;
      if (d.resume) return cmd("resume", { name: d.resume }, b, "Resumed");
      if (d.dropslot) {
        if (await ask(win, { title: `Delete parked career "${d.dropslot}"?`, danger: true, ok: "Delete" })) {
          if (await act(b, "Delete slot", () => call("career.cmd", { cmd: "drop_slot", name: d.dropslot }), "Slot deleted")) load();
        }
        return;
      }
      if (!s.active) return;
      if (d.mood) { ci.motivation = +d.mood; render(); return; }
      if (d.style) { ci.race_running_style = +d.style; render(); return; }
      if (d.skrm !== undefined) { ci.skill_array.splice(+d.skrm, 1); render(); return; }
      if (d.hrm !== undefined) { ci.skill_tips_array.splice(+d.hrm, 1); render(); return; }
      if (d.cdrm !== undefined) { ci.chara_effect_id_array.splice(+d.cdrm, 1); render(); return; }
      if (d.racedel) return cmd("race_del", { turn: +d.racedel, refund_fans: true }, b, "Race removed");
      if (d.evdrop) return cmd("event_drop", { event_id: +d.evdrop }, b, "Event dropped");
      if (d.unfire) return cmd("event_undo", { keys: [d.unfire] }, b, "Un-fired");
      if (d.rawkey) return ui.open("save", { key: d.rawkey });
      if (d.quick === "max") {
        for (const [k] of STATS) { const cap = k === "wiz" ? "max_wiz" : `max_${k}`; body.querySelector(`[data-f="${cap}"]`).value = 9999; body.querySelector(`[data-f="${k}"]`).value = 9999; }
        body.querySelector('[data-f="skill_point"]').value = 99999;
        return;
      }
      if (d.quick === "apt") { for (const k of APT_FIELDS) body.querySelector(`[data-f="${k}"]`).value = 8; return; }
      if (d.quick === "bonds") { s.bonds.forEach((x) => { x.evaluation = 100; }); render(); return; }
      if (d.save === "stats") {
        const fields = { motivation: ci.motivation, race_running_style: ci.race_running_style };
        for (const k of [...STATS.map(([x]) => x), ...STATS.map(([x]) => (x === "wiz" ? "max_wiz" : `max_${x}`)), "skill_point", "fans", "vital", "max_vital", "chara_grade"])
          fields[k] = +val(`[data-f="${k}"]`);
        return patch(fields, b, { regrade: body.querySelector("[data-regrade]").checked });
      }
      if (d.save === "apt") { const fields = {}; for (const k of APT_FIELDS) fields[k] = +val(`[data-f="${k}"]`); return patch(fields, b); }
      if (d.save === "skills") return patch({ skill_array: ci.skill_array || [], skill_tips_array: ci.skill_tips_array || [] }, b);
      if (d.save === "conditions") return patch({ chara_effect_id_array: ci.chara_effect_id_array || [] }, b);
      if (d.save === "bonds") {
        const byTarget = new Map(s.bonds.map((x) => [x.target_id, x.evaluation]));
        const arr = (ci.evaluation_info_array || []).map((x) => ({ ...x, evaluation: byTarget.get(x.target_id) ?? x.evaluation }));
        return patch({ evaluation_info_array: arr }, b);
      }
      switch (d.c) {
        case "reconcile": return cmd("reconcile", { clear_flight: false }, b, "Reconciled");
        case "set_turn": return cmd("set_turn", { ...to, value: +val("[data-turn]") }, b, "Turn set");
        case "unlock": return cmd("unlock", { all: true }, b, "Commands unlocked");
        case "lock": return cmd("unlock", { all: true, lock: true }, b, "Commands locked");
        case "event_drop_all": return cmd("event_drop", { all: true }, b, "Events dropped");
        case "event_undo_turn": return cmd("event_undo", { turn: +val("[data-uft]") }, b, "Un-fired");
        case "event_queue": return cmd("event_queue", { event_id: +val("[data-qe]"), story: +val("[data-qs]"), choices: +val("[data-qc]") || 1 }, b, "Queued");
        case "race_add": return cmd("race_add", { program_id: +d.prog, turn: +val("[data-rt]"), rank: +val("[data-rr]"),
          with_rewards: body.querySelector("[data-rw]").checked }, b, "Race recorded");
        case "idle_complete":
          if (await ask(win, { title: "Complete this career?", ok: "Complete", text: "Every stat to 9999, max SP and hints, and the run marked finished. Finish it in the game to bank the veteran." }))
            return cmd("idle_complete", {}, b, "Career completed");
          return;
        case "park": {
          const name = await ask(win, { title: "Park this career", text: "Moves it into a save slot; the account then has no career running.", input: "text", placeholder: "slot name", ok: "Park" });
          if (name) return cmd("park", { name: name.trim() }, b, "Career parked");
          return;
        }
        case "abandon":
          if (await ask(win, { title: "Abandon this career?", danger: true, ok: "Abandon", text: "Removes every career key (undo is in History)." })) {
            if (await act(b, "Abandon", () => call("career.cmd", { cmd: "abandon", confirm: true }), "Career removed")) load();
          }
          return;
        case "data_patch": {
          const path = val("[data-pp]").trim();
          if (!path) return;
          if (await act(b, "Set path", () => call("career.data_patch", { path, value: val("[data-pv]"),
            create: body.querySelector("[data-pc]").checked, full_state: body.querySelector("[data-pf]").checked }), "Set")) load();
          return;
        }
        default:
      }
    });

    const off = store.on((kind) => {
      if (kind === "target") { s = null; lastLog = ""; body.innerHTML = empty("Loading…"); load(); }
    });
    body.innerHTML = empty("Loading…");
    load();
    return off;
  },
};
