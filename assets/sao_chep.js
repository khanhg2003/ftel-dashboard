/* =====================================================================
   Nút copy dùng chung (Danh bạ, Soạn email). Gắn lớp "nut-chep" cho nút, rồi chọn một trong hai cách:
   - data-chep="chữ cần copy"                      -> copy đúng chữ đó (email, số điện thoại, danh sách người nhận).
   - data-chep-nguon="#id-khoi" (+ data-chep-html) -> copy nội dung của một khối trên trang; có data-chep-html thì copy
     CẢ định dạng HTML (đậm, xuống dòng) để dán vào Outlook vẫn giữ chữ đậm, kèm bản chữ thường.
   - data-outlook="web" (cùng data-den, data-cc = danh sách email cách nhau dấu ;, data-tieu-nguon="#id", và data-chep-nguon
     + data-chep-html như trên): copy nội dung rồi mở thư mới trên Outlook web (deeplink compose) đã điền sẵn Đến, CC, tiêu đề;
     nội dung chữ trơn (mất chữ đậm) đi luôn trong link nên mở ra là đủ, không cần dán. Link quá dài (> LINK_TOI_DA) thì bỏ nội dung khỏi
     link; bản có chữ đậm luôn nằm trong clipboard để Ctrl+V. (Thử `mailto:` và file .eml ngày 10/10/2026: máy chủ app dùng Outlook web nên mailto không mở được gì.)
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

    const LINK_TOI_DA = 8000;                                   // link dài quá thì bỏ nội dung khỏi link, nội dung vẫn nằm trong clipboard

    /* Outlook web nhận thư mới qua `compose?mailtouri=<mailto đã mã hoá>` (đúng đường nó tự đăng ký làm chương trình mail).
       Dùng riêng các tham số to / cc thì Outlook bỏ qua CC (chủ app báo 10/10/2026), mailtouri thì đọc đủ Đến, CC, tiêu đề, nội dung. */
    function taoLinkOutlook(den, cc, tieu, noiDung) {
        const mailto = function (body) {
            const q = [];
            if (cc.length) { q.push('cc=' + cc.join(',')); }
            q.push('subject=' + encodeURIComponent(tieu));
            if (body) { q.push('body=' + encodeURIComponent(body.replace(/\r?\n/g, '\r\n'))); }
            return 'mailto:' + den.join(',') + '?' + q.join('&');
        };
        const link = function (body) {
            return 'https://outlook.office.com/mail/deeplink/compose?mailtouri=' + encodeURIComponent(mailto(body));
        };
        const co = link(noiDung);
        return co.length <= LINK_TOI_DA ? co : link('');
    }

    if (typeof document !== 'undefined') { document.addEventListener('click', async function (e) {
        const b = e.target && e.target.closest ? e.target.closest('.nut-chep') : null;
        if (!b) { return; }
        let chu = b.dataset.chep || '';
        let html = null;
        if (b.dataset.chepNguon) {
            const k = document.querySelector(b.dataset.chepNguon);
            if (!k) { return; }
            chu = k.innerText.trim();
            html = b.dataset.chepHtml !== undefined ? k.innerHTML : null;
        }
        let ok = chu ? await copy(chu, html) : false;     // không có gì để copy cũng báo lỗi, đừng im lặng
        if (b.dataset.outlook === 'web') {            // mở thư dù copy lỗi: thư vẫn có Đến, CC, tiêu đề
            const tieu = document.querySelector(b.dataset.tieuNguon);
            const cua = window.open(taoLinkOutlook(danhSach(b.dataset.den), danhSach(b.dataset.cc), tieu ? tieu.innerText.trim() : '', chu), '_blank');
            if (!cua) { ok = false; }                                       // trình duyệt chặn cửa sổ mới
        }
        b.classList.toggle(ok ? 'da-chep' : 'chep-loi', true);
        setTimeout(function () { b.classList.remove('da-chep', 'chep-loi'); }, 1500);
    }); }
    if (typeof module !== 'undefined') { module.exports = {taoLinkOutlook, danhSach}; }          // để kiểm thử bằng Node
})();
