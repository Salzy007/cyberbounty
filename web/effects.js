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
})();
