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
    let du = null, loc = '', toiLa = '', chonTay = false, moThieu = false, moHen = false;
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


    function chonNgay() {                                       // các ngày ca được dời tới (ngày mai → ngày xa nhất cho nhập trước), mỗi ngày một dòng
        let o = '<option value="">Chọn ngày…</option>', n = ngayKe(du.ngay), i = 0;
        while (n <= (du.xa_nhat || '') && i < 8) {
            o += '<option value="' + n + '">' + (i === 0 ? 'Ngày mai · ' : '') + THU[new Date(n + 'T00:00:00').getDay()] + ' ' + ngayVn(n) + '</option>';
            n = ngayKe(n); i++;
        }
        return i ? o : '<option value="">Chưa có ngày để dời</option>';
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
        t.classList.add('hien');
        clearTimeout(t._h);
        t._h = setTimeout(function () { t.classList.remove('hien'); }, 2400);
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
            + ('0' + (d.getMonth() + 1)).slice(-2) + ' · ' + nhan + '</span><span class="grow"></span><label class="onl-chon-nhan">Nhân viên</label>' + chon + '</div>'
            + '<div class="onl-kpi">' + o('tong', tk.tong, 'Ca dự kiến', loc ? 'của ' + esc(tenCua(loc)) : 'cả phòng') + o('cho', tk.cho, 'Đang chờ lắp', 'chưa triển khai')
            + o('dang', tk.dang, 'Đang triển khai', 'đang lắp đặt') + o('xong', tk.online, 'Đã online', tk.tong ? Math.round(ph(tk.online)) + '% số ca dự kiến' : 'chưa có ca') + '</div>'
            + '<div class="onl-thanh" title="Xanh lá: đã online · Xanh dương: đang triển khai · Vàng: chờ lắp"><i class="x" style="width:' + ph(tk.online) + '%"></i><i class="d" style="width:'
            + ph(tk.dang) + '%"></i><i class="c" style="width:' + ph(tk.cho) + '%"></i></div>'
            + (loc ? '' : '<div class="onl-goi">Chọn một nhân viên ở ô trên để thêm ca vào từng khung giờ.</div>');
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
            + '<div class="onl-c-nut">' + nut + '<span class="grow"></span>'
            + '<details class="onl-mn"><summary title="Dời khung giờ, dời ngày, sửa ghi chú, huỷ">⋯</summary><div class="onl-mn-ds">'
            + '<div class="onl-mn-nhom"><div class="onl-mn-nhan">Dời ca</div>'
            + '<label class="onl-mn-hang"><span>Khung</span><select data-act="khung" data-id="' + c.id + '">' + khung + '</select></label>'
            + '<label class="onl-mn-hang"><span>Ngày</span><select data-act="ngay" data-id="' + c.id + '">' + chonNgay() + '</select></label></div>'
            + '<div class="onl-mn-nhom">'
            + '<button type="button" data-act="sua" data-id="' + c.id + '">' + (c.gc ? 'Sửa ghi chú' : 'Thêm ghi chú') + '<small>' + ((c.ls || []).length > 1 ? 'Lịch sử' : '') + '</small></button>'
            + (lech ? '<button type="button" class="luu-y" data-act="dong-bo-hen" data-id="' + c.id + '">Đổi ngày hẹn ở Nhập tồn<small>→ ' + ngayVn(du.ngay) + '</small></button>' : '')
            + '</div>'
            + '<div class="onl-mn-nhom"><button type="button" class="xoa" data-act="xoa" data-id="' + c.id + '" data-ma="' + esc(c.ma) + '">Huỷ ca này</button></div></div></details></div></article>';
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
        dat('onl-hen', veHen());
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

    function themMa(acc, khung, chu, xn) {
        if (!String(chu || '').trim()) { return; }
        gui('them', {acc: acc, khung: khung, text: chu, xn: !!xn});
        bao('Đang thêm ca...');
    }

    function lenh(act, e) {
        if (!du) { return; }
        const d = e.dataset, c = d.id ? tim(d.id) : null;
        if (act === 'tt' && c) { if (c.tt === d.val) { return; } c.tt = d.val; gui('tt', {id: c.id, val: d.val}); }
        else if (act === 'ngay' && c) {
            if (!d.ngay) { return; }
            du.ca = du.ca.filter(function (x) { return x !== c; });
            bao('Đã dời ' + c.ma + ' sang ngày ' + d.ngay.slice(8, 10) + '/' + d.ngay.slice(5, 7));
            gui('mai', {id: c.id, ngay: d.ngay});
        }
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
        else if (act === 'mo-hen') { moHen = !moHen; }
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
            const b = t.closest('#onl-goc [data-act]');
            if (!t.closest('.onl-mn')) { document.querySelectorAll('.onl-mn[open]').forEach(function (m) { m.open = false; }); }
            if (!t.closest('.onl-ton')) { document.querySelectorAll('.onl-ton[open]').forEach(function (m) { m.open = false; }); }
            if (!b || b.tagName === 'SELECT' || b.tagName === 'OPTION') { return; }
            lenh(b.dataset.act, b);
        });
        document.addEventListener('change', function (e) {
            const s = e.target && e.target.closest ? e.target.closest('#onl-goc select[data-act]') : null;
            if (!s || !du) { return; }
            if (s.dataset.act === 'loc-nv-sel') { chonNv(s.value); return; }
            const c = tim(s.dataset.id);
            if (s.dataset.act === 'ngay') { if (s.value) { s.dataset.ngay = s.value; lenh('ngay', s); } return; }
            if (s.dataset.act === 'khung' && c && c.khung !== s.value) {
                c.khung = s.value;
                gui('khung', {id: c.id, val: s.value});
                capNhatThieu();
                ve();
            }
        });
        document.addEventListener('keydown', function (e) {
            const o = e.target && e.target.classList && e.target.classList.contains('onl-nhap') ? e.target : null;
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
                    themMa(h.acc, h.khung, h.ds.map(function (x) { return x.ma; }).join(' '), true);
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
