/* =====================================================================
   Tiết kiệm CPU máy chủ: trang Báo cáo ngày tự hỏi máy chủ mỗi NHIP_MS (dcc.Interval "bn-nhip").
   Tab đang ẩn (khoá màn hình, chuyển app, sang tab khác) thì tắt nhịp đó; quay lại thì bật và nạp ngay một lần,
   để người xem luôn thấy số mới mà máy chủ không phải trả lời những lượt không ai nhìn.
   ===================================================================== */
(function () {
    function chinh() {
        // dcc.Interval không có phần tử DOM, nên nhận ra trang bằng bảng của nó
        if (!document.getElementById('bn-luoi') || !window.dash_clientside) { return; }
        const an = document.hidden;
        const gui = {disabled: an};
        if (!an) { gui.n_intervals = Date.now() % 1000000000; }      // đổi giá trị để callback nạp lại ngay
        window.dash_clientside.set_props('bn-nhip', gui);
    }
    document.addEventListener('visibilitychange', chinh);
})();
