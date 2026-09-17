// Trợ lý AI (con cáo): đầu và mắt nhìn theo chuột, Enter để gửi, bấm câu hỏi gợi ý là gửi luôn.
(function () {
  var x = -1, y = -1, cho = false;
  function ve() {
    cho = false;
    document.querySelectorAll('svg.cao').forEach(function (svg) {
      var r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
      if (!r.width || !vb) { return; }
      var dau = svg.querySelector('.cao-dau');
      if (dau) {       // cổ xoay về phía chuột, đầu nhô nhẹ theo hướng đó
        var hx = x - (r.left + 0.475 * r.width), hy = y - (r.top + 0.55 * r.height), hd = Math.hypot(hx, hy) || 1;
        var gan = Math.min(1, hd / 160);
        dau.style.transform = 'translate(' + (hx / hd * 3 * gan).toFixed(2) + 'px,' + (hy / hd * 2 * gan).toFixed(2) +
          'px) rotate(' + (hx / hd * 18 * gan).toFixed(1) + 'deg)';
      }
      svg.querySelectorAll('.cao-nguoi').forEach(function (g) {
        var cx = r.left + (+g.dataset.cx / vb.width) * r.width, cy = r.top + (+g.dataset.cy / vb.height) * r.height;
        var dx = x - cx, dy = y - cy, d = Math.hypot(dx, dy) || 1, m = Math.min(2.3, d / 30);
        g.setAttribute('transform', 'translate(' + (dx / d * m).toFixed(2) + ' ' + (dy / d * m).toFixed(2) + ')');
      });
    });
  }
  document.addEventListener('pointermove', function (e) {
    x = e.clientX; y = e.clientY;
    if (!cho) { cho = true; requestAnimationFrame(ve); }
  }, {passive: true});

  function gui() { var n = document.getElementById('ai-chat-gui'); if (n) { n.click(); } }
  document.addEventListener('keydown', function (e) {
    if (e.target && e.target.id === 'ai-chat-o' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault(); gui();
    }
  });
  document.addEventListener('click', function (e) {
    var nut = e.target.closest && e.target.closest('.ai-goi-y-cau');
    if (nut) { window.__aiCau = nut.dataset.cau || nut.innerText; gui(); }
  });
})();
