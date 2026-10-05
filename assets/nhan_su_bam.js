/* =====================================================================
   Bấm vào một nhân sự ở BẤT KỲ bảng nào có lớp "nhan-su-bam" -> mở ngăn chi tiết nhân sự (app/ui/ngan_nhan_su.py).

   - Mặc định bấm ĐÚP vào dòng. Lớp "nhan-su-bam-1": bấm một lần (bảng chỉ để xem, như Báo cáo phòng).
   - Lớp "nhan-su-bam-ten": chỉ ô tên mới mở ngăn (bảng nhập liệu: bấm đúp vào ô khác là để sửa ô đó).
   - Màn hình cảm ứng khó bấm đúp nên bấm một lần vào ô tên là mở.
   - Người được chọn lấy từ dữ liệu của dòng (acc_norm, hoặc acc viết thường), ghi vào dcc.Store "ns-mo";
     máy chủ kiểm quyền lại, trình duyệt chỉ báo "ai" và "gợi ý phòng".
   - Phím Esc đóng ngăn.
   ===================================================================== */
(function () {
    const COT_TEN = ['ho_ten', 'ten', 'acc', 'nhan_vien'];

    function nhanSu(e, kieuBam) {
        const o = e.target && e.target.closest ? e.target.closest('.ag-cell') : null;
        if (!o) { return; }
        const luoi = o.closest('.nhan-su-bam');
        if (!luoi || !luoi.id) { return; }
        const la1 = luoi.classList.contains('nhan-su-bam-1');
        const laTen = luoi.classList.contains('nhan-su-bam-ten');
        const cot = o.getAttribute('col-id');
        const camUng = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
        if (kieuBam === 'click' && !la1 && !(camUng && COT_TEN.indexOf(cot) >= 0)) { return; }
        if (kieuBam === 'dblclick' && la1) { return; }          // bảng bấm một lần đã mở ở lần bấm đầu
        if (o.closest('.ag-floating-top, .ag-floating-bottom')) { return; }      // dòng tổng
        const dong = o.closest('.ag-row');
        if (!dong || !window.dash_ag_grid || !window.dash_ag_grid.getApi) { return; }
        let api = null;
        try { api = window.dash_ag_grid.getApi(luoi.id); } catch (err) { return; }
        const nut = api && api.getRowNode ? api.getRowNode(dong.getAttribute('row-id')) : null;
        const d = nut && nut.data;
        // dòng tiêu đề cụm nhân viên ("nhom", Nhập tồn) cũng mở được; dòng tổng thì không
        if (!d || (d.loai_dong && d.loai_dong !== 'data' && d.loai_dong !== 'nhom')) { return; }
        if (laTen && d.loai_dong !== 'nhom' && COT_TEN.indexOf(cot) < 0) { return; }
        const acc = String(d.acc_norm || d.acc || '').trim().toLowerCase();
        if (!acc) { return; }
        window.dash_clientside.set_props('ns-mo', {data: {acc: acc, phong: d.phong_code || null, t: Date.now()}});
    }

    document.addEventListener('dblclick', function (e) { nhanSu(e, 'dblclick'); }, true);
    document.addEventListener('click', function (e) { nhanSu(e, 'click'); }, true);
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') { return; }
        const ngan = document.getElementById('ns-ngan');
        const dong = document.getElementById('ns-ngan-dong');
        if (ngan && dong && ngan.classList.contains('mo')) { dong.click(); }
    });
})();
