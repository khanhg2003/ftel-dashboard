# Hướng dẫn sử dụng — App Báo cáo Sales & HR

*Dành cho người lần đầu mở app. Đọc một lượt khoảng 5–7 phút.*

---

## 1. App này làm gì cho mình?

Trước đây mỗi ngày phải tải file về, copy sang Google Sheet, dán công thức, cộng tay rồi
chụp màn hình gửi nhóm. App này làm thay phần giữa: **anh chị chỉ tải file lên, mọi con số
tự chạy ra đúng mẫu báo cáo đang dùng.**

Ba việc app làm giúp:

1. **Đọc file** — tự biết file nào là Internet, file nào là Truyền hình, file nào là Camera.
2. **Sắp số vào đúng phòng** — nhìn acc người bán trên từng hợp đồng rồi ghép với danh mục nhân sự.
3. **Dựng báo cáo** — ra đúng bảng quen thuộc, kèm biểu đồ và cảnh báo.

---

## 2. Đăng nhập

- Địa chỉ app: người quản trị sẽ đưa, dạng `http://192.168.x.x:8050` — gõ vào trình duyệt
  (Chrome, Edge đều được), không cần cài gì.
- Lần đầu dùng tài khoản người quản trị cấp. **Đổi mật khẩu ngay** sau khi vào.
- Gõ sai mật khẩu 5 lần thì tài khoản bị khoá 15 phút. Quên mật khẩu thì nhờ người quản trị
  đặt lại giúp.

Số liệu chia hai lớp: **số chung** (theo phòng, bầy, chi nhánh) và **chi tiết nhân sự**
(tên, acc, số từng người).

| Vai trò | Số chung | Chi tiết nhân sự (Báo cáo phòng, Hiệu suất nhân sự) |
|---|---|---|
| Quản trị (BGĐ) | Toàn chi nhánh, sửa được mọi thứ | Mọi phòng |
| Trưởng phòng | Toàn chi nhánh (Báo cáo Tổng, Tracking, Phân tích, Chất lượng dữ liệu) | Chỉ phòng mình phụ trách (kiêm nhiệm thì nhiều phòng) |
| Nhập liệu | Toàn chi nhánh, nạp file | Không xem |

---

## 3. Việc mỗi ngày (3 bước, khoảng 2 phút)

**Bước 1 — Tải file lên.** Vào **Nạp dữ liệu**, kéo cả 3 file vừa tải từ hệ thống vào khung
(Internet, Truyền hình, Camera). Chọn được nhiều file cùng lúc. Đầu tháng có thêm file NSLĐ
thì kéo chung luôn, nhớ chọn tháng cho file đó.

**Bước 2 — Xem qua rồi bấm Lưu.** App hiện 20 dòng đầu của mỗi file để anh chị liếc cho chắc,
kèm số dòng đọc được và số dòng phải bỏ (nếu có, app ghi rõ vì sao). Bấm
**Lưu tất cả vào hệ thống**.

> Tải nhầm lại đúng file cũ cũng không sao — app nhận ra hợp đồng đã có và không cộng thêm lần nữa.

**Bước 3 — Xem và gửi báo cáo.** Vào **Báo cáo Tổng**, bấm **Chụp ảnh (PNG)** là có tấm ảnh
đầy đủ cả bảng để gửi vào nhóm Zalo. Cần bản tính toán tiếp thì bấm **Excel**.

---

## 4. Từng mục trong menu

### Báo cáo Tổng — *Hôm nay cả chi nhánh làm được bao nhiêu?*
Bảng giống hệt mẫu đang dùng: mỗi dòng một phòng, cuối mỗi bầy có dòng tổng, dưới cùng là
tổng toàn chi nhánh.

- **Số trong bảng là cộng dồn** từ ngày 01 đến ngày đang chọn.
- Riêng nhóm cột cuối *“Kết quả thực hiện ngày”* là số của riêng ngày đó.
- Ô **xanh** là tốt, **vàng** là tạm, **đỏ** là cần để ý.
- Ô **Cỡ bảng** để sẵn *Vừa màn hình* nên không phải kéo ngang.

### Tracking ngày — *Ngày nào phòng nào bán tốt?*
Mỗi cột là một ngày. Ô xanh = hôm đó phòng bán nhiều hơn mức thường ngày **của chính phòng
đó**; ô đỏ = bán kém hoặc không có số. Nhìn ngang một dòng là thấy phòng đang lên hay đang xuống.

### So sánh kỳ — *Tuần này hơn hay kém tuần trước?*
Chọn hai khoảng ngày (có ba nút gợi ý sẵn). App chỉ ra phòng nào tăng, phòng nào giảm, và
danh sách **người bán sụt nhiều nhất** để biết cần hỏi thăm ai trước.

### Hiệu suất nhân sự — *Ai đang bán tốt, ai đang đuối?*
Thanh lọc: Ngày · Chi nhánh · **Phòng** (mặc định tất cả phòng kinh doanh). Trang có 2 tab:

- **1 · Bán hàng trong kỳ**: số online luỹ kế đến ngày chọn của từng người, ghép với thâm niên và NSLĐ.
- **2 · Năng suất lao động (NSLĐ)**: lấy từ các file NSLĐ hằng tháng.
  - *NSLĐ ITN theo tháng*: mỗi phòng mỗi tháng = tổng ITN cả phòng / số NVKD; dòng Total tính
    cùng cách cho toàn chi nhánh. Chuyển "Từng nhân sự" để xem ITN từng người.
  - *NSLĐ tân binh*: người vào làm trong năm; số lượng, đã nghỉ, tỷ lệ out, ITN bình quân ở
    tháng làm việc thứ 1, 2, 3… Chuyển "Từng tân binh" để xem từng người.
  - Cần nạp đủ file NSLĐ các tháng (tên file có tháng, VD "NSLĐ T8.2026"); nạp nhiều file một lượt được.

Ở tab 1, Xem trước mục **Cần trao đổi sớm**: mỗi người có sẵn lý do (7 ngày chưa có số,
tuần này giảm từ một nửa, NSLĐ chưa đạt). Cột **So với cùng thâm niên** so với trung vị người
cùng mốc thâm niên. Bảng chi tiết có ô tìm, lọc thâm niên / tình trạng và nút Excel.

### Import danh mục nhân sự và cơ cấu bằng Excel
- **Nhân sự**: Quản trị → Danh mục nhân sự → *Tải file mẫu* (điền sẵn danh mục hiện tại) → sửa →
  *Import Excel* → xem trước → *Áp dụng*. File là danh sách **đầy đủ**: acc không có trong file
  được ghi chú "Nghỉ" (không xoá). App tự tính lại phòng cho hợp đồng đã nạp.
- **Bầy / phòng**: Cấu hình → Cơ cấu tổ chức → *Nhập nhanh bằng Excel*. Bầy, phòng không có trong
  file giữ nguyên; muốn ngừng dùng thì ghi "Không" ở cột Đang dùng.
- Thay đổi ít thì vẫn sửa trực tiếp trong bảng như cũ. Ô tìm ở Danh mục nhân sự tìm theo acc, mã NV, phòng.

### Chất lượng dữ liệu — *Số liệu có chỗ nào sai không?*
Nên xem trước khi gửi báo cáo. Kiểm 5 thứ: hợp đồng chưa biết tính cho phòng nào, acc lạ chưa
có trong danh mục, ngày nào quên tải file, đơn tồn quá 7 ngày, hợp đồng đã huỷ mà vẫn tính.

### Nạp dữ liệu
Nơi đưa file vào app (xem mục 3).

### Quản trị
- **Danh sách người được vào app**: tạo tài khoản, chọn vai trò và phạm vi, khoá, đặt lại mật khẩu.
- **Ai thuộc phòng nào**: khai acc người bán thuộc phòng nào — đây là bảng quyết định số chạy
  về phòng nào.
- **Lịch sử nạp** (cuối trang): giờ nạp, file, người nạp; lỡ nhầm thì tích chọn rồi bấm *Gỡ bỏ*.

### Cấu hình
Khai báo **Bầy**, **Phòng kinh doanh**, **cơ cấu bầy của từng tháng** và **chỉ tiêu tháng**.
Tháng sau đổi phòng sang bầy khác thì sửa ở đây, tháng cũ vẫn giữ nguyên cơ cấu cũ.

---

## 5. Các từ hay gặp

| Từ | Nghĩa đơn giản |
|---|---|
| **Số online** | Hợp đồng đã online, khách bắt đầu dùng — con số tính thành tích |
| **Số tồn** (chưa online) | Khách đã ký nhưng chưa online, và còn nằm trong file mới nhất |
| **V.VIP** | Hợp đồng có gói truyền hình V.VIP (app tính cả V.VIP Plus) |
| **PTTB CNQL** | Hợp đồng do chi nhánh mình quản lý sau bán |
| **Bầy** | Nhóm gồm nhiều phòng kinh doanh, mỗi tháng xếp lại được |
| **Acc inside** | Tài khoản nhân viên trên hệ thống bán hàng, ví dụ `DNG.HongDTA3` |
| **Tỷ lệ HTKH** | Đã đạt bao nhiêu phần trăm chỉ tiêu tháng |
| **Chưa gán phòng** | Hợp đồng mà app chưa biết tính cho phòng nào (acc chưa có trong danh mục) |

---

## 6. Gặp khó thì xem ở đây

**Số trong app lệch với file Sheet cũ.**
App đếm mỗi hợp đồng đúng một lần, file cũ có vài dòng bị đếm trùng. Kỳ 01–11/09 file cũ ghi
1.397 số online, app ra 1.394 — chênh do 4 dòng trùng và 1 dòng bị sót. Số của app là số đúng.

**Có hợp đồng rơi vào “Chưa gán phòng”.**
Acc người bán chưa có trong danh mục. Vào *Quản trị → Ai thuộc phòng nào*, thêm acc đó, rồi
bấm **Tính lại việc gán phòng**. Số sẽ tự chạy về đúng phòng, kể cả dữ liệu đã nạp trước đó.

**Tải nhầm file.**
*Nạp dữ liệu → Lịch sử nạp* → tích chọn dòng đó → **Gỡ bỏ**.

**Bảng rộng quá, xem không hết.**
Ô *Cỡ bảng* đã để sẵn “Vừa màn hình”. Cần ảnh rõ để gửi nhóm thì dùng **Chụp ảnh (PNG)** —
ảnh luôn đầy đủ dù màn hình nhỏ.

**Vào app không được.**
Mở `http://<địa-chỉ-app>/healthz`. Nếu hiện `"status": "ok"` thì app vẫn chạy, vấn đề nằm ở
tài khoản (có thể đang bị khoá 15 phút). Nếu không mở được thì báo người quản trị.

**Sửa danh mục xong mà báo cáo chưa đổi.**
Bấm **Tính lại việc gán phòng** ở trang Quản trị.

---

## 7. Vài việc theo tháng

| Khi nào | Làm gì |
|---|---|
| Đầu tháng | *Cấu hình* → cơ cấu Bầy của kỳ (nếu có thay đổi) + nhập chỉ tiêu tháng |
| Có file NSLĐ | Nạp ở trang *Nạp dữ liệu*, nhớ chọn đúng tháng |
| Nhân sự vào/ra/chuyển phòng | *Quản trị → Ai thuộc phòng nào*, rồi bấm *Tính lại việc gán phòng* |
| Có người nghỉ việc | *Quản trị → Danh sách người được vào app* → chuyển sang **Ngừng dùng** |

---

*Mọi thao tác tải file, sửa, xoá đều được ghi nhật ký. Số liệu nằm trên máy chủ của chi nhánh,
không gửi ra ngoài.*
