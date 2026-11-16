# Thử tin Zalo thật cho Điều hành liên khối (4 người đại diện)

Mục đích: cho vài người cảm nhận tin Zalo thật, trong khi dữ liệu vẫn là bộ **minh hoạ** (không có khách hàng thật).
Mỗi người đóng một vai: **KD** (trưởng phòng Kinh doanh), **DVKH** (trưởng nhóm), **KT** (điều hành Kỹ thuật), **BGD** (giám đốc chi nhánh).

## An toàn
- Chỉ gửi tới mã chat của người đã tự nhắn đăng ký với bot. Không đăng ký thì không ai nhận gì.
- Tin của các quản lý khác trong bộ minh hoạ chỉ ghi vào hộp thư trên màn hình, không gửi thật.
- Mọi tin mở đầu bằng "[THỬ NGHIỆM · dữ liệu minh hoạ, không phải khách thật]".
- Dùng **bot riêng** của hướng này (không dùng chung bot Bản tin 8h hay bot Tra cứu giá, vì mỗi bot chỉ gắn được một webhook).
- **Không dán token vào chat, vào file code hay lên GitHub.** Chỉ đặt trong cửa sổ PowerShell.

## Bước 1: tạo bot
Tạo thêm một bot Zalo mới giống cách đã tạo bot Bản tin / Tra cứu giá (ví dụ tên "Bot Điều hành liên khối thử"). Lấy **token** của bot.

## Bước 2: đăng ký 4 người thử
Mở PowerShell trong thư mục dự án (`E:\lien-khoi-demo`), chạy lần lượt:

```powershell
$env:LIEN_KHOI_ZALO_TOKEN = "dán-token-ở-đây"
$env:LIEN_KHOI_ZALO_GUI = "1"
python scripts/lien_khoi_zalo_thu.py dang-ky
```

Rồi mỗi người thử mở bot trên Zalo và nhắn **đúng một chữ**: `KD`, `DVKH`, `KT` hoặc `BGD`. Bot trả lời "Đã ghi nhận bạn là đại diện...". Đủ 4 người thì script tự dừng (hoặc nhấn Ctrl+C).
Xem lại: `python scripts/lien_khoi_zalo_thu.py xem`. Gửi tin thử cho từng người: `python scripts/lien_khoi_zalo_thu.py thu`.

Nếu báo "Bot đang gắn webhook": chạy `python scripts/lien_khoi_webhook.py go` rồi làm lại.

## Bước 3: chạy bản demo có gửi thật
Trong **cùng cửa sổ PowerShell** (để còn biến môi trường):

```powershell
Get-NetTCPConnection -LocalPort 8060 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
python scripts/xem_demo_lien_khoi.py
```

Mở http://127.0.0.1:8060/lienkhoi, tab **Theo dõi & Zalo**. Dòng vàng phải ghi **"THỬ ZALO: ..."**. Nếu vẫn ghi "GIẢ LẬP" nghĩa là thiếu token, thiếu `LIEN_KHOI_ZALO_GUI=1` hoặc chưa có người đăng ký.

## Bước 4: chạy kịch bản
1. Bấm **Chuẩn bị demo**, rồi **2. Gửi việc mới qua Zalo**: người đại diện KD, DVKH, KT mỗi người nhận một tin tổng hợp (tin của Trưởng phòng KD team 1, Trưởng nhóm DVKH 1, Điều hành Kỹ thuật 1).
2. Bấm **Lùi đồng hồ +25 giờ**, rồi **3. Chạy nhắc**: các đại diện nhận tin nhắc.
3. Bấm **Lùi đồng hồ +25 giờ** lần nữa, rồi **3. Chạy nhắc**: **BGD** nhận tin báo giám đốc chi nhánh (việc quá 48 giờ, gom theo team).
4. Người thử đọc tin và trả lời các câu hỏi trong `docs/THU_NGHIEM_NGUOI_DUNG.md`. Quản lý giao việc trên app (không phải trả lời trên Zalo), người điều khiển app là người chạy demo.

## Kết thúc
`python scripts/lien_khoi_zalo_thu.py go` (xoá file đăng ký, tắt chế độ thử), rồi đóng cửa sổ PowerShell.

## Cách hoạt động (cho người sửa code)
`zalo_viec.kenh()` trả "zalo_thu" khi chạy minh hoạ VÀ có `LIEN_KHOI_ZALO_TOKEN`, `LIEN_KHOI_ZALO_GUI=1` và file `data/zalo_thu.json` (`{"KD": "<mã chat>", ...}`).
Chỉ các quản lý trong `MA_DAI_DIEN_THU` (tpkd_01, tn_dvkh_01, dh_kt_01, gd_01) được gửi thật. Có test chặn gửi nhầm (`tests/test_lien_khoi_quan_ly.py`).
