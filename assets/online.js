/* =====================================================================
   Theo dõi Online trong ngày (mục dưới bảng Báo cáo ngày; quy tắc: app/online_ca.py, trang: app/ui/pages/baocaongay_online.py).

   Cách dùng (chủ app báo bản trước "khó xài" nên làm lại 12/10/2026):
   - Chọn NHÂN VIÊN một lần ở đầu mục (tài khoản dùng chung đã chọn "Tôi là" thì tự chọn sẵn người đó).
   - Mỗi KHUNG GIỜ là một cột; gõ hoặc dán mã hợp đồng ngay ở cuối cột đó rồi Enter = thêm ca vào đúng khung, không phải chọn gì nữa.
     "Từ HĐ tồn" ở cuối cột liệt kê HĐ tồn của người đang chọn, bấm là thêm vào cột đó.
   - Mỗi ca một THẺ: nhãn màu góc phải là trạng thái, hai nút "Đang lắp" / "✓ Đã online" đổi trạng thái một cú bấm, ⋯ = dời khung / dời ngày / sửa ghi chú / huỷ.
   Máy chủ gửi MỘT gói dữ liệu vào dcc.Store `onl-du-lieu`; file này tự vẽ và đổi NGAY trên màn hình rồi mới báo máy chủ qua `onl-sk`
   (máy chủ kiểm quyền, ghi lịch sử, gửi lại số thật). Các khối #onl-* không có con do Dash dựng nên sửa trực tiếp.
   ===================================================================== */
(function () {
    const TT_DAI = {du_kien: 'Chờ lắp', dang_lam: 'Đang triển khai', da_online: 'Đã online'};
    const THU = ['Chủ nhật', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy'];
    let du = null, loc = '', toiLa = '', chonTay = false, moThieu = false, moHen = false, moThem = false, themNv = '', themKhung = '', moDoi = false;
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
    function thieuGio(ca, dk, hen) {
        hen = hen || {};
        const out = {}, ds = Object.keys(dk).concat(Object.keys(hen), ca.map(function (c) { return c.acc; }));
        ds.forEach(function (a) {
            if (out[a] !== undefined) { return; }
            const cua = ca.filter(function (c) { return c.acc === a; });
            const chua = cua.filter(function (c) { return c.khung === 'chua'; }).length, khai = cua.length - chua;
            const can = Math.max(Number(dk[a] || 0), khai + chua + Number(hen[a] || 0));
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

    function ngayKe(iso) {                                      // ngày kế tiếp của một ngày YYYY-MM-DD (không lệch múi giờ)
        const d = new Date(iso + 'T00:00:00');
        d.setDate(d.getDate() + 1);
        return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
    }


    function chonNgay() {                                       // các ngày ca được dời tới: từ hôm nay tới ngày xa nhất cho nhập trước, trừ ngày đang xem (dời nhầm thì dời về lại được)
        let o = '<option value="">' + (du.ngay === du.hom_nay ? 'Hôm nay (giữ nguyên)' : 'Ngày này (giữ nguyên)') + '</option>', n = du.hom_nay, i = 0, dem = 0;
        while (n <= (du.xa_nhat || '') && i < 9) {
            if (n !== du.ngay) {
                o += '<option value="' + n + '">' + (i === 0 ? 'Hôm nay · ' : i === 1 ? 'Ngày mai · ' : '') + THU[new Date(n + 'T00:00:00').getDay()] + ' ' + ngayVn(n) + '</option>';
                dem++;
            }
            n = ngayKe(n); i++;
        }
        return dem ? o : '<option value="">Chưa có ngày để dời</option>';
    }

    function ngayVn(iso) { return String(iso || '').slice(8, 10) + '/' + String(iso || '').slice(5, 7); }

    function tenCua(acc) {
        const x = du.nv.filter(function (n) { return n.a === acc; })[0];
        return x ? x.t : acc;
    }

    function tenNgan(acc) {                                     // "Ánh Thắng": hai chữ cuối của họ tên, cho dòng ca khi đang xem cả phòng
        const t = tenCua(acc).trim().split(/\s+/);
        return t.length > 1 ? t.slice(-2).join(' ') : t[0];
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
        t._ht = null;
        t.classList.add('hien');
        clearTimeout(t._h);
        t._h = setTimeout(function () { t.classList.remove('hien'); }, 2400);
    }

    function baoHoanTac(chu, ham) {                              // thông báo kèm nút "Hoàn tác" (12 giây), bấm là chạy `ham`
        bao(chu);
        const t = document.getElementById('onl-toast');
        t._ht = ham;
        t.appendChild(document.createTextNode(' '));
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'onl-ht'; b.textContent = 'Hoàn tác';
        t.appendChild(b);
        clearTimeout(t._h);
        t._h = setTimeout(function () { t.classList.remove('hien'); t._ht = null; }, 12000);
    }

    // ------------------------------------------------------------------ vẽ
    /* Đầu mục: ngày, ô chọn nhân viên, số ca đã online + thanh tiến độ. */
    function veDau(ca, tk) {
        const d = new Date(du.ngay + 'T00:00:00'), hn = du.ngay === du.hom_nay;
        const nhan = hn ? 'Hôm nay' : (du.ngay > du.hom_nay ? 'Nhập trước' : 'Đã qua');
        const ph = function (n) { return tk.tong ? n * 100 / tk.tong : 0; };
        const th = du.thieu, lienQuan = du.nv.filter(function (n) { return th[n.a]; }), khac = du.nv.filter(function (n) { return !th[n.a]; });
        const opt = function (n) {
            const t = th[n.a];
            return '<option value="' + esc(n.a) + '"' + (n.a === loc ? ' selected' : '') + '>' + esc(n.t)
                + (t ? ' · ' + t.khai + '/' + t.can + ' ca' + (t.thieu > 0 ? ' · thiếu ' + t.thieu : '') : '') + '</option>';
        };
        const o = function (cls, n, nhanO, phu) { return '<div class="onl-k ' + cls + '"><span>' + nhanO + '</span><b>' + n + '</b><em>' + phu + '</em></div>'; };
        const chon = '<select class="onl-nv-chon" data-act="loc-nv-sel" title="Chọn nhân viên: chỉ xem ca của người đó và thêm ca cho người đó"><option value="">Cả phòng</option>'
            + (lienQuan.length ? '<optgroup label="Có ca hôm nay">' + lienQuan.map(opt).join('') + '</optgroup>' : '')
            + (khac.length ? '<optgroup label="Chưa có ca">' + khac.map(opt).join('') + '</optgroup>' : '') + '</select>';
        return '<div class="onl-tren"><h3>Theo dõi Online</h3><span class="onl-ngay">' + THU[d.getDay()] + ', ' + ('0' + d.getDate()).slice(-2) + '/'
            + ('0' + (d.getMonth() + 1)).slice(-2) + ' · ' + nhan + '</span><span class="grow"></span><label class="onl-chon-nhan">Nhân viên</label>' + chon
            + (du.ngay < du.hom_nay ? '' : '<button type="button" class="onl-them-mo" data-act="mo-them" title="Thêm ca phát sinh chưa có ở Nhập tồn">+ Thêm ca</button>') + '</div>'
            + '<div class="onl-kpi">' + o('tong', tk.tong, 'Ca dự kiến', loc ? 'của ' + esc(tenCua(loc)) : 'cả phòng') + o('cho', tk.cho, 'Đang chờ lắp', 'chưa triển khai')
            + o('dang', tk.dang, 'Đang triển khai', 'đang lắp đặt') + o('xong', tk.online, 'Đã online', tk.tong ? Math.round(ph(tk.online)) + '% số ca dự kiến' : 'chưa có ca') + '</div>'
            + '<div class="onl-thanh" title="Xanh lá: đã online · Xanh dương: đang triển khai · Vàng: chờ lắp"><i class="x" style="width:' + ph(tk.online) + '%"></i><i class="d" style="width:'
            + ph(tk.dang) + '%"></i><i class="c" style="width:' + ph(tk.cho) + '%"></i></div>'
            ;
    }

    /* Dòng nhắc gập sẵn: người đã gõ dự kiến online mà chưa khai đủ mã + khung giờ. Bấm tên là chọn người đó để khai. */
    function veNhac() {
        const th = du.thieu, ds = du.nv.filter(function (n) { return th[n.a] && th[n.a].thieu > 0; });
        if (!ds.length || du.ngay < du.hom_nay) { return ''; }
        return '<div class="onl-nhac"><button type="button" class="onl-nhac-tt" data-act="mo-thieu">' + ds.length + ' người chưa khai đủ giờ online <span>' + (moThieu ? '▴' : '▾') + '</span></button>'
            + (moThieu ? '<div class="onl-nhac-ds">' + ds.map(function (n) {
                return '<button type="button" data-act="chon-nv" data-acc="' + esc(n.a) + '">' + esc(n.t) + ' <em>' + th[n.a].khai + '/' + th[n.a].can + '</em></button>';
            }).join('') + '<span>Mỗi ca cần mã hợp đồng và khung giờ.</span></div>' : '') + '</div>';
    }

    function quaGio(c, now) {
        const k = du.khung.filter(function (x) { return x.ma === c.khung; })[0];
        return c.tt !== 'da_online' && c.khung !== 'chua' && k && phut(k.den) !== null && now > phut(k.den);
    }

    function khungKeTiep(now) {                                 // khung đang diễn ra hoặc sắp tới gần nhất (không tính Chưa hẹn giờ)
        return du.khung.filter(function (x) { return x.ma !== 'chua' && phut(x.den) !== null && phut(x.den) > now; })[0] || null;
    }

    /* Thanh "cần xử lý ngay": ca quá giờ chưa online, hoặc cuối ngày còn ca chưa online. Dời cả nhóm bằng một cú bấm. */
    function veXuLy(goc) {
        if (du.ngay !== du.hom_nay) { return ''; }
        const now = bayGio(), chuaXong = goc.filter(function (c) { return c.tt !== 'da_online'; });
        const chinh = du.khung.filter(function (k) { return !k.phu && phut(k.den) !== null; });
        const cuoiNgay = chinh.length ? Math.max.apply(null, chinh.map(function (k) { return phut(k.den); })) : null;
        const ids = function (ds) { return ds.map(function (c) { return c.id; }).join(','); };
        if (cuoiNgay !== null && now >= cuoiNgay && chuaXong.length) {
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

    /* Nhập tồn có ca hẹn thi công đúng ngày đang xem mà chưa có ca ở đây: MỘT dòng gập (giống dòng "chưa khai đủ giờ"); mở ra thì gom theo người,
       chọn khung giờ một lần rồi bấm từng mã hoặc "Thêm tất cả". */
    function veHen() {
        if (du.ngay < du.hom_nay || !du.hen) { return ''; }
        const hn = du.ngay === du.hom_nay, nhom = [];
        let tong = 0;
        Object.keys(du.hen).forEach(function (a) { if (!loc || a === loc) { nhom.push(a); tong += du.hen[a].length; } });
        if (!tong) { return ''; }
        const tt = '<button type="button" class="onl-hen-tt" data-act="mo-hen">Nhập tồn hẹn ' + (hn ? 'hôm nay' : 'ngày này') + ': ' + tong + ' ca chưa xếp khung giờ <span>'
            + (moHen ? '▴' : '▾') + '</span></button>';
        if (!moHen) { return '<div class="onl-hen">' + tt + '</div>'; }
        const tiep = hn ? khungKeTiep(bayGio()) : null, macDinh = tiep || du.khung.filter(function (k) { return !k.phu; })[0];
        const chonKhung = du.khung.filter(function (k) { return k.ma !== 'chua'; }).map(function (k) {
            return '<option value="' + esc(k.ma) + '"' + (macDinh && k.ma === macDinh.ma ? ' selected' : '') + '>' + esc(k.nhan) + '</option>';
        }).join('');
        return '<div class="onl-hen">' + tt + '<div class="onl-hen-ds"><div class="onl-hen-khung">Xếp vào khung <select>' + chonKhung + '</select><span>rồi bấm mã để thêm</span></div>'
            + nhom.map(function (a) {
                return '<div class="onl-hen-nguoi"><b>' + esc(tenCua(a)) + '</b><div class="onl-hen-ma">' + du.hen[a].map(function (x) {
                    return '<button type="button" data-act="them-hen" data-acc="' + esc(a) + '" data-ma="' + esc(x.ma) + '" title="Tồn ' + x.ton + ' ngày">' + esc(x.ma) + '</button>';
                }).join('') + (du.hen[a].length > 1 ? '<button type="button" class="tat" data-act="them-hen-tat" data-acc="' + esc(a) + '">Thêm tất cả (' + du.hen[a].length + ')</button>' : '') + '</div></div>';
            }).join('') + '</div></div>';
    }

    /* Ca phát sinh trong ngày mà chưa kịp có ở Nhập tồn: ngoài trang chỉ có MỘT nút, bấm mới mở khung 4 ô (mã HĐ, người phụ trách, khung giờ, ghi chú).
       Khung nằm trong hộp thoại `onl-tm` (Python dựng), nội dung vẽ ở đây và không phụ thuộc bộ lọc đang chọn nên chữ đang gõ không bị xoá khi bảng vẽ lại. */
    function veThem() {
        if (du.ngay < du.hom_nay) { return ''; }
        const macDinh = (du.ngay === du.hom_nay ? khungKeTiep(bayGio()) : null) || du.khung.filter(function (k) { return !k.phu; })[0];
        const kh = themKhung || (macDinh ? macDinh.ma : '');
        const opt = function (v, t, chon) { return '<option value="' + esc(v) + '"' + (chon ? ' selected' : '') + '>' + esc(t) + '</option>'; };
        return '<div class="onl-them-f">'
            + '<label>Mã hợp đồng<input class="t-ma" type="text" placeholder="VD: DAAAP6381 (dán nhiều mã được)" autocomplete="off"></label>'
            + '<label>Người phụ trách<select class="t-nv" data-act="them-nv">' + opt('', 'Chọn người…', !themNv)
            + du.nv.map(function (n) { return opt(n.a, n.t, n.a === themNv); }).join('') + '</select></label>'
            + '<label>Khung giờ<select class="t-kh" data-act="them-kh">' + du.khung.map(function (k) { return opt(k.ma, k.nhan, k.ma === kh); }).join('') + '</select></label>'
            + '<label>Ghi chú<input class="t-gc" type="text" maxlength="200" placeholder="Không bắt buộc" autocomplete="off"></label>'
            + '<div class="onl-them-loi"></div></div>';
    }

    /* Menu ⋯ → "Dời ca": chọn khung giờ + ngày rồi bấm MỘT nút xác nhận (nút nói rõ sẽ dời tới đâu), nên bấm nhầm một ô không làm ca đi đâu cả. */
    function nhanKhung(ma) { return (du.khung.filter(function (k) { return k.ma === ma; })[0] || {}).nhan || ''; }
    function ngayDai(iso) { return THU[new Date(iso + 'T00:00:00').getDay()] + ' ' + ngayVn(iso); }

    function capNhatNutDoi(m) {
        const c = tim(m.dataset.id), kh = m.querySelector('[data-act="dm-kh"]'), ng = m.querySelector('[data-act="dm-ngay"]'), nut = m.querySelector('[data-act="dm-ok"]');
        if (!c || !kh || !ng || !nut) { return; }
        nut.disabled = !ng.value && kh.value === c.khung;
        nut.title = nut.disabled ? 'Chọn khung giờ hoặc ngày mới để dời' : (ng.value ? 'Dời sang ' + ngayDai(ng.value) + ' · ' + nhanKhung(kh.value) : 'Chuyển sang ' + nhanKhung(kh.value));
    }

    function xacNhanDoi(m) {                                    // hỏi lại trước khi dời, dời xong có nút Hoàn tác
        const c = tim(m.dataset.id), kh = m.querySelector('[data-act="dm-kh"]').value, ng = m.querySelector('[data-act="dm-ngay"]').value;
        if (!c) { return; }
        if (ng) {
            if (!window.confirm('Dời ca ' + c.ma + ' sang ' + ngayDai(ng) + ' · ' + nhanKhung(kh) + '?\nNgày hẹn thi công ở Nhập tồn sẽ đổi theo.')) { return; }
            const goc = du.ngay, khCu = c.khung;
            du.ca = du.ca.filter(function (x) { return x !== c; });
            gui('mai', {id: c.id, ngay: ng, khung: kh});
            baoHoanTac('Đã dời ' + c.ma + ' sang ' + ngayDai(ng), function () {
                gui('ve_ngay', {ma: c.ma, tu: ng, ve: goc, khung: khCu});
                bao('Đang đưa ' + c.ma + ' về lại ' + ngayDai(goc) + '...');
            });
        } else if (kh !== c.khung) {
            if (!window.confirm('Chuyển ca ' + c.ma + ' sang ' + nhanKhung(kh) + '?')) { return; }
            const khCu = c.khung;
            c.khung = kh;
            gui('khung', {id: c.id, val: kh});
            baoHoanTac('Đã chuyển ' + c.ma + ' sang ' + nhanKhung(kh), function () {
                const x = tim(c.id);
                if (x) { x.khung = khCu; gui('khung', {id: x.id, val: khCu}); capNhatThieu(); ve(); }
                bao('Đã hoàn tác ' + c.ma);
            });
        }
        capNhatThieu();
        ve();
    }

    function moHopThem(mo) {
        window.dash_clientside.set_props('onl-tm', {className: mo ? 'modal mo' : 'modal'});
        if (mo) { setTimeout(function () { const o = document.querySelector('#onl-them .t-ma'); if (o) { o.focus(); } }, 80); }
    }

    /* Thống kê ca dời của ngày đang xem: MỘT thanh gập (xám, ẩn sẵn); mở ra thì gom theo ngày đích / ngày gốc. */
    function veDoi() {
        const d = du.doi || {di: [], den: []};
        const loai = function (ds) { return ds.filter(function (x) { return !loc || x.a === loc; }); };
        const di = loai(d.di), den = loai(d.den);
        if (!di.length && !den.length) { return ''; }
        const tt = '<button type="button" class="onl-doi-tt" data-act="mo-doi">Ca dời ngày: ' + [di.length ? di.length + ' dời đi' : '', den.length ? den.length + ' dời đến' : ''].filter(Boolean).join(' · ')
            + ' <span>' + (moDoi ? '▴' : '▾') + '</span></button>';
        if (!moDoi) { return '<div class="onl-doi">' + tt + '</div>'; }
        const nhom = function (ds, khoa, tieu, mui) {
            if (!ds.length) { return ''; }
            const g = {};
            ds.forEach(function (x) { (g[x[khoa]] = g[x[khoa]] || []).push(x); });
            return '<div class="onl-doi-nhom"><div class="onl-doi-nhan">' + tieu + ' <em>' + ds.length + ' ca</em></div>' + Object.keys(g).sort().map(function (k) {
                // Dời đi (khoa 'den' = ngày đích k): ca đang ở ngày k, đưa về NGÀY NÀY. Dời đến (khoa 'tu' = ngày gốc k): ca đang ở NGÀY NÀY, trả về ngày gốc k.
                const tu = khoa === 'den' ? k : du.ngay, ve = khoa === 'den' ? du.ngay : k, mas = g[k].map(function (x) { return x.ma; }).join(',');
                const nut = '<button type="button" class="onl-doi-ve" data-act="doi-ve" data-tu="' + tu + '" data-ve="' + ve + '" data-mas="' + esc(mas) + '" title="'
                    + (khoa === 'tu' ? 'Trả ' + g[k].length + ' ca về ' : 'Đưa ' + g[k].length + ' ca về ') + ngayDai(ve) + '">↩ '
                    + (khoa === 'tu' ? 'Trả về ' + ngayVn(ve) : ve === du.hom_nay ? 'Đưa về hôm nay' : 'Đưa về ' + ngayVn(ve)) + '</button>';
                return '<div class="onl-doi-d"><b>' + mui + ' ' + ngayDai(k) + '</b><span>' + g[k].length + ' ca</span><div class="onl-doi-ma">' + g[k].map(function (x) {
                    return '<i title="' + esc(tenCua(x.a)) + '">' + esc(x.ma) + (loc ? '' : ' · ' + esc(tenNgan(x.a))) + '</i>';
                }).join('') + '</div>' + nut + '</div>';
            }).join('') + '</div>';
        };
        return '<div class="onl-doi">' + tt + '<div class="onl-doi-ds">' + nhom(di, 'den', 'Dời đi', '→') + nhom(den, 'tu', 'Dời đến', '←') + '</div></div>';
    }

    function veDong(c, hn, now) {
        const qua = hn && quaGio(c, now), xong = c.tt === 'da_online', dang = c.tt === 'dang_lam', lech = (du.lech || {})[c.ma];
        const khung = du.khung.map(function (x) {
            return '<option value="' + esc(x.ma) + '"' + (x.ma === c.khung ? ' selected' : '') + '>' + esc(x.nhan) + '</option>';
        }).join('');
        const nut = xong
            ? '<button type="button" class="onl-b" data-act="tt" data-id="' + c.id + '" data-val="du_kien" title="Bỏ trạng thái đã online">Bỏ đã online</button>'
            : '<button type="button" class="onl-b' + (dang ? ' on' : '') + '" data-act="tt" data-id="' + c.id + '" data-val="' + (dang ? 'du_kien' : 'dang_lam') + '" title="Đánh dấu đang triển khai (bấm lại để bỏ)">Đang lắp</button>'
                + '<button type="button" class="onl-b chinh" data-act="tt" data-id="' + c.id + '" data-val="da_online" title="Ca đã online">✓ Đã online</button>';
        return '<article class="onl-c ' + c.tt + (qua ? ' qua' : '') + '" data-id="' + c.id + '">'
            + '<div class="onl-c-dau"><span class="onl-ma">' + esc(c.ma) + '</span><span class="grow"></span><span class="onl-bg ' + c.tt + '">' + TT_DAI[c.tt] + '</span></div>'
            + '<div class="onl-c-ai">' + (loc ? '' : '<span title="' + esc(tenCua(c.acc)) + '">' + esc(tenNgan(c.acc)) + '</span>')
            + (qua ? '<em class="onl-tre">quá giờ</em>' : '') + (c.doi >= 3 ? '<em class="onl-tre" title="Ca dời nhiều lần dễ bị huỷ">đã dời ' + c.doi + ' lần</em>' : '')
            + (lech ? '<em class="onl-lech" title="Nhập tồn đang ghi ' + (lech.loai === 'tra_ve' ? 'trả về' : 'hẹn thi công') + ' ngày ' + ngayVn(lech.ngay) + ', khác ngày của ca">Nhập tồn: ' + ngayVn(lech.ngay) + '</em>' : '')
            + (c.gc ? '<small title="' + esc(c.gc) + '">' + esc(c.gc) + '</small>' : '') + '</div>'
            + (c.khung === 'chua' && !xong ? '<select class="onl-xep" data-act="khung" data-id="' + c.id + '" title="Chọn khung giờ cho ca này"><option value="chua" selected>Xếp khung giờ…</option>'
                + du.khung.filter(function (k) { return k.ma !== 'chua'; }).map(function (k) { return '<option value="' + esc(k.ma) + '">' + esc(k.nhan) + '</option>'; }).join('') + '</select>' : '')
            + '<div class="onl-c-nut">' + nut + '<span class="grow"></span>'
            + '<details class="onl-mn"><summary title="Dời khung giờ, dời ngày, sửa ghi chú, huỷ">⋯</summary><div class="onl-mn-ds">'
            + '<div class="onl-mn-nhom">'
            + '<button type="button" data-act="sua" data-id="' + c.id + '">' + (c.gc ? 'Sửa ghi chú' : 'Thêm ghi chú') + '<small>' + ((c.ls || []).length > 1 ? 'Lịch sử' : '') + '</small></button>'
            + (lech ? '<button type="button" class="luu-y" data-act="dong-bo-hen" data-id="' + c.id + '">Đổi ngày hẹn ở Nhập tồn<small>→ ' + ngayVn(du.ngay) + '</small></button>' : '')
            + '</div>'
            + '<div class="onl-mn-form" data-id="' + c.id + '"><div class="onl-mn-nhom"><div class="onl-mn-nhan">Dời ca</div>'
            + '<label class="onl-mn-hang"><span>Khung</span><select data-act="dm-kh">' + khung + '</select></label>'
            + '<label class="onl-mn-hang"><span>Ngày</span><select data-act="dm-ngay">' + chonNgay() + '</select></label></div>'
            + '<div class="onl-mn-chan"><button type="button" class="onl-mn-ok" data-act="dm-ok" disabled title="Chọn khung giờ hoặc ngày mới để dời">Dời ca</button>'
            + '<button type="button" class="onl-mn-huy" data-act="xoa" data-id="' + c.id + '" data-ma="' + esc(c.ma) + '">Hủy ca</button></div></div></div></details></div></article>';
    }

    /* Chân mỗi cột: ô gõ / dán mã + danh sách HĐ tồn của người đang chọn. Chưa chọn người thì nhắc chọn. */
    function veChan(k) {
        if (!loc) { return ''; }
        const henMa = {};
        ((du.hen && du.hen[loc]) || []).forEach(function (x) { henMa[x.ma] = 1; });
        const ton = ((du.ton && du.ton[loc]) || []).slice().sort(function (a, b) { return (henMa[b.ma] ? 1 : 0) - (henMa[a.ma] ? 1 : 0); });
        const dd = ton.length ? '<details class="onl-ton"><summary>Từ HĐ tồn (' + ton.length + ')</summary><div class="onl-ton-ds">' + ton.map(function (x) {
            return '<button type="button" data-act="them-ton" data-khung="' + esc(k.ma) + '" data-ma="' + esc(x.ma) + '"><b>' + esc(x.ma) + '</b><span>' + (henMa[x.ma] ? '<i>hẹn hôm nay</i> · ' : '')
                + 'tồn ' + x.ton + ' ngày</span></button>';
        }).join('') + '</div></details>' : '';
        return '<div class="onl-chan"><input type="text" class="onl-nhap" data-khung="' + esc(k.ma) + '" maxlength="400" autocomplete="off" placeholder="+ Thêm mã HĐ (dán nhiều mã)">' + dd + '</div>';
    }

    function veBang(ca, goc) {
        const hn = du.ngay === du.hom_nay, now = hn ? bayGio() : null, tk = thongKe(ca, du.khung);
        const cot = du.khung.filter(function (k) {              // khung phụ (Sau 17h30, Chưa hẹn giờ) chỉ hiện khi đang có ca
            return !k.phu || goc.some(function (c) { return c.khung === k.ma; });
        });
        return '<div class="onl-luoi" style="--so-cot:' + cot.length + '">' + cot.map(function (k) {
            const s = tk.khung[k.ma], ds = ca.filter(function (c) { return c.khung === k.ma; });
            const a = phut(k.tu), b = phut(k.den), ph = function (n) { return s.tong ? Math.round(n * 100 / s.tong) : 0; };
            let gd = '', nhan = '';
            if (hn && a !== null && b !== null) {
                if (now >= b) { gd = (s.cho + s.dang) > 0 ? 'tre' : 'qua'; nhan = gd === 'tre' ? 'Quá giờ' : 'Đã qua'; }
                else if (now >= a) { gd = 'nay'; nhan = 'Đang diễn ra'; }
                else { gd = 'sau'; nhan = 'Sắp tới'; }
            }
            return '<section class="onl-cot ' + gd + '"><header><div class="onl-cot-ten"><b>' + esc(k.nhan) + '</b>' + (nhan ? '<span class="onl-tag ' + gd + '">' + nhan + '</span>' : '')
                + '</div><div class="onl-cot-so"><b>' + s.tong + '</b> ca' + (s.tong ? ' · ' + s.online + ' online' : '') + '</div>'
                + '<div class="onl-mini"><i class="x" style="width:' + ph(s.online) + '%"></i><i class="d" style="width:' + ph(s.dang) + '%"></i><i class="c" style="width:' + ph(s.cho) + '%"></i></div></header>'
                + '<div class="onl-ds">' + ds.map(function (c) { return veDong(c, hn, now); }).join('') + '</div>' + veChan(k) + '</section>';
        }).join('') + '</div>';
    }

    function ve() {
        if (!du || !document.getElementById('onl-bang')) { return; }
        const goc = du.ca.slice().sort(function (a, b) {
            const i = function (c) { return du.khung.map(function (k) { return k.ma; }).indexOf(c.khung); };
            return (i(a) - i(b)) || (a.id - b.id);
        });
        const ca = loc ? goc.filter(function (c) { return c.acc === loc; }) : goc;
        const giu = document.activeElement && document.activeElement.classList && document.activeElement.classList.contains('onl-nhap') ? document.activeElement : null;
        const giuGt = giu ? {khung: giu.dataset.khung, v: giu.value} : null;
        dat('onl-hero', veDau(ca, thongKe(ca, du.khung)) + veNhac());
        dat('onl-them', veThem());
        dat('onl-hen', veHen());
        dat('onl-doi', veDoi());
        dat('onl-xuly', veXuLy(goc));
        dat('onl-bang', veBang(ca, goc));
        if (giuGt) {                                            // đang gõ dở mà bảng vẽ lại (nhịp tự động): giữ chữ và con trỏ
            const o = document.querySelector('.onl-nhap[data-khung="' + giuGt.khung + '"]');
            if (o) { o.value = giuGt.v; o.focus(); }
        }
    }

    // ------------------------------------------------------------------ đổi tức thì trên màn hình rồi mới báo máy chủ
    function tim(id) { return du.ca.filter(function (c) { return String(c.id) === String(id); })[0]; }

    function henSo() {                                          // số ca hẹn hôm nay (Nhập tồn) mỗi người còn chưa có ca
        const o = {};
        Object.keys(du.hen || {}).forEach(function (a) { o[a] = du.hen[a].length; });
        return o;
    }

    function capNhatThieu() { du.thieu = thieuGio(du.ca, du.dk, henSo()); }

    function chonNv(acc) { loc = acc || ''; chonTay = true; ve(); }

    function themMa(acc, khung, chu, xn, gc) {
        if (!String(chu || '').trim()) { return; }
        gui('them', {acc: acc, khung: khung, text: chu, xn: !!xn, gc: gc || ''});
        bao('Đang thêm ca...');
    }

    function themTay() {                                        // gửi ca phát sinh từ khung 4 ô; thiếu gì thì báo ngay trong khung
        const f = document.getElementById('onl-them');
        if (!f || !f.querySelector('.t-ma')) { return; }
        const ma = f.querySelector('.t-ma'), gc = f.querySelector('.t-gc'), kh = f.querySelector('.t-kh'), loi = f.querySelector('.onl-them-loi');
        const bao_loi = function (chu, o) { loi.textContent = chu; if (o) { o.focus(); } };
        if (!ma.value.trim()) { bao_loi('Nhập mã hợp đồng.', ma); return; }
        if (!themNv) { bao_loi('Chọn người phụ trách.', f.querySelector('.t-nv')); return; }
        loi.textContent = '';
        themKhung = kh.value;
        themMa(themNv, kh.value, ma.value, false, gc.value);
        ma.value = ''; gc.value = '';
        moHopThem(false);
        if (loc && loc !== themNv) { loc = themNv; chonTay = true; ve(); }
    }

    function lenh(act, e) {
        if (!du) { return; }
        const d = e.dataset, c = d.id ? tim(d.id) : null;
        if (act === 'tt' && c) { if (c.tt === d.val) { return; } c.tt = d.val; gui('tt', {id: c.id, val: d.val}); }
        else if (act === 'xoa' && c) {
            if (!window.confirm('Huỷ ca ' + d.ma + '?')) { return; }
            du.ca = du.ca.filter(function (x) { return x !== c; });
            bao('Đã huỷ ca ' + d.ma);
            gui('xoa', {id: c.id});
        }
        else if (act === 'sua' && c) {
            gui('sua', {id: c.id});
            let lan = 0;                                          // cửa sổ mở sau khi máy chủ trả lời: chờ rồi đặt con trỏ vào ô ghi chú
            const tim = setInterval(function () {
                const md = document.getElementById('onl-md'), o = document.getElementById('onl-md-gc');
                if (md && o && md.className.indexOf(' mo') >= 0) { o.focus(); o.setSelectionRange(o.value.length, o.value.length); clearInterval(tim); }
                else if (++lan > 20) { clearInterval(tim); }
            }, 100);
            return;
        }
        else if (act === 'them-ton') { themMa(loc, d.khung, d.ma); return; }
        else if (act === 'dm-ok') { xacNhanDoi(e.closest('.onl-mn-form')); return; }
        else if (act === 'mo-hen') { moHen = !moHen; }
        else if (act === 'mo-doi') { moDoi = !moDoi; }
        else if (act === 'doi-ve') {                              // đưa các ca đã dời về lại ngày cũ (nhóm trong thanh "Ca dời ngày")
            const mas = String(d.mas || '').split(',').filter(Boolean);
            if (!window.confirm('Đưa ' + mas.length + ' ca (' + mas.join(', ') + ') về lại ' + ngayDai(d.ve) + '?' + String.fromCharCode(10) + 'Ngày hẹn thi công ở Nhập tồn sẽ đổi theo.')) { return; }
            gui('ve_ngay', {mas: mas, tu: d.tu, ve: d.ve, khung: ''});
            bao('Đang đưa ' + mas.length + ' ca về lại ' + ngayDai(d.ve) + '...');
            return;
        }
        else if (act === 'mo-them') { themNv = themNv || loc || toiLa || ''; ve(); moHopThem(true); return; }
        else if (act === 'them-hen' || act === 'them-hen-tat') {
            const k = e.closest('.onl-hen').querySelector('select');
            const ma = act === 'them-hen' ? d.ma : (du.hen[d.acc] || []).map(function (x) { return x.ma; }).join(' ');
            themMa(d.acc, k ? k.value : '', ma);
            return;
        }
        else if (act === 'dong-bo-hen' && c) { if (du.lech) { delete du.lech[c.ma]; } bao('Đang cập nhật ngày hẹn ở Nhập tồn...'); gui('dong_bo_hen', {id: c.id}); }
        else if (act === 'mo-thieu') { moThieu = !moThieu; }
        else if (act === 'chon-nv') { loc = d.acc; chonTay = true; }
        else if (act === 'bulk') {
            const ids = String(d.ids || '').split(',').filter(Boolean).map(Number);
            if (d.loai === 'mai') { du.ca = du.ca.filter(function (x) { return ids.indexOf(x.id) < 0; }); bao('Đã dời ' + ids.length + ' ca sang ngày mai'); }
            else { du.ca.forEach(function (x) { if (ids.indexOf(x.id) >= 0) { x.khung = d.val; } }); bao('Đã dời ' + ids.length + ' ca sang khung mới'); }
            gui('bulk', {loai: d.loai, val: d.val || '', ids: ids});
        }
        else { return; }
        capNhatThieu();
        ve();
    }

    function nap(goi) {
        du = goi && goi.ca ? goi : null;
        if (du) {
            if (loc && !du.nv.some(function (n) { return n.a === loc; })) { loc = ''; }
            if (!chonTay && toiLa && !loc && du.nv.some(function (n) { return n.a === toiLa; })) { loc = toiLa; }      // "Tôi là" → xem sẵn ca của mình
        }
        ve();
        return Date.now();
    }

    if (typeof document !== 'undefined') {
        document.addEventListener('click', function (e) {
            const t = e.target && e.target.closest ? e.target : null;
            if (!t) { return; }
            if (t.closest('#onl-toast .onl-ht')) { const tb = document.getElementById('onl-toast'), h = tb._ht; if (h) { tb._ht = null; h(); } return; }
            if (t.closest('#onl-tm-ok')) { themTay(); return; }
            if (t.closest('#onl-tm-dong, #onl-tm-huy')) { moHopThem(false); return; }
            const b = t.closest('#onl-goc [data-act]');
            if (!t.closest('.onl-mn')) { document.querySelectorAll('.onl-mn[open]').forEach(function (m) { m.open = false; }); }
            if (!t.closest('.onl-ton')) { document.querySelectorAll('.onl-ton[open]').forEach(function (m) { m.open = false; }); }
            if (!b || b.tagName === 'SELECT' || b.tagName === 'OPTION') { return; }
            lenh(b.dataset.act, b);
        });
        document.addEventListener('change', function (e) {
            const s = e.target && e.target.closest ? e.target.closest('#onl-goc select[data-act], #onl-tm select[data-act]') : null;
            if (!s || !du) { return; }
            if (s.dataset.act === 'loc-nv-sel') { chonNv(s.value); return; }
            if (s.dataset.act === 'dm-kh' || s.dataset.act === 'dm-ngay') { capNhatNutDoi(s.closest('.onl-mn-form')); return; }
            if (s.dataset.act === 'them-nv') { themNv = s.value; return; }
            if (s.dataset.act === 'them-kh') { themKhung = s.value; return; }
            const c = tim(s.dataset.id);
            if (s.dataset.act === 'khung' && c && c.khung !== s.value) {
                c.khung = s.value;
                bao('Đã xếp ' + c.ma + ' vào ' + ((du.khung.filter(function (k) { return k.ma === s.value; })[0] || {}).nhan || ''));
                gui('khung', {id: c.id, val: s.value});
                capNhatThieu();
                ve();
            }
        });
        document.addEventListener('keydown', function (e) {
            const o = e.target && e.target.classList && e.target.classList.contains('onl-nhap') ? e.target : null;
            if (e.target && e.target.closest && e.target.closest('#onl-them') && e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); themTay(); return; }
            if (e.target && e.target.id === 'onl-md-gc' && e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const ok = document.getElementById('onl-md-ok');
                if (ok) { ok.click(); }
                return;
            }
            if (o && e.key === 'Enter') { e.preventDefault(); const v = o.value; o.value = ''; themMa(loc, o.dataset.khung, v); }
        });
        setInterval(function () {                                // đánh dấu "đang diễn ra" / "quá giờ" chạy theo đồng hồ
            const dangChon = document.activeElement && document.activeElement.closest && document.activeElement.closest('#onl-goc');
            if (du && du.ngay === du.hom_nay && !dangChon) { ve(); }
        }, 60000);
    }

    if (typeof window !== 'undefined') {
        window.dash_clientside = window.dash_clientside || {};
        window.dash_clientside.ftel = Object.assign(window.dash_clientside.ftel || {}, {
            ve_online: nap,
            onl_bao: function (tb) { if (tb && tb.msg) { bao(tb.msg); } return window.dash_clientside.no_update; },
            onl_hoi: function (h) {                              // Nhập tồn đang hẹn / trả về NGÀY KHÁC: hỏi sale trước, đồng ý thì thêm và Nhập tồn tự đổi ngày
                if (!h || !h.ds || !h.ds.length) { return window.dash_clientside.no_update; }
                const dong = h.ds.map(function (x) { return x.ma + ' (Nhập tồn đang ' + (x.loai === 'tra_ve' ? 'ghi trả về' : 'hẹn thi công') + ' ngày ' + ngayVn(x.ngay) + ')'; }).join('\n');
                if (window.confirm('Các hợp đồng sau đang có ngày khác ở Nhập tồn:\n' + dong + '\n\nChuyển sang hẹn thi công ngày ' + ngayVn(h.ngay)
                    + '? Nhập tồn sẽ tự cập nhật ngày hẹn.')) {
                    themMa(h.acc, h.khung, h.ds.map(function (x) { return x.ma; }).join(' '), true, h.gc);
                }
                return window.dash_clientside.no_update;
            },
            onl_toi_la: function (v) {                           // "Tôi là" đổi: xem sẵn ca của người đó (trừ khi đã tự chọn người khác)
                toiLa = v || '';
                if (du && !chonTay && toiLa && du.nv.some(function (n) { return n.a === toiLa; })) { loc = toiLa; ve(); }
                return window.dash_clientside.no_update;
            }
        });
    }
    if (typeof module !== 'undefined') { module.exports = {thongKe, thieuGio, phut}; }          // để kiểm thử bằng Node
})();
