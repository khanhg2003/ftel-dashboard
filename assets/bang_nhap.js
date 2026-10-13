/* =====================================================================
   Bảng nhập Báo cáo ngày: không để số sale vừa gõ "nhảy về 0" (chủ app báo 13/10/2026).

   Ba việc, đều ở trình duyệt:
   1. SỔ CHỜ LƯU: mỗi ô vừa gõ được ghi vào sổ cho tới khi máy chủ báo đã xử lý (`bn-da-luu.xong`). Quá 8 giây chưa thấy báo thì gửi lại
      (tối đa 4 lần, cách nhau dãn dần; gửi lại cùng một số nên không sợ lưu đôi). Hết lượt vẫn chưa được thì hiện dòng đỏ "Chưa lưu được N ô", bấm là thử lại.
   2. BẢO VỆ Ô ĐANG CHỜ: số máy chủ gửi về để làm mới bảng (nhịp tự nạp, vá dòng sau khi lưu) KHÔNG được ghi đè lên dòng còn ô đang chờ lưu hay
      đang gõ, kẻo số cũ trong database đè mất số vừa gõ trên màn hình (máy chủ chưa kịp lưu thì đọc lại ra số cũ).
   3. BÁO TRẠNG THÁI: dòng nhỏ cạnh tiêu đề bảng "Đang lưu N ô…" / "✓ Đã lưu".
   ===================================================================== */
(function () {
    const COT = ['muc_tieu', 'khtn', 'da_ban', 'onl_sang', 'onl_chieu', 'thuc_hien', 'mt_thang', 'ghi_chu'];
    const CHO_GIAY = 8000, TOI_DA_LAN = 4;                // gửi lại sau 8 giây, rồi 16, 24, 32 (cộng dồn theo số lần)
    const cho = {};                                   // acc_norm -> {cột: {ev, gui_luc, lan}}
    let hen = null, daLuu = 0;

    function dem() {
        return Object.keys(cho).reduce(function (n, a) { return n + Object.keys(cho[a]).length; }, 0);
    }

    function hienChip() {
        const e = document.getElementById('bn-luu-tt');
        if (!e) { return; }
        const n = dem();
        const hong = Object.keys(cho).reduce(function (n2, a) {
            return n2 + Object.keys(cho[a]).filter(function (c) { return cho[a][c].lan >= TOI_DA_LAN && Date.now() - cho[a][c].gui_luc > CHO_GIAY * (TOI_DA_LAN + 1); }).length;
        }, 0);
        if (hong) { e.textContent = 'Chưa lưu được ' + hong + ' ô · bấm để thử lại'; e.className = 'bn-luu-tt loi'; }
        else if (n) { e.textContent = 'Đang lưu ' + n + ' ô…'; e.className = 'bn-luu-tt dang'; }
        else if (daLuu && Date.now() - daLuu < 4000) { e.textContent = '✓ Đã lưu'; e.className = 'bn-luu-tt xong'; }
        else { e.textContent = ''; e.className = 'bn-luu-tt'; }
    }

    function guiLai(p) {
        p.gui_luc = Date.now();
        window.dash_clientside.set_props('bn-luoi', {cellValueChanged: [Object.assign({}, p.ev, {gui_lai: Date.now()})]});
    }

    function nhip() {
        const bay = Date.now();
        Object.keys(cho).forEach(function (a) {
            Object.keys(cho[a]).forEach(function (c) {
                const p = cho[a][c];
                if (bay - p.gui_luc > CHO_GIAY * (p.lan + 1) && p.lan < TOI_DA_LAN) { p.lan += 1; guiLai(p); }
            });
        });
        hienChip();
        if (!dem() && !(daLuu && Date.now() - daLuu < 4000)) { clearInterval(hen); hen = null; }
    }

    function batNhip() { if (!hen) { hen = setInterval(nhip, 1500); } }

    function dangSua(api) {                           // acc_norm của các dòng đang có ô mở để gõ
        const ds = {};
        (api.getEditingCells() || []).forEach(function (c) {
            const node = api.getDisplayedRowAtIndex(c.rowIndex);
            if (node && node.data) { ds[node.data.acc_norm] = true; }
        });
        return ds;
    }

    if (typeof document !== 'undefined') {
        document.addEventListener('click', function (e) {
            if (!e.target.closest || !e.target.closest('#bn-luu-tt.loi')) { return; }
            Object.keys(cho).forEach(function (a) { Object.keys(cho[a]).forEach(function (c) { cho[a][c].lan = 0; guiLai(cho[a][c]); }); });
            hienChip();
        });
        window.addEventListener('beforeunload', function (e) {
            if (dem()) { e.preventDefault(); e.returnValue = ''; }
        });
    }

    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.ftel = Object.assign(window.dash_clientside.ftel || {}, {
        bn_ghi_nho: function (ev) {                   // ô vừa gõ xong: ghi vào sổ chờ lưu
            (Array.isArray(ev) ? ev : ev ? [ev] : []).forEach(function (x) {
                const acc = x.data && x.data.acc_norm;
                if (x.gui_lai || !acc || COT.indexOf(x.colId) < 0) { return; }
                (cho[acc] = cho[acc] || {})[x.colId] = {ev: {colId: x.colId, value: x.value, data: {acc_norm: acc}}, gui_luc: Date.now(), lan: 0};
            });
            batNhip();
            hienChip();
            return window.dash_clientside.no_update;
        },
        bn_xac_nhan: function (luu) {                 // máy chủ báo đã xử lý những ô nào (kể cả ô bị từ chối theo luật): bỏ khỏi sổ
            const xong = luu && luu.xong ? luu.xong : [];
            xong.forEach(function (x) {
                const p = cho[x[0]] && cho[x[0]][x[1]];
                if (p && String(p.ev.value) === String(x[2])) {
                    delete cho[x[0]][x[1]];
                    if (!Object.keys(cho[x[0]]).length) { delete cho[x[0]]; }
                }
            });
            if (xong.length) { daLuu = Date.now(); batNhip(); }
            hienChip();
            return window.dash_clientside.no_update;
        },
        bn_ap_dung: function (d) {                    // làm mới các dòng máy chủ gửi về, trừ dòng đang chờ lưu / đang gõ
            if (!d || !d.rows || !d.rows.length) { return window.dash_clientside.no_update; }
            let con = 40;
            const lam = function () {
                let api = null;
                try { api = window.dash_ag_grid.getApi('bn-luoi'); } catch (e) { api = null; }
                if (!api) { if (con-- > 0) { setTimeout(lam, 100); } return; }
                const sua = dangSua(api);
                const doi = d.rows.filter(function (r) { return !cho[r.acc_norm] && !sua[r.acc_norm]; });
                if (doi.length) { api.applyTransaction({update: doi}); }
            };
            lam();
            return window.dash_clientside.no_update;
        }
    });
})();
