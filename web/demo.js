/* CyberBounty — демо-режим без сервера.
   Включается, когда сайт открыт не с нашего Python-сервера: на GitHub Pages или просто файлом (двойной клик по index.html).
   Все правила брони — те же, что в app/booking.py (пересечения, прошлое, часы 10:00–02:00, бронь не выходит за закрытие,
   двойное нажатие = одна бронь, цену считает «сервер»), только «сервером» тут служит этот файл, а базой — localStorage браузера.
   Локально через `python main.py` (адрес 127.0.0.1 или localhost) демо не включается: работает настоящий сервер. */
(function () {
  "use strict";
  var host = location.hostname;
  var forced = /[?&]demo(=1)?\b/.test(location.search);
  var real = (host === "127.0.0.1" || host === "localhost") && location.protocol !== "file:" && !forced;
  window.CB_DEMO = !real;
  if (real) return;

  var KEY = "cbdemo:v1";
  var TZ = 3 * 3600, STEP = 1800, DAYS_AHEAD = 7, DURATIONS = [1, 2, 3, 5];
  var WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  var ADMIN_PASSWORD = "demo";
  var USER_TTL = 30 * 86400, ADMIN_TTL = 12 * 3600;

  /* ---------- хранилище ---------- */
  var ZONES = [
    { id: "standard", name: "Standard", tagline: "RTX 4060 · 240 Hz", price: 6, open_min: 600, close_min: 1560, place_word: "PC", sort: 0, count: 12 },
    { id: "vip", name: "VIP", tagline: "RTX 4080 · 360 Hz · кресла", price: 12, open_min: 600, close_min: 1560, place_word: "VIP", sort: 1, count: 6 },
    { id: "tournament", name: "Tournament", tagline: "Турнирные столы для команд", price: 18, open_min: 600, close_min: 1560, place_word: "Table", sort: 2, count: 4 },
    { id: "lounge", name: "Lounge", tagline: "PlayStation 5 · диваны · 4K TV", price: 10, open_min: 600, close_min: 1560, place_word: "Sofa", sort: 3, count: 4 },
  ];
  function fresh() {
    var db = { v: 1, zones: {}, places: [], bookings: [], users: [], nextBooking: 1, nextUser: 1, nextPlace: 1, seeded: {}, session: null, admin: null, version: 1 };
    ZONES.forEach(function (z) {
      db.zones[z.id] = { id: z.id, name: z.name, tagline: z.tagline, price: z.price, open_min: z.open_min, close_min: z.close_min, place_word: z.place_word, sort: z.sort };
      for (var n = 1; n <= z.count; n++) db.places.push({ id: db.nextPlace++, zone_id: z.id, number: n });
    });
    return db;
  }
  var db;
  function load() {
    try { db = JSON.parse(localStorage.getItem(KEY)); } catch (e) { db = null; }
    if (!db || db.v !== 1) db = fresh();
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(db)); } catch (e) { /* память браузера недоступна: работаем в рамках вкладки */ } }

  /* ---------- время (Минск, UTC+3) ---------- */
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function parts(ts) { var d = new Date((ts + TZ) * 1000); return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), wd: (d.getUTCDay() + 6) % 7, h: d.getUTCHours(), mi: d.getUTCMinutes() }; }
  function hhmm(ts) { var p = parts(ts); return pad(p.h) + ":" + pad(p.mi); }
  function ddmm(ts) { var p = parts(ts); return pad(p.d) + "." + pad(p.m) + " " + WEEKDAYS[p.wd]; }
  function iso(y, m, d) { return y + "-" + pad(m) + "-" + pad(d); }
  function isoOf(ts) { var p = parts(ts); return iso(p.y, p.m, p.d); }
  function midnight(isoDay) { var a = isoDay.split("-").map(Number); return Date.UTC(a[0], a[1] - 1, a[2]) / 1000 - TZ; }
  function addDays(isoDay, n) { return isoOf(midnight(isoDay) + n * 86400 + 43200); }
  function validIso(t) { return typeof t === "string" && /^\d{4}-\d{2}-\d{2}$/.test(t) && isoOf(midnight(t) + 43200) === t; }
  function zoneDays(now) { var t = isoOf(now), out = []; for (var i = 0; i <= DAYS_AHEAD; i++) out.push(addDays(t, i)); return out; }
  function win(zone, day) { var b = midnight(day); return [b + zone.open_min * 60, b + zone.close_min * 60]; }
  function hm(min) { return pad(Math.floor(min / 60) % 24) + ":" + pad(min % 60); }

  function Err(code, message, status) { var e = new Error(message); e.code = code; e.status = status || 400; return e; }

  /* ---------- чтение ---------- */
  function zonePlaces(zid) { return db.places.filter(function (p) { return p.zone_id === zid; }).sort(function (a, b) { return a.number - b.number; }); }
  function sortedZones() { return Object.keys(db.zones).map(function (k) { return db.zones[k]; }).sort(function (a, b) { return a.sort - b.sort; }); }
  function getZone(id) { var z = db.zones[id]; if (!z) throw Err("no_zone", "Такой зоны нет.", 404); return z; }
  function getPlace(id) {
    var p = typeof id === "number" ? db.places.filter(function (x) { return x.id === id; })[0] : null;
    if (!p) throw Err("no_place", "Такого места нет.", 404);
    return { place: p, zone: db.zones[p.zone_id] };
  }
  function parseDay(text, now) {
    if (!validIso(text) || zoneDays(now).indexOf(text) < 0) throw Err("bad_date", validIso(text) ? "Эта дата недоступна для брони." : "Неверная дата.");
    return text;
  }
  function confirmed() { return db.bookings.filter(function (b) { return b.status === "confirmed"; }); }
  function placeLabel(p, z) { return z.place_word + " " + p.number; }
  function view(b) {
    var pz = getPlace(b.place_id), z = pz.zone;
    return { id: b.id, code: "CB-" + ("0000" + b.id).slice(-4), zone: z.name, place: placeLabel(pz.place, z), date: ddmm(b.start_ts), start_time: hhmm(b.start_ts), end_time: hhmm(b.end_ts),
      start: b.start_ts, end: b.end_ts, hours: b.hours, price: b.price, status: b.status, client: b.client_name, phone: b.client_phone, user_id: b.user_id };
  }

  function catalog(now) {
    return sortedZones().map(function (z) {
      return { id: z.id, name: z.name, tagline: z.tagline, price: z.price, place_word: z.place_word, open: hm(z.open_min), close: hm(z.close_min),
        places: zonePlaces(z.id).map(function (p) { return { id: p.id, number: p.number }; }), days: zoneDays(now) };
    });
  }

  function busyAt(zid, at, span) {
    var ids = {}; zonePlaces(zid).forEach(function (p) { ids[p.id] = 1; });
    var rows = confirmed().filter(function (b) { return ids[b.place_id] && b.start_ts < at + Math.max(span, 1) && b.end_ts > at; }).sort(function (a, b) { return a.start_ts - b.start_ts; });
    var out = {};
    rows.forEach(function (r) {
      if (out[r.place_id] !== undefined) return;
      if (r.start_ts > at) { out[r.place_id] = "с " + hhmm(r.start_ts); return; }
      var end = r.end_ts, nxt;
      while ((nxt = confirmed().filter(function (b) { return b.place_id === r.place_id && b.start_ts === end; })[0])) end = nxt.end_ts;
      out[r.place_id] = "до " + hhmm(end);
    });
    return out;
  }

  function zoneSlots(zid, dayText, now) {
    var zone = getZone(zid), d = parseDay(dayText, now), dayStart = midnight(d), dayEnd = dayStart + 86400;
    var places = zonePlaces(zid), ids = {}; places.forEach(function (p) { ids[p.id] = 1; });
    var busy = confirmed().filter(function (b) { return ids[b.place_id] && b.end_ts > dayStart - 86400 && b.start_ts < dayEnd + 86400; });
    var out = [];
    [addDays(d, -1), d].forEach(function (session) {
      var w = win(zone, session), t = w[0];
      while (t + DURATIONS[0] * 3600 <= w[1]) {
        if (t >= dayStart && t < dayEnd && t >= now) {
          var free = {};
          DURATIONS.forEach(function (h) {
            if (t + h * 3600 <= w[1]) free[h] = places.length - busy.filter(function (x) { return x.start_ts < t + h * 3600 && x.end_ts > t; }).length;
          });
          out.push({ start: t, time: hhmm(t), after_midnight: t < dayStart + zone.open_min * 60, free: free });
        }
        t += STEP;
      }
    });
    out.sort(function (a, b) { return a.start - b.start; });
    return { date: d, total: places.length, slots: out };
  }

  /* ---------- создание и отмена ---------- */
  function createBooking(user, body, now) {
    var placeId = body.place_id, start = body.start, hours = body.hours, key = body.key;
    if (DURATIONS.indexOf(hours) < 0) throw Err("bad_hours", "Выберите 1, 2, 3 или 5 часов.");
    if (typeof start !== "number" || Math.floor(start) !== start || start % STEP) throw Err("bad_time", "Время начала должно быть кратно 30 минутам.");
    if (key !== undefined && key !== null && (typeof key !== "string" || key.length < 8 || key.length > 64)) throw Err("bad_key", "Неверный ключ запроса.");
    var pz = getPlace(placeId), zone = pz.zone, end = start + hours * 3600;
    if (start < now) throw Err("past", "Это время уже прошло. Выберите другое.");
    var days = zoneDays(now), sessions = [addDays(days[0], -1)].concat(days);
    var ok = sessions.some(function (s) { var w = win(zone, s); return w[0] <= start && end <= w[1]; });
    if (!ok || start >= midnight(days[0]) + (DAYS_AHEAD + 1) * 86400) throw Err("closed", "Клуб в это время закрыт, или бронь выходит за время закрытия.");
    if (key) {
      var same = db.bookings.filter(function (b) { return b.user_id === user.id && b.idem_key === key; })[0];
      if (same) return { booking: view(same), duplicate: true };                         // двойное нажатие = одна бронь
    }
    var clash = confirmed().some(function (b) { return b.place_id === placeId && b.start_ts < end && b.end_ts > start; });
    if (clash) throw Err("taken", "Это место уже занято на выбранное время.", 409);
    var b = { id: db.nextBooking++, user_id: user.id, client_name: user.name, client_phone: user.phone, place_id: placeId, start_ts: start, end_ts: end, hours: hours,
      price: zone.price * hours, status: "confirmed", idem_key: key || null, created_ts: Math.floor(now) };   // цена только из «базы»
    db.bookings.push(b);
    return { booking: view(b), duplicate: false };
  }
  function cancelBooking(id, now) {
    var b = db.bookings.filter(function (x) { return x.id === id; })[0];
    if (!b) throw Err("no_booking", "Такой брони нет.", 404);
    if (b.status === "canceled") throw Err("already", "Бронь уже отменена.", 409);
    if (b.end_ts <= now) throw Err("finished", "Эта бронь уже закончилась.", 409);
    b.status = "canceled"; b.canceled_ts = Math.floor(now);
    return view(b);
  }
  function cancelByClient(id, uid, now) {
    var b = db.bookings.filter(function (x) { return x.id === id; })[0];
    if (!b || b.user_id !== uid) throw Err("no_booking", "Такой брони нет.", 404);
    if (b.status === "canceled") throw Err("already", "Бронь уже отменена.", 409);
    if (b.start_ts <= now) throw Err("started", "Бронь уже началась. Отмену решает клуб: напишите администратору.", 409);
    return cancelBooking(id, now);
  }

  /* ---------- админка ---------- */
  function dayOverview(dayText, now) {
    if (!validIso(dayText)) throw Err("bad_date", "Неверная дата.");
    var d = dayText, dayStart = midnight(d), dayEnd = dayStart + 86400;
    var zs = sortedZones(), zi = {}; zs.forEach(function (z, i) { zi[z.id] = i; });
    var rows = db.bookings.filter(function (b) { return b.start_ts >= dayStart && b.start_ts < dayEnd; }).sort(function (a, b) {
      var pa = getPlace(a.place_id), pb = getPlace(b.place_id);
      return a.start_ts - b.start_ts || zi[pa.zone.id] - zi[pb.zone.id] || pa.place.number - pb.place.number;
    });
    var bookings = rows.map(view), live = bookings.filter(function (b) { return b.status === "confirmed"; });
    var near = confirmed().filter(function (b) { return b.end_ts > dayStart && b.start_ts < dayEnd + 86400; });
    var fromTs = Math.ceil(Math.floor(now) / STEP) * STEP;
    var zones = zs.map(function (z) {
      var wins = [];
      [addDays(d, -1), d].forEach(function (session, idx) {
        var w = win(z, session), o = Math.max(w[0], dayStart), c = Math.min(w[1], dayEnd + 86400);
        if (idx === 0) c = Math.min(c, dayEnd);
        if (c > o) wins.push([o, c]);
      });
      var places = zonePlaces(z.id).map(function (p) {
        var busy = near.filter(function (b) { return b.place_id === p.id; }).map(function (b) { return [b.start_ts, b.end_ts]; }).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
        var free = [];
        wins.forEach(function (w) {
          var cursor = Math.max(w[0], fromTs);
          busy.forEach(function (be) {
            if (be[1] <= cursor || be[0] >= w[1]) return;
            if (be[0] > cursor) free.push([cursor, be[0]]);
            cursor = Math.max(cursor, be[1]);
          });
          if (cursor < w[1]) free.push([cursor, w[1]]);
        });
        free = free.filter(function (f) { return f[1] > f[0]; });
        var whole = wins.length ? (!busy.length && fromTs <= wins[wins.length - 1][0]) : false;
        return { id: p.id, label: placeLabel(p, z), free: free.map(function (f) { return hhmm(f[0]) + "–" + hhmm(f[1]); }), free_all: whole };
      });
      return { id: z.id, name: z.name, price: z.price, places: places };
    });
    return { date: d, canceled_total: db.bookings.filter(function (b) { return b.status === "canceled"; }).length, bookings: bookings,
      total: live.reduce(function (s, b) { return s + b.price; }, 0), zones: zones };
  }

  /* ---------- «живая» витрина: сразу видно занятые места ---------- */
  function rng(seed) { var s = seed >>> 0; return function () { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
  var DEMO_NAMES = ["Артём К.", "Даша М.", "Никита Р.", "Макс В.", "Лиза П.", "Илья С.", "Кирилл Т.", "Настя Б.", "Егор Л.", "Вика Н."];
  function seedDemo(now) {
    var changed = false;
    zoneDays(now).slice(0, 4).forEach(function (day) {
      if (db.seeded[day]) return;
      db.seeded[day] = 1; changed = true;
      var r = rng(midnight(day) / 86400);
      sortedZones().forEach(function (z) {
        zonePlaces(z.id).forEach(function (p) {
          if (r() > 0.45) return;
          var h = [1, 2, 2, 3][Math.floor(r() * 4)], startHour = 13 + Math.floor(r() * 9);
          var s = midnight(day) + startHour * 3600 + (r() > 0.5 ? 1800 : 0), e = s + h * 3600, w = win(z, day);
          if (s < now || e > w[1]) return;
          var clash = db.bookings.some(function (b) { return b.status === "confirmed" && b.place_id === p.id && b.start_ts < e && b.end_ts > s; });
          if (clash) return;
          var name = DEMO_NAMES[Math.floor(r() * DEMO_NAMES.length)];
          db.bookings.push({ id: db.nextBooking++, user_id: 0, client_name: name, client_phone: "37529" + (1000000 + Math.floor(r() * 8999999)), place_id: p.id, start_ts: s, end_ts: e, hours: h,
            price: z.price * h, status: "confirmed", idem_key: null, created_ts: Math.floor(now) });
        });
      });
    });
    return changed;
  }

  /* ---------- сессии ---------- */
  function me(now) {
    var s = db.session;
    if (!s || s.exp < now) return null;
    var u = db.users.filter(function (x) { return x.id === s.uid; })[0];
    return u ? pub(u) : null;
  }
  function pub(u) { return { id: u.id, name: u.name, phone: u.phone || null, email: u.email || null, via: { telegram: !!u.telegram, google: !!u.google, email: !!u.email, phone: !!u.phone } }; }
  var DEMO_NAMES = { telegram: "Игрок Telegram", google: "Игрок Google", email: "Игрок (почта)" };
  function needUser(now) { var u = me(now); if (!u) { var e = Err("auth", "Войдите, чтобы забронировать.", 401); throw e; } return u; }
  function isAdmin(now) { return !!(db.admin && db.admin.exp > now); }
  function cleanPhone(raw) { var d = String(typeof raw === "string" ? raw : "").replace(/\D/g, ""); if (d.length < 7 || d.length > 15) throw Err("bad_phone", "Введите телефон: от 7 до 15 цифр."); return d; }
  function cleanName(raw) { var n = String(typeof raw === "string" ? raw : "").replace(/\s+/g, " ").trim(); if (n.length < 2 || n.length > 40) throw Err("bad_name", "Имя — от 2 до 40 символов."); return n; }

  /* ---------- «ожидание изменений» (мгновенное обновление между вкладками) ---------- */
  var waiters = [];
  function bump() { db.version++; save(); var w = waiters; waiters = []; w.forEach(function (f) { f(); }); }
  window.addEventListener("storage", function (e) { if (e.key === KEY) { load(); var w = waiters; waiters = []; w.forEach(function (f) { f(); }); } });
  function wait(since) {
    if (since === null || since === undefined || db.version !== since) return Promise.resolve({ version: db.version, changed: since !== null && since !== undefined });
    return new Promise(function (resolve) {
      var done = false;
      function fin() { if (done) return; done = true; resolve({ version: db.version, changed: db.version !== since }); }
      waiters.push(fin); setTimeout(fin, 25000);
    });
  }

  /* ---------- маршруты (те же адреса, что у настоящего сервера) ---------- */
  function route(method, path, query, body) {
    var now = Date.now() / 1000, m;
    if (seedDemo(now)) { db.version++; save(); }
    if (method === "GET" && path === "/config") return { zones: catalog(now), durations: DURATIONS.slice(), version: db.version, now: Math.floor(now), me: me(now) };
    if (method === "GET" && (m = path.match(/^\/zones\/([^/]+)\/slots$/))) return zoneSlots(m[1], query.date, now);
    if (method === "GET" && (m = path.match(/^\/zones\/([^/]+)\/busy$/))) {
      var at = parseInt(query.at, 10), hours = query.hours === undefined ? 1 : parseInt(query.hours, 10);
      if (DURATIONS.indexOf(hours) < 0 || !(at >= now - 1800 && at <= now + 9 * 86400)) throw Err("bad_time", "Это время недоступно.");
      getZone(m[1]);
      return { busy: busyAt(m[1], at, hours * 3600) };
    }
    if (method === "POST" && path === "/login") {
      var name = cleanName(body.name), phone = cleanPhone(body.phone);
      var u = db.users.filter(function (x) { return x.phone === phone; })[0];
      if (u) u.name = name; else { u = { id: db.nextUser++, name: name, phone: phone, created_ts: Math.floor(now) }; db.users.push(u); }
      db.session = { uid: u.id, exp: now + USER_TTL }; save();
      return { me: pub(u) };
    }
    if (method === "GET" && path === "/auth/providers") return { telegram: { enabled: true }, google: { enabled: true }, email: { enabled: true }, demo: true };
    if (method === "POST" && path === "/auth/demo") {                     // имитация: настоящий вход (Telegram/Google/почта) работает только на сервере
      var prov = body.provider;
      if (!DEMO_NAMES[prov]) throw Err("bad_provider", "Неизвестный способ входа.");
      var cur = me(now), du = cur && db.users.filter(function (x) { return x.id === cur.id; })[0];
      du = du || db.users.filter(function (x) { return x[prov]; })[0];
      if (!du) { du = { id: db.nextUser++, name: DEMO_NAMES[prov], phone: null, created_ts: Math.floor(now) }; db.users.push(du); }
      du[prov] = true; if (prov === "email" && !du.email) du.email = "demo@example.com";
      db.session = { uid: du.id, exp: now + USER_TTL }; save();
      return { me: pub(du) };
    }
    if (method === "POST" && path === "/logout") { db.session = null; save(); return { ok: true }; }
    if (method === "POST" && path === "/bookings") { var r = createBooking(needUser(now), body, now); if (!r.duplicate) bump(); return r; }
    if (method === "GET" && path === "/my-bookings") {
      var usr = needUser(now);
      return { bookings: db.bookings.filter(function (b) { return b.user_id === usr.id; }).sort(function (a, b) { return b.start_ts - a.start_ts; }).slice(0, 50).map(view) };
    }
    if (method === "POST" && (m = path.match(/^\/bookings\/(\d+)\/cancel$/))) { var c = cancelByClient(+m[1], needUser(now).id, now); bump(); return { booking: c }; }
    if (method === "POST" && path === "/admin/login") {
      if (typeof body.password !== "string" || body.password !== ADMIN_PASSWORD) throw Err("denied", "Неверный пароль.", 403);
      db.admin = { exp: now + ADMIN_TTL }; save(); return { ok: true };
    }
    if (method === "POST" && path === "/admin/logout") { db.admin = null; save(); return { ok: true }; }
    if (path.indexOf("/admin/") === 0 || path === "/admin") {
      if (!isAdmin(now)) throw Err("denied", "Админка только для владельца.", 403);
      if (method === "GET" && path === "/admin/me") return { ok: true };
      if (method === "GET" && path === "/admin/day") return dayOverview(query.date, now);
      if (method === "POST" && (m = path.match(/^\/admin\/bookings\/(\d+)\/cancel$/))) { var cb = cancelBooking(+m[1], now); bump(); return { booking: cb }; }
      if (method === "DELETE" && (m = path.match(/^\/admin\/bookings\/(\d+)$/))) {
        var b = db.bookings.filter(function (x) { return x.id === +m[1]; })[0];
        if (!b) throw Err("no_booking", "Такой брони нет.", 404);
        if (b.status !== "canceled") throw Err("active", "Стереть можно только отменённую бронь. Подтверждённые остаются в истории.", 409);
        db.bookings = db.bookings.filter(function (x) { return x !== b; }); bump(); return { ok: true };
      }
      if (method === "POST" && path === "/admin/clear") { var n = db.bookings.length; db.bookings = db.bookings.filter(function (x) { return x.status !== "canceled"; }); bump(); return { removed: n - db.bookings.length }; }
      if (method === "PATCH" && (m = path.match(/^\/admin\/zones\/([^/]+)$/))) {
        var p = body.price;
        if (typeof p !== "number" || Math.floor(p) !== p || p < 1 || p > 1000) throw Err("bad_price", "Цена за час — целое число от 1 до 1000.");
        getZone(m[1]).price = p; bump(); return { ok: true };
      }
    }
    throw Err("not_found", "Не найдено.", 404);
  }

  /* ---------- подмена fetch для адресов /api ---------- */
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  function reply(data, status) { return new Response(JSON.stringify(data), { status: status || 200, headers: { "content-type": "application/json" } }); }
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var i = url.indexOf("/api");
    if (i < 0 || url.indexOf("://") > 0 && url.indexOf(location.host) < 0 && location.protocol !== "file:") return realFetch ? realFetch(input, init) : Promise.reject(new Error("fetch"));
    var rest = url.slice(i + 4), q = rest.indexOf("?"), path = q < 0 ? rest : rest.slice(0, q), query = {};
    if (q >= 0) rest.slice(q + 1).split("&").forEach(function (kv) { var a = kv.split("="); query[decodeURIComponent(a[0])] = decodeURIComponent(a[1] || ""); });
    var method = ((init && init.method) || "GET").toUpperCase(), body = {};
    try { body = init && init.body ? JSON.parse(init.body) : {}; } catch (e) { body = {}; }
    load();                                                    // всегда читаем свежее состояние (вдруг другая вкладка изменила)
    if (method === "GET" && path === "/wait") return wait(query.since === undefined ? null : parseInt(query.since, 10)).then(function (d) { return reply(d); });
    return new Promise(function (resolve) {
      setTimeout(function () {                                 // небольшая «сетевая» пауза, как у настоящего сервера
        try { resolve(reply(route(method, path, query, body))); }
        catch (e) { resolve(reply({ error: e.message || "Ошибка", code: e.code }, e.status || 500)); }
      }, 60);
    });
  };
  load();

  /* ---------- пометки интерфейса ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    var n = document.getElementById("demoNote"); if (n) n.hidden = false;
    var h = document.getElementById("demoHint"); if (h) h.hidden = false;
    document.documentElement.classList.add("is-demo");
  });
})();
