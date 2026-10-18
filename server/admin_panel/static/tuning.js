// Career tuning: the region's client_config.json knobs that bend career
// training. Server-wide (every account in this region), applied on the next
// training screen with no server restart. Blank = the real formula.

import { REGION_NAME, act, call, esc, icon, store } from "./core.js";
import { empty } from "./widgets.js";

export const tuningWin = {
  title: "Career tuning", icon: "bolt", size: [520, 420], place: [0.3, 0.08, 0.5, 0.84], key: "0",
  mount(body, win) {
    let d = null;
    body.classList.add("flush");

    async function load() {
      try { d = await call("tuning.get"); } catch (ex) { body.innerHTML = empty(esc(ex.message)); return; }
      render();
    }
    function render() {
      body.innerHTML = `<div class="pane-top"><div class="faint">${REGION_NAME[store.region]} · every account in this region · blank = real behaviour<br>
          <span class="mono">${esc(d.path)}</span></div></div>
        <div class="pane-scroll"><div class="ed-sec">${d.knobs.map((k) => `<div class="ed-row">
            <label style="flex:1">${esc(k.label)}<span class="faint" style="font-size:11px">${esc(k.help)}</span></label>
            <input type="number" class="num wide" data-k="${k.key}" value="${k.value ?? ""}" min="${k.min}" max="${k.max}"
              step="${k.kind === "int" ? 1 : 0.1}" placeholder="off"></div>`).join("")}</div></div>
        <div class="pane-foot row"><button class="btn sm" data-a="reset">Reset all</button><span class="grow"></span>
          <button class="btn primary sm" data-a="save">${icon("save")} Save</button></div>`;
    }
    const values = (blank) => Object.fromEntries([...body.querySelectorAll("[data-k]")].map((i) => [i.dataset.k, blank ? null : i.value.trim() || null]));

    body.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-a]");
      if (!b) return;
      const r = await act(b, "Saving tuning", () => call("tuning.set", { values: values(b.dataset.a === "reset") }),
        b.dataset.a === "reset" ? "Tuning reset" : "Tuning saved");
      if (r) { d = r; render(); }
    });

    win.refresh = load;
    const off = store.on((kind) => { if (kind === "target") load(); });
    body.innerHTML = empty("Loading…");
    load();
    return off;
  },
};
