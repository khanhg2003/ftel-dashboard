/* =====================================================================
   Nói để nhập Báo cáo ngày (app/giong_noi.py, app/ui/pages/baocaongay_giong.py).

   Bấm nút micro #bn-gn-mic: bắt đầu nghe, bấm lần nữa (hoặc quá 60 giây) thì dừng. Có hai cách chuyển thành chữ:
   - "trinh_duyet" (mặc định, miễn phí): nhận dạng giọng nói có sẵn của trình duyệt (Chrome / Edge / Safari), chữ
     ra ngay trên máy; không gửi ghi âm về máy chủ của app.
   - "openai": ghi âm rồi gửi máy chủ để OpenAI chuyển thành chữ (chính xác hơn, tính tiền). Cũng là đường dự phòng
     khi trình duyệt không có nhận dạng sẵn. Quản trị chọn ở Quản trị → Trợ lý AI.
   Kết quả ghi vào dcc.Store "bn-gn-kq": {loai: "chu", van_ban} hoặc {loai: "am", mime, b64}.
   ===================================================================== */
(function () {
    const TOI_DA_GIAY = 60;
    const KIEU_AM = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    const NhanDang = window.SpeechRecognition || window.webkitSpeechRecognition;
    let st = null;                       // phiên đang nghe

    function $(id) { return document.getElementById(id); }

    function trangThai(chu, loai) {      // dòng báo nổi phía trên nút; dựng bằng DOM thuần để React không ghi đè
        let e = $('bn-gn-tt');
        if (!e) { e = document.createElement('div'); e.id = 'bn-gn-tt'; document.body.appendChild(e); }
        e.textContent = chu || '';
        e.className = chu ? 'co ' + (loai || '') : '';
    }

    function nut(dang) {
        const b = $('bn-gn-mic');
        if (!b) { return; }
        b.classList.toggle('dang-nghe', !!dang);
        const c = b.querySelector('.gn-chu');
        if (c) { c.textContent = dang ? 'Bấm để dừng' : 'Nói để nhập'; }
    }

    function gui(du_lieu) {
        window.dash_clientside.set_props('bn-gn-kq', {data: Object.assign({t: Date.now()}, du_lieu)});
        trangThai('Đang phân tích…', 'bao');
        let lan = 0;                     // tắt dòng báo khi hộp kiểm tra đã hiện (hoặc sau 45 giây)
        const hen = setInterval(function () {
            const h = $('bn-gn');
            if ((h && h.classList.contains('mo')) || ++lan > 150) { clearInterval(hen); trangThai(''); }
        }, 300);
    }

    function dong() {
        if (!st) { return; }
        clearInterval(st.dem);
        clearTimeout(st.han);
        nut(false);
    }

    // ------------------------------------------------------------ nhận dạng sẵn của trình duyệt
    function nghePhienTrinhDuyet() {
        const r = new NhanDang();
        r.lang = 'vi-VN';
        r.interimResults = true;
        r.continuous = false;            // Android hay lặp chữ khi continuous=true; tự bật lại khi ngắt quãng
        let chot = '', tam = '', loi = '';
        st = {kieu: 'chu', dung: false, r: r, bat: Date.now()};
        const hien = function () {
            const giay = Math.floor((Date.now() - st.bat) / 1000);
            const chu = (chot + ' ' + tam).trim();
            trangThai('Đang nghe ' + giay + 's… ' + (chu ? '“' + chu + '”' : 'hãy nói'), 'nghe');
        };
        r.onresult = function (e) {
            tam = '';
            for (let i = e.resultIndex; i < e.results.length; i++) {
                const t = e.results[i][0].transcript.trim();
                if (e.results[i].isFinal) { chot = (chot + ' ' + t).trim(); } else { tam += ' ' + t; }
            }
            hien();
        };
        r.onerror = function (e) {
            loi = e.error || 'loi';
            if (loi === 'no-speech' || loi === 'aborted') { loi = ''; }
        };
        r.onend = function () {
            if (!st.dung && !loi) {                  // ngắt quãng im lặng: nghe tiếp cho tới khi người dùng bấm dừng
                try { r.start(); return; } catch (err) { /* đang chạy rồi */ }
            }
            dong();
            const chu = (chot + ' ' + tam).trim();
            const thongBao = {
                'not-allowed': 'Chưa cấp quyền micro. Bấm biểu tượng khoá cạnh địa chỉ web, cho phép micro rồi thử lại.',
                'service-not-allowed': 'Điện thoại chưa bật đọc chính tả. iPhone: Cài đặt → Cài đặt chung → Bàn phím → '
                    + 'Bật đọc chính tả. Hoặc bấm nút Gõ rồi dùng micro của bàn phím.',
                'audio-capture': 'Không tìm thấy micro trên thiết bị này.',
                'network': 'Mất mạng nên chưa nghe được, kiểm tra kết nối rồi thử lại.',
                'language-not-supported': 'Thiết bị chưa hỗ trợ nghe tiếng Việt. Bấm nút Gõ rồi dùng micro của bàn phím.'
            }[loi];
            if (chu) { gui({loai: 'chu', van_ban: chu, cach: 'trinh_duyet'}); }
            else { trangThai(thongBao || 'Không nghe được gì, bạn thử nói lại nhé.', 'loi'); }
            st = null;
        };
        nut(true);
        hien();
        st.dem = setInterval(hien, 1000);
        st.han = setTimeout(dungNghe, TOI_DA_GIAY * 1000);
        r.start();
    }

    // ------------------------------------------------------------ ghi âm gửi máy chủ (OpenAI)
    function blobSangB64(blob) {
        return new Promise(function (xong) {
            const f = new FileReader();
            f.onloadend = function () { xong(String(f.result)); };
            f.readAsDataURL(blob);
        });
    }

    async function nghePhienGhiAm() {
        let luong;
        try { luong = await navigator.mediaDevices.getUserMedia({audio: true}); }
        catch (err) {
            trangThai('Chưa cấp quyền micro. Bấm biểu tượng khoá cạnh địa chỉ web, cho phép micro rồi thử lại.', 'loi');
            return;
        }
        const kieu = KIEU_AM.find(function (k) { return window.MediaRecorder && MediaRecorder.isTypeSupported(k); }) || '';
        const rec = new MediaRecorder(luong, kieu ? {mimeType: kieu} : {});
        const manh = [];
        st = {kieu: 'am', rec: rec, bat: Date.now()};
        rec.ondataavailable = function (e) { if (e.data && e.data.size) { manh.push(e.data); } };
        rec.onstop = async function () {
            luong.getTracks().forEach(function (t) { t.stop(); });
            dong();
            st = null;
            const blob = new Blob(manh, {type: rec.mimeType || kieu || 'audio/webm'});
            if (blob.size < 2000) { trangThai('Ghi âm quá ngắn, bạn thử lại nhé.', 'loi'); return; }
            gui({loai: 'am', mime: blob.type, b64: await blobSangB64(blob), cach: 'openai'});
        };
        nut(true);
        const hien = function () {
            trangThai('Đang ghi âm ' + Math.floor((Date.now() - st.bat) / 1000) + 's… bấm nút để dừng', 'nghe');
        };
        hien();
        st.dem = setInterval(hien, 1000);
        st.han = setTimeout(dungNghe, TOI_DA_GIAY * 1000);
        rec.start();
    }

    function dungNghe() {
        if (!st) { return; }
        st.dung = true;
        try { if (st.kieu === 'chu') { st.r.stop(); } else { st.rec.stop(); } } catch (err) { dong(); st = null; }
    }

    function batDau(b) {
        const cach = b.dataset.engine === 'openai' ? 'openai' : 'trinh_duyet';
        const coKey = b.dataset.openai === '1';
        if (cach === 'trinh_duyet' && NhanDang) { nghePhienTrinhDuyet(); return; }
        if ((cach === 'openai' || !NhanDang) && coKey && window.MediaRecorder && navigator.mediaDevices) {
            nghePhienGhiAm();
            return;
        }
        trangThai('Trình duyệt này chưa nghe được giọng nói. Bấm nút Gõ rồi dùng micro của bàn phím.', 'loi');
    }

    document.addEventListener('click', function (e) {
        const b = e.target && e.target.closest ? e.target.closest('#bn-gn-mic') : null;
        if (!b) { return; }
        if (st) { dungNghe(); } else { trangThai(''); batDau(b); }
    });
    document.addEventListener('visibilitychange', function () { if (document.hidden) { dungNghe(); } });
})();
