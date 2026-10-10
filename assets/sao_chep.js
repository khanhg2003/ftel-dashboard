/* =====================================================================
   Nút copy dùng chung (Danh bạ, Soạn email). Gắn lớp "nut-chep" cho nút, rồi chọn một trong hai cách:
   - data-chep="chữ cần copy"                      -> copy đúng chữ đó (email, số điện thoại, danh sách người nhận).
   - data-chep-nguon="#id-khoi" (+ data-chep-html) -> copy nội dung của một khối trên trang; có data-chep-html thì copy
     CẢ định dạng HTML (đậm, xuống dòng) để dán vào Outlook vẫn giữ chữ đậm, kèm bản chữ thường.
   - data-outlook="mailto" (cùng data-den, data-cc = danh sách email cách nhau dấu ;, data-tieu-nguon="#id", và data-chep-nguon
     + data-chep-html như trên): copy nội dung rồi mở thư mới trong chương trình mail mặc định (Outlook) đã điền sẵn Đến, CC, tiêu
     đề; người dùng chỉ việc Ctrl+V vào thân thư. mailto không nhét được nội dung (giới hạn độ dài, mất chữ đậm) nên nội dung đi
     bằng clipboard.
   - data-outlook="eml": tải về thư nháp .eml (X-Unsent) có đủ Đến, CC, tiêu đề VÀ nội dung có định dạng; bấm đúp file là
     Outlook mở thư nháp, không cần dán.
   Copy xong nút nháy chữ "Đã copy" (lớp da-chep) khoảng 1,5 giây. Dùng Clipboard API; trình duyệt cũ / không có
   quyền thì quay về execCommand("copy").
   ===================================================================== */
(function () {
    function copyThuong(chu) {
        const o = document.createElement('textarea');
        o.value = chu;
        o.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
        document.body.appendChild(o);
        o.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(o);
        return ok;
    }

    async function copy(chu, html) {
        try {
            if (html && navigator.clipboard && window.ClipboardItem) {
                await navigator.clipboard.write([new ClipboardItem({
                    'text/html': new Blob([html], {type: 'text/html'}),
                    'text/plain': new Blob([chu], {type: 'text/plain'})})]);
                return true;
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(chu);
                return true;
            }
        } catch (e) { /* bị chặn quyền: thử cách cũ */ }
        return copyThuong(chu);
    }

    function danhSach(chu) {
        return (chu || '').split(/[;,]/).map(function (x) { return x.trim(); }).filter(Boolean);
    }

    function diaChi(e) { return encodeURIComponent(e).replace(/%40/g, '@'); }

    function taoMailto(den, cc, tieu) {
        const q = [];
        if (cc.length) { q.push('cc=' + cc.map(diaChi).join(',')); }
        q.push('subject=' + encodeURIComponent(tieu));
        return 'mailto:' + den.map(diaChi).join(',') + '?' + q.join('&');
    }

    function b64(chu) {                                         // UTF-8 -> base64
        let nhi = '';
        new TextEncoder().encode(chu).forEach(function (b) { nhi += String.fromCharCode(b); });
        return btoa(nhi);
    }

    function tieuDeMa(tieu) {                                   // RFC 2047: mỗi từ mã hoá <= 75 ký tự
        const kt = Array.from(tieu), cum = [];
        for (let i = 0; i < kt.length; i += 15) { cum.push('=?UTF-8?B?' + b64(kt.slice(i, i + 15).join('')) + '?='); }
        return cum.join('\r\n ');
    }

    function taoEml(den, cc, tieu, htmlThan) {
        const html = '<html><head><meta charset="utf-8"></head><body style="font-family:Calibri,Arial,sans-serif;font-size:11pt">' +
            htmlThan + '</body></html>';
        return ['X-Unsent: 1', 'To: ' + den.join(', '), cc.length ? 'Cc: ' + cc.join(', ') : null,
            'Subject: ' + tieuDeMa(tieu), 'MIME-Version: 1.0', 'Content-Type: text/html; charset=utf-8',
            'Content-Transfer-Encoding: base64', '', (b64(html).match(/.{1,76}/g) || []).join('\r\n'), '']
            .filter(function (d) { return d !== null; }).join('\r\n');
    }

    function taiEml(b) {
        const than = document.querySelector(b.dataset.chepNguon), tieu = document.querySelector(b.dataset.tieuNguon);
        if (!than || !tieu) { return false; }
        const eml = taoEml(danhSach(b.dataset.den), danhSach(b.dataset.cc), tieu.innerText.trim(), than.innerHTML);
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([eml], {type: 'message/rfc822'}));
        a.download = 'thu-nhap.eml';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
        return true;
    }

    if (typeof document !== 'undefined') { document.addEventListener('click', async function (e) {
        const b = e.target && e.target.closest ? e.target.closest('.nut-chep') : null;
        if (!b) { return; }
        if (b.dataset.outlook === 'eml') {
            b.classList.toggle(taiEml(b) ? 'da-chep' : 'chep-loi', true);
            setTimeout(function () { b.classList.remove('da-chep', 'chep-loi'); }, 1500);
            return;
        }
        let chu = b.dataset.chep || '';
        let html = null;
        if (b.dataset.chepNguon) {
            const k = document.querySelector(b.dataset.chepNguon);
            if (!k) { return; }
            chu = k.innerText.trim();
            html = b.dataset.chepHtml !== undefined ? k.innerHTML : null;
        }
        const ok = chu ? await copy(chu, html) : false;     // không có gì để copy cũng báo lỗi, đừng im lặng
        if (ok && b.dataset.outlook === 'mailto') {
            const tieu = document.querySelector(b.dataset.tieuNguon);
            window.location.href = taoMailto(danhSach(b.dataset.den), danhSach(b.dataset.cc), tieu ? tieu.innerText.trim() : '');
        }
        b.classList.toggle(ok ? 'da-chep' : 'chep-loi', true);
        setTimeout(function () { b.classList.remove('da-chep', 'chep-loi'); }, 1500);
    }); }
    if (typeof module !== 'undefined') { module.exports = {taoMailto, taoEml, danhSach}; }          // để kiểm thử bằng Node
})();
