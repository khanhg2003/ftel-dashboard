/* =====================================================================
   Danh bạ chạy NGAY TRÊN TRÌNH DUYỆT (app/danh_ba.py `cho_trinh_duyet`, app/ui/pages/danhba.py, soanmail.py).

   Máy chủ gửi MỘT LẦN toàn bộ danh bạ dạng gọn; trình duyệt lọc và vẽ HTML trực tiếp (trước đây mỗi lần đổi bộ lọc là một lượt
   hỏi máy chủ + dựng lại hàng nghìn thành phần Dash nên trễ, có lúc ô chọn đã đổi mà danh sách chưa kịp đổi).

   Hai nơi dùng chung (khai báo ở MO):
   - "db": trang Danh bạ. CHỈ xem từng chi nhánh, dạng sơ đồ cây theo phòng ban (chủ app chốt 10/10/2026: bỏ dạng thẻ và
     bỏ "Mọi chi nhánh"); mở trang là Đà Nẵng. Nút Sửa trên ô của người sale tự thêm.
   - "sm": hộp Tra danh bạ của Soạn email: thẻ người, tìm trong toàn danh bạ hoặc theo chi nhánh, nút Đến / CC.
   Nút Sửa / Đến / CC ghi sự kiện vào dcc.Store qua dash_clientside.set_props; máy chủ xử lý và kiểm quyền.
   Nút copy do assets/sao_chep.js lo (chỉ cần data-chep).
   ===================================================================== */
(function () {
    const MO = {
        db: {kq: 'db-kq', dem: 'db-dem', tim: 'db-tim', dv: 'db-dv', moi: false},
        sm: {kq: 'sm-db-kq', dem: 'sm-db-dem', tim: 'sm-db-tim', dv: 'sm-db-dv', gioiHan: 30, moi: true}
    };
    const KHO = {db: {du_lieu: null, dv: ''}, sm: {du_lieu: null, dv: ''}};
    // Sơ đồ cây theo PHÒNG BAN dựng từ chức danh: ban giám đốc ở gốc, mỗi phòng ban là một nhánh. Đường nối chỉ nói
    // "phòng ban này thuộc chi nhánh", KHÔNG nói ai báo cáo cho ai (file danh bạ không có cột "báo cáo cho").
    const GOC = ['giam_doc', 'pho_giam_doc'];
    const PB = [{ten: 'Kỹ thuật và hạ tầng', nhom: ['truong_phong_kt', 'ha_tang'],
                 con: {ten: 'Đội trưởng theo khu vực', nhom: ['doi_truong']}},
                {ten: 'Chăm sóc khách hàng (DVKH)', nhom: ['dvkh']}, {ten: 'Kế toán', nhom: ['ke_toan']},
                {ten: 'Hành chính nhân sự', nhom: ['hcns']}, {ten: 'Khác', nhom: ['khac']}];
    const IC = {
        mail: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/><path d="M3 7l9 6 9-6"/></svg>',
        phone: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>',
        copy: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2z"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
    };

    function boDau(s) {
        return String(s == null ? '' : s).toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(/[̀-ͯ]/g, '');
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
        });
    }

    /* Lọc: mọi từ khoá (bỏ dấu) phải nằm trong chuỗi tìm của người đó; người khớp ngay trong TÊN xếp trước,
       còn lại giữ thứ tự máy chủ đã xếp (nhóm chức danh, cấp bậc, tên). */
    function loc(ds, q, dv, nhom) {
        const k = boDau(q).split(/\s+/).filter(Boolean);
        let kq = ds.filter(function (r) {
            return (!dv || r.v === dv) && (!nhom || nhom === 'all' || r.n === nhom)
                && k.every(function (x) { return r.q.indexOf(x) >= 0; });
        });
        if (k.length) {
            const ten = function (r) { return k.every(function (x) { return r.b.indexOf(x) >= 0; }); };
            kq = kq.filter(ten).concat(kq.filter(function (r) { return !ten(r); }));
        }
        return kq;
    }

    function vien(ten) {
        const t = String(ten || '').trim().split(/\s+/);
        return (t.length >= 2 ? t[t.length - 2][0] + t[t.length - 1][0] : String(ten || '').slice(0, 2)).toUpperCase();
    }

    function the(r, nhomTen) {                                       // thẻ người của hộp Tra danh bạ (Soạn email)
        const so = String(r.d || '').replace(/\D/g, '');
        const nguon = String(r.s || '').replace('TAY', 'Thêm tay') + (r.u ? ' · ' + r.u : '');
        let h = '<div class="db-the"><div class="db-dau"><div class="db-vien">' + esc(vien(r.t)) + '</div><div>'
            + '<div class="db-ten"><b>' + esc(r.t) + '</b><span class="db-nhom-n ' + esc(r.n) + '">' + esc(nhomTen[r.n] || '') + '</span></div>'
            + '<div class="desc">' + esc([r.c, r.v].filter(Boolean).join(' · ')) + '</div></div></div>';
        if (r.e) {
            h += '<div class="db-dong">' + IC.mail + '<span class="db-gia-tri">' + esc(r.e) + '</span>'
                + '<button class="nut-chep" title="Copy email" data-chep="' + esc(r.e) + '">' + IC.copy + '</button></div>';
        }
        if (r.k) {
            h += '<div class="db-dong phu"><span class="db-nhan">Email khác</span><span class="db-gia-tri">' + esc(r.k)
                + '</span><button class="nut-chep" title="Copy email khác" data-chep="' + esc(r.k) + '">' + IC.copy + '</button></div>';
        }
        if (r.d || r.x) {
            h += '<div class="db-dong">' + IC.phone + (r.d ? '<a class="db-gia-tri" href="tel:' + so + '">' + esc(r.d) + '</a>' : '')
                + (r.x ? '<span class="db-nhan">máy lẻ ' + esc(r.x) + '</span>' : '')
                + (r.d ? '<button class="nut-chep" title="Copy số" data-chep="' + so + '">' + IC.copy + '</button>' : '') + '</div>';
        }
        if (r.g) { h += '<div class="db-ghi-chu">' + esc(r.g) + '</div>'; }
        h += '<div class="db-chan"><span class="db-nguon" title="Nguồn dữ liệu và ngày cập nhật">' + esc(nguon) + '</span><div class="grow"></div>';
        h += r.e ? '<button class="btn nho" data-chon="den" data-id="' + r.i + '">Đến</button>'
            + '<button class="btn nho" data-chon="cc" data-id="' + r.i + '">CC</button>' : '<span class="desc">Chưa có email</span>';
        return h + '</div></div>';
    }

    function chiaPhongBan(ds) {
        const theo = function (nhom) {
            return ds.filter(function (r) { return nhom.indexOf(r.n) >= 0; }).sort(function (a, b) { return (a.r || 0) - (b.r || 0); });
        };
        return {
            goc: theo(GOC),
            pb: PB.map(function (p) {
                return {ten: p.ten, ds: theo(p.nhom), con: p.con ? {ten: p.con.ten, ds: theo(p.con.nhom)} : null};
            }).filter(function (p) { return p.ds.length || (p.con && p.con.ds.length); })
        };
    }

    function nut(r, cuHon, goc) {
        const so = String(r.d || '').replace(/\D/g, '');
        let h = '<div class="db-n' + (goc ? ' goc' : '') + '"><b>' + esc(r.t) + '</b><span class="db-n-cv">' + esc(r.c) + '</span>';
        if (r.g) { h += '<span class="db-n-gc" title="' + esc(r.g) + '">' + esc(r.g) + '</span>'; }
        if (r.e) {
            h += '<span class="db-n-dong">' + IC.mail + '<span class="db-gia-tri" title="' + esc(r.e) + '">' + esc(r.e)
                + '</span><button class="nut-chep" title="Copy email" data-chep="' + esc(r.e) + '">' + IC.copy + '</button></span>';
        }
        if (r.d || r.x) {
            h += '<span class="db-n-dong">' + IC.phone + (r.d ? '<a class="db-gia-tri" href="tel:' + so + '">' + esc(r.d) + '</a>' : '')
                + (r.x ? '<span class="db-nhan">lẻ ' + esc(r.x) + '</span>' : '')
                + (r.d ? '<button class="nut-chep" title="Copy số" data-chep="' + so + '">' + IC.copy + '</button>' : '') + '</span>';
        }
        if (cuHon && r.s === 'TIN') { h += '<em class="db-n-cu" title="Chi nhánh này có bản mới hơn (PNC), người này chỉ có trong file TIN cũ">TIN · có thể cũ</em>'; }
        if (r.y) { h += '<button class="btn nho db-n-sua" data-sua="' + r.y + '">Sửa</button>'; }          // người sale tự thêm
        return h + '</div>';
    }

    function veSoDo(st, kq, dem) {
        const q = (document.getElementById(MO.db.tim) || {}).value || '';
        if (!st.du_lieu.ds.length) {
            if (dem) { dem.textContent = ''; }
            kq.innerHTML = '<div class="card"><div class="desc">Chưa có danh bạ. Quản trị nạp file PNC và TIN ở cuối trang Danh bạ.</div></div>';
            return;
        }
        const ds = loc(st.du_lieu.ds, q, st.dv, 'all');
        const cuHon = ds.some(function (r) { return r.s.indexOf('PNC') >= 0 || r.s.indexOf('TAY') >= 0; });
        const cu = function (r) { return cuHon && r.s === 'TIN'; };
        // cấp bậc trước (trưởng trên phó), cùng cấp thì người chỉ có trong file TIN cũ xuống cuối
        const xep = function (d) {
            return d.slice().sort(function (a, b) { return ((a.r || 0) - (b.r || 0)) || ((cu(a) ? 1 : 0) - (cu(b) ? 1 : 0)); });
        };
        if (dem) { dem.textContent = ds.length + ' người'; }
        if (!ds.length) { kq.innerHTML = '<div class="card"><div class="desc">Không có ai khớp.</div></div>'; return; }
        const c = chiaPhongBan(ds);
        const dsHtml = function (d) { return xep(d).map(function (r) { return nut(r, cuHon, false); }).join(''); };
        const pbHtml = function (p) {
            const tong = p.ds.length + (p.con ? p.con.ds.length : 0);
            return '<div class="db-pb"><div class="db-pb-ten"><span>' + esc(p.ten) + '</span><i>' + tong + '</i></div><div class="db-ds">'
                + dsHtml(p.ds) + (p.con && p.con.ds.length ? '<div class="db-sub"><div class="db-sub-ten"><span>' + esc(p.con.ten)
                + '</span><i>' + p.con.ds.length + '</i></div><div class="db-ds">' + dsHtml(p.con.ds) + '</div></div>' : '') + '</div></div>';
        };
        kq.innerHTML = '<div class="db-cay"><div class="db-cay-trong"><div class="db-goc">'
            + (c.goc.length ? xep(c.goc).map(function (r) { return nut(r, cuHon, true); }).join('')
                : '<div class="db-n goc trong">Chưa có thông tin ban giám đốc</div>')
            + '</div>' + (c.pb.length ? '<div class="db-than"></div><div class="db-nhanh">' + c.pb.map(pbHtml).join('') + '</div>' : '')
            + '</div></div>';
    }

    function ve(ma) {
        const mo = MO[ma], st = KHO[ma], kq = document.getElementById(mo.kq);
        if (!kq || !st.du_lieu) { return; }
        const dem = document.getElementById(mo.dem);
        if (ma === 'db') { veSoDo(st, kq, dem); return; }
        const q = (document.getElementById(mo.tim) || {}).value || '';
        const ds = loc(st.du_lieu.ds, q, st.dv, 'all'), hien = ds.slice(0, mo.gioiHan);
        if (dem) {
            dem.textContent = hien.length ? hien.length + ' / ' + ds.length + ' người'
                + (ds.length > hien.length ? ' · gõ thêm để thu hẹp' : '') + (st.du_lieu.moi ? ' · ' + st.du_lieu.moi : '') : '';
        }
        kq.innerHTML = hien.length ? hien.map(function (r) { return the(r, st.du_lieu.nhom); }).join('')
            : '<div class="card"><div class="desc">' + (st.du_lieu.ds.length ? 'Không có ai khớp.'
                : 'Chưa có danh bạ. Quản trị nạp file PNC và TIN ở cuối trang Danh bạ.') + '</div></div>';
    }

    // Ô chọn chi nhánh: gõ chữ để tìm, danh sách gom theo khu vực (máy chủ gửi sẵn `dv` = [{mien, ds}]).
    function cbVe(ma, q) {
        const st = KHO[ma], ds = document.getElementById(MO[ma].dv + '-ds');
        if (!ds || !st.du_lieu) { return; }
        const k = boDau(q || '').trim();
        let h = k || !MO[ma].moi ? '' : '<div class="db-cb-it' + (st.dv ? '' : ' on') + '" data-v="">Mọi chi nhánh</div>';
        (st.du_lieu.dv || []).forEach(function (g) {
            const it = g.ds.filter(function (d) { return !k || boDau(d).indexOf(k) >= 0 || boDau(g.mien).indexOf(k) >= 0; });
            if (it.length) {
                h += '<div class="db-cb-nh">' + esc(g.mien) + '</div>' + it.map(function (d) {
                    return '<div class="db-cb-it' + (d === st.dv ? ' on' : '') + '" data-v="' + esc(d) + '">' + esc(d) + '</div>';
                }).join('');
            }
        });
        ds.innerHTML = h || '<div class="db-cb-nh">Không có chi nhánh nào khớp</div>';
    }

    function cbMo(ma, mo) {
        const g = document.getElementById(MO[ma].dv + '-cb');
        if (g) { g.classList.toggle('mo', mo); }
    }

    function cbKhoiPhuc(ma) {                                        // chữ trong ô luôn là chi nhánh đang chọn
        const i = document.getElementById(MO[ma].dv + '-tim');
        if (i) { i.value = KHO[ma].dv || ''; }
    }

    function cbChon(ma, v) {
        KHO[ma].dv = v || '';
        cbKhoiPhuc(ma);
        cbMo(ma, false);
        ve(ma);
    }

    function nap(ma, du_lieu) {
        const st = KHO[ma];
        st.du_lieu = du_lieu && du_lieu.ds ? du_lieu : null;
        if (st.du_lieu && !MO[ma].moi) {                             // trang Danh bạ luôn có một chi nhánh: mặc định Đà Nẵng
            const con = (st.du_lieu.dv || []).some(function (g) { return g.ds.indexOf(st.dv) >= 0; });
            if (!con) { st.dv = st.du_lieu.dv_mac_dinh || ''; }
        }
        cbKhoiPhuc(ma);
        ve(ma);
        return Date.now();
    }

    if (typeof document !== 'undefined') {
        let hen = null;
        const maTu = function (id) { return id === MO.db.tim ? 'db' : (id === MO.sm.tim ? 'sm' : null); };
        const maCb = function (id) { return id === MO.db.dv + '-tim' ? 'db' : (id === MO.sm.dv + '-tim' ? 'sm' : null); };
        const lenh = function (e) {
            const ma = e.target && maTu(e.target.id);
            if (!ma) { return; }
            clearTimeout(hen);
            hen = setTimeout(function () { ve(ma); }, 60);
        };
        document.addEventListener('input', lenh);
        document.addEventListener('change', lenh);
        document.addEventListener('focusin', function (e) {
            const ma = e.target && maCb(e.target.id);
            if (!ma) { return; }
            e.target.select();
            cbVe(ma, '');
            cbMo(ma, true);
            const ds = document.getElementById(MO[ma].dv + '-ds'), on = ds && ds.querySelector('.db-cb-it.on');
            if (on) { ds.scrollTop = Math.max(0, on.offsetTop - ds.clientHeight / 2); }       // mở ra là thấy ngay chi nhánh đang chọn
        });
        document.addEventListener('input', function (e) {
            const ma = e.target && maCb(e.target.id);
            if (ma) { cbVe(ma, e.target.value); cbMo(ma, true); }
        });
        document.addEventListener('keydown', function (e) {
            const ma = e.target && maCb(e.target.id);
            if (!ma) { return; }
            if (e.key === 'Escape') { cbKhoiPhuc(ma); cbMo(ma, false); e.target.blur(); }
            if (e.key === 'Enter') {
                const ds = '#' + MO[ma].dv + '-ds .db-cb-it';
                const it = document.querySelector(ds + ':not([data-v=""])') || document.querySelector(ds);
                if (it) { cbChon(ma, it.dataset.v); }
                e.target.blur();
            }
        });
        document.addEventListener('click', function (e) {
            const t = e.target && e.target.closest ? e.target : null;
            if (!t) { return; }
            const it = t.closest('.db-cb-it');
            if (it) { cbChon(it.closest('.db-cb').id === 'db-dv-cb' ? 'db' : 'sm', it.dataset.v); return; }
            if (!t.closest('.db-cb')) {                                     // bấm ra ngoài: đóng danh sách, trả lại chữ đang chọn
                ['db', 'sm'].forEach(function (m) { cbMo(m, false); cbKhoiPhuc(m); });
            }
            const sua = t.closest('[data-sua]'), chon = t.closest('[data-chon]');
            if (sua) {
                window.dash_clientside.set_props('db-sk-sua', {data: {id: Number(sua.dataset.sua), t: Date.now()}});
            } else if (chon) {
                window.dash_clientside.set_props('sm-sk-chon', {data: {vt: chon.dataset.chon, id: Number(chon.dataset.id), t: Date.now()}});
            }
        });
    }

    if (typeof window !== 'undefined') {
        window.dash_clientside = window.dash_clientside || {};
        window.dash_clientside.ftel = Object.assign(window.dash_clientside.ftel || {}, {
            nap_db: function (d) { return nap('db', d); },
            nap_sm: function (d) { return nap('sm', d); }
        });
    }
    if (typeof module !== 'undefined') { module.exports = {loc, boDau, chiaPhongBan}; }          // để kiểm thử bằng Node
})();
