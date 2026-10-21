// Ô chuyển khối ở chân menu (thẻ details): bấm ra ngoài hoặc nhấn Esc thì đóng.
(function () {
  function dong(e) {
    document.querySelectorAll(".khoi-doi[open]").forEach(function (d) {
      if (!e || e.type === "keydown" || !d.contains(e.target)) d.removeAttribute("open");
    });
  }
  document.addEventListener("click", dong);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") dong(e); });
})();
