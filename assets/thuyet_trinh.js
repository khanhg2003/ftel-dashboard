/* Thuyết trình AI (trang /thuyettrinh): đọc to slide bằng giọng sẵn có của trình duyệt, tự chuyển slide, nghe giọng nói để ra lệnh hoặc đặt câu hỏi.
   Miễn phí (Web Speech API), không gửi âm thanh lên máy chủ: chỉ chữ đã nhận dạng được gửi đi như một câu hỏi gõ tay. Mọi nút là nút Dash; ở đây chỉ bấm hộ và đặt giá trị ô nhập. */
(function () {
  var TT = { phat: false, ma: 0, tuPhat: false, nghe: null, dangNghe: false };
  var SO_CHU = { mot: 1, hai: 2, ba: 3, bon: 4, nam: 5, sau: 6, bay: 7, tam: 8, chin: 9, muoi: 10 };

  function el(id) { return document.getElementById(id); }
  function boDau(s) { return (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase().trim(); }
  function bao(chu) { var e = el("tt-js-bao"); if (e) e.textContent = chu || ""; }
  function bam(id) { var e = el(id); if (e && !e.disabled) e.click(); }
  function datGiaTri(id, v) {
    var e = el(id);
    if (!e) return;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(e, v);
    e.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function tocDo() { var e = el("tt-toc-do"); return e ? parseFloat(e.value) || 1 : 1; }
  function tuChuyen() { var c = document.querySelector("#tt-tu-chuyen input"); return !c || c.checked; }
  function coBai() { return !!document.querySelector("#tt-slide .tt-slide"); }
  function loiHienTai() { var e = el("tt-loi"); return e ? e.textContent : ""; }
  function veNut() {
    var b = el("tt-phat"), m = el("tt-mic");
    if (b) b.textContent = TT.phat ? "⏸ Tạm dừng" : "▶ Phát";
    if (m) m.classList.toggle("dang-nghe", TT.dangNghe);
  }

  function giong() {
    var ds = (window.speechSynthesis ? speechSynthesis.getVoices() : []).filter(function (v) { return /^vi/i.test(v.lang); });
    if (!ds.length) return null;
    var tot = ds.filter(function (v) { return /HoaiMy|NamMinh|Natural|Online/i.test(v.name); })[0];
    return tot || ds[0];
  }
  function kiemTraGiong() {
    if (!window.speechSynthesis) { bao("Trình duyệt này không đọc được chữ thành tiếng. Hãy dùng Chrome hoặc Edge."); return; }
    if (!giong()) bao("Máy này chưa có giọng tiếng Việt, trình duyệt sẽ dùng giọng mặc định. Edge thường có sẵn giọng tiếng Việt tự nhiên.");
  }

  function dung() { TT.ma++; try { speechSynthesis.cancel(); } catch (e) { /* bỏ qua */ } }

  /* Đọc từng câu một: Chrome hay tự ngắt khi đọc một đoạn dài. `xong` chạy khi đọc hết (không chạy nếu bị ngắt). */
  function noi(chu, xong) {
    if (!window.speechSynthesis || !chu) { if (xong) xong(); return; }
    dung();
    var ma = TT.ma, cau = (chu.match(/[^.!?]+[.!?]?/g) || []).map(function (c) { return c.trim(); }).filter(Boolean), k = 0;
    function tiep() {
      if (ma !== TT.ma) return;
      if (k >= cau.length) { if (xong) xong(); return; }
      var u = new SpeechSynthesisUtterance(cau[k++]);
      u.lang = "vi-VN"; u.rate = tocDo();
      var v = giong(); if (v) u.voice = v;
      u.onend = tiep; u.onerror = tiep;
      speechSynthesis.speak(u);
    }
    setTimeout(tiep, 80);
  }

  function xongSlide() {
    var tiep = el("tt-tiep");
    if (TT.phat && tuChuyen() && tiep && !tiep.disabled) { bam("tt-tiep"); return; }
    TT.phat = false; veNut();
  }

  function phatHoacDung() {
    if (!coBai()) { TT.tuPhat = true; bam("tt-tao"); return; }
    if (TT.phat) { dung(); TT.phat = false; veNut(); return; }
    TT.phat = true; veNut(); noi(loiHienTai(), xongSlide);
  }

  /* ---- lệnh bằng giọng nói: câu ngắn khớp lệnh thì chạy lệnh, còn lại là câu hỏi cho AI. `phanTich` là hàm thuần (có test bằng Node). */
  function phanTich(chu, coBaiRoi) {
    var n = boDau(chu), tu = n.split(/\s+/).length, m;
    if (!coBaiRoi) return /(thuyet trinh|bat dau|trinh bay)/.test(n) ? { lenh: "tao" } : { lenh: "chua_co_bai" };
    if (tu <= 7) {
      if ((m = n.match(/slide\s*(so\s*)?(\d+|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)/))) return { lenh: "slide", so: SO_CHU[m[2]] || parseInt(m[2], 10) };
      if (/^(tiep tuc|doc tiep|phat|bat dau lai)/.test(n)) return { lenh: "phat" };
      if (/^(dung|tam dung|nghi|im)/.test(n)) return { lenh: "dung" };
      if (/^(noi lai|doc lai|lai di)/.test(n)) return { lenh: "lai" };
      if (/^(tiep|slide tiep|sang tiep|qua tiep|tiep theo|next)/.test(n)) return { lenh: "tiep" };
      if (/^(lui|quay lai|slide truoc|truoc do|back)/.test(n)) return { lenh: "lui" };
    }
    return { lenh: "hoi", chu: chu };
  }

  function xuLy(chu) {
    var l = phanTich(chu, coBai());
    if (l.lenh === "tao") { TT.tuPhat = true; bam("tt-tao"); }
    else if (l.lenh === "chua_co_bai") bao("Chưa có bài thuyết trình. Nói “thuyết trình” hoặc bấm “Tạo bài thuyết trình” trước.");
    else if (l.lenh === "slide") datGiaTri("tt-nhay", l.so + ":" + Date.now());
    else if (l.lenh === "phat") { if (!TT.phat) phatHoacDung(); }
    else if (l.lenh === "dung") { dung(); TT.phat = false; veNut(); }
    else if (l.lenh === "lai") { TT.phat = true; veNut(); noi(loiHienTai(), xongSlide); }
    else if (l.lenh === "tiep") bam("tt-tiep");
    else if (l.lenh === "lui") bam("tt-lui");
    else {
      dung(); TT.phat = false; veNut();
      datGiaTri("tt-cau-hoi", l.chu);
      setTimeout(function () { bam("tt-hoi"); }, 80);
    }
  }

  function nghe() {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { bao("Trình duyệt này chưa hỗ trợ nghe giọng nói. Hãy dùng Chrome hoặc Edge."); return; }
    if (TT.dangNghe && TT.nghe) { TT.nghe.stop(); return; }
    dung(); TT.phat = false;
    var r = new SR();
    r.lang = "vi-VN"; r.interimResults = false; r.maxAlternatives = 1;
    r.onresult = function (e) { var t = e.results[0][0].transcript; bao("Đã nghe: “" + t + "”"); xuLy(t); };
    r.onerror = function (e) { bao(e.error === "not-allowed" ? "Trình duyệt chưa được cấp quyền dùng micro cho trang này." : "Chưa nghe rõ, bạn bấm mic và nói lại nhé."); };
    r.onend = function () { TT.dangNghe = false; veNut(); };
    TT.nghe = r; TT.dangNghe = true; veNut(); bao("Đang nghe… hãy nói.");
    try { r.start(); } catch (e) { TT.dangNghe = false; veNut(); }
  }

  /* ---- sự kiện: bấm trên toàn trang (nút do Dash dựng lại nên gắn ở document) */
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b || !b.id || b.id.indexOf("tt-") !== 0) return;
    if (b.id === "tt-phat") phatHoacDung();
    else if (b.id === "tt-mic") nghe();
    else if (b.id === "tt-tao") { dung(); TT.phat = false; veNut(); }
    else if (b.id === "tt-lui" || b.id === "tt-tiep") { if (e.isTrusted) { dung(); } }
    else if (b.id === "tt-hoi") { dung(); TT.phat = false; veNut(); }
    else if (b.id === "tt-toan-man") { var k = el("tt-khung"); if (k && k.requestFullscreen) k.requestFullscreen(); }
  }, true);

  document.addEventListener("keydown", function (e) {
    if (!el("tt-khung")) return;
    var o = e.target && e.target.tagName;
    if (o === "INPUT" || o === "TEXTAREA" || o === "SELECT") { if (e.key === "Enter" && e.target.id === "tt-cau-hoi") { dung(); TT.phat = false; veNut(); } return; }
    if (e.key === "ArrowRight") bam("tt-tiep");
    else if (e.key === "ArrowLeft") bam("tt-lui");
    else if (e.key === " ") { e.preventDefault(); phatHoacDung(); }
  });

  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = function () { if (el("tt-khung")) kiemTraGiong(); };

  window.dash_clientside = Object.assign(window.dash_clientside || {}, {
    tt: {
      phanTich: phanTich,
      /* slide mới hiện ra: đang ở chế độ phát thì đọc luôn */
      noiSlide: function (chu) {
        if (TT.tuPhat && chu) { TT.tuPhat = false; TT.phat = true; }
        veNut();
        if (TT.phat && chu) { kiemTraGiong(); noi(chu, xongSlide); }
        return window.dash_clientside.no_update;
      },
      /* câu trả lời của AI về slide: đọc to rồi dừng ở đó (bấm "Phát" / nói "đọc tiếp" để nghe tiếp bài) */
      noiTraLoi: function (du_lieu) {
        if (du_lieu && du_lieu.text) { TT.phat = false; veNut(); noi(du_lieu.text, null); }
        return window.dash_clientside.no_update;
      }
    }
  });
})();
