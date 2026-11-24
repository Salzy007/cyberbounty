/* Игры клуба — ОДИН список: из него строятся и бегущая строка под героем, и раздел «Игры» с карточками и окном.
   Порядок и названия меняйте только здесь. cover: "файл.jpg" в img/games/ — обложка (см. credits.html); если null — карточка показывает название на плашке. */
(function () {
  var GAMES = [
    { id: "cs2", name: "CS2", genre: "Тактический шутер", mode: "5 на 5, командная игра", players: "от 1 до 5", platform: "ПК", zones: "Standard, VIP, Tournament", hue: 28, cover: "cs2.webp",
      text: "Классика командных шутеров: раунды, экономика и точные выстрелы. Для тренировок и турниров у нас стоят мониторы 240 Гц и мыши без задержки." },
    { id: "dota2", name: "Dota 2", genre: "MOBA", mode: "5 на 5, командная игра", players: "от 1 до 5", platform: "ПК", zones: "Standard, VIP, Tournament", hue: 8, cover: "dota2.webp",
      text: "Долгие матчи, героев больше сотни и тактика на каждую минуту. Берите друзей и занимайте соседние места: всей командой играть удобнее рядом." },
    { id: "valorant", name: "Valorant", genre: "Тактический шутер", mode: "5 на 5, командная игра", players: "от 1 до 5", platform: "ПК", zones: "Standard, VIP, Tournament", hue: 350, cover: "valorant.webp",
      text: "Шутер со способностями агентов: быстрые раунды и командная работа. Высокая частота кадров на наших ПК делает прицеливание заметно легче." },
    { id: "fortnite", name: "Fortnite", genre: "Королевская битва", mode: "соло, дуэт, отряд", players: "от 1 до 4", platform: "ПК, PlayStation 5", zones: "Standard, VIP, PS5 Lounge", hue: 265, cover: "fortnite.webp",
      text: "Построил, прыгнул, победил. Можно играть на ПК или развалиться на диване с геймпадом в зоне PS5 Lounge, а друзей позвать в один отряд." },
    { id: "apex", name: "Apex Legends", genre: "Королевская битва", mode: "отряд из трёх", players: "от 1 до 3", platform: "ПК, PlayStation 5", zones: "Standard, VIP, PS5 Lounge", hue: 12, cover: "apex.webp",
      text: "Быстрый шутер с героями и умениями. Отряды по три человека, динамичное движение и бои на каждом шагу." },
    { id: "lol", name: "League of Legends", genre: "MOBA", mode: "5 на 5, командная игра", players: "от 1 до 5", platform: "ПК", zones: "Standard, VIP, Tournament", hue: 200, cover: "lol.webp",
      text: "Одна из самых популярных MOBA: чемпионы, линии и командные схватки. На нашем Tournament-столе удобно собрать команду из пяти." },
    { id: "eafc", name: "EA FC", genre: "Футбольный симулятор", mode: "один на один или команда", players: "от 1 до 4", platform: "PlayStation 5, ПК", zones: "PS5 Lounge, Standard", hue: 150, cover: "eafc.webp",
      text: "Футбол с друзьями на большом экране: дуэли на диване, турниры по вечерам и ничья, которой никто не хотел." },
    { id: "gta5", name: "GTA V", genre: "Открытый мир", mode: "одиночная сюжетка и онлайн", players: "от 1 до 4", platform: "ПК, PlayStation 5", zones: "Standard, VIP, PS5 Lounge", hue: 120, cover: "gta5.webp",
      text: "Огромный город, сюжет и свободная игра онлайн с друзьями. Ехать некуда торопиться: сядьте в VIP-кресло и выберите, чем заняться." },
    { id: "rocket", name: "Rocket League", genre: "Автофутбол", mode: "1 на 1, 2 на 2, 3 на 3", players: "от 1 до 6", platform: "PlayStation 5, ПК", zones: "PS5 Lounge, Standard", hue: 215, cover: "rocket.webp",
      text: "Футбол на машинах с ракетными ускорителями. Правила простые, матчи короткие, а играть вдвоём на одном диване особенно весело." },
    { id: "ow2", name: "Overwatch 2", genre: "Командный шутер", mode: "5 на 5, командная игра", players: "от 1 до 5", platform: "ПК, PlayStation 5", zones: "Standard, VIP, PS5 Lounge", hue: 35, cover: "ow2.webp",
      text: "Герои с разными ролями: танки, поддержка и урон. Сыгранная команда за соседними местами выигрывает намного чаще." }
  ];
  window.CB_GAMES = GAMES;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };

  /* бегущая строка: тот же список, дважды подряд для бесшовной петли */
  var track = $(".ticker__track");
  if (track) track.innerHTML = GAMES.concat(GAMES).map(function (g) { return '<span data-game="' + g.id + '">' + esc(g.name) + "</span>"; }).join("");

  /* обложка: если файл есть — картинка, иначе плашка с названием */
  function art(g, big) {
    if (g.cover) return '<img decoding="async" src="img/games/' + g.cover + '" alt="Обложка игры ' + esc(g.name) + '"' + (big ? "" : ' loading="lazy"') + ">";
    return '<span class="gart__plate" style="--h:' + g.hue + '"><b>' + esc(g.name) + "</b></span>";
  }
  var grid = $("#gamesGrid");
  if (grid) grid.innerHTML = GAMES.map(function (g) {
    return '<button class="gcard reveal" type="button" data-game="' + g.id + '" aria-label="Об игре ' + esc(g.name) + '"><span class="gart">' + art(g) + '</span><span class="gcard__t"><b>' + esc(g.cover ? g.name : g.genre) + "</b><small>" + esc(g.cover ? g.genre : g.platform) + "</small></span></button>";
  }).join("");

  function open(id) {
    var g = GAMES.filter(function (x) { return x.id === id; })[0], m = $("#mGame");
    if (!g || !m) return;
    $("#gmArt").innerHTML = art(g, true);
    $("#gmT").textContent = g.name;
    $("#gmGenre").textContent = g.genre;
    $("#gmText").textContent = g.text;
    $("#gmFacts").innerHTML = [["Режим", g.mode], ["Игроков", g.players], ["Платформа", g.platform], ["Где у нас", g.zones]].map(function (r) { return "<div><dt>" + r[0] + "</dt><dd>" + esc(r[1]) + "</dd></div>"; }).join("");
    $(".modal__card", m).scrollTop = 0;
    openModal(m);
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-game]");
    if (t) open(t.dataset.game);
  });
  var go = $("#gmBook");
  if (go) go.addEventListener("click", function () { closeModal($("#mGame")); });
})();
