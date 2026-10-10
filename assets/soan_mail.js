/* =====================================================================
   Soạn email: bản xem trước là một "lá thư" SỬA ĐƯỢC TRỰC TIẾP (assets/sao_chep.js copy đúng chữ đang hiện).
   Máy chủ chỉ gửi `kq` (tiêu đề + các đoạn) qua dcc.Store `sm-kq`; trình duyệt tự vẽ vào #sm-tieu và #sm-than. Hai khối này
   KHÔNG do React quản lý nội dung nên chữ sale gõ thêm không bị Dash xoá khi dựng lại.
   Cũng xử lý thẻ chọn loại mail (.sm-loai-the). Quy tắc: sale đã sửa tay phần nào thì phần đó được GIỮ NGUYÊN khi đổi ô bên trái (hiện thanh vàng báo); bấm
   "Dựng lại từ các ô" mới bỏ phần sửa tay. Mỗi loại mail giữ phần sửa riêng. Vào lại trang thì làm lại từ đầu
   (các ô cũng trống), tránh mang thư cũ sang khách khác.
   ===================================================================== */
(function () {
    const sua = {};                       // loai -> {tieu?: chữ, than?: html}
    let lamLai = null;

    function esc(s) {
        return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; });
    }

    /* doan = [[[chữ, đậm?], ...], ...]: mỗi đoạn một <p>; \n xuống dòng; [Ô còn trống] tô nổi để sale thấy */
    function htmlThan(doan) {
        return (doan || []).map(function (d) {
            let o = '';
            d.forEach(function (p) {
                p[0].split('\n').forEach(function (dong, j) {
                    if (j) { o += '<br>'; }
                    dong.split(/(\[[^\]]+\])/).forEach(function (c) {
                        if (!c) { return; }
                        o += /^\[[^\]]+\]$/.test(c) ? '<span class="sm-thieu">' + esc(c) + '</span>'
                            : (p[1] ? '<b>' + esc(c) + '</b>' : esc(c));
                    });
                });
            });
            return '<p>' + o + '</p>';
        }).join('');
    }

    function ve(kq) {
        const than = document.getElementById('sm-than'), tieu = document.getElementById('sm-tieu');
        const bao = document.getElementById('sm-sua-bao');
        if (!than || !tieu || !kq) { return window.dash_clientside.no_update; }
        if (!than.dataset.khoi) {                                   // vừa vào trang: bỏ phần sửa tay của lần trước
            than.dataset.khoi = '1';
            Object.keys(sua).forEach(function (k) { delete sua[k]; });
            lamLai = kq.lam_lai;
        }
        if (kq.lam_lai !== lamLai) { lamLai = kq.lam_lai; delete sua[kq.loai]; }
        const s = sua[kq.loai] || {};
        tieu.textContent = s.tieu !== undefined ? s.tieu : kq.tieu_de;
        than.innerHTML = s.than !== undefined ? s.than : htmlThan(kq.doan);
        than.dataset.loai = tieu.dataset.loai = kq.loai;
        if (bao) { bao.classList.toggle('an', s.tieu === undefined && s.than === undefined); }
        return window.dash_clientside.no_update;
    }

    function khoiSua(e) {
        return e.target && e.target.closest ? e.target.closest('#sm-than, #sm-tieu') : null;
    }

    if (typeof document !== 'undefined') {
        document.addEventListener('click', function (e) {           // thẻ chọn loại mail: đổi ngay, máy chủ chỉ nhận giá trị mới
            const the = e.target && e.target.closest ? e.target.closest('.sm-loai-the') : null;
            if (!the) { return; }
            document.querySelectorAll('.sm-loai-the').forEach(function (t) { t.classList.toggle('chon', t === the); });
            window.dash_clientside.set_props('sm-loai', {data: the.dataset.loai});
        });
        document.addEventListener('input', function (e) {
            const el = khoiSua(e);
            if (!el || !el.dataset.loai) { return; }
            const s = sua[el.dataset.loai] = sua[el.dataset.loai] || {};
            if (el.id === 'sm-tieu') { s.tieu = el.textContent; } else { s.than = el.innerHTML; }
            const bao = document.getElementById('sm-sua-bao');
            if (bao) { bao.classList.remove('an'); }
        });
        document.addEventListener('paste', function (e) {           // dán chữ trơn: không mang định dạng Word / web vào thư
            const el = khoiSua(e);
            if (!el) { return; }
            e.preventDefault();
            const chu = ((e.clipboardData || window.clipboardData).getData('text/plain') || '');
            document.execCommand('insertText', false, el.id === 'sm-tieu' ? chu.replace(/\s+/g, ' ') : chu);
        });
        document.addEventListener('keydown', function (e) {         // tiêu đề chỉ một dòng
            if (e.key === 'Enter' && e.target && e.target.id === 'sm-tieu') { e.preventDefault(); }
        });
    }

    if (typeof window !== 'undefined') {
        window.dash_clientside = window.dash_clientside || {};
        window.dash_clientside.ftel = Object.assign(window.dash_clientside.ftel || {}, {ve_mail: ve});
    }
    if (typeof module !== 'undefined') { module.exports = {htmlThan}; }          // để kiểm thử bằng Node
})();
