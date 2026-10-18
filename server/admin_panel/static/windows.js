// Window types. Each: { title, icon, size: [min w, min h], place: [x, y, w, h] as fractions of the
// desktop for the default layout, key (Alt+key), tools?(win), mount(body, win) -> cleanup }.

import { esc, store, ui } from "./core.js";
import { archipelagoWin } from "./archipelago.js";

const errorsWin = {
  title: "Errors", icon: "alert", size: [420, 300], place: [0.55, 0.5, 0.45, 0.5], dock: false,
  mount(body, win) {
    let openId = null;
    const render = () => {
      const list = [...store.errors].reverse();
      body.innerHTML = list.length ? list.map((e) => `<div class="err ${e.id === openId ? "open" : ""}" data-id="${esc(e.id)}">
          <div class="row"><b class="err-title grow">${esc(e.title)}</b><span class="faint">${new Date(e.t * 1000).toLocaleTimeString()}</span></div>
          <div class="err-msg">${esc(e.message)}</div>
          ${e.id === openId && e.detail ? `<pre class="err-detail">${esc(e.detail)}</pre>` : ""}</div>`).join("")
        : `<div class="empty">No errors.</div>`;
    };
    body.addEventListener("click", (e) => {
      const el = e.target.closest(".err");
      if (!el || e.target.closest(".err-detail")) return;
      openId = openId === el.dataset.id ? null : el.dataset.id;
      render();
    });
    win.reveal = (opts) => { if (opts.error) { openId = opts.error; render(); } };
    const off = store.on((k) => { if (k === "errors") render(); });
    render();
    return off;
  },
};

// This panel is Archipelago-only: UmaPS's save editor windows (users.js,
// save.js, supports.js, ...) are kept but not registered.
export const WINDOWS = {
  archipelago: archipelagoWin,
  errors: errorsWin,
};

export function drag(handle, target, onEnd) {
  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button, select, input")) return;
    const parent = target.offsetParent;
    const sx = e.clientX - target.offsetLeft, sy = e.clientY - target.offsetTop;
    handle.setPointerCapture(e.pointerId);
    const move = (m) => {
      target.style.left = Math.min(Math.max(m.clientX - sx, 0), parent.clientWidth - 60) + "px";
      target.style.top = Math.min(Math.max(m.clientY - sy, 0), parent.clientHeight - 40) + "px";
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      onEnd?.();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
}

// Buttons anywhere that open a window: <button data-open="users">
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-open]");
  if (b) ui.open(b.dataset.open, b.dataset.openArg ? JSON.parse(b.dataset.openArg) : {});
});
