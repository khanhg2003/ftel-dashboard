/* =====================================================================
   Nút copy dùng chung (Danh bạ, Soạn email). Gắn lớp "nut-chep" cho nút, rồi chọn một trong hai cách:
   - data-chep="chữ cần copy"                      -> copy đúng chữ đó (email, số điện thoại, danh sách người nhận).
   - data-chep-nguon="#id-khoi" (+ data-chep-html) -> copy nội dung của một khối trên trang; có data-chep-html thì copy
     CẢ định dạng HTML (đậm, xuống dòng) để dán vào Outlook vẫn giữ chữ đậm, kèm bản chữ thường.
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

    document.addEventListener('click', async function (e) {
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
        const ok = chu ? await copy(chu, html) : false;     // không có gì để copy cũng báo lỗi, đừng im lặng
        b.classList.toggle(ok ? 'da-chep' : 'chep-loi', true);
        setTimeout(function () { b.classList.remove('da-chep', 'chep-loi'); }, 1500);
    });
})();
