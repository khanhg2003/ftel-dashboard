/* Thuyết trình AI (trang /thuyettrinh): đọc to slide bằng GIỌNG AI TIẾNG VIỆT (Gemini, máy chủ tạo từng câu, người nghe chọn giọng), hiện PHỤ ĐỀ từng câu cạnh hình con cáo, tự chuyển slide, nghe giọng nói để tạo bài / ra lệnh / đặt câu hỏi.
   Nghe dùng Web Speech API của trình duyệt (miễn phí, âm thanh không gửi lên máy chủ: chỉ chữ đã nhận dạng được gửi đi như một yêu cầu hoặc câu hỏi gõ tay). Mọi nút là nút Dash; ở đây chỉ bấm hộ và đặt giá trị ô nhập. */
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
  function loiHien() { var e = el("tt-loi-hien"); return e ? e.textContent : ""; }

  /* ---- phụ đề: chip trạng thái, câu người dùng vừa yêu cầu / hỏi, câu đang đọc */
  function chip(chu, kieu) { var e = el("tt-chip"); if (e) { e.textContent = chu; e.className = "tt-chip " + (kieu || ""); } }
  function yeuCau(chu) { var e = el("tt-yc-hien"); if (e) e.textContent = chu ? "🗣 " + chu : ""; }
  function phuDe(chu) { var e = el("tt-phu-de-chu"); if (e) e.textContent = chu || ""; }
  function veNut() {
    var b = el("tt-phat"), m = el("tt-mic"), f = el("tt-phu-de");
    if (b) b.textContent = TT.phat ? "⏸ Tạm dừng" : "▶ Phát";
    if (m) m.classList.toggle("dang-nghe", TT.dangNghe);
    if (f) f.classList.toggle("dang-noi", TT.phat);
  }

  /* ---- giọng đọc: CHỈ giọng AI tiếng Việt (Gemini) do máy chủ tạo, người nghe chọn ở bảng "Giọng của Fox" (nhớ trên máy này). Không dùng giọng của trình duyệt: máy hay không có giọng Việt và đọc bằng giọng nước ngoài. */
  var GIONG_MAC_DINH = "Sulafat";
  var MAU_THU = "Dạ, em là Fox, trợ lý của FTEL Đà Nẵng. Hôm nay chi nhánh mình đạt một nghìn bốn trăm ba mươi tám online, phòng IBB 7 đang dẫn đầu. Anh cần em báo cáo thêm gì không ạ?";
  function giongDangDung() { try { return localStorage.getItem("tt-giong") || GIONG_MAC_DINH; } catch (e) { return GIONG_MAC_DINH; } }
  function veGiong() {
    var d = giongDangDung();
    document.querySelectorAll(".tt-gv").forEach(function (g) {
      var la = g.getAttribute("data-giong") === d, t = g.querySelector(".tt-gv-dang");
      g.classList.toggle("dang-dung", la);
      if (t) t.style.display = la ? "" : "none";
    });
  }
  function baoGiong(chu, kieu) { var e = el("tt-gv-bao"); if (e) { e.textContent = chu || ""; e.className = "tt-gv-bao" + (kieu ? " " + kieu : ""); } bao(chu); }
  function datGiong(ten) { try { localStorage.setItem("tt-giong", ten); } catch (e) { /* bỏ qua */ } veGiong(); baoGiong("Đã chọn giọng " + ten + ". Giọng này dùng từ câu đọc tiếp theo.", "ok"); }
  /* Mở khoá phát âm thanh ngay trong lúc bấm (một số trình duyệt chặn phát tiếng sau khi chờ mạng): cho phần tử audio phát một đoạn im lặng rồi dùng lại chính nó. */
  var IM_LANG = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
  function moKhoa(a) { try { a.src = IM_LANG; var p = a.play(); if (p && p.catch) p.catch(function () { /* bỏ qua */ }); } catch (e) { /* bỏ qua */ } }

  function dung() {
    TT.ma++;
    clearTimeout(TT.hen);
    [TT.am, TT.thu].forEach(function (a) { if (a) { a.onended = null; a.onerror = null; try { a.pause(); } catch (e) { /* bỏ qua */ } } });
  }

  /* xin âm thanh từng câu (nhớ trong trang, xin sẵn các câu kế tiếp để không bị ngắt quãng) */
  function layAm(chu, giong) {
    TT.dem = TT.dem || {};
    var kh = giong + "|" + chu;
    if (!TT.dem[kh]) {
      var p = fetch("/api/thuyet-trinh/doc", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chu: chu, giong: giong }), credentials: "same-origin" })
        .then(function (r) {
          if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.loi || ("Lỗi " + r.status)); });
          return r.blob();
        })
        .then(function (b) { return URL.createObjectURL(b); });
      p.catch(function () { delete TT.dem[kh]; });
      TT.dem[kh] = p;
      var ks = Object.keys(TT.dem);
      if (ks.length > 120) delete TT.dem[ks[0]];
    }
    return TT.dem[kh];
  }

  function tachCau(chu) { return (chu || "").split(/(?<=[.!?])\s+/).map(function (c) { return c.trim(); }).filter(Boolean); }

  /* Chưa đọc được (chưa có mã Gemini, lỗi mạng...): vẫn chạy bài theo nhịp chữ, mỗi câu hiện đủ lâu để đọc, và báo lý do. */
  function noiIm(cau, dep, xong, ma) {
    var k = 0;
    function tiep() {
      if (ma !== TT.ma) return;
      if (k >= cau.length) { if (xong) xong(); return; }
      var i = k++;
      phuDe(dep[i]);
      TT.hen = setTimeout(tiep, Math.max(1500, cau[i].length * 70 / tocDo()));
    }
    tiep();
  }

  /* Đọc từng câu và hiện đúng câu đó làm phụ đề. `hien` là bản chữ đẹp để hiển thị (cùng số câu với bản đọc thì dùng). `xong` chạy khi đọc hết. */
  function noi(chu, xong, hien) {
    if (!chu) { if (xong) xong(); return; }
    dung();
    var ma = TT.ma, cau = tachCau(chu), dep = tachCau(hien), k = 0, giong = giongDangDung();
    if (dep.length !== cau.length) dep = cau;
    function lui(i, e) {
      bao("Chưa đọc được bằng giọng " + giong + ": " + ((e && e.message) || "lỗi") + " Bài vẫn chạy theo phụ đề.");
      noiIm(cau.slice(i), dep.slice(i), xong, ma);
    }
    function tiep() {
      if (ma !== TT.ma) return;
      if (k >= cau.length) { if (xong) xong(); return; }
      var i = k++;
      phuDe(dep[i]);
      for (var n = 1; n <= 2; n++) if (i + n < cau.length) layAm(cau[i + n], giong).catch(function () { /* lỗi sẽ báo khi tới câu đó */ });
      layAm(cau[i], giong).then(function (url) {
        if (ma !== TT.ma) return;
        var a = TT.am || (TT.am = new Audio());
        a.src = url; a.defaultPlaybackRate = a.playbackRate = tocDo();
        a.onended = tiep; a.onerror = function () { lui(i, new Error("không phát được âm thanh.")); };
        var p = a.play();
        if (p && p.catch) p.catch(function () { if (ma === TT.ma) lui(i, new Error("trình duyệt chặn phát âm thanh.")); });
      }).catch(function (e) { if (ma === TT.ma) lui(i, e); });
    }
    bao("Đang đọc bằng giọng " + giong + ".");
    tiep();
  }

  function ngheThu(ten, nut) {
    dung(); TT.phat = false; veNut();
    var a = TT.thu || (TT.thu = new Audio()), chu = nut ? nut.textContent : "";
    moKhoa(a);
    function xong() { if (nut) { nut.disabled = false; nut.textContent = chu; } }
    if (nut) { nut.disabled = true; nut.textContent = "Đang tạo…"; }
    baoGiong("Đang tạo giọng " + ten + " (lần đầu mất khoảng 8 giây)…");
    layAm(MAU_THU, ten).then(function (url) {
      xong();
      a.onended = function () { baoGiong("Thấy giọng " + ten + " hợp thì bấm “Dùng giọng này”.", "ok"); };
      a.onerror = function () { baoGiong("Không phát được âm thanh của giọng " + ten + ". Kiểm tra loa hoặc âm lượng của trình duyệt.", "loi"); };
      a.src = url; a.playbackRate = tocDo();
      var p = a.play();
      if (p && p.catch) p.catch(function (e) { baoGiong("Trình duyệt không cho phát âm thanh (" + ((e && e.name) || "lỗi") + "). Bấm Nghe thử lần nữa.", "loi"); });
      baoGiong("Đang phát giọng " + ten + "…", "ok");
    }).catch(function (e) { xong(); baoGiong("Chưa nghe thử được giọng " + ten + ": " + ((e && e.message) || "lỗi"), "loi"); });
  }

  function xongSlide() {
    var tiep = el("tt-tiep");
    if (TT.phat && tuChuyen() && tiep && !tiep.disabled) { bam("tt-tiep"); return; }
    TT.phat = false; veNut();
    chip(tiep && tiep.disabled ? "Em đã thuyết trình xong. Anh có thể hỏi thêm." : "Đã dừng. Bấm Phát hoặc nói “đọc tiếp”.", "dung");
  }

  function phatHoacDung() {
    if (!coBai()) { bam("tt-tao"); return; }
    if (TT.phat) { dung(); TT.phat = false; veNut(); chip("Đã tạm dừng. Bấm Phát hoặc nói “đọc tiếp”.", "dung"); return; }
    TT.phat = true; veNut(); chip("Em đang thuyết trình…", "noi"); noi(loiHienTai(), xongSlide, loiHien());
  }

  /* ---- lệnh bằng giọng nói. `phanTich` là hàm thuần (có test bằng Node): chưa có bài thì mọi câu là YÊU CẦU tạo bài; có bài rồi thì câu ngắn khớp lệnh là lệnh, câu bắt đầu bằng
     "thuyết trình / báo cáo / tạo bài" là yêu cầu bài mới, còn lại là câu hỏi cho AI. */
  function phanTich(chu, coBaiRoi) {
    var n = boDau(chu), tu = n.split(/\s+/).length, m;
    if (!coBaiRoi) return { lenh: "tao", chu: chu };
    if (/^(thuyet trinh|bao cao|tao bai|lam bai|trinh bay)\b/.test(n) && tu >= 3) return { lenh: "tao", chu: chu };
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

  function taoTuYeuCau(chu) { yeuCau(chu); datGiaTri("tt-yeu-cau", chu); setTimeout(function () { bam("tt-tao"); }, 80); }

  function xuLy(chu) {
    var l = phanTich(chu, coBai());
    if (l.lenh === "tao") taoTuYeuCau(l.chu);
    else if (l.lenh === "slide") datGiaTri("tt-nhay", l.so + ":" + Date.now());
    else if (l.lenh === "phat") { if (!TT.phat) phatHoacDung(); }
    else if (l.lenh === "dung") { dung(); TT.phat = false; veNut(); chip("Đã tạm dừng. Bấm Phát hoặc nói “đọc tiếp”.", "dung"); }
    else if (l.lenh === "lai") { TT.phat = true; veNut(); chip("Em đang thuyết trình…", "noi"); noi(loiHienTai(), xongSlide, loiHien()); }
    else if (l.lenh === "tiep") bam("tt-tiep");
    else if (l.lenh === "lui") bam("tt-lui");
    else {
      dung(); TT.phat = false; veNut(); yeuCau(l.chu); chip("Em đang trả lời…", "nghi");
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
    r.onerror = function (e) { chip("Sẵn sàng", ""); bao(e.error === "not-allowed" ? "Trình duyệt chưa được cấp quyền dùng micro cho trang này." : "Chưa nghe rõ, bạn bấm mic và nói lại nhé."); };
    r.onend = function () { TT.dangNghe = false; veNut(); };
    TT.nghe = r; TT.dangNghe = true; veNut(); chip("Em đang nghe anh nói…", "nghe"); bao(coBai() ? "Đang nghe… hãy nói lệnh hoặc câu hỏi." : "Đang nghe… hãy nói yêu cầu, ví dụ “phân tích phòng IBB7”.");
    try { r.start(); } catch (e) { TT.dangNghe = false; veNut(); }
  }

  /* ---- sự kiện: bấm trên toàn trang (nút do Dash dựng lại nên gắn ở document) */
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b || !b.id || b.id.indexOf("tt-") !== 0) return;
    if (b.id === "tt-phat") phatHoacDung();
    else if (b.id === "tt-mic") nghe();
    else if (b.id === "tt-tao") {
      dung(); TT.phat = false; TT.tuPhat = true; veNut(); chip("Em đang chuẩn bị bài thuyết trình…", "nghi");
      var y = el("tt-yeu-cau"); yeuCau(y && y.value ? y.value : "Báo cáo toàn bộ chi nhánh");
      phuDe("Đang dựng slide và viết lời thuyết trình, anh chờ khoảng nửa phút…");
    }
    else if (b.id === "tt-lui" || b.id === "tt-tiep") { if (e.isTrusted) dung(); }
    else if (b.id === "tt-hoi") { dung(); TT.phat = false; veNut(); var q = el("tt-cau-hoi"); if (q && q.value) yeuCau(q.value); chip("Em đang trả lời…", "nghi"); }
    else if (b.id === "tt-toan-man") { var k = el("tt-khung"); if (k && k.requestFullscreen) k.requestFullscreen(); }
  }, true);

  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest(".tt-gv-nghe, .tt-gv-dung") : null;
    if (!b) return;
    var ten = b.getAttribute("data-giong");
    if (b.classList.contains("tt-gv-nghe")) ngheThu(ten, b); else datGiong(ten);
  });
  if (window.MutationObserver) new MutationObserver(function () {
    var d = el("tt-giong-ds");
    if (d && !d.getAttribute("data-da-ve")) { d.setAttribute("data-da-ve", "1"); veGiong(); }
  }).observe(document.documentElement, { childList: true, subtree: true });

  document.addEventListener("keydown", function (e) {
    if (!el("tt-khung")) return;
    var o = e.target && e.target.tagName;
    if (o === "INPUT" || o === "TEXTAREA" || o === "SELECT") {
      if (e.key === "Enter" && e.target.id === "tt-cau-hoi") { dung(); TT.phat = false; veNut(); if (e.target.value) yeuCau(e.target.value); chip("Em đang trả lời…", "nghi"); }
      if (e.key === "Enter" && e.target.id === "tt-yeu-cau") { dung(); TT.phat = false; TT.tuPhat = true; veNut(); chip("Em đang chuẩn bị bài thuyết trình…", "nghi"); yeuCau(e.target.value || "Báo cáo toàn bộ chi nhánh"); }
      return;
    }
    if (e.key === "ArrowRight") bam("tt-tiep");
    else if (e.key === "ArrowLeft") bam("tt-lui");
    else if (e.key === " ") { e.preventDefault(); phatHoacDung(); }
  });


  window.dash_clientside = Object.assign(window.dash_clientside || {}, {
    tt: {
      phanTich: phanTich,
      /* slide mới hiện ra: đang ở chế độ phát (hoặc vừa tạo bài xong) thì đọc luôn */
      noiSlide: function (chu) {
        if (TT.tuPhat && chu) { TT.tuPhat = false; TT.phat = true; }
        veNut();
        if (TT.phat && chu) { chip("Em đang thuyết trình…", "noi"); noi(chu, xongSlide, loiHien()); }
        else if (chu) { phuDe(loiHien()); }
        return window.dash_clientside.no_update;
      },
      /* câu trả lời của AI về slide: đọc to rồi dừng ở đó (bấm "Phát" / nói "đọc tiếp" để nghe tiếp bài) */
      noiTraLoi: function (du_lieu) {
        if (du_lieu && du_lieu.text) {
          TT.phat = false; veNut(); chip("Em đang trả lời…", "noi");
          noi(du_lieu.text, function () { chip("Anh hỏi tiếp hoặc nói “đọc tiếp”.", "dung"); }, du_lieu.hien);
        }
        return window.dash_clientside.no_update;
      }
    }
  });
})();
