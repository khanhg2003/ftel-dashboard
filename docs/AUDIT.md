# Audit hiện trạng & Kế hoạch hoàn thiện

Cập nhật: 12/09/2026 (sau giai đoạn 1 + 3 + 4 và đợt tối ưu trải nghiệm A→F) · Người thực hiện: Claude (Senior Fullstack / Data Architect)

Cách audit: đối chiếu 3 nguồn — (1) Project Brief ban đầu, (2) file báo cáo Google Sheet
đang dùng thật (mọi khối A → E), (3) rủi ro vận hành khi có nhiều người dùng.
Mỗi hạng mục chấm: ✅ xong · 🟡 làm một phần · ❌ chưa có.

---

## 1. Bảng trạng thái chức năng

### 1.1 Nạp & xử lý dữ liệu
| # | Chức năng | TT | Ghi chú |
|---|---|---|---|
| 1 | Nhận diện loại file theo tên cột | ✅ | 5 loại: Internet, FPT Play, Camera, NSLĐ, Danh mục NV |
| 1b | **Đã chạy thử với 4 file .xlsx gốc thật (12/09/2026)** | ✅ | Internet 1.678 dòng · Truyền hình 1.235 · Camera 1.081 (gộp 61 dòng trùng) · NSLĐ 106 — **0 dòng lỗi**, nạp lại lần hai không nhân đôi |
| 2 | Chống lệch cột (NFC + alias + kiểm tra kiểu từng ô) | ✅ | Dòng sai ≥2 ô bị chặn, báo "nghi lệch cột" |
| 3 | Xem trước + xác nhận mới lưu | ✅ | Kèm danh sách dòng lỗi và lý do |
| 4 | Chống trùng khi upload lại | ✅ | Upsert theo mã HĐ / mã băm dòng |
| 5 | Ghi nhật ký mỗi lần nạp (`upload_batch`) | ✅ | Có hash file, số dòng mới/cập nhật |
| 6 | **Hoàn tác một lần nạp (rollback batch)** | ✅ | Nạp dữ liệu → *Lịch sử nạp* → gỡ bỏ lần nạp (có ghi nhật ký) |
| 7 | **Màn hình lịch sử nạp dữ liệu** | ✅ | Nạp dữ liệu → *Lịch sử nạp*: file, người nạp, số dòng mới/cập nhật |
| 8 | Chọn sheet khi file .xlsx có nhiều sheet | 🟡 | Đang mặc định sheet đầu tiên (4 file thật đều 1 sheet) |
| 8b | **Nạp nhiều file trong một lượt** | ✅ | Kéo 3-4 file, xem trước từng file, lưu một lần |
| 9 | Cột tiền (ARPU, trả trước) | 🟡 | Định dạng trong CSV lẫn lộn — chờ file .xlsx gốc |
| 10 | **Kiểm tra chất lượng dữ liệu** | ✅ | Trang *Chất lượng dữ liệu*: chưa gán phòng, acc lạ, ngày thiếu, HĐ bất thường, tồn đọng lâu |

### 1.2 Cơ cấu tổ chức & cấu hình
| # | Chức năng | TT | Ghi chú |
|---|---|---|---|
| 11 | Tạo / sửa / ẩn **Bầy** trên giao diện | ✅ | Vừa bổ sung |
| 12 | Tạo / sửa **Phòng kinh doanh** (loại, chi nhánh, nhóm Khác, thứ tự) | ✅ | Vừa bổ sung |
| 13 | Gán phòng vào bầy **theo từng tháng** | ✅ | Có sao chép kỳ trước / quay về mặc định |
| 14 | Chỉ tiêu tháng theo phòng | ✅ | Thêm nút sao chép kỳ trước |
| 15 | Danh mục nhân sự → phòng | ✅ | Quản trị → *Danh mục nhân sự*: thêm/sửa/xoá + tính lại việc gán phòng |
| 16 | Nhân sự chuyển phòng giữa tháng | 🟡 | Sửa được ngày hiệu lực trên giao diện; phần tính theo mốc thời gian vẫn chờ dữ liệu thật |
| 17 | Chỉ tiêu theo Bầy / chi nhánh | ❌ | Hiện chỉ có chỉ tiêu theo phòng |

### 1.3 Báo cáo
| # | Chức năng | TT | Ghi chú |
|---|---|---|---|
| 18 | **Báo cáo Tổng** (khối tổng hợp cũ) + heatmap + cỡ bảng | ✅ | Khớp từng ô với sheet. Mặc định *Vừa màn hình* - xem trọn bảng không cần kéo ngang |
| 18b | **Chụp ảnh báo cáo ra PNG** | ✅ | Vẽ ở máy chủ (Pillow) nên luôn đủ 100% dòng & cột, nét, gửi thẳng vào nhóm |
| 18c | Lọc chi nhánh DNG / QNM | ✅ | Có ở Báo cáo Tổng, Tracking, So sánh kỳ, Nhân sự, Chất lượng dữ liệu |
| 19 | Tracking ngày (Khối A/B) + cộng dồn (C1/C2) | ✅ | Ghim hàng ngày + cột Bầy/Phòng/Tổng, heatmap theo mức của từng phòng |
| 20 | Khối D1 — DNG Khác / QNM Khác | ✅ | Có dòng tổng riêng trong Tracking (155 / 60 khớp sheet) |
| 21 | **Khối D2 — Top 10 sale hụt số giữa 2 kỳ** | ✅ | Trang *So sánh kỳ*, đã đối chiếu đúng số kỳ 16-22/08 vs 23-29/08 |
| 22 | Báo cáo theo **khoảng ngày tự chọn** (tuần, 7 ngày gần nhất) | ✅ | Trang *So sánh kỳ*: chọn 2 khoảng bất kỳ, có mẫu sẵn |
| 23 | Xuất dữ liệu | ✅ | CSV + Excel giữ gộp tiêu đề, màu heatmap, dòng tổng in đậm |
| 24 | Biểu đồ xu hướng, so sánh phòng | ✅ | |
| 25 | Hiệu suất nhân sự (bảng + 2 biểu đồ) | ✅ | Thêm đường cong lên tay nghề, cảnh báo sớm, thời gian triển khai HĐ |

### 1.4 Người dùng & bảo mật
| # | Chức năng | TT | Ghi chú |
|---|---|---|---|
| 26 | Đăng nhập, mã hoá argon2, khoá sau 5 lần sai | ✅ | |
| 27 | Nhật ký thao tác (audit log) | ✅ | |
| 28 | Phân quyền theo vai trò + phạm vi phòng/bầy | ✅ | Đã có kiểm thử tự động cho 3 vai trò (admin / giám đốc bầy / trưởng phòng) |
| 29 | **Màn hình quản lý tài khoản** (tạo, đổi quyền, khoá) | ✅ | Quản trị → *Tài khoản*: tạo, đổi vai trò/phạm vi, khoá, đặt lại mật khẩu |
| 30 | Bắt đổi mật khẩu lần đầu / quên mật khẩu | 🟡 | Admin đặt lại được mật khẩu; chưa bắt buộc đổi ở lần đăng nhập đầu |
| 36 | **Thêm / xoá tài khoản bằng hộp thoại** | ✅ | Kiểm tra trùng tên, bắt buộc chọn phạm vi, chặn tự xoá mình và xoá admin cuối |
| 37 | **Thêm / xoá Bầy & Phòng bằng hộp thoại** | ✅ | Bầy còn phòng hoặc phòng đang có số liệu thì chặn xoá, hướng sang “Ngừng dùng” |
| 38 | Chọn dòng bằng ô tích + nhắc “có thay đổi chưa lưu” | ✅ | Áp cho tài khoản, danh mục nhân sự, bầy, phòng, chỉ tiêu |
| 39 | Trang 404 + lối đi tiếp sau khi nạp dữ liệu | ✅ | Nạp xong có nút sang Báo cáo Tổng / Chất lượng dữ liệu |
| 41 | **Trang Hướng dẫn sử dụng trong app** | ✅ | Viết cho người mới, không dùng từ kỹ thuật; bản file ở docs/HUONGDAN.md |
| 42 | **Chọn kỳ báo cáo không giới hạn số tháng** | ✅ | Nút lùi/tới + danh sách tháng, tự có tháng mới |
| 43 | Nút thu gọn menu cố định ở đáy sidebar | ✅ | Bấm một cái thu lại / mở ra, nhớ lựa chọn cho lần sau |
| 44 | Toàn bộ chú thích chuẩn hoá theo lối viết UX | ✅ | Tiêu đề là danh từ ngắn, chú thích một dòng nói rõ con số nghĩa là gì / cần làm gì |
| 45 | Menu cuộn riêng khi màn hình thấp | ✅ | Nút *Thu gọn* luôn nằm trong tầm nhìn |
| 46 | Bảng dài cuộn trong khung, tiêu đề cột luôn hiển thị | ✅ | Nhân sự, So sánh kỳ, Quản trị, Cấu hình |
| 47 | Thanh lọc kỳ + chi nhánh dính dưới tiêu đề | ✅ | Đổi phạm vi xem mà không phải cuộn ngược lên |
| 48 | Biểu đồ diễn biến xem theo Bầy hoặc Phòng | ✅ | 8 phòng dẫn đầu vẽ riêng, còn lại gộp một đường |
| 49 | Xếp hạng nhân sự thay biểu đồ chấm | ✅ | Hiện thẳng tên người, không phải rê chuột từng điểm |
| 40 | Vai trò *Nhân viên* lọc theo mã NV của chính mình | ✅ | Tra `staff_map` theo mã NV, không có thì dùng phạm vi đã gán |

### 1.5 AI & vận hành
| # | Chức năng | TT | Ghi chú |
|---|---|---|---|
| 31 | Chatbot hỏi đáp số liệu | ❌ | Đã chốt dùng OpenAI API |
| 32 | Tự sinh nhận định sau khi nạp dữ liệu | ❌ | |
| 33 | Sao lưu database tự động | ✅ | `scripts/backup_db.py` (API backup của SQLite), giữ 30 bản, đặt lịch theo docs/VANHANH.md |
| 34 | Chạy nền như dịch vụ + HTTPS | ✅ | `serve.py` (waitress) + `/healthz` + log xoay vòng; hướng dẫn Task Scheduler/NSSM/Caddy trong docs/VANHANH.md |
| 35 | Kiểm thử tự động (pytest) cho công thức | ✅ | 39 phép kiểm: công thức, chuẩn hoá, phân quyền, dựng trang, sao lưu |

---

## 2. Nguyên tắc kiến trúc — vì sao dễ sửa về sau

Cấu hình chia 3 tầng, **code không chứa số liệu nghiệp vụ**:

| Tầng | Nơi lưu | Ai sửa | Sửa gì |
|---|---|---|---|
| 1. Danh mục vận hành | Database (`dim_bay`, `dim_phong`, `phong_bay_thang`, `target_monthly`, `staff_map`) | BGD / Admin, ngay trên giao diện | Bầy, phòng, cơ cấu từng tháng, chỉ tiêu, nhân sự |
| 2. Quy tắc & ánh xạ | File YAML trong `config/` | Người quản trị kỹ thuật | `columns.yml` (tên cột file export), `rules.yml` (V.VIP, gộp dòng trùng, nhóm thâm niên, ngưỡng màu), `org.yml` (chỉ dùng khởi tạo lần đầu + quy tắc gán phòng dự phòng), `staff_overrides.yml` |
| 3. Logic | Code Python | Lập trình viên | Cách tính, cách hiển thị |

Các việc thường gặp và chỗ cần đụng tới:

| Tình huống | Làm ở đâu | Có phải sửa code không |
|---|---|---|
| Thêm phòng kinh doanh mới | Cấu hình → Phòng kinh doanh | Không |
| Tách/gộp bầy, đổi tên bầy | Cấu hình → Danh mục Bầy | Không |
| Tháng sau đổi phòng sang bầy khác | Cấu hình → Cơ cấu Bầy của kỳ | Không |
| Hệ thống đổi tên cột file export | `config/columns.yml`, thêm tên mới vào danh sách `ten` | Không |
| Đổi ngưỡng tô màu | `config/rules.yml` → `heatmap` | Không |
| Đổi định nghĩa V.VIP | `config/rules.yml` → `vvip` | Không |
| Thêm chỉ số mới (VD: PayTV Only) | `app/metrics.py` → `METRICS` + cột trong `app/overview.py` | Có, ~10 dòng |
| Thêm loại file export mới | Thêm một mục trong `datasets` của `columns.yml` + bảng mới trong `models.py` | Có |

---

## 3. Kế hoạch hoàn thiện (đề xuất thứ tự)

### Giai đoạn 1 — Đưa vào dùng thật ✅ **đã xong** (mục 5 đã kiểm với file .xlsx thật)
1. **Quản lý tài khoản trên giao diện**: tạo user, chọn vai trò, chọn phạm vi phòng/bầy, khoá/mở, đặt lại mật khẩu.
2. **Kiểm tra chất lượng dữ liệu**: bảng cảnh báo HĐ chưa gán phòng, acc lạ, ngày thiếu dữ liệu, lệch tổng so với kỳ trước.
3. **Lịch sử nạp dữ liệu + hoàn tác**: xem các lần nạp, gỡ bỏ một lần nạp sai.
4. **Sửa danh mục nhân sự ngay trên UI** (thêm/sửa/chuyển phòng, có ngày hiệu lực).
5. Nạp file export gốc `.xlsx` thật, kiểm tra lại toàn bộ ánh xạ cột.

### Giai đoạn 2 — AI (đã chốt dùng OpenAI API) — *làm sau cùng theo yêu cầu*
6. **Chatbot hỏi đáp số liệu**: chuyển câu hỏi thành SQL trên các view đã lọc quyền, ẩn danh tên nhân sự, chặn truy cập bảng gốc.
7. **Tự sinh nhận định** sau mỗi lần nạp: Python tính biến động/bất thường, AI chỉ viết lời diễn giải.

### Giai đoạn 3 — Báo cáo & phân tích sâu ✅ **đã xong**
8. Khối D2 — Top 10 sale hụt số giữa 2 kỳ (đúng như sheet đang dùng).
9. Báo cáo theo khoảng ngày tự chọn (tuần / 7 ngày gần nhất / so sánh 2 kỳ).
10. Xuất Excel giữ định dạng và màu.
11. Phân tích nhân sự chuyên sâu: đường cong lên tay nghề theo lứa tuyển, cảnh báo sớm nghỉ việc, phễu tồn (tạo HĐ → online), so sánh phòng sau khi khử cơ cấu thâm niên.

### Giai đoạn 4 — Vận hành ổn định ✅ **đã xong** (trừ mục 15, chỉ làm khi cần)
12. Kiểm thử tự động cho các công thức (chốt số liệu đã đối chiếu làm mốc).
13. Sao lưu database tự động hằng ngày.
14. Chạy như dịch vụ nền (waitress/NSSM hoặc Docker) + HTTPS + tên miền nội bộ.
15. Chuyển sang PostgreSQL khi số người dùng tăng (code không phải sửa).

---

## 4. Rủi ro cần lưu ý

| Rủi ro | Ảnh hưởng | Cách xử lý |
|---|---|---|
| ~~Chưa có kiểm thử tự động~~ | Đã xử lý | 39 phép kiểm (`python -m pytest -q`) chốt bộ số mốc 01–11/09 |
| ~~Chưa có sao lưu~~ | Đã xử lý | `scripts/backup_db.py` chạy theo lịch; **cần kiểm tra thư mục `backups/` hằng tuần** |
| ~~Danh mục nhân sự chỉ nạp bằng file~~ | Đã xử lý | Sửa trực tiếp ở Quản trị → *Danh mục nhân sự* |
| ~~Chưa test vai trò Viewer~~ | Đã xử lý | `tests/test_phan_quyen.py` dựng 3 vai trò và kiểm tra dữ liệu bị cắt đúng phạm vi |
| Mật khẩu admin mặc định | Ai biết mật khẩu mẫu đều vào được | `serve.py` cảnh báo khi khởi động — **đổi ngay trong Quản trị → Tài khoản** |
| Chưa nạp file `.xlsx` gốc thật | Ánh xạ cột có thể lệch so với CSV đang dùng | Giai đoạn 1 mục 5 — chờ file export thật |
