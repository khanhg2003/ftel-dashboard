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

    /* Hộp Tra danh bạ: bấm Đến / CC phải thấy ngay là đã thêm. Thẻ người đổi sang xanh + nút thành "✓ Đã thêm vào Đến", nút kia
       thành "Chuyển sang CC", kèm thông báo nhỏ ở đáy màn hình. Trạng thái đọc từ các thẻ người nhận trên thư (#sm-chips) nên luôn
       khớp thật; `tam` giữ phần vừa bấm trong lúc chờ máy chủ xác nhận. #sm-db-kq do trình duyệt vẽ nên sửa trực tiếp được. */
    const tam = {};                                              // email (chữ thường) -> 'den' | 'cc'
    const NHAN = {den: 'Đến', cc: 'CC'};
    let cho = null;

    function emailThe(the) {
        const e = the.querySelector('.db-gia-tri');
        return e ? e.textContent.trim().toLowerCase() : '';
    }

    function daChon() {
        const kq = {};
        document.querySelectorAll('#sm-chips .sm-dong-chip').forEach(function (d) {
            const vt = d.querySelector('.sm-vt'), loai = vt && vt.textContent.trim() === 'CC' ? 'cc' : 'den';
            d.querySelectorAll('.sm-chip').forEach(function (c) { kq[(c.title || '').split(' ')[0].toLowerCase()] = loai; });
        });
        return Object.assign(kq, tam);
    }

    function danhDau() {
        const co = daChon();
        const kq = document.getElementById('sm-db-kq') || document.createElement('div');
        document.querySelectorAll('.sm-gy-dd .sm-gy').forEach(function (dong) {       // gợi ý xổ xuống: dòng nào đã có trên thư
            const vt = co[(dong.dataset.email || '').toLowerCase()] || '';
            if ((dong.dataset.trang || '') !== vt) { dong.dataset.trang = vt; }
        });
        kq.querySelectorAll('.db-the').forEach(function (the) {
            const vt = co[emailThe(the)] || '';
            if ((the.dataset.trang || '') === vt) { return; }
            the.dataset.trang = vt;
            the.querySelectorAll('[data-chon]').forEach(function (b) {
                const l = b.dataset.chon;
                b.textContent = !vt ? NHAN[l] : (l === vt ? '✓ Đã thêm vào ' + NHAN[l] : 'Chuyển sang ' + NHAN[l]);
                b.classList.toggle('da-them', l === vt);
            });
        });
    }

    function bao(chu) {
        let t = document.getElementById('sm-toast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'sm-toast';
            t.className = 'sm-toast';
            document.body.appendChild(t);
        }
        t.textContent = chu;
        t.classList.add('hien');
        clearTimeout(t._h);
        t._h = setTimeout(function () { t.classList.remove('hien'); }, 2200);
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
        document.addEventListener('click', function (e) {           // bấm Đến / CC ở hộp Tra danh bạ
            const b = e.target && e.target.closest ? e.target.closest('#sm-db-kq [data-chon]') : null;
            if (!b || b.classList.contains('da-them')) { return; }
            const the = b.closest('.db-the'), ten = the.querySelector('.db-ten b'), truoc = the.dataset.trang;
            tam[emailThe(the)] = b.dataset.chon;
            danhDau();
            bao('✓ ' + (truoc ? 'Đã chuyển ' : 'Đã thêm ') + (ten ? ten.textContent : '') + (truoc ? ' sang ' : ' vào ') + NHAN[b.dataset.chon]);
        });
        document.addEventListener('click', function (e) {           // nút Đến / CC trong gợi ý xổ xuống
            const b = e.target && e.target.closest ? e.target.closest('.sm-gy-dd .sm-gy button[data-vt]') : null;
            if (b) {
                const dong = b.closest('.sm-gy'), ten = dong.querySelector('.sm-gy-ten'), truoc = dong.dataset.trang;
                if (truoc === b.dataset.vt) { return; }
                tam[(dong.dataset.email || '').toLowerCase()] = b.dataset.vt;
                danhDau();
                bao('✓ ' + (truoc ? 'Đã chuyển ' : 'Đã thêm ') + (ten ? ten.firstChild.textContent : '') + (truoc ? ' sang ' : ' vào ') + NHAN[b.dataset.vt]);
            } else if (!(e.target.closest && e.target.closest('.sm-gy-dd'))) {   // bấm ra ngoài thì đóng
                document.querySelectorAll('.sm-gy-dd[open]').forEach(function (d) { d.open = false; });
            }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { document.querySelectorAll('.sm-gy-dd[open]').forEach(function (d) { d.open = false; }); }
        });
        new MutationObserver(function (ms) {
            if (ms.some(function (m) { return m.target.closest && m.target.closest('#sm-chips'); })) {
                Object.keys(tam).forEach(function (k) { delete tam[k]; });            // máy chủ đã cập nhật thư: lấy theo thư
            }
            if (!cho) { cho = requestAnimationFrame(function () { cho = null; danhDau(); }); }
        }).observe(document.documentElement, {childList: true, subtree: true});
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
