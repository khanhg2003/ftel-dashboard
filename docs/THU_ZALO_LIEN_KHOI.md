# Thử tin Zalo thật cho Điều hành liên khối (4 vai: Kinh doanh, DVKH, Kỹ thuật, Ban giám đốc)

Mục đích: cảm nhận tin Zalo thật, trong khi dữ liệu vẫn là bộ **minh hoạ** (không có khách hàng thật).
Một bot dùng chung. Một người có thể đóng cả 4 vai (tin về chung một chat, mỗi tin ghi rõ "gửi thay cho ai"), hoặc 4 người, mỗi người một vai.

## An toàn
- Chỉ gửi tới mã chat của người đã tự nhắn đăng ký với bot. Không đăng ký thì không ai nhận gì.
- Chỉ 4 quản lý đại diện (Trưởng phòng KD team 1, Trưởng nhóm DVKH 1, Điều hành Kỹ thuật 1, Giám đốc chi nhánh) được gửi thật. Tin của các quản lý khác chỉ ghi vào hộp thư trên màn hình.
- Mọi tin mở đầu bằng "[THỬ NGHIỆM · dữ liệu minh hoạ, không phải khách thật]".
- Dùng **bot riêng** của hướng này (không dùng chung bot Bản tin 8h hay Tra cứu giá).
- **Không dán token vào chat, file code hay GitHub.** Chỉ đặt trong cửa sổ PowerShell. Token lộ thì tạo lại bot.

## Bước 1: tạo bot (làm một lần)
1. Trong Zalo, tìm OA **Zalo Bot Manager**, bấm menu **Tạo bot** (mở Zalo Bot Creator).
2. Đặt tên bot, **bắt buộc bắt đầu bằng chữ "Bot"** (ví dụ "Bot Điều hành liên khối"). Bấm **Tạo Bot**.
3. Zalo gửi **Bot Token** qua tin nhắn. Giữ kín.

## Bước 2: đăng ký người thử
Mở PowerShell trong thư mục dự án (`E:\lien-khoi-demo`):

```powershell
$env:LIEN_KHOI_ZALO_TOKEN = "dán-token-ở-đây"
$env:LIEN_KHOI_ZALO_GUI = "1"
python scripts/lien_khoi_zalo_thu.py dang-ky
```

Rồi mở chat với bot trên Zalo và nhắn:
- `ALL` để một tài khoản đóng **cả 4 vai**, hoặc
- các chữ `KD`, `DVKH`, `KT`, `BGD` (nhiều chữ trong một tin được, mỗi người nhắn chữ của mình).

Bot trả lời "Đã ghi nhận bạn là đại diện...". Đủ 4 vai thì script tự dừng (hoặc Ctrl+C). Người nhắn sau đè lên người trước cùng vai.
Xem lại: `python scripts/lien_khoi_zalo_thu.py xem`. Gửi tin thử: `python scripts/lien_khoi_zalo_thu.py thu`. Tắt chế độ thử: `python scripts/lien_khoi_zalo_thu.py go`.

Nhật ký ghi "Zalo từ chối (mã 408)" là bình thường (không có tin mới trong 30 giây).

## Bước 3: bật bản demo có gửi thật
Trong **cùng cửa sổ PowerShell** (để còn biến môi trường):

```powershell
Get-NetTCPConnection -LocalPort 8060 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
python scripts/xem_demo_lien_khoi.py
```

Mở http://127.0.0.1:8060/lienkhoi, tab **Theo dõi & Zalo**. Dòng vàng phải ghi **"THỬ ZALO: ..."**. Ghi "GIẢ LẬP" nghĩa là thiếu token, thiếu `LIEN_KHOI_ZALO_GUI=1` hoặc chưa có người đăng ký.

## Cách A: tự bấm từng bước (xem rõ từng thứ)
1. **Chuẩn bị demo**, rồi **2. Gửi việc mới qua Zalo**: 3 vai (KD, DVKH, KT) mỗi vai nhận một tin tổng hợp.
2. Ở ô **Tôi là** chọn một quản lý, chọn nhiều việc, chọn **Giao cho**, bấm **Giao các việc đã chọn**.
3. **Lùi đồng hồ +25 giờ**, rồi **3. Chạy nhắc**: các vai nhận tin nhắc.
4. **Lùi đồng hồ +25 giờ** lần nữa, **3. Chạy nhắc**: vai **BGD** nhận tin báo giám đốc chi nhánh (việc quá 48 giờ, gom theo team).

## Cách B: để bot tự chủ động gửi (không phải bấm nút)
Mở một cửa sổ PowerShell khác (cùng biến môi trường như Bước 2), chạy:

```powershell
python scripts/lien_khoi_chay_tu_dong.py --chuan-bi --moi 1 --gio-moi-vong 24 --so-vong 4
```

Mỗi **phút thật = một ngày** của bản minh hoạ. Bot tự làm đủ ba bước mỗi vòng và anh chỉ ngồi xem Zalo:
- Vòng 1 (ngay): tin giao việc tổng hợp cho các vai.
- Vòng 2 (sau 1 phút): tin nhắc việc quá 24 giờ.
- Vòng 3 (sau 2 phút): tin báo giám đốc chi nhánh cho vai BGD.
- Vòng 4: không gửi thêm (việc đã gửi, đã nhắc, đã báo thì không gửi lại).

Trang web dùng chung file trạng thái, mở tab **Theo dõi & Zalo** hoặc **Hiệu quả** cùng lúc để xem số đổi theo. Dừng sớm: Ctrl+C.

Dùng dữ liệu thật về sau (không phải bản thử): đặt `LIEN_KHOI_NGUON=that`, nạp danh sách người nhận thật, bot Zalo riêng, rồi chạy `python scripts/lien_khoi_chay_tu_dong.py --moi 15` (hoặc đặt thành dịch vụ). `--gio-moi-vong` và `--chuan-bi` chỉ dùng được ở bản minh hoạ.

## Câu hỏi nên hỏi người nhận tin
Xem `docs/THU_NGHIEM_NGUOI_DUNG.md`.

## Cách hoạt động (cho người sửa code)
`zalo_viec.kenh()` trả "zalo_thu" khi chạy minh hoạ VÀ có `LIEN_KHOI_ZALO_TOKEN`, `LIEN_KHOI_ZALO_GUI=1` và file `data/zalo_thu.json` (`{"KD": "<mã chat>", ...}`).
Chỉ các quản lý trong `MA_DAI_DIEN_THU` (tpkd_01, tn_dvkh_01, dh_kt_01, gd_01) được gửi thật. Có test chặn gửi nhầm (`tests/test_lien_khoi_quan_ly.py`).
Đăng ký dùng `getUpdates` (long polling, không cần địa chỉ https); bot đang gắn webhook thì chạy `python scripts/lien_khoi_webhook.py go` trước.
