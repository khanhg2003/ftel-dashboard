/* =====================================================================
   Ctrl + Shift + Z = làm lại ô vừa lùi, ở các bảng nhập liệu (Nhập tồn, Báo cáo ngày).

   ag-grid tự nhận Ctrl + Z (lùi lại) và Ctrl + Y (làm lại), nhưng người dùng quen
   Ctrl + Shift + Z của Word / Excel nên gõ Ctrl + Y không ai nghĩ ra. File này gắn thêm
   đúng một phím tắt đó, dẫn về cùng lệnh làm lại của ag-grid - chủ app chốt 27/09/2026.

   Chạy cho mọi bảng có bật undo, không phải sửa từng trang.
   ===================================================================== */
(function () {
    function bangDangGo(el) {
        const luoi = el && el.closest ? el.closest('.ag-root-wrapper') : null;
        if (!luoi) { return null; }
        const goc = luoi.closest('[id]');
        return goc ? goc.id : null;
    }

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'z' && e.key !== 'Z') { return; }
        if (!e.shiftKey || !(e.ctrlKey || e.metaKey)) { return; }
        const gid = bangDangGo(e.target);
        if (!gid || !window.dash_ag_grid || !window.dash_ag_grid.getApi) { return; }
        let api = null;
        try { api = window.dash_ag_grid.getApi(gid); } catch (err) { return; }
        if (!api || !api.redoCellEditing) { return; }
        // chỉ chặn phím khi bảng này thật sự có bật lùi / làm lại
        if (!api.getGridOption || !api.getGridOption('undoRedoCellEditing')) { return; }
        e.preventDefault();
        api.redoCellEditing();
    }, true);
})();
