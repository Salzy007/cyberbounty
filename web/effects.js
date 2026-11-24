/* Эффекты сайта: глитч заголовков, наклон карточек, параллакс героя, «Как это работает» по прокрутке,
   искры на местах, молния при брони, искра от касания. Только transform и opacity. */
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const rnd = (a, b) => a + Math.random() * (b - a);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const layer = (style) => { const d = document.createElement("div"); d.className = "fx-el fx-top"; d.style.cssText = style; document.body.append(d); return d; };
  const EASE = "cubic-bezier(.2,.7,.3,1)";

  /* ---- 1. глитч заголовков: один раз при первом появлении ---- */
  const heads = $$(".sec__head h2, .sec--cta h2, #about h2");
  heads.forEach((h) => h.setAttribute("data-t", h.textContent));
  if (!reduce) {
    const io = new IntersectionObserver((es) => es.forEach((en) => {
      if (!en.isIntersecting) return;
      const t = en.target;                                   // один раз за визит на страницу
      t.classList.add("gl-go"); io.unobserve(t);
      setTimeout(() => t.classList.remove("gl-go"), 700);
    }), { threshold: 0.7 });
    heads.forEach((h) => io.observe(h));
  }

  /* ---- 2. наклон карточек к курсору и к касанию ---- */
  const TILT = ".tile, .gcard";
  let cur = null;
  const untilt = (el) => { if (!el) return; el.style.transform = ""; el.style.transition = ""; el.style.transitionDelay = ""; if (el === cur) cur = null; };
  const tilt = (e) => {
    const el = e.target.closest && e.target.closest(TILT);
    if (cur && el !== cur) untilt(cur);
    if (!el || !el.classList.contains("in")) return;
    cur = el;
    const r = el.getBoundingClientRect(), px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    el.style.transitionDelay = "0s"; el.style.transition = "transform .12s ease-out, border-color .3s, box-shadow .3s";
    el.style.transform = `perspective(800px) rotateX(${((.5 - py) * 12).toFixed(2)}deg) rotateY(${((px - .5) * 14).toFixed(2)}deg) translateY(-3px) scale(1.012)`;
    el.style.setProperty("--mx", (px * 100).toFixed(0) + "%"); el.style.setProperty("--my", (py * 100).toFixed(0) + "%");
  };
  if (!reduce) {
    document.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") tilt(e); }, { passive: true });
    document.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse") tilt(e); }, { passive: true });
    ["pointerup", "pointercancel"].forEach((n) => document.addEventListener(n, () => untilt(cur), { passive: true }));
    document.addEventListener("pointerleave", () => untilt(cur));
  }

  /* ---- 3. искры (места, касания) ---- */
  const sparks = (x, y, n = 7, dist = 46) => {
    if (reduce) return;
    const c1 = css("--amber"), c2 = css("--cyan");
    const ring = layer(`left:${x - 14}px;top:${y - 14}px;width:28px;height:28px;border-radius:50%;border:2px solid ${c1};box-shadow:0 0 14px ${c2};`);
    ring.animate({ transform: ["scale(.2)", "scale(2.4)"], opacity: [.95, 0] }, { duration: 520, easing: EASE }).onfinish = () => ring.remove();
    for (let i = 0; i < n; i++) {
      const a = (Math.PI * 2 * i) / n + rnd(-.3, .3), d = rnd(.6, 1) * dist;
      const s = layer(`left:${x - 2}px;top:${y - 2}px;width:4px;height:4px;border-radius:50%;background:${i % 2 ? c1 : "#fff"};box-shadow:0 0 8px ${c2};`);
      s.animate({ transform: ["translate(0,0) scale(1)", `translate(${(Math.cos(a) * d).toFixed(1)}px,${(Math.sin(a) * d).toFixed(1)}px) scale(.2)`], opacity: [1, 0] }, { duration: rnd(380, 560), easing: EASE }).onfinish = () => s.remove();
    }
  };
  document.addEventListener("click", (e) => {                       // место на схеме: искра, когда оно выбрано
    const seat = e.target.closest && e.target.closest(".seat");
    if (!seat || seat.disabled) return;
    setTimeout(() => { if (seat.getAttribute("aria-pressed") === "true") { const r = seat.getBoundingClientRect(); sparks(r.left + r.width / 2, r.top + r.height / 2, 8, 52); } }, 30);
  });
  document.addEventListener("pointerdown", (e) => {                 // касание пальцем: маленькая искра
    if (e.pointerType === "mouse" || reduce) return;
    if (e.target.closest && e.target.closest("input, textarea, select, .modal")) return;
    sparks(e.clientX, e.clientY, 5, 30);
  }, { passive: true });

  /* ---- 5. параллакс героя ---- */
  const hero = $("#hero"), photo = $(".hero__photo"), heroIn = $(".hero__in");
  if (hero && photo && heroIn && !reduce) {
    photo.classList.add("plx");
    let t = false;
    const upd = () => {
      t = false;
      const y = scrollY, h = hero.offsetHeight;
      if (y > h * 1.1) return;
      photo.style.transform = `translate3d(0, ${(y * .22).toFixed(1)}px, 0)`;
      heroIn.style.transform = `translate3d(0, ${(y * .1).toFixed(1)}px, 0)`;
      heroIn.style.opacity = String(Math.max(0, 1 - (y / h) * 1.1).toFixed(3));
    };
    addEventListener("scroll", () => { if (!t) { t = true; requestAnimationFrame(upd); } }, { passive: true });
    upd();
  }


  /* ---- меню: неоновая черта плавно переезжает к активному пункту ---- */
  const nav = $(".nav");
  if (nav) {
    const bar = document.createElement("i"); bar.className = "nav__bar"; nav.append(bar);
    let first = true;
    const place = () => {
      const a = nav.querySelector("a.on");
      if (!a || !a.offsetWidth) { bar.classList.remove("on"); return; }
      const pd = parseFloat(getComputedStyle(a).paddingLeft) || 11;
      const x = a.offsetLeft + pd, w = a.offsetWidth - pd * 2;
      if (first) { bar.style.transition = "none"; }
      bar.style.transform = `translateX(${x}px) scaleX(${(w / 100).toFixed(3)})`;
      bar.classList.add("on");
      if (first) { void bar.offsetWidth; bar.style.transition = ""; first = false; }
    };
    const mo = new MutationObserver(place);                 // следим только за самими пунктами (не за чертой: иначе бесконечный цикл)
    $$("a", nav).forEach((a) => mo.observe(a, { attributes: true, attributeFilter: ["class"] }));
    addEventListener("resize", () => { first = true; place(); });
    place();
  }

  /* ---- прокрутка: лампочка-ползунок с метками разделов, бегущая строка по скорости, шапка вниз/вверх, настроение фона ---- */
  (() => {
    const secs = $$("main > section");
    const NAMES = { hero: "Главная", how: "Как это работает", book: "Бронь", about: "О нас", services: "Услуги", games: "Игры", reviews: "Отзывы", faq: "Вопросы" };
    const MOOD = { how: "cyan", book: "cyan", about: "amber", services: "violet", games: "pink", reviews: "amber", faq: "cyan" };
    const zap = document.createElement("div");
    zap.className = "zap"; zap.setAttribute("aria-hidden", "true");
    zap.innerHTML = '<i class="zap__fill"></i><div class="zap__ticks"></div><i class="zap__tip"><b></b></i><svg class="zap__arc" viewBox="0 0 60 24" preserveAspectRatio="none" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M60 12 L48 6 L40 15 L28 5 L18 14 L6 8"/></svg><span class="zap__label"></span><div class="zap__hit"></div>';
    document.body.append(zap);
    const fill = $(".zap__fill", zap), tip = $(".zap__tip", zap), arc = $(".zap__arc", zap), ticksBox = $(".zap__ticks", zap), label = $(".zap__label", zap), hit = $(".zap__hit", zap);
    const marked = secs.filter((sec) => sec.id && NAMES[sec.id]);
    const ticks = marked.map((sec) => { const t = document.createElement("i"); t.className = "zap__tick"; ticksBox.append(t); return t; });
    const bg = $(".bg");
    if (bg) { const m = document.createElement("div"); m.className = "bg__mood"; bg.append(m); }

    let H = innerHeight, ticking = false, cur = -1, shown = false, lastSH = 0, drag = false, lastY = scrollY, tickY = [];
    const maxScroll = () => document.documentElement.scrollHeight - H;
    const yOf = (p) => 9 + p * (H - 18);
    const layout = () => {
      const max = maxScroll(); lastSH = document.documentElement.scrollHeight;
      tickY = marked.map((sec) => yOf(Math.min(1, Math.max(0, (sec.getBoundingClientRect().top + scrollY) / (max || 1)))));
      ticks.forEach((t, i) => { t.style.transform = `translate3d(0, ${tickY[i].toFixed(1)}px, 0)`; });
    };
    const spark = (y) => {
      if (reduce) return;
      tip.classList.remove("hit"); arc.classList.remove("hit");
      arc.style.transform = `translate3d(0, ${y - 24}px, 0)`;
      void tip.offsetWidth; tip.classList.add("hit"); arc.classList.add("hit");
    };
    const showLabel = (clientY) => {
      let k = 0, best = 1e9;
      tickY.forEach((y, i) => { const d = Math.abs(y - clientY); if (d < best) { best = d; k = i; } });
      if (!marked[k]) return;
      label.textContent = NAMES[marked[k].id];
      label.style.transform = `translate3d(0, ${Math.min(H - 20, Math.max(20, clientY)) - 14}px, 0)`;
      label.classList.add("on");
    };
    // ползунок: тянуть лампочку или кликнуть по линии; рядом с меткой мышью - плавный переход к разделу
    const scrollToY = (clientY) => {
      const p = Math.min(1, Math.max(0, (clientY - 9) / (H - 18)));
      scrollTo({ top: p * maxScroll(), left: 0, behavior: "instant" });
    };
    hit.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const k = tickY.findIndex((y) => Math.abs(y - e.clientY) <= 9);
      if (k >= 0 && e.pointerType === "mouse") { marked[k].scrollIntoView({ behavior: "smooth", block: "start" }); showLabel(e.clientY); return; }
      drag = true; zap.classList.add("drag"); try { hit.setPointerCapture(e.pointerId); } catch (err) {}
      scrollToY(e.clientY); showLabel(e.clientY);
    });
    hit.addEventListener("pointermove", (e) => { if (drag) scrollToY(e.clientY); if (drag || e.pointerType === "mouse") showLabel(e.clientY); });
    const end = () => { drag = false; zap.classList.remove("drag"); setTimeout(() => { if (!drag) label.classList.remove("on"); }, 500); };
    hit.addEventListener("pointerup", end); hit.addEventListener("pointercancel", end);
    hit.addEventListener("pointerleave", () => { if (!drag) label.classList.remove("on"); });

    // бегущая строка: ускоряется от скорости прокрутки, при прокрутке вверх идёт назад
    const track = $(".ticker__track");
    let anim = null, rate = 1, target = 1, loop = 0, lastT = performance.now();
    const tickLoop = () => {
      rate += (target - rate) * .16; target += (1 - target) * .07;
      if (anim) anim.playbackRate = rate;
      if (Math.abs(rate - 1) < .03 && Math.abs(target - 1) < .03) { if (anim) anim.playbackRate = 1; loop = 0; return; }
      loop = requestAnimationFrame(tickLoop);
    };
    const kick = (dy, dt) => {
      if (reduce || !track || Math.abs(dy) < 2) return;
      if (!anim) { anim = track.getAnimations()[0]; if (!anim) return; try { anim.currentTime = (+anim.currentTime || 0) + 1e7; } catch (err) {} }   // запас времени, чтобы идти назад было можно
      target = Math.min(6, Math.max(-3, 1 + (dy / dt) * 3));
      if (!loop) loop = requestAnimationFrame(tickLoop);
    };

    // шапка: прячется при прокрутке вниз, возвращается при прокрутке вверх
    const topbar = $("#top"), menu = $("#menu");
    const header = (y, dy) => {
      if (!topbar || reduce) return;
      const menuOpen = menu && !menu.hidden;
      if (y < 160 || dy < -6 || menuOpen || document.documentElement.classList.contains("lock")) topbar.classList.remove("hide");
      else if (dy > 6) topbar.classList.add("hide");
    };

    const update = () => {
      ticking = false;
      if (document.documentElement.scrollHeight !== lastSH) layout();
      const max = maxScroll(), y = scrollY, p = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0, dy = y - lastY;
      fill.style.transform = `scaleY(${p})`;
      const ty = yOf(p) - 9;
      tip.style.transform = `translate3d(0, ${ty}px, 0)`;
      const on = y > 24; if (on !== shown) { shown = on; zap.classList.toggle("on", on); }
      let idx = -1; const line = H * .4;
      secs.forEach((sec, i) => { if (sec.getBoundingClientRect().top <= line) idx = i; });
      if (idx !== cur) {
        const first = cur === -1; cur = idx;
        const sec = secs[idx]; document.documentElement.dataset.mood = (sec && MOOD[sec.id]) || "";
        const ti = sec ? marked.indexOf(sec) : -1; ticks.forEach((t, i) => t.classList.toggle("on", i === ti));
        if (!first && shown) spark(ty + 9);
      }
      const now = performance.now(); kick(dy, Math.max(8, now - lastT)); lastT = now;
      header(y, dy); lastY = y;
    };
    const req = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    addEventListener("scroll", req, { passive: true });
    addEventListener("resize", () => { H = innerHeight; layout(); req(); });
    addEventListener("load", () => { layout(); req(); });
    layout(); update();
  })();
})();
