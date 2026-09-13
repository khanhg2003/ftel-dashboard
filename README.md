# FTEL · Sales & HR Performance Dashboard

App nội bộ thay thế quy trình báo cáo thủ công trên Google Sheets cho chi nhánh Đà Nẵng & Quảng Nam.

## Chạy app

```bash
pip install -r requirements.txt
python scripts/seed_from_sheet.py     # nạp dữ liệu mẫu từ sheet cũ (chỉ chạy 1 lần)
python run.py                         # thử trên máy mình: http://127.0.0.1:8050
python serve.py                       # chạy thật cho cả phòng dùng (waitress)
python -m pytest -q                   # 67 phép kiểm - chạy sau mỗi lần sửa công thức
```

Tài khoản mặc định: **`admin` / `Ftel@2026`** — **đổi mật khẩu ngay** trong
*Quản trị → Tài khoản* (khởi động `serve.py` sẽ cảnh báo nếu chưa đổi).
Vận hành, sao lưu, chạy nền như dịch vụ: xem [docs/VANHANH.md](docs/VANHANH.md).

## Cấu trúc

```
app/
  config.py          nạp .env + các file YAML trong config/
  db.py, models.py   SQLAlchemy: dim_phong, staff_map, dim_employee, hr_monthly,
                     fact_internet, fact_fptplay, fact_camera, target_monthly,
                     upload_batch, users, audit_log
  org.py             cơ cấu Bầy/Phòng + quy tắc gán phòng cho từng hợp đồng
  metrics.py         chỉ số Tracking (Khối A/B/C/D), tiến độ tháng
  hr_metrics.py      nối số bán với hồ sơ NSLĐ theo từng nhân sự
  auth.py            đăng nhập argon2, khoá sau 5 lần sai, phân quyền theo phạm vi phòng
  ingest/
    normalize.py     chuẩn hoá Unicode NFC, acc, mã NV, ngày, số (định dạng lẫn lộn)
    loader.py        dò cột theo TÊN + kiểm tra kiểu từng dòng (bắt dòng lệch cột)
    commit.py        ghi vào DB theo khoá (không thể đếm trùng), ghi nhật ký
  overview.py        bảng Tổng quan ngày (đúng bố cục khối tổng hợp cũ)
  admin_service.py   tài khoản, danh mục nhân sự, lịch sử nạp, kiểm tra chất lượng dữ liệu
  export_excel.py    xuất Excel giữ định dạng gộp tiêu đề + màu heatmap
  ui/                giao diện Dash: Tổng quan / Tracking / So sánh kỳ / Nhân sự /
                     Chất lượng dữ liệu / Nạp dữ liệu / Quản trị / Cấu hình
tests/               test_bao_cao.py (công thức), test_phan_quyen.py (quyền + vận hành)
scripts/backup_db.py sao lưu database, giữ 30 bản gần nhất
serve.py             máy chủ waitress + /healthz + ghi log logs/app.log
config/
  org.yml            Bầy → Phòng, quy tắc gán phòng dự phòng
  columns.yml        bản đồ tên cột của từng loại file export
  rules.yml          quy tắc nghiệp vụ (V.VIP Plus, gộp dòng trùng, nhóm thâm niên)
  staff_overrides.yml  ghi đè phòng cho acc cá biệt
```

## Quy tắc nghiệp vụ đã áp dụng (BGD chốt 11/09/2026)

| Quy tắc | Cách xử lý |
|---|---|
| Camera 2 dòng giống hệt nhau | Tính là 1 (khoá là mã băm của cả dòng) |
| `TIN.MinhLH1` | Chỉ tính cho Phòng CUS DNG2 (sửa trong `config/staff_overrides.yml`) |
| V.VIP Plus | Tính vào V.VIP (`config/rules.yml`) |
| NV chưa có trong danh mục | Vào "Chưa gán phòng", vẫn cộng vào tổng chi nhánh |
| Tiến độ tháng | Chia đúng số ngày thật của tháng (sheet cũ chia 31 cho tháng 30 ngày) |

## Đối chiếu số liệu (kỳ 01–11/09/2026)

| Chỉ số | App | Sheet cũ | Ghi chú |
|---|---|---|---|
| Số Online | 1.394 | 1.397 | sheet đếm trùng 4, bỏ sót 1 |
| Số V.VIP | 980 | 983 | sheet đếm trùng 3 |
| Camera | 554 | 587 | sheet đếm cả dòng trùng |

## Tính năng giao diện

- **Báo cáo Tổng** (trang mặc định): đúng bố cục bảng tổng hợp cũ, header gộp nhóm, heatmap 5 mức
  trên các cột %, dòng bầy/tổng in đậm. Chọn ngày bằng lịch (ngày chưa có dữ liệu bị chặn) hoặc
  4 nút chọn nhanh.
- **Cỡ bảng “Vừa màn hình”** (Báo cáo Tổng & Tracking): tự tính tỷ lệ theo bề rộng cửa sổ để xem
  trọn bảng trong một khung hình, không phải kéo ngang; vẫn chọn tay được 50% → 200%.
- **Chụp ảnh (PNG)**: xuất nguyên bảng thành ảnh vẽ ở máy chủ - đủ 100% dòng và cột, nét, có tiêu đề
  ngày, dùng để gửi vào nhóm cho nhân viên xem.
- **Lọc chi nhánh** Đà Nẵng / Quảng Nam ở tất cả trang báo cáo (kể cả bảng cảnh báo nhân sự).
- **Chọn kỳ báo cáo** bằng nút lùi/tới + danh sách tháng: tháng mới có dữ liệu tự xuất hiện,
  không phải sửa code mỗi đầu tháng.
- **Thanh lọc dính** dưới tiêu đề: cuộn tới đâu cũng đổi được kỳ và chi nhánh.
- **Bảng dài cuộn trong khung**, tiêu đề cột luôn nhìn thấy; menu cũng cuộn riêng khi màn hình thấp.
- **Diễn biến theo ngày** xem được theo Bầy hoặc theo Phòng (8 phòng dẫn đầu + nhóm còn lại).
- **Nạp nhiều file một lượt**: kéo cả 3 file bán hàng (và file NSLĐ đầu tháng) rồi lưu một lần.
- **Tracking ngày**: ghim hàng tiêu đề ngày và cột Bầy/Phòng/Tổng khi cuộn; ô ngày tô màu theo mức
  so với ngày thường của chính phòng đó.
- **Cơ cấu Bầy theo tháng** (Cấu hình): mỗi tháng gán lại phòng vào bầy, có nút *Sao chép tháng trước*.
  Báo cáo của tháng nào dùng đúng cơ cấu của tháng đó; tháng chưa cấu hình thì dùng `config/org.yml`.
- **So sánh kỳ**: chọn 2 khoảng ngày bất kỳ (có mẫu sẵn: 7 ngày gần nhất, tuần trước…),
  ra chênh lệch theo phòng và **Top sale hụt số / tăng số** — đúng Khối D2 của sheet.
- **Chất lượng dữ liệu**: hợp đồng chưa gán phòng, acc lạ, ngày thiếu dữ liệu, hợp đồng
  bất thường, tồn đọng lâu — kiểm trước khi gửi báo cáo.
- **Quản trị**: tài khoản (thêm bằng hộp thoại có kiểm tra, đổi vai trò + phạm vi, khoá, đặt lại
  mật khẩu, xoá có xác nhận), danh mục nhân sự, lịch sử nạp kèm nút **gỡ bỏ một lần nạp**.
- **Cấu hình**: thêm Bầy / Phòng kinh doanh bằng hộp thoại, xoá có kiểm tra ràng buộc, cơ cấu Bầy
  theo từng tháng, chỉ tiêu tháng.
- **Xuất Excel** giữ nguyên gộp tiêu đề, màu heatmap và dòng tổng in đậm (ngoài CSV).
- Tông màu theo bộ nhận diện FPT (xanh dương chủ đạo, cam nhấn, xanh lá tín hiệu tốt), icon SVG.

## Hướng dẫn cho người dùng

Trong app có sẵn mục **Hướng dẫn sử dụng** (menu Trợ giúp) viết bằng lời đời thường cho
người lần đầu dùng. Bản để in/gửi kèm: [docs/HUONGDAN.md](docs/HUONGDAN.md).

## Audit & kế hoạch

Xem [docs/AUDIT.md](docs/AUDIT.md): bảng trạng thái 35 hạng mục chức năng, nguyên tắc
3 tầng cấu hình (DB / YAML / code) và kế hoạch 4 giai đoạn.

## Việc còn lại

Giai đoạn 1 (đưa vào dùng thật), 3 (báo cáo & phân tích sâu) và 4 (vận hành ổn định)
đã xong. Còn lại:

1. Nạp file export gốc `.xlsx` (Internet / FPT Play / Camera) qua trang **Nạp dữ liệu**,
   đối chiếu lại ánh xạ cột với file thật.
2. Nhập chỉ tiêu thật trong **Cấu hình** (số hiện tại lấy tạm từ sheet cũ).
3. Nạp file NSLĐ của QNM và các tháng trước; chốt công thức điểm ITN + ngưỡng OK/NOT OK.
4. Tạo tài khoản cho trưởng phòng / giám đốc bầy trong **Quản trị**.
5. **Giai đoạn 2 — AI**: chatbot hỏi đáp số liệu + insight tự động sau mỗi lần nạp
   (OpenAI API, chạy trên view đã lọc quyền, ẩn danh tên) — làm sau cùng theo yêu cầu.
