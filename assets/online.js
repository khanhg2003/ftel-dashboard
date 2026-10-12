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
    let du = null, loc = '', locTt = '', locKhung = '';
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
    /* Kiểu "sổ điều phối": một dòng tóm tắt + thanh tiến độ phẳng, tab lọc theo người, rồi mỗi khung giờ là một nhóm dòng (mã HĐ · người ·
       trạng thái). Không thẻ, không màu pastel, không hoạt hình - để đọc nhanh và nhiều ca vẫn gọn. */
    function veTom(ca, tk) {
        const d = new Date(du.ngay + 'T00:00:00');
        const hn = du.ngay === du.hom_nay;
        const nhan = hn ? 'Hôm nay' : (du.ngay > du.hom_nay ? 'Nhập trước' : 'Đã qua');
        const ph = function (n) { return tk.tong ? n * 100 / tk.tong : 0; };
        const o = function (tt, cls, n, nhanO) {
            return '<button type="button" class="onl-o ' + cls + (locTt === tt ? ' chon' : '') + '" data-act="loc-tt" data-tt="' + tt
                + '"><b>' + n + '</b> ' + nhanO + '</button>';
        };
        const gt = loc ? ' · chỉ ' + esc(tenCua(loc)) : '';
        return '<div class="onl-tren"><h3>Theo dõi Online</h3><span class="onl-ngay">' + THU[d.getDay()] + ', ' + ('0' + d.getDate()).slice(-2) + '/'
            + ('0' + (d.getMonth() + 1)).slice(-2) + ' · ' + nhan + esc(gt) + '</span></div>'
            + '<div class="onl-so"><span class="onl-lon"><b>' + tk.online + '</b>/' + tk.tong + ' ca đã online' + (tk.tong ? ' (' + Math.round(ph(tk.online)) + '%)' : '') + '</span>'
            + o('du_kien', 'cho', tk.cho, 'chờ lắp') + o('dang_lam', 'dang', tk.dang, 'đang triển khai') + o('da_online', 'xong', tk.online, 'đã online') + '</div>'
            + '<div class="onl-thanh" title="Xanh lá: đã online · Xanh dương: đang triển khai · Vàng: chờ lắp"><i class="x" style="width:' + ph(tk.online) + '%"></i><i class="d" style="width:'
            + ph(tk.dang) + '%"></i><i class="c" style="width:' + ph(tk.cho) + '%"></i></div>';
    }

    /* Dải "giai đoạn trong ngày": mỗi khung giờ một ô (số ca, số đã online, đã qua / đang diễn ra / sắp tới). Bấm ô để chỉ xem khung đó. */
    function veGiaiDoan(ca, goc) {
        const hn = du.ngay === du.hom_nay, now = hn ? bayGio() : null, tk = thongKe(ca, du.khung);
        const cot = du.khung.filter(function (k) { return !k.phu || goc.some(function (c) { return c.khung === k.ma; }); });
        if (!goc.length) { return ''; }
        return '<div class="onl-gd">' + cot.map(function (k) {
            const s = tk.khung[k.ma], a = phut(k.tu), b = phut(k.den), ph = function (n) { return s.tong ? Math.round(n * 100 / s.tong) : 0; };
            let gd = '', nhan = '';
            if (hn && a !== null && b !== null) {
                if (now >= b) { gd = (s.cho + s.dang) > 0 ? 'tre' : 'qua'; nhan = gd === 'tre' ? 'Quá giờ ' + (s.cho + s.dang) + ' ca' : 'Đã qua'; }
                else if (now >= a) { gd = 'nay'; nhan = 'Đang diễn ra'; }
                else { gd = 'sau'; nhan = 'Sắp tới'; }
            }
            return '<button type="button" class="onl-gd-o ' + gd + (locKhung === k.ma ? ' chon' : '') + '" data-act="loc-khung" data-khung="' + esc(k.ma) + '">'
                + '<span class="onl-gd-gio">' + esc(k.nhan) + '</span><span class="onl-gd-so"><b>' + s.tong + '</b> ca</span>'
                + '<span class="onl-gd-ph">' + (s.tong ? s.online + ' đã online' : 'chưa có ca') + '</span>'
                + '<span class="onl-gd-thanh"><i class="x" style="width:' + ph(s.online) + '%"></i><i class="d" style="width:' + ph(s.dang) + '%"></i><i class="c" style="width:'
                + ph(s.cho) + '%"></i></span><em>' + nhan + '</em></button>';
        }).join('') + '</div>';
    }

    function quaGio(c, now) {
        const k = du.khung.filter(function (x) { return x.ma === c.khung; })[0];
        return c.tt !== 'da_online' && c.khung !== 'chua' && k && phut(k.den) !== null && now > phut(k.den);
    }

    function khungKeTiep(now) {                                 // khung đang diễn ra hoặc sắp tới gần nhất (không tính Chưa hẹn giờ)
        const k = du.khung.filter(function (x) { return x.ma !== 'chua' && phut(x.den) !== null && phut(x.den) > now; })[0];
        return k || null;
    }

    /* Thanh "cần xử lý ngay": ca quá giờ chưa online, hoặc cuối ngày còn ca chưa online. Dời cả nhóm bằng một cú bấm. */
    function veXuLy(goc) {
        if (du.ngay !== du.hom_nay) { return ''; }
        const now = bayGio(), chuaXong = goc.filter(function (c) { return c.tt !== 'da_online'; });
        const chinh = du.khung.filter(function (k) { return !k.phu && phut(k.den) !== null; });
        const cuoi = chinh.length ? Math.max.apply(null, chinh.map(function (k) { return phut(k.den); })) : null;
        const ids = function (ds) { return ds.map(function (c) { return c.id; }).join(','); };
        if (cuoi !== null && now >= cuoi && chuaXong.length) {
            return '<div class="onl-xl"><span><b>Hết giờ làm việc, còn ' + chuaXong.length + ' ca chưa online.</b></span>'
                + '<button type="button" data-act="bulk" data-loai="mai" data-ids="' + ids(chuaXong) + '">Dời hết sang mai</button></div>';
        }
        const qua = goc.filter(function (c) { return quaGio(c, now); });
        if (!qua.length) { return ''; }
        const tiep = khungKeTiep(now);
        return '<div class="onl-xl"><span><b>' + qua.length + ' ca quá giờ</b> mà chưa online.</span>'
            + (tiep ? '<button type="button" data-act="bulk" data-loai="khung" data-val="' + esc(tiep.ma) + '" data-ids="' + ids(qua) + '">Dời sang ' + esc(tiep.nhan) + '</button>' : '')
            + '<button type="button" data-act="bulk" data-loai="mai" data-ids="' + ids(qua) + '">Dời sang mai</button></div>';
    }

    function veNguoi(goc) {
        const th = du.thieu, ds = du.nv.map(function (n) { return n.a; }).filter(function (a) { return th[a]; });
        if (!ds.length) { return ''; }
        const tab = ds.map(function (a) {
            const t = th[a], n = goc.filter(function (c) { return c.acc === a; }).length;
            return '<button type="button" class="onl-tab' + (a === loc ? ' chon' : '') + (t.thieu > 0 ? ' thieu' : '') + '" data-act="loc-nv" data-acc="' + esc(a)
                + '" title="' + esc(tenCua(a)) + ' · đã khai ' + t.khai + '/' + t.can + ' ca có giờ">' + esc(tenGoi(a, ds)) + ' <small>' + n + '</small></button>';
        }).join('');
        return '<div class="onl-tabs"><button type="button" class="onl-tab' + (loc ? '' : ' chon') + '" data-act="loc-nv" data-acc="">Cả phòng</button>' + tab + '</div>';
    }

    function veCanhBao() {
        const th = du.thieu, ds = du.nv.map(function (n) { return n.a; }).filter(function (a) { return th[a] && th[a].thieu > 0; });
        if (!ds.length || du.ngay < du.hom_nay) { return ''; }
        return '<div class="onl-cb"><b>Chưa khai đủ giờ online:</b> ' + ds.map(function (a) {
            const t = th[a];
            return '<button type="button" class="onl-cb-nv" data-act="them-nv" data-acc="' + esc(a) + '" title="Bấm để thêm ca cho người này">'
                + esc(tenCua(a)) + ' <em>' + t.khai + '/' + t.can + '</em></button>';
        }).join('') + ' <span class="onl-cb-goi">Mỗi ca cần mã hợp đồng và khung giờ.</span></div>';
    }

    function veDong(c, k, hn, now) {
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
        return '<div class="onl-dong ' + c.tt + (qua ? ' qua' : '') + (locTt && locTt !== c.tt ? ' mo' : '') + '" data-id="' + c.id + '">'
            + '<span class="onl-ma">' + esc(c.ma) + (qua ? '<em class="onl-tre">quá giờ</em>' : '') + (c.doi >= 3 ? '<em class="onl-tre" title="Ca dời nhiều lần dễ bị huỷ">đã dời ' + c.doi + ' lần</em>' : '') + '</span>'
            + '<span class="onl-giua"><span class="onl-ten" title="' + esc(c.acc) + '">' + esc(ten) + (c.gc ? '<small title="' + esc(c.gc) + '">' + esc(c.gc) + '</small>' : '') + '</span>'
            + '<span class="onl-act"><select data-act="khung" data-id="' + c.id + '" title="Dời sang khung giờ khác">' + khung + '</select>'
            + '<button type="button" class="onl-mai" data-act="mai" data-id="' + c.id + '" title="Dời ca sang ngày mai">Mai</button>'
            + '<button type="button" class="onl-ic" data-act="sua" data-id="' + c.id + '" title="Sửa ghi chú, đổi người phụ trách, xem lịch sử">Sửa</button>'
            + '<button type="button" class="onl-ic xoa" data-act="xoa" data-id="' + c.id + '" data-ma="' + esc(c.ma) + '" title="Huỷ ca này">Huỷ</button>'
            + (ls ? '<span class="onl-ls" title="' + esc(ls) + '">Lịch sử</span>' : '') + '</span></span>'
            + '<span class="onl-tt">' + nut + '</span></div>';
    }

    function veBang(ca, goc) {
        const hn = du.ngay === du.hom_nay, now = hn ? bayGio() : null;
        const tk = thongKe(ca, du.khung);
        if (!goc.length) {
            return '<div class="onl-rong"><b>Chưa có ca nào trong ngày</b><span>Nhập mã hợp đồng, chọn nhân viên và khung giờ ở ô phía trên để bắt đầu theo dõi.</span></div>';
        }
        const cot = du.khung.filter(function (k) {              // khung phụ (Sau 17h30, Chưa hẹn giờ) chỉ hiện khi đang có ca
            return locKhung ? k.ma === locKhung : (!k.phu || goc.some(function (c) { return c.khung === k.ma; }));
        });
        return '<div class="onl-ds">' + cot.map(function (k) {
            const s = tk.khung[k.ma], ds = ca.filter(function (c) { return c.khung === k.ma; });
            const a = phut(k.tu), b = phut(k.den);
            const hienTai = hn && a !== null && b !== null && now >= a && now < b;
            const quaGio = hn && b !== null && now >= b && (s.cho + s.dang) > 0;
            return '<section class="onl-nhom' + (hienTai ? ' hien-tai' : '') + (quaGio ? ' qua-gio' : '') + (k.ma === 'chua' ? ' chua' : '') + '">'
                + '<header><span class="onl-gio">' + esc(k.nhan) + '</span><span class="onl-gio-so">' + (s.tong ? '<b>' + s.tong + '</b> ca · ' + s.online + ' online' : 'chưa có ca') + '</span>'
                + (hienTai ? '<span class="onl-tag">đang diễn ra</span>' : '') + (quaGio ? '<span class="onl-tag tre">quá giờ ' + (s.cho + s.dang) + ' ca</span>' : '')
                + '<span class="grow"></span><button type="button" class="onl-them" data-act="them" data-khung="' + esc(k.ma) + '" title="Thêm ca vào khung này">+ Thêm</button></header>'
                + ds.map(function (c) { return veDong(c, k, hn, now); }).join('') + '</section>';
        }).join('') + '</div>';
    }

    function ve() {
        if (!du || !document.getElementById('onl-bang')) { return; }
        const goc = du.ca.slice().sort(function (a, b) {
            const i = function (c) { return du.khung.map(function (k) { return k.ma; }).indexOf(c.khung); };
            return (i(a) - i(b)) || (a.id - b.id);
        });
        const ca = loc ? goc.filter(function (c) { return c.acc === loc; }) : goc;
        dat('onl-hero', veTom(ca, thongKe(ca, du.khung)));
        dat('onl-nguoi', veNguoi(goc));
        dat('onl-gd', veGiaiDoan(ca, goc));
        dat('onl-xuly', veXuLy(goc));
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
        else if (act === 'loc-khung') { locKhung = locKhung === d.khung ? '' : d.khung; }
        else if (act === 'bulk') {
            const ids = String(d.ids || '').split(',').filter(Boolean).map(Number);
            if (d.loai === 'mai') { du.ca = du.ca.filter(function (x) { return ids.indexOf(x.id) < 0; }); bao('Đã dời ' + ids.length + ' ca sang ngày mai'); }
            else { du.ca.forEach(function (x) { if (ids.indexOf(x.id) >= 0) { x.khung = d.val; } }); bao('Đã dời ' + ids.length + ' ca sang khung mới'); }
            gui('bulk', {loai: d.loai, val: d.val || '', ids: ids});
        }
        else if (act === 'loc-tt') { locTt = locTt === d.tt ? '' : d.tt; }
        else if (act === 'loc-nv') { loc = loc === d.acc ? '' : d.acc; }
        else { return; }
        capNhatThieu();
        ve();
    }

    function nap(goi) {
        du = goi && goi.ca ? goi : null;
        if (du && loc && !du.thieu[loc] && !du.ca.some(function (c) { return c.acc === loc; })) { loc = ''; }
        if (du && locKhung && !du.khung.some(function (k) { return k.ma === locKhung; })) { locKhung = ''; }
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
