/* =====================================================================
   Thanh "tiến độ nhập báo cáo" của trang Báo cáo ngày (app/ui/pages/baocaongay.py → _tien_do): bấm tên người chưa nhập thì cuộn tới
   đúng dòng của người đó trong bảng, nháy dòng và mở sẵn ô đầu tiên để gõ. Bảng nhận dòng theo acc_norm (getRowId = params.data.id).
   ===================================================================== */
(function () {
    function toi(acc) {
        let api = null;
        try { api = window.dash_ag_grid.getApi('bn-luoi'); } catch (e) { api = null; }
        const luoi = document.getElementById('bn-luoi');
        if (!api || !luoi) { return; }
        const nut = api.getRowNode(acc);
        if (!nut) { return; }
        luoi.scrollIntoView({block: 'center', behavior: 'smooth'});
        api.ensureNodeVisible(nut, 'middle');
        api.flashCells({rowNodes: [nut], flashDuration: 1400, fadeDuration: 900});
        setTimeout(function () {
            try { api.startEditingCell({rowIndex: nut.rowIndex, colKey: 'muc_tieu'}); } catch (e) { /* ô không sửa được: thôi */ }
        }, 450);
    }

    if (typeof document !== 'undefined') {
        document.addEventListener('click', function (e) {
            const b = e.target && e.target.closest ? e.target.closest('.bn-td [data-bn-acc]') : null;
            if (b) { toi(b.dataset.bnAcc); }
        });
    }
    if (typeof module !== 'undefined') { module.exports = {toi}; }
})();
