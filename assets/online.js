/* =====================================================================
   Theo dõi Online trong ngày (mục dưới bảng Báo cáo ngày; quy tắc: app/online_ca.py, trang: app/ui/pages/baocaongay_online.py).
   Máy chủ gửi MỘT gói dữ liệu vào dcc.Store `onl-du-lieu`; file này tự vẽ: vòng tiến độ + số ca, hàng chip nhân viên (cũng là bộ lọc),
   cảnh báo ai chưa khai đủ giờ, bảng cột theo khung giờ (mỗi mã hợp đồng một thẻ). Chỉ hiện người CÓ ca (đã gõ dự kiến online hoặc
   đã có phiếu), người dự kiến 0 ẩn hẳn. Bấm đổi trạng thái / dời khung / dời mai / huỷ thì đổi NGAY trên màn hình rồi mới gửi máy chủ
   qua Store `onl-sk` (máy chủ kiểm quyền, ghi lịch sử, gửi lại số thật). Các khối #onl-* không có con do Dash dựng nên sửa trực tiếp.
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

    /* Phải giống hệt online_ca.thieu_gio (có test đối chiếu). */
    function thieuGio(ca, dk) {
        const out = {}, ds = Object.keys(dk).concat(ca.map(function (c) { return c.acc; }));
        ds.forEach(function (a) {
            if (out[a] !== undefined) { return; }
            const cua = ca.filter(function (c) { return c.acc === a; });
            const chua = cua.filter(function (c) { return c.khung === 'chua'; }).length, khai = cua.length - chua;
            const can = Math.max(Number(dk[a] || 0), khai + chua);
            out[a] = can > 0 ? {can: can, khai: khai, chua: chua, thieu: can - khai} : null;
        });
        Object.keys(out).forEach(function (a) { if (out[a] === null) { delete out[a]; } });
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

    function avatar(ten) {                                      // chữ viết tắt + màu cố định theo tên
        const t = String(ten || '?').trim().split(/\s+/);
        const ch = (t.length >= 2 ? t[t.length - 2][0] + t[t.length - 1][0] : String(ten || '?').slice(0, 2)).toUpperCase();
        let h = 0;
        for (let i = 0; i < ten.length; i++) { h = (h * 31 + ten.charCodeAt(i)) % 360; }
        return '<i class="onl-av" style="background:hsl(' + h + ',55%,92%);color:hsl(' + h + ',55%,32%)">' + esc(ch) + '</i>';
    }

    function tenCua(acc) {
        const x = du.nv.filter(function (n) { return n.a === acc; })[0];
        return x ? x.t : acc;
    }

    function tenGoi(acc, ds) {                                  // "Thắng"; trùng tên gọi trong danh sách thì thêm chữ lót
        const t = tenCua(acc).trim().split(/\s+/), goi = t[t.length - 1];
        const trung = ds.filter(function (a) { const u = tenCua(a).trim().split(/\s+/); return u[u.length - 1] === goi; }).length > 1;
        return trung && t.length > 1 ? t.slice(-2).join(' ') : goi;
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
    function veHero(ca, tk) {
        const d = new Date(du.ngay + 'T00:00:00');
        const hn = du.ngay === du.hom_nay;
        const nhan = hn ? 'Hôm nay' : (du.ngay > du.hom_nay ? 'Nhập trước' : 'Đã qua');
        const ph = function (n) { return tk.tong ? n * 100 / tk.tong : 0; };
        const x = ph(tk.online), dd = x + ph(tk.dang), cc = dd + ph(tk.cho);
        const vong = 'conic-gradient(var(--onl-xong) 0 ' + x + '%,var(--onl-dang) ' + x + '% ' + dd + '%,#F0C36B ' + dd + '% ' + cc + '%,#E3E9F1 ' + cc + '% 100%)';
        const o = function (tt, cls, n, nhanO) {
            return '<button type="button" class="onl-o ' + cls + (locTt === tt ? ' chon' : '') + '" data-act="loc-tt" data-tt="' + tt
                + '"><b>' + n + '</b><span>' + nhanO + '</span></button>';
        };
        const gt = loc ? ' · của ' + esc(tenCua(loc)) : '';
        return '<div class="onl-hero"><div class="onl-vong" style="background:' + vong + '"><div><b>' + (tk.tong ? Math.round(x) : 0) + '<small>%</small></b>'
            + '<span>online</span></div></div><div class="onl-hero-gt"><div class="onl-hero-tieu"><h3>Theo dõi Online</h3><span class="onl-nhan'
            + (hn ? ' hn' : '') + '">' + nhan + '</span></div><div class="desc">' + THU[d.getDay()] + ', ' + ('0' + d.getDate()).slice(-2) + '/'
            + ('0' + (d.getMonth() + 1)).slice(-2) + ' · ' + (tk.tong ? '<b>' + tk.online + '</b> / ' + tk.tong + ' ca đã online' : 'Chưa có ca nào')
            + gt + '</div><div class="onl-stat">' + o('du_kien', 'cho', tk.cho, 'Đang chờ lắp') + o('dang_lam', 'dang', tk.dang, 'Đang triển khai')
            + o('da_online', 'xong', tk.online, 'Đã online') + '</div></div></div>';
    }

    function veNguoi(goc) {
        const th = du.thieu, ds = du.nv.map(function (n) { return n.a; }).filter(function (a) { return th[a]; });
        if (!ds.length) { return ''; }
        const chip = ds.map(function (a) {
            const cua = goc.filter(function (c) { return c.acc === a; }), t = th[a];
            const cham = cua.map(function (c) { return '<i class="' + c.tt + '"></i>'; }).join('');
            return '<button type="button" class="onl-ch' + (a === loc ? ' chon' : '') + (t.thieu > 0 ? ' thieu' : '') + '" data-act="loc-nv" data-acc="' + esc(a)
                + '" title="' + esc(tenCua(a)) + ' · ' + cua.length + ' ca đã khai, dự kiến ' + t.can + '">' + avatar(tenCua(a)) + '<span>' + esc(tenGoi(a, ds))
                + '</span><span class="onl-cham">' + cham + '</span></button>';
        }).join('');
        return '<div class="onl-nguoi"><button type="button" class="onl-ch tat-ca' + (loc ? '' : ' chon') + '" data-act="loc-nv" data-acc="">Cả phòng</button>' + chip + '</div>';
    }

    function veCanhBao() {
        const th = du.thieu, ds = du.nv.map(function (n) { return n.a; }).filter(function (a) { return th[a] && th[a].thieu > 0; });
        if (!ds.length || du.ngay < du.hom_nay) { return ''; }
        return '<div class="onl-cb"><b>Chưa khai đủ giờ online:</b>' + ds.map(function (a) {
            const t = th[a];
            return '<button type="button" class="onl-cb-nv" data-act="them-nv" data-acc="' + esc(a) + '" title="Bấm để thêm ca cho người này">'
                + esc(tenCua(a)) + ' <em>' + t.khai + '/' + t.can + '</em></button>';
        }).join('') + '<span class="onl-cb-goi">Bấm tên để thêm ca. Cần mã hợp đồng và khung giờ cho từng ca đã dự kiến.</span></div>';
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
            + '<div class="onl-ca-dau"><b class="onl-ma">' + esc(c.ma) + '</b>' + (qua ? '<span class="onl-qua">Quá giờ</span>' : '')
            + '<span class="grow"></span><button type="button" class="onl-ic" data-act="sua" data-id="' + c.id
            + '" title="Sửa ghi chú, đổi người phụ trách, xem lịch sử">✎</button></div>'
            + '<div class="onl-ai" title="' + esc(c.acc) + '">' + avatar(ten) + '<span>' + esc(ten) + '</span></div>'
            + (c.gc ? '<div class="onl-gc" title="' + esc(c.gc) + '">' + esc(c.gc) + '</div>' : '')
            + '<div class="onl-tt">' + nut + '</div>'
            + '<div class="onl-chan"><select data-act="khung" data-id="' + c.id + '" title="Dời sang khung giờ khác">' + khung + '</select>'
            + '<button type="button" class="onl-mai" data-act="mai" data-id="' + c.id + '" title="Dời ca sang ngày mai">Mai ›</button>'
            + '<button type="button" class="onl-ic xoa" data-act="xoa" data-id="' + c.id + '" data-ma="' + esc(c.ma) + '" title="Huỷ ca này">✕</button>'
            + (ls ? '<span class="onl-ls" title="' + esc(ls) + '">⟲</span>' : '') + '</div></article>';
    }

    function veBang(ca, goc) {
        const hn = du.ngay === du.hom_nay, now = hn ? bayGio() : null;
        const tk = thongKe(ca, du.khung);
        if (!goc.length) {
            return '<div class="onl-rong"><b>Chưa có ca nào trong ngày</b><span>Nhập mã hợp đồng, chọn nhân viên và khung giờ ở ô phía trên để bắt đầu theo dõi.</span></div>';
        }
        const cot = du.khung.filter(function (k) {              // khung phụ (Sau 17h30, Chưa hẹn giờ) chỉ hiện khi đang có ca
            return !k.phu || goc.some(function (c) { return c.khung === k.ma; });
        });
        return '<div class="onl-luoi" style="--so-cot:' + cot.length + '">' + cot.map(function (k) {
            const s = tk.khung[k.ma], ds = ca.filter(function (c) { return c.khung === k.ma; });
            const a = phut(k.tu), b = phut(k.den);
            const hienTai = hn && a !== null && b !== null && now >= a && now < b;
            const quaGio = hn && b !== null && now >= b && (s.cho + s.dang) > 0;
            const ph = function (n) { return s.tong ? Math.round(n * 100 / s.tong) : 0; };
            return '<section class="onl-cot' + (hienTai ? ' hien-tai' : '') + (quaGio ? ' qua-gio' : '') + (k.ma === 'chua' ? ' chua' : '') + (ds.length ? '' : ' trong') + '">'
                + '<header><div class="onl-cot-ten"><b>' + esc(k.nhan) + '</b>'
                + (hienTai ? '<span class="onl-now">Đang diễn ra</span>' : '') + (quaGio ? '<span class="onl-trehan">Quá giờ ' + (s.cho + s.dang) + '</span>' : '')
                + '</div><div class="onl-cot-so"><b>' + s.tong + '</b> ca' + (s.tong ? ' · <span>' + s.online + ' online</span>' : '')
                + '</div><div class="onl-mini"><i class="x" style="width:' + ph(s.online) + '%"></i><i class="d" style="width:' + ph(s.dang) + '%"></i>'
                + '<i class="c" style="width:' + ph(s.cho) + '%"></i></div>'
                + '<button type="button" class="onl-them" data-act="them" data-khung="' + esc(k.ma) + '" title="Thêm ca vào khung này">+</button></header>'
                + '<div class="onl-ds">' + (ds.length ? ds.map(function (c) { return veThe(c, k, hn, now); }).join('')
                    : '<div class="onl-trong">Chưa có ca</div>') + '</div></section>';
        }).join('') + '</div>';
    }

    function ve() {
        if (!du || !document.getElementById('onl-bang')) { return; }
        const goc = du.ca.slice().sort(function (a, b) {
            const i = function (c) { return du.khung.map(function (k) { return k.ma; }).indexOf(c.khung); };
            return (i(a) - i(b)) || (a.id - b.id);
        });
        const ca = loc ? goc.filter(function (c) { return c.acc === loc; }) : goc;
        dat('onl-hero', veHero(ca, thongKe(ca, du.khung)));
        dat('onl-nguoi', veNguoi(goc));
        dat('onl-canh-bao', veCanhBao());
        dat('onl-bang', veBang(ca, goc));
    }

    // ------------------------------------------------------------------ đổi tức thì trên màn hình rồi mới báo máy chủ
    function tim(id) { return du.ca.filter(function (c) { return String(c.id) === String(id); })[0]; }

    function capNhatThieu() { du.thieu = thieuGio(du.ca, du.dk); }

    function batDauThem(acc, khung) {                           // đưa người dùng tới ô thêm ca, điền sẵn nhân viên / khung giờ
        if (acc) { window.dash_clientside.set_props('onl-f-nv', {value: acc}); }
        if (khung) { window.dash_clientside.set_props('onl-f-khung', {value: khung}); }
        const o = document.getElementById('onl-f-hd');
        if (o) { o.focus(); o.scrollIntoView({block: 'center', behavior: 'smooth'}); }
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
        else if (act === 'them') { batDauThem('', d.khung); return; }
        else if (act === 'them-nv') { batDauThem(d.acc, ''); return; }
        else if (act === 'loc-tt') { locTt = locTt === d.tt ? '' : d.tt; }
        else if (act === 'loc-nv') { loc = loc === d.acc ? '' : d.acc; }
        else { return; }
        capNhatThieu();
        ve();
    }

    function nap(goi) {
        du = goi && goi.ca ? goi : null;
        if (du && loc && !du.thieu[loc] && !du.ca.some(function (c) { return c.acc === loc; })) { loc = ''; }
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
            const s = e.target && e.target.closest ? e.target.closest('#onl-goc select[data-act="khung"]') : null;
            if (!s || !du) { return; }
            const c = tim(s.dataset.id);
            if (c && c.khung !== s.value) {
                c.khung = s.value;
                gui('khung', {id: c.id, val: s.value});
                capNhatThieu();
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
    if (typeof module !== 'undefined') { module.exports = {thongKe, thieuGio, phut}; }          // để kiểm thử bằng Node
})();
