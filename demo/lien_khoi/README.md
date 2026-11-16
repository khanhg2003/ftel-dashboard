# Bộ dữ liệu MINH HOẠ đã ghép mã (hướng điều hành liên khối)

**Đây là dữ liệu giả định để minh hoạ.** Ba khối (Kinh doanh, DVKH, Kỹ thuật) đang lấy từ ba chi nhánh khác nhau nên mã hợp đồng không trùng. Bộ này đặt cho
167 hợp đồng một mã giả (`MHAAA0001`...) rồi gắn thêm sự kiện của cả ba khối vào cùng mã để các luật liên khối có chỗ chạy.

Bộ gốc dồn nhiều ca có vấn đề, gần như không có khách ổn định. `scripts/bo_sung_demo.py` thêm 60 hợp đồng ổn định (`MHAAA0168`..`MHAAA0227`: đã online 3–40 tháng,
không SR, không nợ, một lần triển khai đúng hẹn) và file `cuoc.csv` để minh hoạ tab Phân loại khách hàng. Tổng cộng 227 hợp đồng. Các dòng gốc giữ nguyên.

| File | Nội dung | Nguồn gốc |
|---|---|---|
| `kd.csv` | hợp đồng Kinh doanh: ngày tạo, online, sale, gói, đang tồn hay không | dựng từ ngày trong file Kỹ thuật, sale đổi thành `sale_NN` |
| `kt_block.csv` | KPI Kỹ thuật theo block / lô (đúng hẹn lần 1, đúng hẹn, quá hẹn, bảo trì quá 24 giờ, thời gian xử lý), không có mã hợp đồng | file KPI Kỹ thuật, tên block đổi thành `Block NN` |
| `kt.csv` | sự kiện Kỹ thuật: tồn, triển khai, checklist lặp, checklist sau triển khai, cáp LAN | 5 file báo cáo Kỹ thuật (Kon Tum), đã đổi mã và tên KTV thành `ktv_NN` |
| `sr_bi_dong.csv`, `sr_chu_dong.csv` | SR của DVKH | mượn loại yêu cầu / tình trạng / kết quả tư vấn từ dữ liệu DVKH sẵn có, đổi mã hợp đồng và người thành `cskh_NN` |
| `no_cuoc.csv` | hợp đồng nằm trong danh sách nợ cước | chọn ngẫu nhiên có hạt giống cố định |
| `dich_vu.csv` | FPT Play (có V.VIP) và Camera kèm hợp đồng | mượn tên gói và giá từ các dòng thật, gắn ngẫu nhiên |
| `cuoc.csv` | lịch sử kỳ cước của hợp đồng đã online: kỳ từ / đến, số tiền, hạn thanh toán, ngày thanh toán (trống = chưa trả), hình thức | GIẢ ĐỊNH hoàn toàn, sinh từ ngày online, số tháng trả trước và cước tháng trong `kd.csv`; hợp đồng trong `no_cuoc.csv` có kỳ gần nhất chưa trả |
| `nguoi_nhan.csv` | danh sách người nhận việc: mã, tên, khối, vai trò, quản lý, mã chat GIẢ (`demo:...`) | dựng từ các tài khoản đã đổi tên + đội trưởng / trưởng phòng / giám đốc giả |
| `meta.json` | ngày "hôm nay" của bộ minh hoạ (14/11/2026) | |

**Không có** tên khách hàng, địa chỉ, số điện thoại, mã hợp đồng thật hay tài khoản nhân sự thật. Script dựng (`scripts/dung_demo_lien_khoi.py`) tự kiểm và dừng nếu còn
lọt dữ liệu thật; `tests/test_lien_khoi.py` kiểm lại mọi lần chạy test.

Dựng lại phần bổ sung (60 hợp đồng ổn định và `cuoc.csv`): `python scripts/bo_sung_demo.py` (cùng hạt giống thì ra đúng cùng kết quả). Script dựng bộ gốc dưới đây nằm ở repo gốc, không có trong bản standalone.

Chạy lại: `python scripts/dung_demo_lien_khoi.py --kt <thư mục có 5 file Kỹ thuật> --db data/thi.db` (cùng hạt giống thì ra đúng cùng kết quả).
Xem thử trên máy: `python scripts/xem_demo_lien_khoi.py`. App chỉ đọc bộ này khi đặt biến môi trường `LIEN_KHOI_NGUON=demo`; mặc định luôn dùng dữ liệu thật của app.
