# Đưa app lên mạng: Supabase + Vercel

Tài liệu từng bước. Mỗi bước ghi rõ **ai làm**: 🧑 bạn làm · 🤖 Claude làm.
Làm lần lượt, xong bước nào nhắn Claude bước đó.

---

## Bức tranh tổng thể

```
Người dùng ──► Vercel (chạy app, máy chủ Tokyo) ──► Supabase (lưu dữ liệu, Tokyo)
                     ▲
                GitHub (nơi cất code, Vercel tự lấy code từ đây mỗi lần cập nhật)
```

| Dịch vụ | Vai trò | Cần tài khoản |
|---|---|---|
| **GitHub** | Cất code. Vercel đọc code từ đây | Có |
| **Supabase** | Database PostgreSQL — thay cho file `data/ftel.db` trên máy | Có |
| **Vercel** | Chạy app, cấp địa chỉ web `https://....vercel.app` | Có |

---

## Bước 0 · Ba điều cần quyết trước 🧑

1. **Dữ liệu nội bộ ra ngoài công ty.** Số bán, acc nhân viên, hồ sơ NSLĐ sẽ nằm trên máy chủ
   của Supabase và Vercel (đặt tại Tokyo, Nhật Bản). Nên hỏi bộ phận IT / bảo mật của chi nhánh trước.
   App đã **bỏ không lưu tên khách hàng** để giảm rủi ro. Ngoại lệ (chốt 21/09/2026): phòng bật trang
   Nhập tồn (hiện chỉ IBB7, `config/rules.yml` → `nhap_ton`) được lưu tên khách hàng trong file Internet, vì sale
   cần tên để cập nhật từng ca tồn. Tên chỉ hiện ở trang Nhập tồn, không gửi lên AI.
2. **Chi phí khi dùng cho công ty.**
   - Vercel gói miễn phí (Hobby) chỉ cho mục đích cá nhân, phi thương mại → dùng cho công ty
     cần gói **Pro (~20 USD/tháng)**.
   - Supabase gói miễn phí **tự tạm dừng nếu 7 ngày không ai dùng** và không có sao lưu tự động
     → dùng thật nên lên gói **Pro (~25 USD/tháng)**.
3. **App sẽ mở ra internet.** Ai có địa chỉ đều thấy trang đăng nhập. Phải đổi mật khẩu
   `admin` ngay sau khi lên mạng (Bước 4).

---

## Bước 1 · GitHub — nơi cất code 🧑

1. Vào **github.com** → **Sign up** (nếu chưa có tài khoản).
2. Góc phải trên → dấu **+** → **New repository**.
3. Điền:
   - **Repository name:** `ftel-dashboard`
   - Chọn **Private** ⚠️ (bắt buộc — không để Public)
   - **Không** tick "Add a README file"
4. Bấm **Create repository**.
5. Copy đường dẫn repo dạng `https://github.com/<tên-bạn>/ftel-dashboard.git` và **gửi Claude**.

> Code đã được Claude chuẩn bị sẵn và **chặn không đưa dữ liệu thật lên GitHub**
> (các file `.csv`, `.xlsx`, `data/`, `.env` đều bị loại).

🤖 Claude sẽ đưa bạn một lệnh để đẩy code lên. Lần đầu chạy, Windows mở cửa sổ
**đăng nhập GitHub** → bạn đăng nhập trong cửa sổ đó (Claude không nhập mật khẩu hộ).

---

## Bước 2 · Supabase — tạo database 🧑

1. Vào **supabase.com** → **Start your project** → **Continue with GitHub**.
2. **New project**:
   - **Name:** `ftel-dashboard`
   - **Database Password:** bấm **Generate a password** → **lưu vào nơi an toàn** (trình quản lý
     mật khẩu). Mất mật khẩu này thì phải đặt lại.
   - **Region:** `Asia-Pacific` → Supabase đặt tại **Tokyo** (`ap-northeast-1`). Gói miễn phí
     hiện không cho chọn Singapore. App trên Vercel được đặt cùng Tokyo (`vercel.json` → `hnd1`)
     để app và database nằm cạnh nhau.
3. Bấm **Create new project**, chờ khoảng 2 phút.
4. Khi xong, bấm nút **Connect** ở thanh trên cùng → tab **Connection String** → mục
   **Type: URI**. Bạn sẽ thấy 3 loại chuỗi, cần 2 loại:

| Loại | Cổng | Dùng cho |
|---|---|---|
| **Session pooler** | `5432` | Chép dữ liệu từ máy lên (Bước 3) |
| **Transaction pooler** | `6543` | Vercel dùng khi chạy app (Bước 4) |

   Mỗi chuỗi có dạng:
   `postgresql://postgres.xxxxxxxx:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
   → thay `[YOUR-PASSWORD]` bằng mật khẩu ở mục 2.

5. **Khuyến nghị bảo mật:** Project Settings → **Data API** → tắt **Enable Data API**.
   App không dùng cổng này; tắt đi là đóng bớt một lối vào dữ liệu.

---

## Bước 3 · Chép dữ liệu từ máy lên Supabase

### 3a. 🧑 Đặt chuỗi kết nối vào máy (không gửi qua chat)

1. Mở thư mục `E:\App Báo cáo - FTEL`.
2. Copy file `.env.example` → đổi tên bản copy thành `.env`
   (nếu Windows ẩn đuôi file, bật **View → File name extensions**).
3. Mở `.env` bằng Notepad, tìm dòng `SUPABASE_DB_URL=` → dán chuỗi **Session pooler** (cổng 5432)
   ngay sau dấu `=`. **Để trống** dòng `DATABASE_URL=`.
4. Lưu file. Nhắn Claude: **"đã xong bước 3a"**.

> ⚠️ Không dán chuỗi kết nối vào khung chat — trong đó có mật khẩu database.

### 3b. 🤖 Claude chép dữ liệu và đối chiếu

Claude chạy:

```bash
python scripts/chuyen_len_supabase.py
python scripts/doi_chieu_supabase.py
```

- Script 1 tạo bảng, chép dữ liệu, **khoá bảng khỏi truy cập công khai**, so số dòng.
- Script 2 chạy lại toàn bộ phép tính báo cáo ở cả hai nơi và so từng con số.
  **Phải báo "KHỚP TUYỆT ĐỐI"** mới làm tiếp.

---

## Bước 4 · Vercel — đưa app lên mạng 🧑

1. Tạo khoá phiên đăng nhập: mở PowerShell trong thư mục app, chạy
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Copy dãy ký tự in ra (giữ riêng, không gửi chat).
2. Vào **vercel.com** → **Sign Up** → **Continue with GitHub**.
3. **Add New… → Project** → tìm `ftel-dashboard` → **Import**.
4. Màn hình cấu hình:
   - **Framework Preset:** `Other`
   - **Root Directory:** `./` (để nguyên)
   - Mở **Environment Variables**, thêm 2 dòng:

| Name | Value |
|---|---|
| `DATABASE_URL` | chuỗi **Transaction pooler** (cổng **6543**) |
| `APP_SECRET_KEY` | dãy ký tự ở mục 1 |

5. Bấm **Deploy**, chờ 3–5 phút.
6. Xong sẽ có địa chỉ dạng `https://ftel-dashboard-xxxx.vercel.app`. Mở thêm
   `https://ftel-dashboard-xxxx.vercel.app/healthz` → phải thấy `"status": "ok"`.
7. Đăng nhập `admin` → **Cấu hình → tab Nhân sự & hệ thống → Đổi mật khẩu** → đặt mật khẩu
   mạnh (từ 12 ký tự, có chữ hoa, số, ký tự đặc biệt).
8. Gửi Claude địa chỉ web (không kèm mật khẩu) để kiểm tra lại toàn bộ trang.

**Nếu Deploy báo lỗi:** copy phần chữ đỏ trong log gửi Claude.
Nếu lỗi có chữ **"exceeds the maximum size"** → làm theo **Phụ lục A**.

---

## Bước 5 · Sau khi lên mạng

- **Từ nay nạp dữ liệu trên bản web.** Không nạp song song trên máy nữa, tránh hai nơi lệch số.
- **Cập nhật app về sau:** Claude sửa code → đẩy lên GitHub → Vercel tự triển khai lại trong
  vài phút. Bạn không cần làm gì thêm.
- **Giới hạn mỗi lượt nạp: 3 MB** (giới hạn của Vercel). File hằng ngày chỉ khoảng 0,8 MB nên
  thoải mái; file cả tháng quá lớn thì chia làm hai lượt, app sẽ báo khi vượt.
- **Lần mở đầu tiên sau lúc lâu không ai dùng sẽ chậm 5–10 giây** (máy chủ Vercel khởi động
  lại). Các lần sau nhanh bình thường.

---

## Phụ lục A · Phương án dự phòng: Render

App dùng nhiều thư viện tính toán (pandas, plotly), bộ cài có thể chạm ngưỡng dung lượng tối đa
Vercel cho phép. Khi đó dùng **Render** — chạy app như một máy chủ thường trực, không giới hạn
dung lượng, không chậm lúc mở lần đầu. Code đã có sẵn file `render.yaml`.

1. 🧑 **render.com** → Sign up with GitHub.
2. 🧑 **New → Blueprint** → chọn repo `ftel-dashboard` → Render đọc `render.yaml`.
3. 🧑 Khi được hỏi `DATABASE_URL` → dán chuỗi **Session pooler** (cổng 5432).
   `APP_SECRET_KEY` Render tự tạo.
4. 🧑 **Apply**. Gói `starter` khoảng 7 USD/tháng, luôn chạy, máy chủ Singapore.

> Lưu ý: Render không có máy chủ Tokyo. Database đang ở Tokyo nên nếu dùng Render, mỗi lượt mở
> trang sẽ chậm hơn Vercel. Khi đó nên cân nhắc tạo lại database Supabase ở Singapore (gói Pro
> cho chọn vùng cụ thể) rồi chép lại dữ liệu bằng `--lam-lai`.

---

## Phụ lục B · Ai giữ gì

| Thứ | Ai giữ | Ghi chú |
|---|---|---|
| Mật khẩu GitHub / Supabase / Vercel | 🧑 Bạn | Claude không bao giờ cần |
| Mật khẩu database Supabase | 🧑 Bạn | Chỉ nằm trong `.env` trên máy và trong Vercel |
| `APP_SECRET_KEY` | 🧑 Bạn | Đổi khoá = mọi người phải đăng nhập lại |
| Code | GitHub (private) | Không chứa dữ liệu thật |
| Dữ liệu | Supabase | Bảng đã khoá khỏi truy cập công khai |
