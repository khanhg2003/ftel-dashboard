# Kịch bản demo 3 phút: Điều hành liên khối

Bản này dành cho nhánh `thi-lien-khoi`, chạy trên máy với **dữ liệu minh hoạ đã ghép mã** và **Zalo giả lập** (không tin nào gửi ra ngoài).
Các con số ghi "khoảng" sẽ lệch nhẹ mỗi lần chạy vì đồng hồ thật tiến lên; đọc số trên màn hình lúc demo, đừng đọc thuộc từ tài liệu.

## Câu chốt (nói ở đầu và nhắc lại ở cuối)
> Bot tra cứu trả lời **khi có người hỏi**. Điều hành liên khối **tự tìm việc, giao đúng người qua Zalo, nhắc khi quá hạn, báo quản lý và đo kết quả**.

## Chuẩn bị (làm trước giờ demo khoảng 5 phút)
1. Mở cửa sổ dòng lệnh trong thư mục dự án, chạy:
   ```bash
   python scripts/xem_demo_lien_khoi.py
   ```
   rồi mở trình duyệt vào **http://127.0.0.1:8060/lienkhoi**. Hoặc dùng `.\scripts\chay_thi.ps1 -Demo`.
2. Mở tab **Theo dõi & Zalo**, bấm **Chuẩn bị demo (nạp 14 ngày mô phỏng)**. Nút này xoá trạng thái cũ, dựng sẵn 14 ngày giao việc mô phỏng (để tab Hiệu quả có số) và lấy 454 phần việc mới của hôm nay (chưa gửi).
3. Kiểm tra nhanh ba điều:
   - Dòng vàng đầu tab Theo dõi ghi **"GIẢ LẬP: tin chỉ ghi vào hộp thư"**.
   - Tab **Việc cần làm** có khoảng **186 việc** (khoảng 88 mức Cao).
   - Tab **Hiệu quả** có số (tỷ lệ xong đúng hạn khoảng 63%) và dòng vàng "… là MÔ PHỎNG".
4. Quên bấm gì hoặc lỡ tay: bấm **Làm lại từ đầu**, rồi **Chuẩn bị demo** lần nữa (mất chưa tới 1 giây).

## Diễn biến (tổng 3 phút)
| Giờ | Bấm gì | Nói gì |
|---|---|---|
| 0:00 - 0:25 | Slide vấn đề | "Một hợp đồng đi qua Kinh doanh, Kỹ thuật, DVKH nhưng không ai cầm trọn. Việc rơi ở chỗ giao nhau." |
| 0:25 - 1:00 | Tab **Việc cần làm**. Chọn luật **Sự cố lặp** ở ô Luật. | "Hệ thống tự đọc dữ liệu ba khối và tìm ra khoảng 186 việc theo 4 luật: chờ online lâu, lỗi sớm sau lắp, sự cố lặp, khách có ý rời. Mỗi việc nói rõ ai nhận và vì sao." |
| 1:00 - 1:25 | Tab **Hồ sơ hợp đồng**, bấm hợp đồng **MHAAA0090**. | "Hợp đồng này dính hai luật. Ba khối cùng nói về một mã: Kỹ thuật ghi checklist lặp, DVKH có SR, Kinh doanh có gói và sale. Sale, CSKH, KTV phụ trách hiện ngay đầu trang." (Đây chỉ là chi tiết khi cần, không phải điểm nhấn.) |
| 1:25 - 2:05 | Tab **Theo dõi & Zalo**: bấm **2. Gửi việc mới qua Zalo**. Kéo xuống Hộp thư, mở tin của **Trưởng phòng KD team 6**. Rồi ở ô **Tôi là** chọn **Trưởng nhóm DVKH 1**, chọn 3 việc, ô **Giao cho** chọn **cskh_01**, bấm **Giao các việc đã chọn**. | "Mỗi sáng 11 quản lý (trưởng phòng KD từng team, trưởng nhóm DVKH, điều hành Kỹ thuật) nhận MỘT tin tổng hợp việc của team mình: bao nhiêu việc, loại nào, của ai, vài việc mức Cao nên giao trước. Quản lý không phải trả lời từng mã trên Zalo: vào app, chọn nhiều việc, giao cho nhân viên một lần. Việc chưa rõ người phụ trách về trưởng phòng khối." |
| 2:05 - 2:30 | Bấm **Lùi đồng hồ +25 giờ**, rồi **3. Chạy nhắc & báo quản lý**. Bấm **Lùi +25 giờ** lần nữa, rồi **3** lần nữa. | "Sau 24 giờ việc chưa xong: nhắc quản lý, khoảng 137 phần việc. Sau 48 giờ: báo **giám đốc chi nhánh** MỘT tin tổng hợp theo từng team, khoảng 85 việc. Không ai phải ngồi rà thủ công." |
| 2:30 - 3:00 | Tab **Hiệu quả**. | "Quản lý thấy ngay: xong đúng hạn khoảng 62%, xử lý trung vị khoảng 12 giờ, phản hồi của quản lý trong 4 giờ khoảng 54%, và **bảng theo team**: trưởng nhóm DVKH 1 đang thấp nhất. Nhập mốc trước đây (40 giờ, 35%) là thấy mức cải thiện. Đây là điều bot tra cứu không làm." |

Gợi ý ở bước cuối: nhập **40** vào "Giờ xử lý trước đây", **35** vào "% xong đúng hạn trước đây", bấm **Lưu mốc**.

## Phải nói rõ khi trình bày (đừng để ban giám khảo tự phát hiện)
- Dữ liệu là **minh hoạ đã ghép mã**: ba khối đang lấy từ ba chi nhánh khác nhau nên mã hợp đồng được đặt lại cho trùng nhau. Mã, tên người, ngày tháng là giả định. Phần Kỹ thuật dựng từ file báo cáo Kỹ thuật thật nhưng đã đổi hết mã và tên.
- **14 ngày lịch sử là mô phỏng**, và người nhận "làm việc" cũng là mô phỏng (có người nhanh, người chậm). Số đo thật chỉ có sau khi dùng thật.
- **Zalo giả lập**: tin chỉ ghi vào hộp thư trên màn hình. Tin gửi cho QUẢN LÝ, không gửi từng nhân viên; việc cập nhật làm trên app. Phần gửi thật và nhận trả lời thật đã viết và có test, cần bot Zalo riêng để bật.
- Chạy hoàn toàn trên máy, **không đụng hệ thống đang chạy**.

## Câu hỏi khó và gợi ý trả lời
| Câu hỏi | Gợi ý |
|---|---|
| Có trùng CUS 360 hay bot tra cứu của công ty không? | "Công cụ tra cứu trả lời khi được hỏi, theo từng hợp đồng. Bên em tự phát hiện việc xuyên ba khối, giao đúng người, nhắc, báo quản lý và đo kết quả. Hồ sơ hợp đồng chỉ là màn xem chi tiết kèm theo." (Nên xác nhận bằng cách hỏi người dùng bot công ty: có tự nhắn không, có giao việc cho từng người không, có báo quản lý khi quá hạn không.) |
| Số liệu có thật không? | "Phần luật chạy trên dữ liệu thật của từng khối. Việc ghép mã giữa ba khối và 14 ngày lịch sử là minh hoạ vì ba file đang từ ba chi nhánh khác nhau. Khi cùng một mã hợp đồng thì chạy luôn, không phải viết lại." |
| Thông tin khách có bị lộ không? | "Không có tên khách, địa chỉ, số điện thoại trong bất kỳ bảng hay tin nhắn nào. Có test tự động chặn dữ liệu thật lọt vào bộ minh hoạ." |
| Triển khai thật cần gì? | "Mã hợp đồng dùng chung giữa ba khối, danh sách người nhận việc (ai thuộc khối nào, quản lý là ai, mã chat Zalo), một bot Zalo riêng. Phần còn lại đã có." |
| Đo hiệu quả bằng gì? | "Tỷ lệ xong đúng hạn, thời gian xử lý, tỷ lệ phản hồi trong 4 giờ, số việc quá hạn và báo quản lý. So với mốc đo được trước khi dùng." |
| Quản lý nhận tin mà không giao thì sao? | "Hệ thống nhắc sau 24 giờ, sau 48 giờ báo giám đốc chi nhánh theo từng team. Quản lý ghi 'giao cho ai' trên app nên vẫn đo được từng người, từng team." |
| Vì sao gửi quản lý mà không gửi nhân viên? | "Giữ đúng cách điều hành hiện tại: quản lý phân việc cho cấp dưới. Cũng chỉ cần danh sách Zalo của khoảng 15 đến 25 quản lý thay vì cả trăm nhân viên, nên chạy thử thật dễ." |

## Nếu có sự cố khi demo
| Triệu chứng | Cách xử lý |
|---|---|
| Trang không mở | Kiểm tra cửa sổ dòng lệnh còn chạy `xem_demo_lien_khoi.py`; chạy lại rồi tải lại trang. |
| Tab Hiệu quả trống | Quay lại tab Theo dõi, bấm **Chuẩn bị demo**. |
| Bấm nhầm, số lộn xộn | **Làm lại từ đầu**, rồi **Chuẩn bị demo**. |
| Hộp thư không có tin | Bấm **2. Gửi việc mới qua Zalo** (chỉ gửi những việc chưa gửi). |

## Sau cuộc thi (không dùng khi demo)
Muốn gửi thật: tạo bot Zalo riêng, đặt `LIEN_KHOI_ZALO_TOKEN` và `LIEN_KHOI_ZALO_GUI=1`, nạp danh sách người nhận, rồi `python scripts/lien_khoi_webhook.py dat` để nhận tin trả lời. Chi tiết trong `AGENTS.md` (hàng "Điều hành liên khối").
