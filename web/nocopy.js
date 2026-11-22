/* запрет копирования текста: выделение, копирование, перетаскивание и меню по правому клику (поля ввода не трогаем) */
(function () {
  var field = function (e) { var t = e.target; return t && t.closest && t.closest("input, textarea, [contenteditable=true]"); };
  ["copy", "cut", "selectstart", "dragstart", "contextmenu"].forEach(function (n) {
    document.addEventListener(n, function (e) { if (!field(e)) e.preventDefault(); });
  });
})();
