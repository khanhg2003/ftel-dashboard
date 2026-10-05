/* =====================================================================
   Báo "đang tải" cho MỌI thao tác của app, không phải sửa từng trang.

   Mỗi lần trình duyệt hỏi máy chủ để cập nhật giao diện (Dash gọi /_dash-update-component), file này:
   1. hiện thanh chạy mỏng trên đầu trang + con trỏ chuột "đang chờ" (html.dang-tai);
   2. làm mờ và gắn vòng xoay lên đúng những khối sắp đổi nội dung (thuộc tính data-dang-tai) - bảng, biểu đồ,
      thẻ chỉ số, cả vùng nội dung khi đổi trang. Kiểu dáng ở assets/style.css (mục "Đang tải").

   Chỉ báo sau 150 ms để thao tác nhanh không nháy. Bỏ qua các lượt không phải do người dùng bấm: Interval tự nạp
   lại (Báo cáo ngày) và lưu từng ô đang gõ (cellValueChanged), kẻo bảng nhập liệu mờ đi giữa lúc đang gõ.
   ===================================================================== */
(function () {
    const CHO_MS = 150;
    const THUOC_TINH_DOI_NOI_DUNG = ['children', 'figure', 'rowData', 'columnDefs', 'options', 'className'];
    let dem = 0;
    const theoId = {};                    // id khối -> số lượt đang chờ cập nhật nó

    function batDau(body) {
        let ids = [];
        let tuDong = false;
        try {
            const j = JSON.parse(body);
            const ra = Array.isArray(j.outputs) ? j.outputs : (j.outputs ? [j.outputs] : []);
            ids = ra.filter(function (o) {
                return typeof o.id === 'string' && THUOC_TINH_DOI_NOI_DUNG.indexOf(o.property) >= 0;
            }).map(function (o) { return o.id; });
            tuDong = (j.changedPropIds || []).some(function (p) {
                return /\.(n_intervals|cellValueChanged)$/.test(p);
            });
        } catch (e) { /* không đọc được thì chỉ hiện thanh chạy */ }
        if (tuDong) { return function () {}; }
        dem += 1;
        const hen = setTimeout(function () {
            document.documentElement.classList.add('dang-tai');
            ids.forEach(function (id) {
                theoId[id] = (theoId[id] || 0) + 1;
                const el = document.getElementById(id);
                if (el) { el.setAttribute('data-dang-tai', '1'); }
            });
        }, CHO_MS);
        return function () {
            clearTimeout(hen);
            dem = Math.max(0, dem - 1);
            if (dem === 0) { document.documentElement.classList.remove('dang-tai'); }
            ids.forEach(function (id) {
                if (!theoId[id]) { return; }          // chưa kịp đánh dấu (xong trước 150 ms)
                theoId[id] -= 1;
                if (theoId[id] <= 0) {
                    delete theoId[id];
                    const el = document.getElementById(id);
                    if (el) { el.removeAttribute('data-dang-tai'); }
                }
            });
        };
    }

    const goc = window.fetch;
    window.fetch = function (url, init) {
        const la = typeof url === 'string' && url.indexOf('_dash-update-component') >= 0;
        if (!la) { return goc.apply(this, arguments); }
        const xong = batDau(init && typeof init.body === 'string' ? init.body : '');
        return goc.apply(this, arguments).finally(xong);
    };

    // thanh chạy trên đầu trang
    function dungThanh() {
        if (document.getElementById('thanh-tai')) { return; }
        const t = document.createElement('div');
        t.id = 'thanh-tai';
        document.body.appendChild(t);
    }
    if (document.body) { dungThanh(); } else { document.addEventListener('DOMContentLoaded', dungThanh); }
})();
