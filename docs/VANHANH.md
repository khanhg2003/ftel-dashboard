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

App tự gửi bản tin số chốt (ảnh báo cáo + nhận định & hành động) cho Ban Giám đốc và trưởng phòng qua Zalo Bot, và nhắc Admin nạp file nếu quá 10:30 mà chưa có số chốt.

**Biến môi trường** (Vercel → Project → Settings → Environment Variables, thêm cho Production rồi Redeploy):

| Biến | Ý nghĩa |
|---|---|
| `ZALO_BOT_TOKEN` | Token của Zalo Bot (chỉ để ở đây, không ghi vào code hay chat) |
| `BAN_TIN_KHOA` | Chuỗi bí mật tự đặt, dài và khó đoán; n8n gửi kèm để được phép gọi |
| `APP_URL` | Địa chỉ app, vd `https://ten-app.vercel.app`. **Phải bắt đầu bằng `https://` thì Ban Giám đốc và trưởng phòng mới nhận được ảnh**; không đặt thì bản tin gửi bản chữ và bỏ dòng liên kết |

**Ban Giám đốc nhận ảnh Báo cáo Tổng rồi một tin chữ "Nhận định & hành động".** Ảnh giống nút *Chụp ảnh* (toàn chi nhánh, luỹ kế tới
ngày số, không có nhận xét AI), kèm một dòng chú thích và liên kết xem chi tiết. Tin chữ ngay sau đó chỉ nói điều ảnh chưa nói: cần bao nhiêu
online mỗi ngày (cả chi nhánh, Đà Nẵng, Quảng Nam), phòng nào cần bù số, chất lượng bán so mặt bằng chung, hợp đồng tồn lâu, và vài việc
đề xuất làm trước ngày nào. Tin này do quy tắc cố định sinh ra (không dùng AI), không có tên khách và không nêu tên nhân sự.
**Trưởng phòng nhận cho từng phòng của mình, theo thứ tự:** ảnh Báo cáo phòng, ảnh Báo cáo Tổng, rồi tin "Nhận định & hành động" của
phòng (mục tiêu cần đạt mỗi ngày, vị trí so các phòng, nhân sự cần trao đổi, bán kèm, hợp đồng tồn, việc đề xuất; có nêu tên nhân sự).
Zalo chỉ nhận đường dẫn ảnh nên app mở một đường tạm `/api/ban-tin/anh/<mã>.png`: **ai có đường dẫn thì mở được ảnh đó không cần đăng
nhập trong 15 phút**, sau đó hết hạn; mã của phòng này không mở được ảnh phòng khác, và không chọn được phòng hay chi nhánh bằng tham số.

Hai công tắc ở `config/rules.yml` mục `ban_tin` (mặc định `anh`):

| Công tắc | `anh` | `chu` (quay về cách cũ hoàn toàn) |
|---|---|---|
| `bgd_dang` | Ban Giám đốc: ảnh Báo cáo Tổng + tin nhận định | Ban Giám đốc: chỉ tin chữ như trước, không có tin nhận định |
| `tp_dang` | Trưởng phòng: ảnh phòng + ảnh Tổng + tin nhận định | Trưởng phòng: tin chữ "Tổng quan" + "Từng nhân sự" như trước |

Gửi ảnh lỗi (chưa có `APP_URL` https, Zalo không tải được ảnh) thì app tự dùng bản chữ để không mất tin: Ban Giám đốc nhận bản chữ cũ
thay ảnh (rồi vẫn nhận tin nhận định); trưởng phòng mất ảnh phòng thì nhận tin chữ "Từng nhân sự" thay, mất ảnh Tổng thì bỏ qua ảnh đó.
Bảng *10 lần gửi gần nhất* ghi lý do ở cột "Lý do". Nhắc Admin vẫn là tin chữ. **Muốn có ảnh thì `APP_URL` bắt buộc bắt đầu bằng `https://`.**
Mỗi ảnh Zalo tải về được dựng khoảng 2 giây nên trưởng phòng nhận 2 ảnh sẽ lâu hơn Ban Giám đốc; lượt chạy quá giờ cho phép sẽ để phần còn lại cho
lượt 15 phút sau.

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

**Thêm trưởng phòng nhận bản tin của phòng mình** (chỉ admin làm được; app không tự liên kết với tài khoản app, admin chọn phòng bằng tay):
1. Nhờ trưởng phòng mở Zalo, tìm *Bot AI FTEL - DNG* và nhắn một câu bất kỳ. Người đó hiện ở thẻ **Người vừa nhắn bot (chờ duyệt)**.
2. Tích chọn dòng đó → *Thêm làm người nhận*.
3. Ở **Loại** chọn **Trưởng phòng**: ô **Phòng** hiện ra, chọn một hoặc nhiều phòng bán hàng (IBB và địa bàn) → Lưu.
4. Sang bảng **Người nhận bản tin Zalo**, tích chọn người vừa thêm → *Gửi thử*: người đó nhận các tin của phòng mình (đầu tin có nhãn
   BẢN THỬ, không tính là đã gửi). Sửa phòng: bấm vào dòng của người đó trong bảng.
Mỗi sáng, ngay sau bản tin Ban Giám đốc, trưởng phòng nhận cho từng phòng: ảnh Báo cáo phòng, ảnh Báo cáo Tổng, tin *Nhận định & hành động* (trưởng phòng,
người đã nghỉ và acc tạm không bị nêu tên, nhưng số của họ vẫn nằm trong số phòng). Khi `tp_dang: chu` thì nhận 2 tin chữ như trước: *Tổng quan* và *Từng nhân sự*.
**Cách đọc `?kho=1` (chạy thử, không gửi, không ghi nhật ký, không dựng ảnh):** `POST /api/ban-tin/chay?kho=1` (kèm header `X-Ban-Tin-Khoa`) trả `bgd_dang`,
`tp_dang`, `app_url_da_cai` (false = chưa có `APP_URL` https nên sẽ gửi bản chữ), `nhan_dinh` (tin nhận định của Ban Giám đốc) và `noi_dung` (bản chữ cũ).
Thêm `&phong=IBB7` thì có `nhan_dinh_phong` (tin nhận định của phòng đó), `noi_dung_phong` (bản chữ cũ) và `kich_thuoc_nhan_dinh` (số ký tự, số kiểu chữ từng tin).

## 7. Chuyển sang PostgreSQL (khi cần)

Sửa `DATABASE_URL` trong `.env`:

```
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ftel
```

Code không phải sửa gì thêm — toàn bộ truy vấn đi qua SQLAlchemy. Chạy lại
`python scripts/seed_from_sheet.py` hoặc nạp lại dữ liệu từ giao diện.
