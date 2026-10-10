/* =====================================================================
   Danh bạ lọc NGAY TRÊN TRÌNH DUYỆT (app/danh_ba.py `cho_trinh_duyet`, app/ui/pages/danhba.py, soanmail.py).

   Trước đây mỗi lần gõ tìm hay đổi nhóm chức danh là một lượt hỏi máy chủ + dựng lại 60 thẻ Dash (hàng nghìn thành
   phần) nên trễ rõ rệt, có lúc ô chọn đã đổi mà danh sách chưa kịp đổi. Nay máy chủ gửi MỘT LẦN toàn bộ danh bạ dạng gọn,
   trình duyệt lọc và vẽ thẻ HTML trực tiếp.

   Hai nơi dùng chung một bộ vẽ (khai báo ở MO):
   - "db": trang Danh bạ (nút Sửa cho người sale tự thêm).
   - "sm": hộp Tra danh bạ của Soạn email (nút Đến / CC cho người có email).
   Nút Sửa / Đến / CC ghi sự kiện vào dcc.Store qua dash_clientside.set_props; máy chủ xử lý và kiểm quyền.
   Nút copy do assets/sao_chep.js lo (chỉ cần data-chep).
   ===================================================================== */
(function () {
    const MO = {
        db: {kq: 'db-kq', dem: 'db-dem', tim: 'db-tim', dv: 'db-dv', gioiHan: 60},
        sm: {kq: 'sm-db-kq', dem: 'sm-db-dem', tim: 'sm-db-tim', dv: 'sm-db-dv', gioiHan: 30, chon: true}
    };
    const KHO = {db: {du_lieu: null, nhom: 'all', che: 'the'}, sm: {du_lieu: null, nhom: 'all', che: 'the'}};
    // Sơ đồ theo CHỨC DANH, không phải quan hệ báo cáo (file danh bạ không có cột "báo cáo cho").
    const TANG = [['Ban giám đốc', ['giam_doc', 'pho_giam_doc']], ['Kỹ thuật và hạ tầng', ['truong_phong_kt', 'ha_tang']],
                  ['Đội trưởng theo khu vực', ['doi_truong']], ['Chăm sóc khách hàng (DVKH)', ['dvkh']], ['Kế toán', ['ke_toan']],
                  ['Hành chính nhân sự', ['hcns']], ['Khác', ['khac']]];
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
       còn lại giữ thứ tự máy chủ đã xếp (chi nhánh của sale, nhóm chức danh, tên). */
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

    function the(r, mo, nhomTen) {
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
        h += '<div class="db-chan"><span class="db-nguon" title="Nguồn dữ liệu và ngày cập nhật">' + esc(nguon) + '</span>';
        if (r.y && !mo.chon) { h += '<button class="btn nho" data-sua="' + r.y + '">Sửa</button>'; }
        h += '<div class="grow"></div>';
        if (mo.chon) {
            h += r.e ? '<button class="btn nho" data-chon="den" data-id="' + r.i + '">Đến</button>'
                + '<button class="btn nho" data-chon="cc" data-id="' + r.i + '">CC</button>'
                : '<span class="desc">Chưa có email</span>';
        }
        return h + '</div></div>';
    }

    function chiaTang(ds) {
        return TANG.map(function (t) { return {ten: t[0], ds: ds.filter(function (r) { return t[1].indexOf(r.n) >= 0; })}; })
            .filter(function (t) { return t.ds.length; });
    }

    function o(r, cuHon) {
        const so = String(r.d || '').replace(/\D/g, '');
        let h = '<div class="db-o"><b>' + esc(r.t) + '</b><span class="db-o-cv">' + esc(r.c) + '</span>';
        if (r.g) { h += '<span class="db-o-gc">' + esc(r.g) + '</span>'; }
        if (r.e) {
            h += '<span class="db-o-dong">' + IC.mail + '<span class="db-gia-tri">' + esc(r.e)
                + '</span><button class="nut-chep" title="Copy email" data-chep="' + esc(r.e) + '">' + IC.copy + '</button></span>';
        }
        if (r.d || r.x) {
            h += '<span class="db-o-dong">' + IC.phone + (r.d ? '<a class="db-gia-tri" href="tel:' + so + '">' + esc(r.d) + '</a>' : '')
                + (r.x ? '<span class="db-nhan">máy lẻ ' + esc(r.x) + '</span>' : '') + '</span>';
        }
        if (cuHon && r.s === 'TIN') { h += '<em class="db-o-cu" title="Chi nhánh này có bản mới hơn (PNC), người này chỉ có trong file TIN cũ">TIN · có thể cũ</em>'; }
        return h + '</div>';
    }

    function veSoDo(st, kq, dem) {
        const q = (document.getElementById(MO.db.tim) || {}).value || '';
        const dv = (document.getElementById(MO.db.dv) || {}).value || '';
        kq.className = 'db-so-do';
        if (!dv) {
            if (dem) { dem.textContent = ''; }
            kq.innerHTML = '<div class="card"><div class="desc">Chọn một chi nhánh để xem sơ đồ.</div></div>';
            return;
        }
        const ds = loc(st.du_lieu.ds, q, dv, 'all');
        const cuHon = ds.some(function (r) { return r.s.indexOf('PNC') >= 0 || r.s.indexOf('TAY') >= 0; });
        if (dem) { dem.textContent = ds.length + ' người · sơ đồ theo chức danh, không thể hiện ai báo cáo cho ai'; }
        const cu = function (r) { return cuHon && r.s === 'TIN'; };            // người chỉ có trong file TIN cũ xếp cuối tầng
        kq.innerHTML = ds.length ? chiaTang(ds).map(function (t, i) {
            t.ds = t.ds.filter(function (r) { return !cu(r); }).concat(t.ds.filter(cu));
            return (i ? '<div class="db-noi"></div>' : '') + '<div class="db-tang"><div class="db-tang-ten">' + esc(t.ten) + ' · ' + t.ds.length
                + '</div><div class="db-hang">' + t.ds.map(function (r) { return o(r, cuHon); }).join('') + '</div></div>';
        }).join('') : '<div class="card"><div class="desc">Không có ai khớp.</div></div>';
    }

    function ve(ma) {
        const mo = MO[ma], st = KHO[ma], kq = document.getElementById(mo.kq);
        if (!kq || !st.du_lieu) { return; }
        if (ma === 'db' && st.che === 'so_do') { veSoDo(st, kq, document.getElementById(mo.dem)); return; }
        kq.className = 'db-luoi';
        const q = (document.getElementById(mo.tim) || {}).value || '';
        const dv = (document.getElementById(mo.dv) || {}).value || '';
        const ds = loc(st.du_lieu.ds, q, dv, st.nhom), hien = ds.slice(0, mo.gioiHan);
        const dem = document.getElementById(mo.dem);
        if (dem) {
            dem.textContent = hien.length ? hien.length + ' / ' + ds.length + ' người'
                + (ds.length > hien.length ? ' · gõ thêm để thu hẹp' : '') + (st.du_lieu.moi ? ' · ' + st.du_lieu.moi : '') : '';
        }
        kq.innerHTML = hien.length ? hien.map(function (r) { return the(r, mo, st.du_lieu.nhom); }).join('')
            : '<div class="card"><div class="desc">' + (st.du_lieu.ds.length ? 'Không có ai khớp.'
                : 'Chưa có danh bạ. Quản trị nạp file PNC và TIN ở cuối trang Danh bạ.') + '</div></div>';
    }

    function nap(ma, du_lieu) {
        const st = KHO[ma];
        st.du_lieu = du_lieu && du_lieu.ds ? du_lieu : null;
        const sel = document.getElementById(MO[ma].dv);
        if (sel && st.du_lieu && sel.options.length <= 1) {            // danh sách chi nhánh đi kèm dữ liệu
            st.du_lieu.dv.forEach(function (d) {
                const o = document.createElement('option');
                o.value = d; o.textContent = d;
                sel.appendChild(o);
            });
        }
        ve(ma);
        return Date.now();
    }

    if (typeof document !== 'undefined') {
        let hen = null;
        const maTu = function (id) { return id === MO.db.tim || id === MO.db.dv ? 'db' : (id === MO.sm.tim || id === MO.sm.dv ? 'sm' : null); };
        const lenh = function (e) {
            const ma = e.target && maTu(e.target.id);
            if (!ma) { return; }
            clearTimeout(hen);
            hen = setTimeout(function () { ve(ma); }, 60);
        };
        document.addEventListener('input', lenh);
        document.addEventListener('change', lenh);
        document.addEventListener('click', function (e) {
            const t = e.target && e.target.closest ? e.target : null;
            if (!t) { return; }
            const chip = t.closest('.db-chip');
            if (chip) {
                KHO.db.nhom = chip.dataset.nhom || 'all';
                document.querySelectorAll('.db-chip').forEach(function (c) { c.classList.toggle('active', c === chip); });
                ve('db');
                return;
            }
            const cd = t.closest('.db-cd');
            if (cd) {
                KHO.db.che = cd.dataset.cd;
                const sel = document.getElementById(MO.db.dv);
                if (KHO.db.che === 'so_do' && sel && !sel.value && sel.options.length > 1) { sel.selectedIndex = 1; }   // chi nhánh của sale
                document.querySelectorAll('.db-cd').forEach(function (b) { b.classList.toggle('active', b === cd); });
                const chips = document.getElementById('db-nhom');
                if (chips) { chips.style.display = KHO.db.che === 'so_do' ? 'none' : ''; }
                ve('db');
                return;
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
    if (typeof module !== 'undefined') { module.exports = {loc, boDau, chiaTang}; }          // để kiểm thử bằng Node
})();
