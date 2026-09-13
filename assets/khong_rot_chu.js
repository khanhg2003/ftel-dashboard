/* =====================================================================
   Tiêu đề cột không bao giờ bị rớt chữ (VD "ONLIN / E", "COMB / O").

   Tiêu đề được phép xuống dòng giữa các TỪ, nhưng không được cắt ngang một từ.
   CSS (style.css) đã chặn việc cắt ngang từ; file này lo phần còn lại: đo từ dài nhất
   trong mỗi tiêu đề, cột nào hẹp hơn từ đó thì nới cột ra vừa đủ.
   Chạy cho MỌI bảng trong app, kể cả bảng mới thêm sau này - không phải sửa từng trang.
   ===================================================================== */
(function () {
    const but = document.createElement('canvas').getContext('2d');

    function tuDaiNhat(el) {
        const cs = getComputedStyle(el);
        but.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
        const gian = parseFloat(cs.letterSpacing) || 0;
        let chu = el.textContent || '';
        if (cs.textTransform === 'uppercase') { chu = chu.toLocaleUpperCase('vi'); }
        return chu.split(/\s+/).filter(Boolean).reduce(function (lon, tu) {
            return Math.max(lon, but.measureText(tu).width + gian * tu.length);
        }, 0);
    }

    async function kiemTra(bang) {
        if (!bang.id || !window.dash_ag_grid || !window.dash_ag_grid.getApiAsync) { return; }
        let api;
        try { api = await window.dash_ag_grid.getApiAsync(bang.id); } catch (e) { return; }
        if (!api || api.isDestroyed && api.isDestroyed()) { return; }
        if (!api.__ftelKhongRotChu) {        // nghe sự kiện của bảng: đổi cột, kéo cột, đổi cỡ
            api.__ftelKhongRotChu = true;
            ['columnResized', 'displayedColumnsChanged', 'newColumnsLoaded', 'gridSizeChanged',
             'firstDataRendered'].forEach(function (su_kien) {
                api.addEventListener(su_kien, function (e) {
                    if (su_kien === 'columnResized' && !e.finished) { return; }
                    lenLich();
                });
            });
        }
        const doi = [];
        bang.querySelectorAll('.ag-header-cell[col-id]').forEach(function (o) {
            const chu = o.querySelector('.ag-header-cell-text');
            const nhan = o.querySelector('.ag-header-cell-label');
            if (!chu || !nhan || !chu.textContent.trim()) { return; }
            // phần icon sắp xếp/lọc (nếu có) chiếm chỗ trong nhãn
            let icon = 0;
            nhan.querySelectorAll('.ag-sort-indicator-container, .ag-header-icon').forEach(function (i) {
                if (i.offsetWidth) { icon += i.offsetWidth; }
            });
            const cho = nhan.clientWidth - icon;
            const can = Math.ceil(tuDaiNhat(chu)) + 2;
            if (cho > 0 && can > cho) {
                const cot = api.getColumn(o.getAttribute('col-id'));
                if (cot) { doi.push({key: cot, newWidth: cot.getActualWidth() + (can - cho)}); }
            }
        });
        if (doi.length) { api.setColumnWidths(doi, true); }
    }

    let cho = null;
    function lenLich() {
        clearTimeout(cho);
        cho = setTimeout(function () {
            document.querySelectorAll('.ag-theme-ftel').forEach(kiemTra);
        }, 120);
    }

    new MutationObserver(function (ds) {
        for (const d of ds) {
            const n = d.target;
            if (n.nodeType === 1 && (n.closest('.ag-header') || n.querySelector && n.querySelector('.ag-header'))) {
                lenLich(); return;
            }
        }
    }).observe(document.documentElement, {childList: true, subtree: true, characterData: true});
    window.addEventListener('resize', lenLich);
})();
