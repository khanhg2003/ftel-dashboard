# Hướng dẫn vận hành

## 1. Chạy app

| Mục đích | Lệnh | Ghi chú |
|---|---|---|
| Phát triển / thử | `python run.py` | Server dev, chỉ máy mình dùng |
| Chạy thật | `python serve.py` | Máy chủ waitress, nhiều người dùng được |
| Đổi cổng | `python serve.py --port 9000` | |
| Chỉ cho máy mình | `python serve.py --host 127.0.0.1` | |

```bash
python serve.py
```

Sau khi chạy, màn hình in sẵn địa chỉ để phát cho mọi người, ví dụ
`http://192.168.1.25:8050`. Nếu cần xem lại: `ipconfig`.

**Tài khoản đầu tiên:** `admin` / `Ftel@2026` — đây là mật khẩu mẫu, mỗi lần khởi động
`serve.py` sẽ cảnh báo nếu chưa đổi. Vào **Quản trị → Tài khoản** đổi ngay, rồi tạo tài
khoản cho từng người (*Trưởng phòng* chọn phòng phụ trách: xem số chung toàn chi nhánh, chi tiết
nhân sự chỉ của phòng mình).

### Kiểm tra app còn sống
`http://<máy-chủ>:8050/healthz` → `{"status": "ok", "du_lieu_moi_nhat": "2026-09-11", ...}`.
Trang này không cần đăng nhập và không lộ số liệu kinh doanh — dùng cho công cụ giám sát
hoặc để kiểm tra nhanh khi có người báo *"vào không được"*.

### Nhật ký
`serve.py` ghi ra `logs/app.log` (xoay vòng 5 file × 2 MB). Mở file này trước tiên khi có lỗi.

## 2. Chạy nền như một dịch vụ Windows

**Cách 1 — Task Scheduler (đơn giản nhất)**

1. Mở *Task Scheduler* → *Create Task*.
2. Tab *General*: đặt tên `FTEL Dashboard`, chọn **Run whether user is logged on or not**.
3. Tab *Triggers*: *New* → **At startup**.
4. Tab *Actions*: *New* →
   - Program: `python` (hoặc đường dẫn đầy đủ tới `python.exe`)
   - Arguments: `serve.py`
   - Start in: `E:\App Báo cáo - FTEL`
5. Tab *Settings*: bỏ chọn *Stop the task if it runs longer than...*

**Cách 2 — NSSM** (nếu muốn quản lý như dịch vụ thật, có tự khởi động lại khi lỗi)

```bash
nssm install FtelDashboard "C:\Users\ADMIN\AppData\Local\Programs\Python\Python311\python.exe" "E:\App Báo cáo - FTEL\serve.py"
nssm set FtelDashboard AppDirectory "E:\App Báo cáo - FTEL"
nssm start FtelDashboard
```

## 3. Sao lưu database

```bash
python scripts/backup_db.py
```

Tạo bản sao vào thư mục `backups/`, giữ 30 bản gần nhất. Bản sao dùng API backup của
SQLite nên an toàn ngay cả khi app đang chạy.

Đặt lịch chạy hằng ngày: Task Scheduler → trigger **Daily 22:00** → Action:
Program `python`, Arguments `scripts/backup_db.py`, Start in `E:\App Báo cáo - FTEL`.

> Khi chuyển sang dùng thật, nên đặt thư mục `backups/` ở ổ khác hoặc đồng bộ lên
> OneDrive/Google Drive của công ty.

## 4. HTTPS

Waitress chạy HTTP. Trong mạng nội bộ thường là đủ. Nếu cần HTTPS:

- **Caddy** (dễ nhất): file `Caddyfile`
  ```
  bao-cao.noi-bo.local {
      reverse_proxy 127.0.0.1:8050
  }
  ```
- Hoặc IIS / nginx làm reverse proxy tới `127.0.0.1:8050`, gắn chứng chỉ nội bộ của công ty.

Khi có HTTPS, mở `app/ui/app.py` và bật thêm `SESSION_COOKIE_SECURE=True`.

## 4b. Khoá phiên đăng nhập

Nếu chưa đặt `APP_SECRET_KEY` trong `.env`, app tự sinh khoá ngẫu nhiên và lưu ở
`data/secret.key`; khởi động lại không làm ai bị đăng xuất. **Đừng chép file này ra ngoài**
và đừng xoá — xoá thì mọi người phải đăng nhập lại.

## 5. Kiểm thử trước khi nâng cấp

```bash
python -m pytest -q
```

67 phép kiểm, gồm:

- `tests/test_bao_cao.py` — chốt các con số đã đối chiếu tay với báo cáo kỳ 01–11/09/2026
  (tổng Online 1.394 · V.VIP 980 · Camera 554 · Khối D1 · Khối D2 · quy tắc gán phòng).
- `tests/test_phan_quyen.py` — phân quyền 3 vai trò, chặn truy cập khi chưa đăng nhập,
  khoá sau 5 lần sai, dựng được cả 8 trang, `/healthz`, sao lưu database.
- `tests/test_giao_dien.py` — ảnh PNG đủ dòng, cỡ bảng vừa màn hình, lọc chi nhánh
  (DNG + QNM = tổng), thêm/xoá tài khoản, ràng buộc khi xoá bầy/phòng, trang 404,
  bảng dài cuộn trong khung, thanh lọc dính.

Bộ kiểm thử chạy trên database riêng `data/kiemthu.db` (tự dựng ở lần chạy đầu từ dữ liệu
gốc kỳ 01-11/09/2026), nên **nạp thêm file mới không làm hỏng các phép kiểm**.

**Luôn chạy lệnh này sau khi sửa công thức hoặc sửa phân quyền** — sai lệch sẽ bị chặn ngay.

## 5a. Hướng dẫn cho người dùng cuối

Gửi anh chị em bản [HUONGDAN.md](HUONGDAN.md), hoặc chỉ họ vào mục **Trợ giúp → Hướng dẫn
sử dụng** ngay trong app (không cần quyền gì đặc biệt cũng xem được).

## 5b. Gửi báo cáo cho nhóm

Trang **Báo cáo Tổng** → nút **Chụp ảnh (PNG)**: tải về một ảnh có đủ toàn bộ dòng và cột,
kèm tiêu đề ngày, giữ nguyên màu heatmap - gửi thẳng vào nhóm Zalo/Telegram.
Ảnh được vẽ ở máy chủ nên không phụ thuộc bạn đang để cỡ bảng bao nhiêu, và không bị
thiếu cột như chụp màn hình.

Cần bản để tính toán tiếp thì dùng **Excel**; cần dữ liệu thô thì dùng **CSV**.

## 6. Việc định kỳ

| Khi nào | Việc |
|---|---|
| Hằng ngày | Kéo cả 3 file export vào *Nạp dữ liệu* → lưu một lần → xem *Chất lượng dữ liệu* → **Báo cáo Tổng → Chụp ảnh (PNG)** → gửi nhóm |
| Đầu tháng | Cấu hình → *Cơ cấu Bầy của kỳ* (nếu có thay đổi) + nhập chỉ tiêu tháng |
| Khi có file NSLĐ | Nạp ở trang *Nạp dữ liệu*, nhớ điền đúng tháng |
| Khi nhân sự vào/ra/chuyển phòng | Quản trị → *Danh mục nhân sự*, rồi bấm *Tính lại việc gán phòng* |
| Hằng tuần | Kiểm tra thư mục `backups/` có bản mới; liếc `logs/app.log` xem có lỗi lặp lại |
| Khi có người vào không được | Mở `/healthz`; nếu `ok` thì là tài khoản (bị khoá 15 phút sau 5 lần sai) |
| Khi có người nghỉ việc | Quản trị → *Tài khoản* → chuyển sang **Ngừng dùng** |

## 6b. Bản tin 8h sáng qua Zalo Bot

App tự gửi bản tin số chốt cho Ban Giám đốc qua Zalo Bot, và nhắc Admin nạp file nếu quá 10:30 mà chưa có số chốt.

**Biến môi trường** (Vercel → Project → Settings → Environment Variables, thêm cho Production rồi Redeploy):

| Biến | Ý nghĩa |
|---|---|
| `ZALO_BOT_TOKEN` | Token của Zalo Bot (chỉ để ở đây, không ghi vào code hay chat) |
| `BAN_TIN_KHOA` | Chuỗi bí mật tự đặt, dài và khó đoán; n8n gửi kèm để được phép gọi |
| `APP_URL` | Địa chỉ app, vd `https://ten-app.vercel.app` (không đặt thì bản tin bỏ dòng liên kết) |

**n8n làm đồng hồ:** tạo workflow gồm *Schedule Trigger* chạy mỗi 15 phút, chỉ trong khoảng 8h tới 11h giờ Việt Nam
(cron `*/15 8-10 * * *` với múi giờ `Asia/Ho_Chi_Minh`) nối với *HTTP Request*: phương thức `POST`, địa chỉ
`https://<app>/api/ban-tin/chay`, header `X-Ban-Tin-Khoa` = giá trị `BAN_TIN_KHOA`. App tự quyết có gửi hay không
nên gọi dư cũng không sao (mỗi người chỉ nhận một lần mỗi ngày số). Thêm `?kho=1` để chạy thử: trả về nội dung bản tin
mà không gửi và không ghi nhật ký.

Mẫu workflow n8n để nhập thẳng: `docs/n8n_ban_tin_8h.json` (đang gọi với `?kho=1`; thay địa chỉ app và khoá, kiểm xong mới bỏ `?kho=1`).

**Thêm người nhận mới bằng cách nhắn bot (cách chính):** vào **Quản trị → Bản tin Zalo → Kết nối Zalo → Kết nối webhook** một lần
(cần đã cài `APP_URL` và `ZALO_BOT_TOKEN`; app tự đặt địa chỉ `<APP_URL>/api/ban-tin/zalo-webhook` và khoá xác thực dẫn xuất từ
`APP_SECRET_KEY`, không phải nhập gì thêm; đổi `APP_SECRET_KEY` thì bấm kết nối lại). Sau đó người cần nhận bản tin mở Zalo, tìm
*Bot AI FTEL - DNG* và nhắn một câu bất kỳ: bot trả lời "Đã ghi nhận…" và người đó hiện ở thẻ **Người vừa nhắn bot (chờ duyệt)**.
Tích chọn dòng đó → *Thêm làm người nhận* → chọn loại (Ban Giám đốc hoặc Admin) → Lưu. *Bỏ qua* xoá khỏi danh sách chờ (nhắn lại thì hiện lại).
App không lưu nội dung tin nhắn, chỉ chat_id và tên hiển thị. **Khi webhook đang bật, lệnh `getUpdates` cũ KHÔNG chạy nữa** (Zalo chỉ cho
dùng một trong hai); muốn quay lại `getUpdates` thì bấm *Ngắt kết nối* (cũng làm người nhắn bot không còn tự hiện trong danh sách chờ).

**Cách cũ, lấy chat_id bằng tay** (chỉ khi webhook đang tắt): người nhận nhắn cho bot trước một tin bất kỳ, rồi gọi
`POST https://bot-api.zaloplatforms.com/bot<TOKEN>/getUpdates` và lấy `result.message.chat.id`. Rồi vào *Thêm người nhận* điền tên, loại và chat_id.
Bấm *Gửi thử* để kiểm tra. Nếu Zalo từ chối gửi chủ động cho người lâu không nhắn thì cột "Lý do" ở bảng
*10 lần gửi gần nhất* sẽ ghi rõ; nhờ người đó nhắn bot một tin rồi thử lại.

## 7. Chuyển sang PostgreSQL (khi cần)

Sửa `DATABASE_URL` trong `.env`:

```
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ftel
```

Code không phải sửa gì thêm — toàn bộ truy vấn đi qua SQLAlchemy. Chạy lại
`python scripts/seed_from_sheet.py` hoặc nạp lại dữ liệu từ giao diện.
