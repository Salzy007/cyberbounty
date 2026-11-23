/* CyberBounty — сайт. Всё, что важно (цена, пересечения, часы), проверяет сервер; здесь только показ и выбор. */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TZ = "Europe/Minsk";
const fmtT = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtD = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, weekday: "short", day: "numeric", month: "long" });
const fmtWd = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, weekday: "short" });
const fmtDm = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, day: "2-digit", month: "2-digit" });
const fmtH = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "numeric", hourCycle: "h23" });
const tm = (ts) => fmtT.format(ts * 1000);
const dateLong = (ts) => fmtD.format(ts * 1000).replace(/^./, (c) => c.toUpperCase());
const isoToDate = (iso) => new Date(iso + "T12:00:00+03:00");
const ZONE_ICON = { standard: "i-monitor", vip: "i-vip", tournament: "i-table", lounge: "i-sofa" };
const SEAT_WORD = { PC: "ПК", VIP: "VIP", Table: "Стол", Sofa: "Диван" };
const seatName = (zone, n) => `${SEAT_WORD[zone.place_word] || zone.place_word} ${n}`;

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch("/api" + path, {
    method, credentials: "same-origin",
    headers: body ? { "content-type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "Что-то пошло не так. Попробуйте ещё раз."), { status: res.status, code: data.code });
  return data;
}

const S = {
  cfg: null, me: null, zone: null, day: null, slots: [], start: null, hours: 2, placeId: null,
  busy: {}, key: null, confirming: false, pending: false, reqId: 0, mapZone: null, my: [],
};

/* ---------- мелочи интерфейса ---------- */
function toast(text, err = false) {
  const el = document.createElement("div");
  el.className = "toast" + (err ? " toast--err" : "");
  el.textContent = text;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4100);
}

let lastFocus = null;
function openModal(el) {
  lastFocus = document.activeElement;
  el.hidden = false;
  document.body.classList.add("lock");
  const f = $("input, button.btn", el);
  if (f && matchMedia("(hover:hover)").matches) setTimeout(() => f.focus({ preventScroll: true }), 60);
}
function closeModal(el) {
  el.hidden = true;
  if (!$$(".modal:not([hidden]), .drawer:not([hidden])").length) document.body.classList.remove("lock");
  if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
}
document.addEventListener("click", (e) => {
  const c = e.target.closest("[data-close]");
  if (c) closeModal(c.closest(".modal, .drawer"));
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $$(".modal:not([hidden]), .drawer:not([hidden])").forEach(closeModal);
});

function setBusy(btn, on) { btn.classList.toggle("busy", on); btn.disabled = on || btn.dataset.off === "1"; }

/* ---------- зоны, даты, время ---------- */
function renderZones() {
  $("#zones").innerHTML = S.cfg.zones.map((z) => `
    <button class="zone" role="tab" type="button" data-zone="${z.id}" aria-selected="${z.id === S.zone.id}">
      <svg class="ic"><use href="#${ZONE_ICON[z.id] || "i-monitor"}"/></svg><b>${esc(z.name)}</b>
      <small>${z.places.length} мест · ${z.price} BYN/ч</small>
    </button>`).join("");
}

function renderDays() {
  $("#days").innerHTML = S.zone.days.map((iso, i) => {
    const d = isoToDate(iso);
    const label = i === 0 ? "Сегодня" : i === 1 ? "Завтра" : fmtWd.format(d);
    return `<button class="day" role="option" type="button" data-day="${iso}" aria-selected="${iso === S.day}"><small>${label}</small><b>${fmtDm.format(d)}</b></button>`;
  }).join("");
}

const ordered = () => S.slots.filter((s) => !s.after_midnight).concat(S.slots.filter((s) => s.after_midnight));
const ok = (s, h = S.hours) => (s.free[h] || 0) > 0;

function renderTimes() {
  /* не перерисовываем кнопки целиком: меняем только состояние, иначе рамка мигает, а лента времени дёргается */
  const list = ordered();
  const box = $("#times"), empty = $("#timesEmpty");
  empty.hidden = list.length > 0;
  if (!list.length) empty.textContent = "На эту дату время вышло. Выберите другой день.";
  box.hidden = !list.length;
  const sig = list.map((s) => s.start + (s.after_midnight ? "n" : "")).join(",");
  const rebuilt = box.dataset.sig !== sig;
  if (rebuilt) {
    box.innerHTML = list.map((s) => `<button class="time" role="option" type="button" data-start="${s.start}">${s.time}${s.after_midnight ? '<svg class="ic"><use href="#i-moon"/></svg>' : ""}</button>`).join("");
    box.dataset.sig = sig;
  }
  const byStart = new Map(list.map((s) => [String(s.start), s]));
  $$(".time", box).forEach((b) => {
    const s = byStart.get(b.dataset.start);
    const sel = s.start === S.start;
    if (b.disabled !== !ok(s)) b.disabled = !ok(s);
    if (b.getAttribute("aria-selected") !== String(sel)) b.setAttribute("aria-selected", String(sel));
  });
  if (rebuilt) {
    const sel = $('.time[aria-selected="true"]', box);
    box.scrollLeft = sel ? Math.max(0, sel.offsetLeft - box.clientWidth / 2 + sel.offsetWidth / 2) : 0;
  }
}

function renderDurs() {
  const box = $("#durs"), slot = S.slots.find((s) => s.start === S.start);
  if (box.children.length !== S.cfg.durations.length) {
    box.innerHTML = S.cfg.durations.map((h) => `<button class="dur" role="radio" type="button" data-h="${h}">${h}<small> ч</small></button>`).join("");
  }
  $$(".dur", box).forEach((b) => {
    const h = +b.dataset.h, off = !(slot && ok(slot, h)), on = h === S.hours;
    if (b.disabled !== off) b.disabled = off;
    if (b.getAttribute("aria-checked") !== String(on)) b.setAttribute("aria-checked", String(on));
  });
}

function fixSelection() {
  /* держим выбор в допустимых границах: время и длительность должны подходить друг другу */
  const list = ordered();
  let slot = list.find((s) => s.start === S.start);
  if (!slot || !Object.keys(slot.free).some((h) => slot.free[h] > 0)) {
    slot = list.find((s) => ok(s)) || list.find((s) => Object.values(s.free).some((n) => n > 0)) || null;
  }
  S.start = slot ? slot.start : null;
  if (slot && !ok(slot)) {
    const hs = S.cfg.durations.filter((h) => ok(slot, h));
    S.hours = hs.filter((h) => h <= S.hours).pop() || hs[0] || S.hours;
  }
}

async function loadSlots(pickFirst = false, silent = false) {
  const id = ++S.reqId;
  if (!silent) $("#times").classList.add("loading");
  let data;
  try { data = await api(`/zones/${S.zone.id}/slots?date=${S.day}`); } catch (e) { $("#times").classList.remove("loading"); if (!silent) toast(e.message, true); return; }
  if (id !== S.reqId) return;
  S.slots = data.slots;
  if (pickFirst) S.start = null;
  fixSelection();
  $("#times").classList.remove("loading");
  renderTimes(); renderDurs();
  await loadBusy();
}

async function loadBusy() {
  const id = S.reqId;
  if (!S.start) { S.busy = {}; return paintMap(); }
  try {
    const r = await api(`/zones/${S.zone.id}/busy?at=${S.start}&hours=${S.hours}`);
    if (id !== S.reqId) return;
    S.busy = r.busy;
  } catch (e) { S.busy = {}; }
  if (S.placeId && S.busy[S.placeId] !== undefined) { toast("Это место только что заняли. Выберите другое.", true); S.placeId = null; S.key = null; }
  paintMap();
}

/* ---------- схема зала ---------- */
function buildMap() {
  const z = S.zone;
  const icon = ZONE_ICON[z.id] || "i-monitor";
  const tv = z.id === "lounge" ? '<div class="tv" aria-hidden="true">TV 4K</div>' : "";
  $("#room").innerHTML = `<div class="map map--${z.id}">${tv}${z.places.map((p, i) => `
    <button class="seat" type="button" data-place="${p.id}" style="--i:${i}" aria-pressed="false" aria-label="${seatName(z, p.number)}">
      <svg class="ic"><use href="#${icon}"/></svg><b>${p.number}</b><small></small>
    </button>`).join("")}</div>`;
  S.mapZone = z.id;
}

function paintMap() {
  if (S.mapZone !== S.zone.id) buildMap();
  const seats = $$(".seat");
  let free = 0;
  seats.forEach((el) => {
    const id = +el.dataset.place, label = S.busy[id];
    const busy = !S.start || label !== undefined;
    if (!busy) free++;
    el.disabled = busy;
    el.setAttribute("aria-pressed", String(id === S.placeId));
    $("small", el).textContent = S.start && label !== undefined ? label : "";
  });
  const fc = $("#freeCount");
  fc.textContent = S.start ? (free ? `Свободно ${free} из ${seats.length}` : "Мест нет") : "";
  fc.style.color = free ? "" : "#ff8da0";
  updateSummary();
}

function swapZone(id) {
  if (id === S.zone.id) return;
  S.zone = S.cfg.zones.find((z) => z.id === id);
  S.placeId = null; S.key = null;
  renderZones();
  const map = $(".map");
  if (map) map.classList.add("swap");
  setTimeout(() => { S.mapZone = null; loadSlots(); }, map ? 180 : 0);
}

/* ---------- итог и подтверждение ---------- */
function updateSummary() {
  const z = S.zone, has = S.placeId && S.start;
  const price = z.price * S.hours;
  $("#sZone").textContent = z.name;
  $("#sSeat").textContent = has ? seatName(z, z.places.find((p) => p.id === S.placeId).number) : "не выбрано";
  $("#sDate").textContent = S.start ? dateLong(S.start) : "—";
  $("#sTime").textContent = S.start ? `${tm(S.start)}–${tm(S.start + S.hours * 3600)} · ${S.hours} ч` : "—";
  $("#sPrice").textContent = S.start ? `${price} BYN` : "—";
  const label = has ? `Подтвердить · ${price} BYN` : S.start ? "Выберите место" : "Нет времени";
  for (const [btn] of [[$("#btnConfirm")], [$("#dockConfirm")]]) {
    btn.dataset.off = has ? "" : "1";
    btn.disabled = !has || S.confirming;
    $(".btn__t", btn).textContent = btn.id === "dockConfirm" ? "Подтвердить" : label;
  }
  $("#dSeat").textContent = has ? `${seatName(z, z.places.find((p) => p.id === S.placeId).number)} · ${z.name}` : "";
  $("#dWhen").textContent = has ? `${tm(S.start)}–${tm(S.start + S.hours * 3600)} · ${price} BYN` : "";
  dock();
}

let bookVisible = false;
function dock() {
  const on = bookVisible && !!(S.placeId && S.start);
  $("#dock").classList.toggle("on", on);
  $("#dock").setAttribute("aria-hidden", String(!on));
}

function showErr(msg) {
  const el = $("#sErr");
  el.textContent = msg; el.hidden = false;
  toast(msg, true);
}

async function confirmBooking() {
  if (S.confirming || !S.placeId || !S.start) return;
  if (!S.me) { S.pending = true; openLogin(); return; }
  S.confirming = true;
  $("#sErr").hidden = true;
  [$("#btnConfirm"), $("#dockConfirm")].forEach((b) => b.classList.add("busy"));
  updateSummary();
  try {
    S.key = S.key || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
    const r = await api("/bookings", { method: "POST", body: { place_id: S.placeId, start: S.start, hours: S.hours, key: S.key } });
    S.key = null; S.placeId = null;
    showTicket(r.booking);
    await Promise.all([loadSlots(), loadMy()]);
  } catch (e) {
    if (e.status === 401) { S.me = null; renderAuth(); S.pending = true; openLogin(); }
    else {
      showErr(e.message);
      if (["taken", "past", "closed", "bad_time"].includes(e.code)) { S.key = null; S.placeId = null; await loadSlots(); }
    }
  } finally {
    S.confirming = false;
    [$("#btnConfirm"), $("#dockConfirm")].forEach((b) => b.classList.remove("busy"));
    updateSummary();
  }
}

function showTicket(b) {
  $("#ticket").innerHTML = `
    <div class="ticket__top"><span class="muted-s">Код брони</span><span class="ticket__code">${esc(b.code)}</span></div>
    <div class="ticket__sep"></div>
    <div class="ticket__rows">
      <div><span>Зона</span><b>${esc(b.zone)}</b></div>
      <div><span>Место</span><b>${esc(seatLabel(b))}</b></div>
      <div><span>Дата</span><b>${esc(dateLong(b.start))}</b></div>
      <div><span>Время</span><b>${esc(b.start_time)}–${esc(b.end_time)} · ${b.hours} ч</b></div>
      <div><span>К оплате в клубе</span><b>${b.price} BYN</b></div>
    </div><div class="ticket__bars" aria-hidden="true"></div>`;
  openModal($("#mTicket"));
}
const seatLabel = (b) => b.place.replace(/^(\S+)/, (w) => SEAT_WORD[w] || w);

/* ---------- вход, мои брони ---------- */
function renderAuth() {
  const me = S.me;
  $("#btnMy").hidden = !me; $("#menuMy").hidden = !me;
  $("#btnLogin").hidden = !!me; $("#menuLogin").hidden = !!me;
  $("#myWho").textContent = me ? me.name : "";
  if (!me) { S.my = []; updateBadge(); }
}
function openLogin() { $("#loginErr").hidden = true; closeMenu(); openModal($("#mLogin")); }

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, btn = $(".btn", f), err = $("#loginErr");
  err.hidden = true; setBusy(btn, true);
  try {
    const r = await api("/login", { method: "POST", body: { name: f.name.value, phone: f.phone.value } });
    S.me = r.me; renderAuth(); closeModal($("#mLogin"));
    toast(`Привет, ${S.me.name}!`);
    loadMy();
    if (S.pending) { S.pending = false; confirmBooking(); }
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
  finally { setBusy(btn, false); }
});
$("#mLogin").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) S.pending = false; });

async function loadMy() {
  if (!S.me) return;
  try { S.my = (await api("/my-bookings")).bookings; } catch (e) { if (e.status === 401) { S.me = null; renderAuth(); } return; }
  updateBadge();
  if (!$("#dMy").hidden) renderMy();
}
const upcoming = (b) => b.status === "confirmed" && b.end * 1000 > Date.now();
function updateBadge() {
  const n = S.my.filter(upcoming).length;
  const el = $("#myBadge");
  el.textContent = n; el.hidden = !n;
}
function bookingCard(b, up) {
  const st = b.status === "canceled" ? '<span class="pill pill--off">Отменена</span>' : up ? '<span class="pill pill--ok">Подтверждена</span>' : '<span class="pill pill--done">Прошла</span>';
  const canCancel = up && b.start * 1000 > Date.now();
  return `<article class="bk ${up ? "bk--up" : b.status === "canceled" || !up ? "bk--off" : ""}" data-id="${b.id}">
    <div class="bk__row"><b>${esc(b.zone)} · ${esc(seatLabel(b))}</b>${st}</div>
    <div class="bk__row"><span class="bk__when">${esc(dateLong(b.start))}, ${esc(b.start_time)}–${esc(b.end_time)}</span><span class="bk__code">${esc(b.code)}</span></div>
    <div class="bk__row"><span class="muted-s">${b.hours} ч</span><b class="price">${b.price} BYN</b></div>
    ${canCancel ? '<div class="bk__act"><button class="mini" data-act="ask" type="button">Отменить</button></div>' : ""}
  </article>`;
}
function renderMy() {
  const up = S.my.filter(upcoming).sort((a, b) => a.start - b.start);
  const old = S.my.filter((b) => !upcoming(b));
  $("#myList").innerHTML = S.my.length
    ? (up.length ? `<p class="sub-h">Ближайшие</p>${up.map((b) => bookingCard(b, true)).join("")}` : "")
      + (old.length ? `<p class="sub-h">История</p>${old.map((b) => bookingCard(b, false)).join("")}` : "")
    : `<div class="empty"><svg class="ic"><use href="#i-ticket"/></svg><p>Пока нет броней.<br>Выберите место — это быстро.</p><button class="btn btn--hot" type="button" data-close data-go="book">Выбрать место</button></div>`;
}
function openMy() { closeMenu(); renderMy(); openModal($("#dMy")); loadMy(); }

$("#myList").addEventListener("click", async (e) => {
  const go = e.target.closest("[data-go]");
  if (go) { setTimeout(() => $("#book").scrollIntoView(), 50); return; }
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const card = btn.closest(".bk"), act = card.querySelector(".bk__act");
  if (btn.dataset.act === "ask") {
    act.innerHTML = '<button class="mini mini--no" data-act="no" type="button">Оставить</button><button class="mini mini--yes" data-act="yes" type="button">Да, отменить</button>';
  } else if (btn.dataset.act === "no") {
    act.innerHTML = '<button class="mini" data-act="ask" type="button">Отменить</button>';
  } else if (btn.dataset.act === "yes") {
    btn.disabled = true;
    try {
      await api(`/bookings/${card.dataset.id}/cancel`, { method: "POST" });
      toast("Бронь отменена");
      await Promise.all([loadMy(), loadSlots()]);
    } catch (ex) { toast(ex.message, true); await loadMy(); }
  }
});
$("#btnLogout").addEventListener("click", async () => {
  try { await api("/logout", { method: "POST" }); } catch (e) { /* уже вышли */ }
  S.me = null; S.my = []; renderAuth(); closeModal($("#dMy")); toast("Вы вышли");
});

/* ---------- события ---------- */
$("#zones").addEventListener("click", (e) => { const b = e.target.closest("[data-zone]"); if (b) swapZone(b.dataset.zone); });
$("#days").addEventListener("click", (e) => {
  const b = e.target.closest("[data-day]");
  if (!b || b.dataset.day === S.day) return;
  S.day = b.dataset.day; S.placeId = null; S.key = null;
  $$(".day").forEach((d) => d.setAttribute("aria-selected", String(d === b)));
  loadSlots(true);
});
$("#times").addEventListener("click", (e) => {
  const b = e.target.closest(".time");
  if (!b || b.disabled) return;
  S.start = +b.dataset.start; S.placeId = null; S.key = null;
  fixSelection();
  renderTimes(); renderDurs(); ++S.reqId; loadBusy();
});
$("#durs").addEventListener("click", (e) => {
  const b = e.target.closest(".dur");
  if (!b || b.disabled) return;
  S.hours = +b.dataset.h; S.key = null;
  const slot = S.slots.find((s) => s.start === S.start);
  if (!slot || !ok(slot)) fixSelection();
  renderTimes(); renderDurs(); ++S.reqId; loadBusy();
});
$("#room").addEventListener("click", (e) => {
  const b = e.target.closest(".seat");
  if (!b || b.disabled) return;
  const id = +b.dataset.place;
  S.placeId = S.placeId === id ? null : id; S.key = null;
  $("#sErr").hidden = true;
  paintMap();
});
$("#btnConfirm").addEventListener("click", confirmBooking);
$("#dockConfirm").addEventListener("click", confirmBooking);
$("#btnLogin").addEventListener("click", openLogin);
$("#menuLogin").addEventListener("click", openLogin);
$("#btnMy").addEventListener("click", openMy);
$("#menuMy").addEventListener("click", openMy);
$("#tkMy").addEventListener("click", () => { closeModal($("#mTicket")); openMy(); });
$$("[data-pick]").forEach((a) => a.addEventListener("click", () => swapZone(a.dataset.pick)));

const menu = $("#menu"), burger = $("#burger");
function closeMenu() { menu.hidden = true; burger.setAttribute("aria-expanded", "false"); }
burger.addEventListener("click", () => { menu.hidden = !menu.hidden; burger.setAttribute("aria-expanded", String(!menu.hidden)); });
menu.addEventListener("click", (e) => { if (e.target.closest("a")) closeMenu(); });

/* ---------- мгновенные обновления и «сейчас свободно» ---------- */
let refreshTimer = 0;
function refresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    await Promise.all([loadSlots(false, true), loadMy(), heroLive()]);
  }, 120);
}
async function live() {
  let since = S.cfg.version;
  for (;;) {
    try {
      const r = await api("/wait?since=" + since);
      since = r.version;
      if (r.changed) refresh();
    } catch (e) { await sleep(3000); }
  }
}
async function heroLive() {
  const el = $("#heroLiveText");
  const h = +fmtH.format(Date.now());
  if (h >= 2 && h < 10) { el.textContent = "Сейчас клуб закрыт. Открываемся в 10:00 — бронь уже доступна"; return; }
  const at = Math.floor(Date.now() / 1800000) * 1800;
  try {
    const rs = await Promise.all(S.cfg.zones.map((z) => api(`/zones/${z.id}/busy?at=${at}&hours=1`)));
    const total = S.cfg.zones.reduce((n, z) => n + z.places.length, 0);
    const free = total - rs.reduce((n, r) => n + Object.keys(r.busy).length, 0);
    el.textContent = free ? `Прямо сейчас свободно ${free} из ${total} мест` : "Сейчас всё занято — бронируйте на другое время";
  } catch (e) { el.textContent = "Места свободны — выбирайте"; }
}

/* ---------- страница: анимации, отзывы, цены ---------- */
const REVIEWS = [
  ["Артём К.", "#35e6ff", "Лучший клуб в городе. VIP-места тихие, 360 Гц — это совсем другая игра. Бронь на сайте заняла 15 секунд."],
  ["Даша М.", "#ff3df0", "Пришли компанией на PS5 Lounge: диван, огромный экран, кальян. Вечер удался, вернёмся."],
  ["Никита Р.", "#ffb21e", "Занял место со смартфона по дороге из универа. Пришёл — всё включено и ждёт. Удобно."],
  ["Макс В.", "#8b5cff", "Турнирный стол на пять человек — идеально для скримов. Гарнитуры и экран тренера на месте."],
  ["Лиза П.", "#38f2a0", "Чисто, красиво, неоновая подсветка. Лимонад на месте, не надо отходить от игры."],
  ["Илья С.", "#35e6ff", "Пинг стабильный, мониторы быстрые. Стандартный зал за свои деньги — отличный вариант."],
  ["Кирилл Т.", "#ff3df0", "Отменил бронь в два касания, когда планы поменялись. Приятно, что всё прозрачно."],
  ["Настя Б.", "#ffb21e", "Ночью после 00:00 тоже весело, играем до закрытия. Персонал вежливый, клавиатуры живые."],
];
function buildReviews() {
  const card = ([n, c, t]) => `<article class="rev"><span class="stars" aria-label="5 из 5">${'<svg class="ic"><use href="#i-star"/></svg>'.repeat(5)}</span><p>${esc(t)}</p><div class="rev__who"><span class="rev__av" style="background:${c}">${esc(n[0])}</span><div><b>${esc(n)}</b><small>игрок CyberBounty</small></div></div></article>`;
  const row = (list) => { const h = list.map(card).join(""); return `<div class="mrow">${h}${h}</div>`; };
  $("#revRows").innerHTML = row(REVIEWS.slice(0, 4)) + row(REVIEWS.slice(4));
}

function countUp(el) {
  const to = +el.dataset.count, t0 = performance.now(), dur = 1400;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
    el.textContent = Math.round(to * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function setupPage() {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const io = new IntersectionObserver((es) => es.forEach((en) => {
    if (!en.isIntersecting) return;
    en.target.classList.add("in");
    $$("[data-count]", en.target).forEach((n) => !reduce && countUp(n));
    io.unobserve(en.target);
  }), { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
  $$(".reveal").forEach((el) => io.observe(el));

  const top = $("#top"), html = document.documentElement, touch = matchMedia("(hover: none), (max-width: 900px)").matches;
  let scrollTimer = 0;
  const onScroll = () => {
    top.classList.toggle("stuck", scrollY > 12);
    if (!touch) return;
    /* пока страницу листают, бесконечные анимации на паузе (см. html.scrolling в style.css) */
    if (!html.classList.contains("scrolling")) html.classList.add("scrolling");
    clearTimeout(scrollTimer); scrollTimer = setTimeout(() => html.classList.remove("scrolling"), 180);
  };
  addEventListener("scroll", onScroll, { passive: true }); onScroll();

  const links = $$(".nav a");
  const so = new IntersectionObserver((es) => es.forEach((en) => {
    if (en.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + en.target.id));
  }), { rootMargin: "-45% 0px -50% 0px" });
  ["book", "about", "services", "reviews"].forEach((id) => so.observe($("#" + id)));

  new IntersectionObserver((es) => { bookVisible = es[0].isIntersecting; dock(); }, { rootMargin: "0px 0px -10% 0px" }).observe($("#book"));

  if (matchMedia("(hover:hover)").matches && !reduce) {
    $$(".tile").forEach((t) => t.addEventListener("pointermove", (e) => { const r = t.getBoundingClientRect(); t.style.setProperty("--mx", e.clientX - r.left + "px"); t.style.setProperty("--my", e.clientY - r.top + "px"); }));
  }
}

/* ---------- живой фон: частицы, сетка и синее свечение, которое идёт за курсором ---------- */
function setupFx() {
  /* масштаб запрещает touch-action в CSS; обработчики gesture и touch не вешаем: из-за них встроенные браузеры (Google, Telegram) ждут страницу перед каждым скроллом */
  if (matchMedia("(hover: none), (max-width: 900px)").matches) return;      // на телефоне фон статичный: частицы и свечение за курсором тяжёлые и не нужны
  const root = document.documentElement, glow = $("#glow"), cv = $("#fx"), ctx = cv.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W = 0, H = 0, dpr = 1, nodes = [];
  let mx = -999, my = -999, gx = -999, gy = -999, lastX = -1, lastY = -1, hidden = false;
  const resize = () => {
    dpr = Math.min(devicePixelRatio || 1, 1.5); W = innerWidth; H = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.max(26, Math.min(64, Math.round((W * H) / 24000)));
    nodes = Array.from({ length: n }, () => ({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .28, vy: (Math.random() - .5) * .28, r: 1 + Math.random() * 1.6, c: Math.random() < .5 ? "53,230,255" : Math.random() < .5 ? "139,92,255" : "255,61,240" }));
  };
  resize(); addEventListener("resize", resize);
  const point = (e) => { mx = e.clientX; my = e.clientY; if (gx < -900) { gx = mx; gy = my; } glow.classList.add("on"); };
  addEventListener("pointermove", point, { passive: true });
  addEventListener("pointerdown", point, { passive: true });
  document.addEventListener("pointerleave", () => glow.classList.remove("on"));
  addEventListener("pointerup", (e) => { if (e.pointerType === "touch") setTimeout(() => glow.classList.remove("on"), 900); });
  document.addEventListener("visibilitychange", () => { hidden = document.hidden; if (!hidden) requestAnimationFrame(tick); });

  function tick() {
    if (hidden) return;
    gx += (mx - gx) * .2; gy += (my - gy) * .2;                       // плавное «догоняние» курсора
    if (mx > -900 && (Math.abs(gx - lastX) > .4 || Math.abs(gy - lastY) > .4)) {      // пишем в стили только когда курсор реально сдвинулся
      lastX = gx; lastY = gy;
      glow.style.transform = `translate3d(${gx.toFixed(1)}px,${gy.toFixed(1)}px,0)`;
      root.style.setProperty("--cx", gx.toFixed(0) + "px"); root.style.setProperty("--cy", gy.toFixed(0) + "px");
    }
    ctx.clearRect(0, 0, W, H);
    for (const n of nodes) {
      n.x += n.vx; n.y += n.vy;
      if (n.x < -20) n.x = W + 20; else if (n.x > W + 20) n.x = -20;
      if (n.y < -20) n.y = H + 20; else if (n.y > H + 20) n.y = -20;
    }
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 < 16900) { ctx.strokeStyle = `rgba(${a.c},${(1 - Math.sqrt(d2) / 130) * .22})`; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      }
      const cx = a.x - gx, cy = a.y - gy, cd = cx * cx + cy * cy;
      if (mx > -900 && cd < 40000) { ctx.strokeStyle = `rgba(53,230,255,${(1 - Math.sqrt(cd) / 200) * .55})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(gx, gy); ctx.stroke(); }
      ctx.fillStyle = `rgba(${a.c},.85)`; ctx.beginPath(); ctx.arc(a.x, a.y, a.r, 0, 6.2832); ctx.fill();
    }
    if (!reduce) requestAnimationFrame(tick);
  }
  tick();
}

/* ---------- ролик «Как это работает»: шаги, полоски как в сторис, пауза, звук ---------- */
/* Звук рисуем прямо в браузере (Web Audio), без файлов. По умолчанию выключен: включает посетитель. */
const PENTA = [523.25, 587.33, 659.25, 783.99, 880, 1046.5, 1174.66, 1318.5, 1568, 1760];   // пентатоника: любые ноты звучат красиво вместе
const Snd = {
  ctx: null, out: null, rev: null, padNodes: null, on: false, mul: 1,
  init() {
    if (this.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const c = (this.ctx = new AC());
    const comp = c.createDynamicsCompressor();
    comp.threshold.value = -14; comp.ratio.value = 5; comp.attack.value = 0.003; comp.release.value = 0.2;
    this.out = c.createGain(); this.out.gain.value = 1.35;                         // общая громкость
    this.out.connect(comp); comp.connect(c.destination);
    const conv = c.createConvolver(), len = Math.floor(c.sampleRate * 1.6), ir = c.createBuffer(2, len, c.sampleRate);   // «зал»: короткое эхо
    for (let ch = 0; ch < 2; ch++) { const d = ir.getChannelData(ch); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6); }
    conv.buffer = ir;
    this.rev = c.createGain(); this.rev.gain.value = 0.55;
    this.rev.connect(conv); conv.connect(this.out);
  },
  /* синт-голос: две слегка расстроенные волны + фильтр, который «раскрывается», и отправка в эхо */
  voice(freq, dur, { type = "sawtooth", vol = 0.2, to = 0, at = 0, cut = 4200, open = 0, rev = 0.3, det = 7 } = {}) {
    if (!this.on || !this.ctx) return;
    const c = this.ctx, t = c.currentTime + at, g = c.createGain(), f = c.createBiquadFilter();
    f.type = "lowpass"; f.Q.value = 3;
    f.frequency.setValueAtTime(open || cut, t); f.frequency.exponentialRampToValueAtTime(Math.max(300, cut), t + dur * 0.7);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol * this.mul, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    [-det, det].forEach((d) => {
      const o = c.createOscillator(); o.type = type; o.detune.value = d;
      o.frequency.setValueAtTime(freq, t);
      if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
      o.connect(f); o.start(t); o.stop(t + dur + 0.05);
    });
    f.connect(g); g.connect(this.out);
    if (rev) { const s = c.createGain(); s.gain.value = rev; g.connect(s); s.connect(this.rev); }
  },
  sine(freq, dur, vol = 0.2, to = 0, at = 0, rev = 0) {
    if (!this.on || !this.ctx) return;
    const c = this.ctx, t = c.currentTime + at, o = c.createOscillator(), g = c.createGain();
    o.frequency.setValueAtTime(freq, t);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol * this.mul, t + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(this.out); o.start(t); o.stop(t + dur + 0.05);
    if (rev) { const s = c.createGain(); s.gain.value = rev; g.connect(s); s.connect(this.rev); }
  },
  noise(dur, vol, f0, f1, at = 0, q = 1.2) {
    if (!this.on || !this.ctx) return;
    const c = this.ctx, t = c.currentTime + at, n = Math.floor(c.sampleRate * dur), buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    const src = c.createBufferSource(), bp = c.createBiquadFilter(), g = c.createGain();
    src.buffer = buf; bp.type = "bandpass"; bp.Q.value = q;
    bp.frequency.setValueAtTime(f0, t); bp.frequency.exponentialRampToValueAtTime(f1, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol * this.mul, t + dur * 0.35); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(bp); bp.connect(g); g.connect(this.out); src.start(t); src.stop(t + dur);
  },
  play(name, arg = 0) {
    const n = PENTA[Math.min(PENTA.length - 1, arg)];
    switch (name) {
      case "swoosh":                                                                     // кибер-свайп: шум вверх + глубокий удар
        this.noise(0.4, 0.34, 300, 6000); this.sine(110, 0.32, 0.5, 38); this.voice(220, 0.28, { vol: 0.1, to: 880, cut: 6000, rev: 0.4 }); break;
      case "tick":                                                                       // цифровой «блип» по ноте пентатоники
        this.voice(n * 2, 0.09, { type: "square", vol: 0.1, cut: 3800, open: 7000, rev: 0.25, det: 3 }); break;
      case "tap":                                                                        // «тук» экрана
        this.noise(0.05, 0.26, 3000, 1200); this.sine(420, 0.1, 0.4, 120); break;
      case "pick":                                                                       // выбор: восходящий пакл-аккорд
        this.voice(n, 0.38, { vol: 0.22, cut: 2600, open: 7500, rev: 0.5 }); this.voice(n * 1.5, 0.34, { vol: 0.14, at: 0.06, cut: 3000, open: 8000, rev: 0.5 }); this.sine(n * 2, 0.5, 0.08, 0, 0.08, 0.5); break;
      case "success":                                                                    // подтверждено: аккорд-арпеджио + удар и блеск
        this.sine(98, 0.5, 0.6, 45); this.noise(0.5, 0.16, 2500, 9000, 0.02, 0.8);
        [0, 2, 3, 5, 7].forEach((k, i) => this.voice(PENTA[k], 0.55, { vol: 0.2, at: i * 0.075, cut: 3200, open: 9000, rev: 0.55 })); break;
      case "ding":                                                                       // колокольчик (FM)
        this.sine(1318.5, 1.2, 0.3, 0, 0, 0.7); this.sine(2637, 0.9, 0.12, 0, 0, 0.7); this.sine(3951, 0.6, 0.06, 0, 0, 0.7); break;
      case "off":                                                                        // выключили: мягкое нисходящее «пум-пум»
        this.voice(n * 1.5, 0.22, { vol: 0.2, cut: 1800, open: 4000, rev: 0.3 }); this.voice(n, 0.3, { vol: 0.2, at: 0.09, to: n * 0.7, cut: 1400, open: 3000, rev: 0.3 }); break;
      case "sparkle":                                                                    // искорки
        [0, 1, 2, 3, 4].forEach((i) => this.sine(PENTA[5 + ((Math.random() * 5) | 0)] * 2, 0.35, 0.09, 0, i * 0.06, 0.8)); break;
    }
  },
  /* тихий фоновый «пад»: глубокий синт-дрон с медленно плывущим фильтром — пока ролик играет */
  pad(on) {
    if (!this.ctx) return;
    const c = this.ctx, t = c.currentTime;
    if (on && !this.padNodes) {
      const g = c.createGain(), f = c.createBiquadFilter(), lfo = c.createOscillator(), lg = c.createGain();
      f.type = "lowpass"; f.Q.value = 5; f.frequency.value = 520;
      lfo.frequency.value = 0.22; lg.gain.value = 260; lfo.connect(lg); lg.connect(f.frequency);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.11, t + 1.2);
      const oscs = [[55, "sawtooth", -6], [55, "sawtooth", 6], [82.4, "triangle", 0], [110, "sawtooth", 3]].map(([fr, ty, d]) => {
        const o = c.createOscillator(); o.type = ty; o.frequency.value = fr; o.detune.value = d; o.connect(f); o.start(t); return o;
      });
      f.connect(g); g.connect(this.out); lfo.start(t);
      this.padNodes = { g, oscs, lfo };
    } else if (!on && this.padNodes) {
      const { g, oscs, lfo } = this.padNodes;
      g.gain.cancelScheduledValues(t); g.gain.setValueAtTime(Math.max(g.gain.value, 0.0001), t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
      oscs.forEach((o) => o.stop(t + 0.6)); lfo.stop(t + 0.6);
      this.padNodes = null;
    }
  },
};
/* что и когда звучит на каждом шаге (секунды в «обычном» времени, умножаются на --k) */
const CUES = [
  [[0, "swoosh"], [0.3, "tick", 0], [0.5, "tick", 1], [0.7, "tick", 2], [0.9, "tick", 3], [2.1, "tap"], [2.3, "pick", 0]],
  [[0, "swoosh"], [0.25, "tick", 0], [0.45, "tick", 1], [0.65, "tick", 2], [1.2, "tap"], [1.3, "pick", 0], [2.2, "tap"], [2.3, "pick", 1], [3.1, "tap"], [3.2, "pick", 2]],
  [[0, "swoosh"], [0.2, "tick", 0], [0.35, "tick", 1], [0.5, "tick", 2], [0.65, "tick", 3], [0.75, "tick", 4], [2.2, "tap"], [2.3, "pick", 1]],
  [[0, "swoosh"], [0.25, "tick", 0], [0.4, "tick", 1], [0.55, "tick", 2], [0.7, "tick", 3], [0.95, "tick", 4], [2.4, "tap"], [2.55, "success"]],
  [[0.05, "swoosh"], [0.7, "tick", 2], [0.8, "ding"], [1.2, "sparkle"], [1.35, "sparkle"]],
];

function setupHow() {
  const root = $("#howStage");
  if (!root) return;
  const STEPS = [
    ["Выберите, где играть", "Standard, VIP, Tournament или PS5 Lounge. Цены видны сразу."],
    ["Дата, время, длительность", "Покажем только то время, когда клуб открыт и есть свободные места."],
    ["Место на схеме зала", "Свободные светятся, занятые затемнены. Занять чужое место нельзя."],
    ["Одно касание", "Цену считает сервер. Двойное нажатие не создаст вторую бронь."],
    ["Билет у вас", "Код брони — в разделе «Мои брони». Приходите и играйте."],
  ];
  /* все подписи лежат друг под другом: при смене шага текст не перерисовывается, а плавно перетекает */
  $("#howSteps").innerHTML = STEPS.map(([t, d], k) => `<div class="cap" aria-hidden="true"><span class="how__count">${k + 1} / ${STEPS.length}</span><b>${esc(t)}</b><p>${esc(d)}</p></div>`).join("");
  const caps = $$(".cap", root), screens = $$(".mk", root), bars = $$(".how-bar", root), play = $("#howPlay"), snd = $("#howSnd");
  const K = parseFloat(getComputedStyle(root).getPropertyValue("--k")) || 1;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let i = -1, playing = !reduce, inView = false, running = false, stepStart = 0, elapsed = 0, timers = [];
  if (reduce) root.classList.add("static");

  const clearCues = () => { timers.forEach(clearTimeout); timers = []; };
  const schedule = (from) => {
    clearCues();
    if (!Snd.on || i < 0) return;
    for (const [t, name, arg] of CUES[i]) {
      const ms = t * K * 1000;
      if (ms >= from) timers.push(setTimeout(() => Snd.play(name, arg), ms - from));
    }
  };
  const sync = () => {
    const want = playing && inView && !document.hidden;
    root.classList.toggle("paused", !want);
    play.setAttribute("aria-pressed", String(!playing));
    play.setAttribute("aria-label", playing ? "Пауза" : "Играть");
    if (want && !running) { stepStart = performance.now() - elapsed; schedule(elapsed); }          // продолжили: звуки догоняют картинку
    if (!want && running) { elapsed = performance.now() - stepStart; clearCues(); }
    running = want;
    Snd.pad(Snd.on && want);
  };
  function go(n) {
    i = (n + STEPS.length) % STEPS.length;
    screens.forEach((s, k) => s.classList.toggle("on", k === i));
    caps.forEach((c, k) => { c.classList.toggle("on", k === i); c.setAttribute("aria-hidden", String(k !== i)); });
    bars.forEach((b, k) => {
      b.classList.remove("fill");
      b.classList.toggle("done", k < i);
      if (k === i) { void b.offsetWidth; b.classList.add("fill"); }
    });
    stepStart = performance.now(); elapsed = 0;
    if (running) schedule(0); else clearCues();
  }
  bars.forEach((b, k) => b.addEventListener("click", () => go(k)));
  root.addEventListener("animationend", (e) => { if (e.animationName === "barFill" && running) go(i + 1); });
  play.addEventListener("click", () => { playing = !playing; sync(); });
  snd.addEventListener("click", () => {
    Snd.on = !Snd.on;
    if (Snd.on) { Snd.init(); if (Snd.ctx && Snd.ctx.state === "suspended") Snd.ctx.resume(); Snd.mul = 0.5; Snd.play("success"); Snd.mul = 1;                       // сигнал самой кнопки — вдвое тише остального звука
      schedule(performance.now() - stepStart); Snd.pad(running); }
    else {
      clearCues(); Snd.pad(false);
      Snd.on = true; Snd.mul = 0.5; Snd.play("off", 2); Snd.mul = 1; Snd.on = false;
    }
    snd.setAttribute("aria-pressed", String(Snd.on));
    snd.setAttribute("aria-label", Snd.on ? "Выключить звук" : "Включить звук");
    $("#howSndT").textContent = Snd.on ? "Звук вкл" : "Звук";
  });
  new IntersectionObserver((es) => {
    inView = es[0].isIntersecting;
    if (inView && i < 0) go(0);
    sync();
  }, { threshold: 0.35 }).observe(root);
  document.addEventListener("visibilitychange", sync);
}

/* ---------- вступительная заставка ---------- */
function setupIntro() {
  const html = document.documentElement, intro = $("#intro");
  if (!html.classList.contains("intro-on")) return;
  let done = false;
  const finish = () => {
    if (done) return; done = true;
    intro.classList.add("go");
    setTimeout(() => { html.classList.add("ready"); }, 380);                  // герой выезжает, когда створки уже расходятся
    setTimeout(() => { html.classList.add("intro-end"); }, 1600);          // створки остаются у краёв экрана как свечение
  };
  const hero = $(".hero__photo img");
  const loaded = Promise.all([document.fonts ? document.fonts.ready : 0, hero && hero.decode ? hero.decode().catch(() => 0) : 0]);
  const minTime = new Promise((r) => setTimeout(r, 2400));
  Promise.race([Promise.all([minTime, loaded]), new Promise((r) => setTimeout(r, 6000))]).then(finish);
  intro.addEventListener("click", finish);
  addEventListener("keydown", (e) => { if (e.key === "Escape" || e.key === "Enter") finish(); });
}

/* ---------- запуск ---------- */
async function init() {
  buildReviews();
  setupPage();
  try { S.cfg = await api("/config"); } catch (e) { toast("Не удалось загрузить данные. Обновите страницу.", true); return; }
  S.me = S.cfg.me; S.zone = S.cfg.zones[0]; S.day = S.zone.days[0];
  S.cfg.zones.forEach((z) => { $$(`[data-price="${z.id}"]`).forEach((el) => (el.textContent = `${z.price} BYN / час`)); });
  renderAuth(); renderZones(); renderDays();
  await loadSlots(true);
  if (!S.slots.length) {                     // сегодня уже поздно — открываем завтра
    S.day = S.zone.days[1]; renderDays(); await loadSlots(true);
  }
  loadMy(); heroLive(); live();
  setInterval(refresh, 60000);
}
setupIntro();
setupHow();
setupFx();
init();
