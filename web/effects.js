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

  /* ---- 1. глитч заголовков: каждый раз при появлении ---- */
  const heads = $$(".sec__head h2, .sec--cta h2");
  heads.forEach((h) => h.setAttribute("data-t", h.textContent));
  if (!reduce) {
    const io = new IntersectionObserver((es) => es.forEach((en) => {
      if (!en.isIntersecting) return;
      const t = en.target;                                   // каждый раз, когда заголовок появляется на экране
      t.classList.remove("gl-go"); void t.offsetWidth; t.classList.add("gl-go");
      clearTimeout(t._gl); t._gl = setTimeout(() => t.classList.remove("gl-go"), 700);
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

  /* ---- 4. молния при подтверждении брони ---- */
  const jag = (x0, y0, x1, y1, disp, depth) => {
    if (!depth) return [[x0, y0], [x1, y1]];
    const mx = (x0 + x1) / 2 + rnd(-disp, disp), my = (y0 + y1) / 2 + rnd(-disp, disp) * .3;
    return jag(x0, y0, mx, my, disp / 2, depth - 1).slice(0, -1).concat(jag(mx, my, x1, y1, disp / 2, depth - 1));
  };
  window.fxBookingZap = () => {
    if (reduce) return;
    const W = innerWidth, H = innerHeight, c1 = css("--amber"), c2 = css("--cyan");
    const tx = W / 2 + rnd(-.08, .08) * W, ty = H * .42, unit = Math.min(W, 520);
    const main = jag(tx + rnd(-.12, .12) * W, -10, tx, ty, unit * .16, 5);
    const forks = [.3, .55, .75].map((f, k) => { const p = main[Math.round((main.length - 1) * f)]; return jag(p[0], p[1], p[0] + (k % 2 ? 1 : -1) * rnd(.08, .18) * unit, p[1] + rnd(.08, .16) * H, unit * .05, 4); });
    const path = (a) => "M" + a.map((p) => p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" L");
    const all = [[main, 3], ...forks.map((f) => [f, 1.4])];
    const lay = (col, m) => all.map(([a, w]) => `<path d="${path(a)}" fill="none" stroke="${col}" stroke-width="${(w * m).toFixed(1)}" stroke-linejoin="round" stroke-linecap="round"/>`).join("");
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "fx-el fx-top"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.cssText = `left:0;top:0;width:${W}px;height:${H}px;transform-origin:50% 0;`;
    svg.innerHTML = `<defs><filter id="fxz" x="-20%" y="-5%" width="140%" height="110%"><feGaussianBlur stdDeviation="6"/></filter></defs><g filter="url(#fxz)" opacity=".9">${lay(c2, 5)}</g><g>${lay(c1, 2.2)}</g><g>${lay("#fff", 1)}</g>`;
    document.body.append(svg);
    const flash = layer(`left:0;top:0;width:100%;height:100%;background:radial-gradient(circle at ${tx}px ${ty}px, #fff 0, ${c1} 12%, ${c2} 34%, rgba(6,7,13,0) 70%);`);
    svg.animate({ transform: ["scaleY(.08)", "scaleY(1)", "scaleY(1)", "scaleY(1)", "scaleY(1)"], opacity: [0, 1, .4, 1, 0], offset: [0, .12, .28, .45, 1] }, { duration: 640, easing: "linear" }).onfinish = () => svg.remove();
    flash.animate({ opacity: [0, .8, .1, .35, 0], offset: [0, .14, .3, .4, 1] }, { duration: 560, easing: "linear" }).onfinish = () => flash.remove();
    setTimeout(() => sparks(tx, ty, 10, 80), 90);
  };

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

  /* ---- 6. «Как это работает»: шаги листаются прокруткой (экран побольше, телефон остаётся на автозапуске) ---- */
  const how = $("#how"), stage = $("#howStage");
  const pinMQ = matchMedia("(min-width: 901px) and (min-height: 780px)");
  if (how && stage && !reduce) {
    const STEPS = 5;
    let t = false, on = false;
    const setPin = () => {
      const want = pinMQ.matches;
      how.classList.toggle("pin", want); on = want;
      how.style.setProperty("--pin-h", want ? `${(STEPS * 62 + 100)}vh` : "");
    };
    const upd = () => {
      t = false;
      if (!on) return;
      const r = how.getBoundingClientRect(), total = how.offsetHeight - innerHeight;
      if (r.top > 0 || r.bottom < innerHeight) return;               // только пока секция «приколота»
      const p = Math.min(.999, Math.max(0, -r.top / total)), n = Math.floor(p * STEPS);
      stage.dispatchEvent(new CustomEvent("howscroll", { detail: n }));
    };
    pinMQ.addEventListener("change", setPin); setPin();
    addEventListener("scroll", () => { if (!t) { t = true; requestAnimationFrame(upd); } }, { passive: true });
  }

})();
