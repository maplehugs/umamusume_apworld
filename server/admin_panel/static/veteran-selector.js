import { esc, gameIcon } from './core.js';
import { APT_FIELDS, APT_LABELS, MOODS, STATS, STYLES, aptBadge, modal } from './widgets.js';

export function veteranCardHTML(h, index, card, skills) {
  const name = card?.name || `Card ${h.card_id}`;
  const skillMap = new Map(skills.map(s => [s.id, s]));
  return `<article class="veteran-card">
    <header>${gameIcon('card', h.card_id)}<div class="grow"><b>${esc(name)}</b><div class="faint">${esc(card?.title || '')}</div><div class="faint">Veteran #${esc(h.trained_chara_id)} · ${esc(h.rarity ?? 3)} stars · Rating ${esc(h.rank_score ?? '—')}</div></div>
      <button type="button" class="btn primary" data-import-veteran="${index}">Import racer</button></header>
    <dl class="veteran-stats">${STATS.map(([key,label]) => `<div><dt>${label}</dt><dd>${esc(h[key] ?? (key === 'power' ? h.pow : null) ?? '—')}</dd></div>`).join('')}
      <div><dt>Skill points</dt><dd>${esc(h.skill_point ?? '—')}</dd></div></dl>
    <div class="veteran-meta"><span>Style: <b>${esc(STYLES[h.running_style] || 'Unspecified')}</b></span><span>Mood: <b>${esc(MOODS[h.motivation ?? 3] || 'Unspecified')}</b></span><span>Fans: <b>${esc(h.fan_count ?? h.fans ?? '—')}</b></span><span>Awakening: <b>${esc(h.talent_level ?? '—')}</b></span></div>
    <div class="veteran-aptitudes">${APT_FIELDS.map((key,i) => `<span>${APT_LABELS[i]} ${h[key] == null ? '—' : aptBadge(h[key])}</span>`).join('')}</div>
    <details><summary>Equipped skills · ${(h.skill_array || []).length}</summary><div class="veteran-equipped">${(h.skill_array || []).map(s => {
      const skill = skillMap.get(s.skill_id);
      return `<span>${skill ? gameIcon('skill', skill.icon, 'xs') : ''}${esc(skill?.name || `Skill ${s.skill_id}`)} <span class="faint">Lv ${esc(s.level ?? 1)}</span></span>`;
    }).join('') || '<span class="faint">No equipped skills</span>'}</div></details>
  </article>`;
}

export function openVeteranSelector(win, roster, cards, skills, imported) {
  const cardMap = new Map(cards.map(c => [c.id, c]));
  const m = modal(win, `<div class="veteran-picker"><header><h3>Import veteran</h3><span class="faint" data-veteran-added></span><button type="button" class="btn primary" data-veteran-close>Done</button></header>
    <p class="faint">Copy trained umas into this race — import as many as you like. Stats, aptitudes and equipped skills are preserved.</p>
    <div class="row"><label>Search veterans<input type="search" data-veteran-search placeholder="Uma name, outfit or veteran ID"></label>
      <label>Sort<select data-veteran-sort><option value="rating">Highest rating</option><option value="stats">Highest stat total</option><option value="name">Name</option><option value="id">Veteran ID</option></select></label></div>
    <p class="faint" data-veteran-count></p><div class="veteran-results" data-veteran-results></div></div>`, {wide:true});
  const search = m.box.querySelector('[data-veteran-search]');
  const sort = m.box.querySelector('[data-veteran-sort]');
  const total = h => STATS.reduce((sum,[key]) => sum + Number(h[key] ?? (key === 'power' ? h.pow : 0) ?? 0),0);
  const name = h => cardMap.get(h.card_id)?.name || '';
  let added = 0;
  function render() {
    const query = search.value.trim().toLowerCase();
    const matches = roster.map((h,index)=>({h,index})).filter(({h}) => {
      const c = cardMap.get(h.card_id);
      return [c?.name,c?.title,h.trained_chara_id,h.card_id].some(value=>String(value ?? '').toLowerCase().includes(query));
    });
    matches.sort((a,b) => (sort.value === 'name' ? name(a.h).localeCompare(name(b.h)) :
      sort.value === 'stats' ? total(b.h)-total(a.h) : sort.value === 'id' ? Number(a.h.trained_chara_id)-Number(b.h.trained_chara_id) :
      Number(b.h.rank_score || 0)-Number(a.h.rank_score || 0)) || a.index-b.index);
    m.box.querySelector('[data-veteran-count]').textContent = `${matches.length} of ${roster.length} veterans`;
    m.box.querySelector('[data-veteran-results]').innerHTML = matches.map(({h,index})=>veteranCardHTML(h,index,cardMap.get(h.card_id),skills)).join('') || '<p class="faint">No matching veterans.</p>';
  }
  search.oninput = render;
  sort.onchange = render;
  m.box.onclick = e => {
    const button = e.target.closest('button');
    if (!button) return;
    e.stopPropagation();
    if (button.hasAttribute('data-veteran-close')) m.close();
    else if (button.dataset.importVeteran !== undefined) {
      imported(structuredClone(roster[+button.dataset.importVeteran]));
      added++;
      m.box.querySelector('[data-veteran-added]').textContent = `${added} added`;
      button.textContent = 'Add again';
      button.classList.remove('primary');
    }
  };
  render(); search.focus();
}
