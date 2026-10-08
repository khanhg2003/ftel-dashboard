/* Báo cáo ngày trên điện thoại: bấm vào ô SỐ trong bảng thì hiện bàn phím số (không phải bàn phím chữ). Ô Ghi chú giữ bàn phím chữ. */
document.addEventListener('focusin', function (e) {
    const o = e.target;
    if (!o || o.tagName !== 'INPUT' || !o.closest || !o.closest('#bn-luoi .ag-cell-inline-editing')) { return; }
    const cot = (o.closest('.ag-cell') || {}).getAttribute ? o.closest('.ag-cell').getAttribute('col-id') : '';
    if (cot !== 'ghi_chu') { o.setAttribute('inputmode', 'numeric'); }
});
