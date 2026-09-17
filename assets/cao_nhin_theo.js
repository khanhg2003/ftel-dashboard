// Con cáo Mây (trợ lý AI): hai con ngươi nhìn theo con trỏ chuột ở bất kỳ đâu trên trang.
(function () {
  var x = -1, y = -1, cho = false;
  function ve() {
    cho = false;
    document.querySelectorAll('svg.cao').forEach(function (svg) {
      var r = svg.getBoundingClientRect();
      if (!r.width) { return; }
      svg.querySelectorAll('.cao-nguoi').forEach(function (g) {
        var cx = r.left + (+g.dataset.cx / 64) * r.width, cy = r.top + (+g.dataset.cy / 64) * r.height;
        var dx = x - cx, dy = y - cy, d = Math.hypot(dx, dy) || 1, m = Math.min(2.3, d / 30);
        g.setAttribute('transform', 'translate(' + (dx / d * m).toFixed(2) + ' ' + (dy / d * m).toFixed(2) + ')');
      });
    });
  }
  document.addEventListener('pointermove', function (e) {
    x = e.clientX; y = e.clientY;
    if (!cho) { cho = true; requestAnimationFrame(ve); }
  }, {passive: true});
})();
