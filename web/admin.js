"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TZ = "Europe/Minsk";
const isoOf = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d);
const wd = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, weekday: "short" });
const dm = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, day: "2-digit", month: "2-digit" });
let day = isoOf(new Date()), data = null;

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch("/api" + path, { method, credentials: "same-origin", headers: body ? { "content-type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(j.error || "Ошибка"), { status: res.status });
  return j;
}
function toast(t, err) { const e = document.createElement("div"); e.className = "toast" + (err ? " toast--err" : ""); e.textContent = t; $("#toasts").append(e); setTimeout(() => e.remove(), 4100); }
function show(logged) { $("#login").hidden = logged; $("#app").hidden = !logged; $("#out").hidden = !logged; }

function renderDays() {
  const out = [];
  for (let i = -3; i <= 7; i++) out.push(isoOf(new Date(Date.now() + i * 86400000)));
  $("#days").innerHTML = out.map((iso, k) => {
    const d = new Date(iso + "T12:00:00+03:00");
    const label = iso === isoOf(new Date()) ? "Сегодня" : wd.format(d);
    return `<button class="day" type="button" data-day="${iso}" aria-selected="${iso === day}"><small>${label}</small><b>${dm.format(d)}</b></button>`;
  }).join("");
}

async function load() {
  try { data = await api("/admin/day?date=" + day); } catch (e) { if (e.status === 403) { show(false); } else toast(e.message, true); return; }
  show(true); render();
}

function render() {
  const live = data.bookings.filter((b) => b.status === "confirmed" && !b.carried);
  $("#kN").textContent = live.length; $("#kSum").textContent = data.total + " BYN"; $("#kOff").textContent = data.canceled_total;
  $("#clear").hidden = !data.canceled_total;
  $("#list").innerHTML = data.bookings.length ? data.bookings.map((b) => `
    <article class="row ${b.status === "canceled" ? "off" : ""}" data-id="${b.id}">
      <div class="row__t">${esc(b.start_time)}–${esc(b.end_time)}<small>${esc(b.code)} · ${b.hours} ч${b.carried ? " · с " + esc(b.date) : ""}</small></div>
      <div class="row__m"><b>${esc(b.zone)} · ${esc(b.place)}</b><span>${esc(b.client)}${b.phone ? " · +" + esc(b.phone) : ""}</span></div>
      <div class="row__r"><b class="price">${b.price} BYN</b><div class="row__act">${
        b.status === "canceled" ? '<span class="pill pill--off">Отменена</span><button class="mini" data-act="del" type="button">Стереть</button>'
        : b.end * 1000 > Date.now() ? '<button class="mini" data-act="ask" type="button">Отменить</button>' : '<span class="pill pill--done">Прошла</span>'}</div></div>
    </article>`).join("") : '<p class="muted-s" style="padding:30px 0;text-align:center">На этот день броней нет.</p>';
  $("#prices").innerHTML = data.zones.map((z) => `<div class="pr"><div><b>${esc(z.name)}</b><small>BYN за час</small></div><div class="pr__in"><input type="number" min="1" max="1000" step="1" value="${z.price}" data-zone="${z.id}" aria-label="Цена ${esc(z.name)}"><button class="mini" data-act="price" data-zone="${z.id}" type="button">Сохранить</button></div></div>`).join("");
  $("#free").innerHTML = data.zones.map((z) => `<div class="zfree"><h4>${esc(z.name)}</h4>${z.places.map((p) => `<div class="pf"><b>${esc(p.label)}</b>${p.free_all ? '<span class="all">весь день свободно</span>' : p.free.length ? p.free.map((f) => `<span>${esc(f)}</span>`).join("") : "<em>занято</em>"}</div>`).join("")}</div>`).join("");
}

$("#days").addEventListener("click", (e) => { const b = e.target.closest("[data-day]"); if (!b) return; day = b.dataset.day; renderDays(); load(); });
$("#list").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]"); if (!btn) return;
  const row = btn.closest(".row"), id = row.dataset.id, act = row.querySelector(".row__act");
  if (btn.dataset.act === "ask") act.innerHTML = '<button class="mini mini--no" data-act="no" type="button">Нет</button><button class="mini mini--yes" data-act="yes" type="button">Да, отменить</button>';
  else if (btn.dataset.act === "no") act.innerHTML = '<button class="mini" data-act="ask" type="button">Отменить</button>';
  else try {
    btn.disabled = true;
    if (btn.dataset.act === "yes") { await api(`/admin/bookings/${id}/cancel`, { method: "POST" }); toast("Бронь отменена"); }
    if (btn.dataset.act === "del") { await api(`/admin/bookings/${id}`, { method: "DELETE" }); toast("Стёрто из истории"); }
    load();
  } catch (ex) { toast(ex.message, true); load(); }
});
$("#clear").addEventListener("click", async (e) => {
  const b = e.currentTarget;
  if (b.dataset.sure !== "1") { b.dataset.sure = "1"; b.textContent = "Точно стереть?"; b.classList.add("mini--yes"); setTimeout(() => { b.dataset.sure = ""; b.textContent = "Стереть отменённые"; b.classList.remove("mini--yes"); }, 4000); return; }
  b.dataset.sure = ""; b.classList.remove("mini--yes"); b.textContent = "Стереть отменённые";
  try { const r = await api("/admin/clear", { method: "POST" }); toast(`Стёрто: ${r.removed}`); load(); } catch (ex) { toast(ex.message, true); }
});
$("#prices").addEventListener("click", async (e) => {
  const b = e.target.closest('[data-act="price"]'); if (!b) return;
  const input = $(`input[data-zone="${b.dataset.zone}"]`);
  try { await api("/admin/zones/" + b.dataset.zone, { method: "PATCH", body: { price: Number(input.value) } }); toast("Цена сохранена"); load(); } catch (ex) { toast(ex.message, true); }
});
$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $(".btn", e.target), err = $("#loginErr"); err.hidden = true; btn.classList.add("busy"); btn.disabled = true;
  try { await api("/admin/login", { method: "POST", body: { password: e.target.password.value } }); e.target.reset(); load(); }
  catch (ex) { err.textContent = ex.message; err.hidden = false; }
  finally { btn.classList.remove("busy"); btn.disabled = false; }
});
$("#out").addEventListener("click", async () => { try { await api("/admin/logout", { method: "POST" }); } catch (e) { /* уже вышли */ } show(false); });

/* мгновенно: новая бронь клиента сразу появляется */
(async function live() {
  let since = null;
  for (;;) {
    try {
      const r = await api("/wait" + (since === null ? "" : "?since=" + since));
      if (since !== null && r.changed && !$("#app").hidden) load();
      since = r.version;
    } catch (e) { await new Promise((r) => setTimeout(r, 3000)); }
  }
})();
renderDays(); load();
