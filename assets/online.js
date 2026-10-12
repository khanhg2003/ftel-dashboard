/* =====================================================================
   Theo dõi Online trong ngày (mục dưới bảng Báo cáo ngày; quy tắc: app/online_ca.py, trang: app/ui/pages/baocaongay_online.py).
   Máy chủ gửi MỘT gói dữ liệu vào dcc.Store `onl-du-lieu`; file này tự vẽ: ô tổng quan + thanh tiến độ, cảnh báo ai chưa khai,
   bảng cột theo khung giờ (mỗi mã hợp đồng một thẻ), danh sách theo nhân viên. Bấm đổi trạng thái / dời khung / dời mai / xoá
   thì đổi NGAY trên màn hình rồi mới gửi máy chủ qua Store `onl-sk` (máy chủ kiểm quyền, ghi lịch sử, gửi lại số thật).
   Các khối #onl-* không có con do Dash dựng nên được sửa trực tiếp.
   ===================================================================== */
(function () {
    const TT_NGAN = {du_kien: 'Chờ', dang_lam: 'Đang lắp', da_online: 'Online'};
    const TT_DAI = {du_kien: 'Dự kiến', dang_lam: 'Đang triển khai', da_online: 'Đã online'};
    const THU = ['Chủ nhật', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy'];
    let du = null, loc = '', locTt = '';
    const cuoi = {};                                            // id khối -> HTML đã vẽ lần trước (giống nhau thì khỏi vẽ lại)

    function esc(s) {
        return String(s === undefined || s === null ? '' : s).replace(/[&<>"]/g, function (c) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
        });
    }

    function dem(ds, tt) { return ds.filter(function (c) { return c.tt === tt; }).length; }

    function so(ds) {
        return {tong: ds.length, cho: dem(ds, 'du_kien'), dang: dem(ds, 'dang_lam'), online: dem(ds, 'da_online')};
    }

    /* Phải giống hệt online_ca.thong_ke (có test đối chiếu). */
    function thongKe(ca, khung) {
        const out = so(ca);
        out.khung = {};
        khung.forEach(function (k) { out.khung[k.ma] = so(ca.filter(function (c) { return c.khung === k.ma; })); });
        out.nv = {};
        ca.forEach(function (c) { if (!out.nv[c.acc]) { out.nv[c.acc] = so(ca.filter(function (x) { return x.acc === c.acc; })); } });
        out.chua_hen = ca.filter(function (c) { return c.khung === 'chua'; }).length;
        return out;
    }

    function phut(hhmm) {
        const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm || '');
        return m ? Number(m[1]) * 60 + Number(m[2]) : null;
    }

    function bayGio() {                                         // phút trong ngày theo giờ Việt Nam, kể cả khi máy đặt múi giờ khác
        try {
            const p = new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false})
                .formatToParts(new Date());
            const g = function (t) { return Number(p.filter(function (x) { return x.type === t; })[0].value); };
            return (g('hour') % 24) * 60 + g('minute');
        } catch (e) {
            const d = new Date();
            return d.getHours() * 60 + d.getMinutes();
        }
    }

    function viet(tenNv) {                                      // chữ viết tắt + màu cố định theo tên cho avatar
        const t = String(tenNv || '?').trim().split(/\s+/);
        const ch = (t.length >= 2 ? t[t.length - 2][0] + t[t.length - 1][0] : String(tenNv || '?').slice(0, 2)).toUpperCase();
        let h = 0;
        for (let i = 0; i < tenNv.length; i++) { h = (h * 31 + tenNv.charCodeAt(i)) % 360; }
        return {ch: ch, h: h};
    }

    function avatar(ten) {
        const a = viet(ten);
        return '<i class="onl-av" style="background:hsl(' + a.h + ',55%,92%);color:hsl(' + a.h + ',55%,32%)">' + esc(a.ch) + '</i>';
    }

    function tenCua(acc) {
        const x = du.nv.filter(function (n) { return n.a === acc; })[0];
        return x ? x.t : acc;
    }

    function dat(id, html) {
        const e = document.getElementById(id);
        if (!e || cuoi[id] === html) { return; }
        cuoi[id] = html;
        e.innerHTML = html;
    }

    function gui(act, d) {
        window.dash_clientside.set_props('onl-sk', {data: Object.assign({act: act, t: Date.now()}, d || {})});
    }

    function bao(chu) {
        let t = document.getElementById('onl-toast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'onl-toast';
            t.className = 'sm-toast';
            document.body.appendChild(t);
        }
        t.textContent = chu;
        t.classList.add('hien');
        clearTimeout(t._h);
        t._h = setTimeout(function () { t.classList.remove('hien'); }, 2400);
    }

    // ------------------------------------------------------------------ vẽ
    function veTongQuan(ca, tk) {
        const d = new Date(du.ngay + 'T00:00:00');
        const hn = du.ngay === du.hom_nay;
        const nhan = hn ? 'Hôm nay' : (du.ngay > du.hom_nay ? 'Nhập trước' : 'Đã qua');
        const ten = loc ? ' · của ' + tenCua(loc) : '';
        const ph = function (n) { return tk.tong ? Math.round(n * 100 / tk.tong) : 0; };
        const ol = ['<option value="">Cả phòng</option>'].concat(du.nv.map(function (n) {
            return '<option value="' + esc(n.a) + '"' + (n.a === loc ? ' selected' : '') + '>' + esc(n.t) + '</option>';
        })).join('');
        const o = function (tt, cls, n, nhanO, phu) {
            return '<button type="button" class="onl-o ' + cls + (locTt === tt ? ' chon' : '') + '" data-act="loc-tt" data-tt="' + tt + '">'
                + '<b>' + n + '</b><span>' + nhanO + '</span>' + (phu ? '<em>' + phu + '</em>' : '') + '</button>';
        };
        return '<div class="onl-dau"><div><h3>Theo dõi Online</h3><div class="desc">' + THU[d.getDay()] + ', ' + ('0' + d.getDate()).slice(-2)
            + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + ' · <span class="onl-nhan' + (hn ? ' hn' : '') + '">' + nhan + '</span>' + esc(ten)
            + '</div></div><select class="onl-loc" data-act="loc-nv-sel" title="Chỉ xem ca của một người">' + ol + '</select></div>'
            + '<div class="onl-kpi">'
            + o('', 'tong', tk.tong, 'Ca dự kiến', '')
            + o('du_kien', 'cho', tk.cho, 'Đang chờ lắp', '')
            + o('dang_lam', 'dang', tk.dang, 'Đang triển khai', '')
            + o('da_online', 'xong', tk.online, 'Đã online', tk.tong ? ph(tk.online) + '%' : '') + '</div>'
            + '<div class="onl-tien" title="Xanh lá: đã online · Xanh dương: đang triển khai · Vàng: đang chờ">'
            + '<i class="x" style="width:' + ph(tk.online) + '%"></i><i class="d" style="width:' + ph(tk.dang) + '%"></i>'
            + '<i class="c" style="width:' + ph(tk.cho) + '%"></i></div>';
    }

    function veCanhBao(ca, tk) {
        const tuongLai = du.ngay >= du.hom_nay;
        const o = [];
        if (tuongLai && du.nv.length) {
            if (du.chua_khai.length) {
                const hien = du.chua_khai.slice(0, 6), them = du.chua_khai.length - hien.length;
                o.push('<div class="onl-cb do"><b>Chưa khai khung giờ online (' + du.chua_khai.length + '):</b> ' + hien.map(function (a) {
                    return '<span class="onl-cb-nv">' + esc(tenCua(a)) + ' <button type="button" data-act="khong" data-acc="' + esc(a)
                        + '" title="Hôm nay người này không có ca online">Không có ca</button></span>';
                }).join('') + (them > 0 ? ' <span class="onl-cb-them">và ' + them + ' người nữa, xem mục Theo nhân viên bên dưới</span>' : '') + '</div>');
            } else {
                o.push('<div class="onl-cb tot">✓ Cả phòng đã khai khung giờ online.</div>');
            }
        }
        if (tk.chua_hen) {
            o.push('<div class="onl-cb vang">' + tk.chua_hen + ' ca chưa hẹn giờ: chọn khung giờ để tính vào ONL sáng / ONL chiều.</div>');
        }
        return o.join('');
    }

    function veThe(c, k, hn, now) {
        const ten = tenCua(c.acc);
        const qua = hn && c.tt !== 'da_online' && k && phut(k.den) !== null && now > phut(k.den);
        const nut = ['du_kien', 'dang_lam', 'da_online'].map(function (t) {
            return '<button type="button" class="' + (c.tt === t ? 'on ' : '') + t + '" data-act="tt" data-id="' + c.id + '" data-val="' + t
                + '" title="' + TT_DAI[t] + '">' + TT_NGAN[t] + '</button>';
        }).join('');
        const khung = du.khung.map(function (x) {
            return '<option value="' + esc(x.ma) + '"' + (x.ma === c.khung ? ' selected' : '') + '>' + esc(x.nhan) + '</option>';
        }).join('');
        const ls = (c.ls || []).length > 1 ? c.ls.slice(-4).map(function (x) {
            return x.luc.slice(11, 16) + ' ' + x.ai + ': ' + x.viec;
        }).join('\n') : '';
        return '<article class="onl-ca ' + c.tt + (qua ? ' qua' : '') + (locTt && locTt !== c.tt ? ' mo' : '') + '" data-id="' + c.id + '">'
            + '<div class="onl-ca-dau"><b class="onl-ma">' + esc(c.ma) + '</b>'
            + (qua ? '<span class="onl-qua">Quá giờ</span>' : '') + '<span class="grow"></span>'
            + '<button type="button" class="onl-ic" data-act="sua" data-id="' + c.id + '" title="Sửa ghi chú, đổi người phụ trách, xem lịch sử">✎</button>'
            + '<button type="button" class="onl-ic xoa" data-act="xoa" data-id="' + c.id + '" data-ma="' + esc(c.ma) + '" title="Huỷ ca này">✕</button></div>'
            + '<div class="onl-ai" title="' + esc(c.acc) + '">' + avatar(ten) + '<span>' + esc(ten) + '</span></div>'
            + (c.gc ? '<div class="onl-gc" title="' + esc(c.gc) + '">' + esc(c.gc) + '</div>' : '')
            + '<div class="onl-tt">' + nut + '</div>'
            + '<div class="onl-chan"><select data-act="khung" data-id="' + c.id + '" title="Dời sang khung giờ khác">' + khung + '</select>'
            + '<button type="button" class="onl-mai" data-act="mai" data-id="' + c.id + '" title="Dời ca sang ngày mai">Mai ›</button>'
            + (ls ? '<span class="onl-ls" title="' + esc(ls) + '">⟲</span>' : '') + '</div></article>';
    }

    function veBang(ca) {
        const hn = du.ngay === du.hom_nay, now = hn ? bayGio() : null;
        const tk = thongKe(ca, du.khung);
        return '<div class="onl-luoi">' + du.khung.map(function (k) {
            const s = tk.khung[k.ma], ds = ca.filter(function (c) { return c.khung === k.ma; });
            const a = phut(k.tu), b = phut(k.den);
            const hienTai = hn && a !== null && b !== null && now >= a && now < b;
            const quaGio = hn && b !== null && now >= b && (s.cho + s.dang) > 0;
            const ph = function (n) { return s.tong ? Math.round(n * 100 / s.tong) : 0; };
            return '<section class="onl-cot' + (hienTai ? ' hien-tai' : '') + (quaGio ? ' qua-gio' : '') + (k.ma === 'chua' ? ' chua' : '') + '">'
                + '<header><div class="onl-cot-ten"><b>' + esc(k.nhan) + '</b>'
                + (hienTai ? '<span class="onl-now">Đang diễn ra</span>' : '') + (quaGio ? '<span class="onl-trehan">Quá giờ ' + (s.cho + s.dang) + ' ca</span>' : '')
                + '</div><div class="onl-cot-so"><b>' + s.tong + '</b> ca' + (s.tong ? ' · <span>' + s.online + ' online</span>' : '')
                + '</div><div class="onl-mini"><i class="x" style="width:' + ph(s.online) + '%"></i><i class="d" style="width:' + ph(s.dang) + '%"></i>'
                + '<i class="c" style="width:' + ph(s.cho) + '%"></i></div>'
                + '<button type="button" class="onl-them" data-act="them" data-khung="' + esc(k.ma) + '" title="Thêm ca vào khung này">+</button></header>'
                + '<div class="onl-ds">' + (ds.length ? ds.map(function (c) { return veThe(c, k, hn, now); }).join('')
                    : '<div class="onl-trong">Chưa có ca</div>') + '</div></section>';
        }).join('') + '</div>';
    }

    function veNv(ca) {
        const tuongLai = du.ngay >= du.hom_nay;
        const dong = du.nv.map(function (n) {
            const cua = ca.filter(function (c) { return c.acc === n.a; });
            const s = so(cua), khong = du.khong_ca.indexOf(n.a) >= 0;
            const cham = cua.map(function (c) {
                const k = du.khung.filter(function (x) { return x.ma === c.khung; })[0];
                return '<i class="' + c.tt + '" title="' + esc(c.ma + ' · ' + (k ? k.nhan : '') + ' · ' + TT_DAI[c.tt]) + '"></i>';
            }).join('');
            let phai;
            if (cua.length) { phai = '<span class="onl-nv-so"><b>' + s.tong + '</b> ca · ' + s.online + ' online</span>'; }
            else if (khong) { phai = '<span class="onl-khong">Không có ca</span><button type="button" data-act="bo-khong" data-acc="' + esc(n.a) + '">Bỏ</button>'; }
            else if (tuongLai) { phai = '<span class="onl-chua">Chưa khai</span><button type="button" data-act="khong" data-acc="' + esc(n.a) + '" title="Hôm nay người này không có ca online">Không có ca</button>'; }
            else { phai = '<span class="onl-nv-so">0 ca</span>'; }
            return '<div class="onl-nv' + (n.a === loc ? ' chon' : '') + '" data-act="loc-nv" data-acc="' + esc(n.a) + '">' + avatar(n.t)
                + '<span class="onl-nv-ten">' + esc(n.t) + '</span><span class="onl-cham">' + cham + '</span>' + phai + '</div>';
        }).join('');
        return du.nv.length ? '<div class="onl-nv-tieu">Theo nhân viên</div><div class="onl-nv-ds">' + dong + '</div>' : '';
    }

    function ve() {
        if (!du || !document.getElementById('onl-bang')) { return; }
        const goc = du.ca.slice().sort(function (a, b) {
            const i = function (c) { return du.khung.map(function (k) { return k.ma; }).indexOf(c.khung); };
            return (i(a) - i(b)) || (a.id - b.id);
        });
        const ca = loc ? goc.filter(function (c) { return c.acc === loc; }) : goc;
        const tk = thongKe(ca, du.khung);
        dat('onl-tong-quan', veTongQuan(ca, tk));
        dat('onl-canh-bao', veCanhBao(goc, thongKe(goc, du.khung)));
        dat('onl-bang', veBang(ca));
        dat('onl-nv', veNv(goc));
    }

    // ------------------------------------------------------------------ đổi tức thì trên màn hình rồi mới báo máy chủ
    function tim(id) { return du.ca.filter(function (c) { return String(c.id) === String(id); })[0]; }

    function capNhatKhaiBao() {
        const co = {};
        du.ca.forEach(function (c) { co[c.acc] = 1; });
        du.khong_ca.forEach(function (a) { co[a] = 1; });
        du.chua_khai = du.nv.filter(function (n) { return !co[n.a]; }).map(function (n) { return n.a; });
    }

    function lenh(act, e) {
        if (!du) { return; }
        const d = e.dataset, c = d.id ? tim(d.id) : null;
        if (act === 'tt' && c) { if (c.tt === d.val) { return; } c.tt = d.val; gui('tt', {id: c.id, val: d.val}); }
        else if (act === 'mai' && c) {
            du.ca = du.ca.filter(function (x) { return x !== c; });
            bao('Đã dời ' + c.ma + ' sang ngày mai');
            gui('mai', {id: c.id});
        }
        else if (act === 'xoa' && c) {
            if (!window.confirm('Huỷ ca ' + d.ma + '?')) { return; }
            du.ca = du.ca.filter(function (x) { return x !== c; });
            bao('Đã huỷ ca ' + d.ma);
            gui('xoa', {id: c.id});
        }
        else if (act === 'sua' && c) { gui('sua', {id: c.id}); return; }
        else if (act === 'them') {
            window.dash_clientside.set_props('onl-f-khung', {value: d.khung});
            const o = document.getElementById('onl-f-hd');
            if (o) { o.focus(); o.scrollIntoView({block: 'center', behavior: 'smooth'}); }
            return;
        }
        else if (act === 'khong' || act === 'bo-khong') {
            const co = act === 'khong';
            du.khong_ca = du.khong_ca.filter(function (a) { return a !== d.acc; }).concat(co ? [d.acc] : []);
            gui('khong', {acc: d.acc, co: co});
        }
        else if (act === 'loc-tt') { locTt = locTt === d.tt ? '' : d.tt; }
        else if (act === 'loc-nv') { loc = loc === d.acc ? '' : d.acc; }
        else { return; }
        capNhatKhaiBao();
        ve();
    }

    function nap(goi) {
        du = goi && goi.ca ? goi : null;
        if (du && loc && !du.nv.some(function (n) { return n.a === loc; })) { loc = ''; }
        if (du) { capNhatKhaiBao(); }
        ve();
        return Date.now();
    }

    if (typeof document !== 'undefined') {
        document.addEventListener('click', function (e) {
            const b = e.target && e.target.closest ? e.target.closest('#onl-goc [data-act]') : null;
            if (!b || b.tagName === 'SELECT' || b.tagName === 'OPTION') { return; }
            lenh(b.dataset.act, b);
        });
        document.addEventListener('change', function (e) {
            const s = e.target && e.target.closest ? e.target.closest('#onl-goc select[data-act]') : null;
            if (!s || !du) { return; }
            if (s.dataset.act === 'loc-nv-sel') { loc = s.value; ve(); return; }
            const c = tim(s.dataset.id);
            if (s.dataset.act === 'khung' && c && c.khung !== s.value) {
                c.khung = s.value;
                gui('khung', {id: c.id, val: s.value});
                ve();
            }
        });
        setInterval(function () {                                // đánh dấu "đang diễn ra" / "quá giờ" chạy theo đồng hồ
            const dangChon = document.activeElement && document.activeElement.closest && document.activeElement.closest('#onl-bang');
            if (du && du.ngay === du.hom_nay && !dangChon) { ve(); }
        }, 60000);
    }

    if (typeof window !== 'undefined') {
        window.dash_clientside = window.dash_clientside || {};
        window.dash_clientside.ftel = Object.assign(window.dash_clientside.ftel || {}, {
            ve_online: nap,
            onl_bao: function (tb) { if (tb && tb.msg) { bao(tb.msg); } return window.dash_clientside.no_update; }
        });
    }
    if (typeof module !== 'undefined') { module.exports = {thongKe, phut}; }          // để kiểm thử bằng Node
})();
