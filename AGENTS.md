# AGENTS.md: quy tắc khi sửa hoặc thêm chức năng

Người (hoặc AI) sửa code app này phải đọc file này trước. Mục tiêu:

- con số luôn đúng;
- code không phình, không lặp;
- trang vẫn nhanh;
- quyền xem luôn được giữ.

Viết lời cho người dùng bằng **tiếng Việt**, dễ hiểu với người không rành kỹ thuật.

---

## 1. App là gì, nằm ở đâu

- **Việc app làm:** Dash 4 + dash-ag-grid + Plotly + pandas + SQLAlchemy + Flask-Login. App thay các Google Sheet báo cáo bán hàng và nhân sự của chi nhánh Đà Nẵng + Quảng Nam.
- **Chạy thật:** Vercel (`api/index.py`, vùng Tokyo) + Supabase Postgres (Tokyo).
- **Trên máy:** SQLite `data/ftel.db`. Test dùng `data/kiemthu.db`, dựng từ dữ liệu gốc kỳ 01-11/09/2026.
- **Quy tắc nghiệp vụ** (công thức Tracking, gán phòng, MTTN, số tồn, camera...) nằm ở `config/rules.yml`, `config/org.yml` và docstring từng module. **Không đoán quy tắc.** Không rõ thì hỏi chủ app rồi ghi lại.

### Bản đồ code: đặt đúng chỗ, không tạo file trùng việc

| Việc | File |
|---|---|
| Đọc / ghi số liệu, công thức (không có giao diện) | `app/*.py`: `metrics.py`, `overview.py`, `phan_tich.py`, `hr_metrics.py`, `ads.py`, `ads_phan_tich.py`, `nhap_ton.py`, `bao_cao_ngay.py`... |
| Nạp file Excel / CSV | `app/ingest/` (`loader.py` đọc, `commit.py` ghi) |
| Cơ cấu bầy / phòng, gán phòng | `app/org.py` (có bộ nhớ tạm riêng + `xoa_cache_org()`) |
| Quyền, người dùng, ghi nhật ký | `app/auth.py` (`ghi_log`, `loc_nhan_su`, `phong_duoc_xem`, `phong_nhan_su`) |
| Nhớ tạm kết quả đọc database | `app/bo_nho.py` (`@nho`, `@ghi`, `xoa`) |
| Thành phần giao diện dùng chung | `app/ui/components.py` (`tip`, `tieu_de`, `ghi_chu`, `card`, `kpi`, `field`, `seg_control`, `modal`, `cua_so`, `alert`, `callback_can_quyen`...) |
| Bảng + định dạng số | `app/ui/luoi.py` (`bang`, `SO`, `SO_1`, `PCT`, `PCT_GACH`, `PCT_DAU`, `CHENH`, `CHENH_PCT`, `USD`, `USD_D`, `VND`) |
| Kỳ báo cáo dùng chung giữa các trang | `app/ui/ky_chung.py` |
| Ngăn chi tiết một nhân sự (mở từ mọi bảng nhân sự) | `app/ui/ngan_nhan_su.py` + `assets/nhan_su_bam.js`; nội dung hồ sơ ở `app/ho_so_nhan_su.py`, `app/ui/pages/phong_ho_so.py` |
| Nhập Báo cáo ngày bằng giọng nói | `app/giong_noi.py` (tách số, khớp tên, quyền) + `app/ui/pages/baocaongay_giong.py` + `assets/ghi_am.js` |
| Theo dõi Online trong ngày (phiếu ca theo mã HĐ + khung giờ, nối với bảng Báo cáo ngày) | `app/online_ca.py` + `app/ui/pages/baocaongay_online.py` + `assets/online.js` |
| Danh bạ liên hệ (đọc hai file PNC / TIN, gộp trùng, tra cứu, người sale tự thêm) | `app/danh_ba.py` + `app/ui/pages/danhba.py` |
| Tra cứu giá gói cước theo phường / xã (lấy thẳng từ dịch vụ của fpt.vn, so hai phường, quét cả tỉnh) | `app/gia_fpt.py` + `app/ui/pages/giafpt.py` (+ `giafpt_ct.py` cửa sổ chi tiết gói, `giafpt_vung.py` tab Giá cả tỉnh) |
| Nhân viên AI (agent theo vai trò) và hook kiểm tra tự động / ghi nhật ký hoạt động (KHÔNG phải một phần của app: giao diện văn phòng AI là việc riêng của CEO, bên ngoài app) | `.claude/agents/coder.md` (agent duy nhất) + `.claude/quy_tac_ngan.md` (luật ngắn cho agent) + `.claude/settings.json` (hook) + `scripts/claude_hook.py` |
| Soạn email (khuôn 3 loại mail, gợi ý người nhận, Fox viết đoạn tình huống) + nút copy dùng chung | `app/soan_mail.py` + `app/ui/pages/soanmail.py` + `assets/sao_chep.js` |
| Khối làm việc (Kinh doanh / DVKH / Kỹ thuật): định nghĩa, menu từng khối, đường dẫn thuộc khối nào | `app/ui/khoi.py` (menu KD vẫn ở `NAV` của `app/ui/app.py`) |
| Khối DVKH: đọc file Excel, nạp database, số liệu, nhận định, phân tích chéo, xu hướng và dự báo, khai thác sâu | `app/dvkh/` (`doc_file.py`, `nap.py`, `so_lieu.py`, `tong_quan.py`, `insight.py`, `cheo.py`, `xu_huong.py`, `khai_thac.py`, `models.py`) + `scripts/nap_dvkh.py` |
| Trang khối DVKH (đường dẫn `/dvkh/...`) | `app/ui/pages/dvkh.py` (định tuyến) + `dvkh_tq.py`, `dvkh_sr_bd.py` (+ `dvkh_sr_bd_sau.py`: giữ chân, khách và dịch vụ), `dvkh_sr_cd.py`, `dvkh_roi_mang.py`, `dvkh_cong_no.py`, `dvkh_nhan_su.py`, `dvkh_insight.py`, `dvkh_nap.py`; thành phần chung `dvkh_chung.py`, biểu đồ và thẻ xu hướng dùng chung `dvkh_ve.py` |
| Phễu bán hàng (dưới Dự báo ở Báo cáo Tổng, nạp từ mục Nạp dữ liệu) | `app/pheu_ban_hang.py` (số liệu + giao diện 5 tầng) + `config/columns.yml` (`pheu_ban_hang`) + `config/rules.yml` (`pheu_ban_hang.don_vi_phong`) |
| Phản hồi hệ thống (nút ghim chân menu trái, popup góp ý lọc mục theo quyền tài khoản, tab tổng hợp ở Quản trị) | `app/phan_hoi.py` + `app/models.py` (`PhanHoi`) |
| Bản tin 8h sáng gửi Zalo Bot (người nhận, chống gửi trùng, nội dung bản tin BGĐ, nhắc Admin nạp file) | `app/ban_tin.py` + `app/zalo_bot.py` (gửi tin) + `app/api_ban_tin.py` (`POST /api/ban-tin/chay` cho n8n) + `app/ui/pages/quantri_ban_tin.py` (tab Quản trị → Bản tin Zalo) + `app/models.py` (`BanTinNguoiNhan`, `BanTinNhatKy`) |
| Bản tin 8h cho TRƯỞNG PHÒNG (người nhận loại `truong_phong`, phòng gắn ở bảng phụ, tin Tổng quan + Từng nhân sự, gửi + chống trùng theo phòng) | `app/ban_tin_phong.py` (+ ô Phòng ở `quantri_ban_tin.py` / `quantri_ban_tin_duyet.py`) + `app/models.py` (`BanTinNguoiNhanPhong`) |
| Thêm người nhận Bản tin bằng cách nhắn bot (webhook Zalo, danh sách chờ duyệt, kết nối / ngắt webhook) | `app/ban_tin_cho_duyet.py` + `POST /api/ban-tin/zalo-webhook` ở `app/api_ban_tin.py` + `app/ui/pages/quantri_ban_tin_duyet.py` + `app/models.py` (`BanTinChoDuyet`) |
| Một trang | `app/ui/pages/<trang>.py`, có `layout()` + `register(app)` (+ `topbar()`) |
| CSS | `assets/style.css` (một file; thêm cuối file, có chú thích nhóm) |

---

## 2. Chống phình code (bắt buộc)

1. **Tìm trước khi viết.** Trước khi thêm hàm, định dạng, bảng, cửa sổ, thẻ: grep xem đã có chưa (`app/ui/components.py`, `app/ui/luoi.py`, module số liệu tương ứng). Có rồi thì dùng lại; thiếu một chút thì **mở rộng hàm chung**, không chép ra bản mới.
2. **Không định nghĩa lại** `SO = {"function": ...}`, `PCT`, `_grid` trong trang. Import từ `app/ui/luoi.py`. Bảng mới dùng `bang(...)`, hoặc hàm `_grid` mỏng của trang đó (chỉ để đặt mặc định riêng).
3. **Cửa sổ nổi:**
   - xem chi tiết → `cua_so(id, ...)`;
   - có nút Lưu / Huỷ → `modal(...)`.
   Không tự dựng `modal-nen` / `modal-hop` bằng tay.
4. **Ghi chú / giải thích:**
   - dùng `tip()` (ⓘ rê chuột), `tieu_de(chu, ghi_chu)`, `card(desc=...)`, `ghi_chu(...)`;
   - viết thành các câu ngắn, có dấu chấm: app tự tách mỗi câu một dòng;
   - không để đoạn chữ dài nằm ngoài giao diện.
5. **Giới hạn kích thước:** một file không quá **~900 dòng**, một hàm không quá **~80 dòng**. Vượt thì tách theo tab / khối. Mẫu có sẵn:
   - `ads.py` → `ads_phan_tich.py`;
   - `pages/ads.py` → `ads_cau_hinh.py`;
   - `pages/phantich.py` → `phantich_tinh.py`.
   Module con import helper từ module mẹ. Module mẹ import module con **trong hàm** (`layout()`, `register()`) để tránh vòng lặp import. Nếu nơi khác đang gọi `module_me.ham`, thì nạp lại tên đó ở cuối module mẹ.
6. **Xoá thẳng code chết**: hàm không còn gọi, tab đã bỏ, file trùng. Không comment-out, không để "phòng khi cần" (git đã giữ lịch sử). **Không xoá dữ liệu / bảng trong database** khi chưa được chủ app đồng ý.
7. **Đặt tên** theo cách đang dùng: tiếng Việt không dấu, chữ thường, gạch dưới (`theo_ngay`, `chi_tiet_tinh`, `ban_online_ngay`). Id Dash có tiền tố trang: `ads-`, `pt-`, `tq-`, `hr-`, `st-`...
8. **Docstring ngắn**, nói *vì sao / quy tắc nghiệp vụ*, không kể lại code làm gì. Ít chú thích trong thân hàm, chỉ ghi chỗ không hiển nhiên.
9. Không thêm thư viện mới vào `requirements.txt` nếu làm được bằng thư viện đang có.
10. Sửa xong chạy `ruff check app --select F,E9`: **không được có cảnh báo** (import / biến không dùng, tên chưa định nghĩa).

---

## 3. Tốc độ

1. **Hàm đọc database mà nhiều callback cùng gọi thì gắn `@nho("<nhóm>")`** (`app/bo_nho.py`). Nhóm hiện có:
   - `so_lieu`: bảng fact, danh sách ngày;
   - `ads`: dữ liệu Ads IBB7.
   Tham số phải hashable (list tự đổi sang tuple). Kết quả trả ra là bản sao, **không sửa tại chỗ** DataFrame con nằm trong dict trả về.
2. **Hàm ghi dữ liệu gắn `@ghi("<nhóm>")`** hoặc gọi `xoa("<nhóm>")`, để số mới hiện ngay. Thêm bảng hoặc đường ghi mới thì phải nghĩ: đọc của nhóm nào sẽ bị cũ?
3. **Mỗi lượt callback đọc một lần rồi dùng chung.** Truyền DataFrame đã đọc vào hàm con (như `theo_page(tu, den, ck, df)`), không gọi lại `theo_ngay(...)` nhiều lần.
4. **Tab / khối đang ẩn không tính.** Callback của tab phải có `Input("<trang>-tab", "value")` và `raise PreventUpdate` (hoặc trả `no_update`) khi tab đó không mở. Nội dung cửa sổ chi tiết dựng khi mở, không dựng sẵn.
5. **Không hỏi database trong vòng lặp** (mỗi phòng / mỗi ngày một câu). Đọc một lần theo khoảng rồi `groupby` bằng pandas, hoặc để SQL tự cộng.
6. **`layout()` phải nhẹ.** Chỉ đọc danh sách ngày / tháng / phòng (đã nhớ tạm). Số liệu nặng để callback nạp.
7. **Ghi nhiều dòng thì dùng executemany**, đừng nhét dữ liệu vào trong câu lệnh (chốt 27/09/2026,
   `ingest/commit._upsert`). `insert().values([800 dòng])` làm mỗi lô thành một câu SQL khác nhau nên
   SQLAlchemy phải dịch lại từ đầu: đo trên file 5.000 dòng, riêng phần dịch chiếm 6,3 trong 9,5 giây.
   Viết `session.execute(stmt, danh_sach_dict)` thì chỉ dịch một lần - cùng file đó còn 0,6 giây. Mọi
   dòng phải cùng một bộ cột, nên lấy hợp các cột rồi điền đủ bằng `.get()` trước khi gửi.
8. **Nạp file: đọc file đúng một lần** (`pages/upload.py`, `_nho_ket_qua` / `_doc_mot_lan`). File bán hàng
   là file luỹ kế cả tháng nên cuối tháng ~5.000 dòng, mỗi lần `load_file` mất ~7 giây; trước đây đọc một
   lần lúc xem trước rồi đọc LẠI lúc bấm Lưu. Nay kết quả đọc được giữ tạm trong bộ nhớ máy chủ, khoá theo
   mã băm nội dung file. Trên Vercel hai thao tác có thể rơi vào hai máy chủ khác nhau nên **phải luôn có
   đường đọc lại**, đừng biến bộ nhớ tạm này thành bắt buộc. `vercel.json` đang đặt `maxDuration: 60`:
   thêm việc gì vào đường nạp thì phải đo lại, chạm mốc đó là lưu hỏng giữa chừng chứ không phải chỉ chậm.

---

## 4. Số liệu đúng

1. **Đổi công thức hay cách đếm nào thì phải đối chiếu số thật** (sheet, hoặc số cũ đã khớp) trước và sau khi sửa. Báo cáo Tổng đã đối chiếu khớp với sheet: đừng làm lệch.
2. **Quy tắc đã chốt** (xem thêm docstring và `config/rules.yml`):
   - *Kỳ:* luỹ kế so cùng kỳ tháng trước; khoảng tự chọn so khoảng liền trước cùng số ngày. Cùng kỳ tính tới ngày có số cuối cùng.
   - *Trưởng phòng:* **không** vào chỉ số cá nhân (xếp hạng, bảng nhân viên, cảnh báo...); số bán vẫn cộng cho phòng (`acc_truong_phong()`).
   - *HĐ do sale chi nhánh khác bán hộ* (chủ app chốt 16/10/2026, thay quy tắc 11/09 "chưa gán phòng vẫn cộng vào tổng"): HĐ có CN Bán
    ngoài DNG_* / QNM (không phải ECOM), acc không có trong danh mục, KHÔNG tính vào số của Đà Nẵng + Quảng Nam ở mọi chỉ số (online,
    tồn, bán mới, V.VIP, FPT Play, Camera, Kết quả ngày, PTTB CNQL). `org.assign_phong` gán mã `NGOAI_CN` (`org.yml` → `fallback.ngoai_chi_nhanh`);
    mã này KHÔNG có trong danh sách phòng nên bảng theo phòng và dòng tổng tự bỏ qua, `hop_dong_online` / `hop_dong_ton` lọc riêng.
    Giữ nguyên: ECOM, nhân sự có trong danh mục. **Đối tượng KH VIP 7 → ANCS, nhưng tách theo CN Quản lý của khách như Inside** (chủ app chốt 16/10/2026, đối chiếu Inside Đà Nẵng 1.508): khách QNM về `ANCS_QNM` (phòng Quảng Nam, bầy Khác), còn lại về `ANCS` (Đà Nẵng); cả hai không cộng nhân sự / mục tiêu vào tổng (`rules.yml` → `tong_chi_nhanh.khong_cong`); cấu hình `org.yml` → `fallback.dac_biet_theo_cn_quan_ly`. Thêm phòng vào `org.yml` KHÔNG tự vào database: phải thêm dòng `dim_phong` (Quản trị → Cơ cấu tổ chức) và thêm mã phòng vào phạm vi của tài khoản đang xem `ANCS`. CN Bán rỗng hoặc lạ kiểu "DNG" vẫn về `CHUA_GAN` để người quản trị soát;
    dòng "Chưa gán phòng" ở Báo cáo Tổng chỉ hiện khi còn số. Dữ liệu đã nạp trước ngày chốt phải chạy lại gán phòng (đổi `CHUA_GAN` → `NGOAI_CN`).
  - *Tên gọi trong giao diện:* dùng "online" / "chưa online", **không bao giờ viết "đấu nối"** (có test kiểm tra). "Bán" (hợp đồng tạo mới) và "online" là HAI chỉ số khác nhau: không viết "bán 159 online", viết "có 159 online". Tránh chữ "kỳ" trơn: ghi "tháng 9", "tháng trước", "khoảng trước đó", "cùng kỳ T8".
   - *Dự báo cuối tháng:* giao diện hiện **hai số song song "3.892 (4.134)"** (chủ app chốt 21/09/2026). Số đứng trước `du_bao` = luỹ kế + (luỹ kế / số ngày đã qua) × số ngày còn lại, không nhân gì - ai cũng cộng lại được. Số trong ngoặc `du_bao_nhip` = nhân thêm hệ số nhịp dồn cuối tháng đo từ tháng trước (`du_bao.nhip_cuoi_thang`, chặn 0,7-1,5, dùng CHUNG cho mọi phòng). Cột `du_bao_tuan` ("Giữ nhịp 7 ngày") = số đứng trước nhưng lấy bình quân 7 ngày gần nhất đã chốt. Đánh giá An toàn / Cần tăng tốc / Rủi ro bám **số đứng trước**. Thử trên tháng 8/2026 (thật 4.322): số đứng trước sai 6,5% (giữa tháng thấp hơn thật 8-10%, khít dần về cuối tháng), số trong ngoặc sai 1,9% (từ ngày 15 là 1,3%) - thực tế thường rơi vào giữa hai số. Nhịp riêng từng phòng KHÔNG lặp lại giữa các tháng (tương quan T7 với T8 của cùng phòng r = -0,05) nên không dùng; nhịp cả chi nhánh ổn định (T7 1,25 · T8 1,26). Thêm hệ số theo thứ trong tuần không cải thiện. Đổi công thức thì phải chạy lại kiểu thử này trước và hỏi chủ app.
   - *Trợ lý AI (Fox):* nhân vật ở `tro_ly.giong_van()` - cố vấn điềm đạm, xưng tên trợ lý, gọi "anh/chị", mỗi số kèm một câu nói rõ ý nghĩa. "Đóng góp" chỉ dùng cho phần tăng; phần thiếu nói "hụt" / "chiếm". Sửa lời dặn hoặc `lam_sach` thì phải tăng `PHIEN_LOI_DAN` để nhận xét cũ hết hiệu lực. Hỏi về một người cụ thể thì dùng công cụ `nhan_su_ca_nhan`.
   - *Nhập tồn* (`app/nhap_ton.py`, chốt 21/09/2026, bật theo phòng ở `config/rules.yml` → `nhap_ton`, hiện chỉ
     IBB7): danh sách = đúng "Số tồn" (`phan_tich.hop_dong_ton`), hợp đồng / tên KH / ngày tạo / acc lấy từ file
     Internet, sale chỉ ghi 3 mục bắt buộc (ghi chú, mốc + ngày, phương án). Trả về ngày D → hạn hết ngày D +
     `han_tra_ve_ngay` (3), quá hạn HĐ tự huỷ nên luôn đỏ; hẹn quá ngày đỏ, đúng hôm nay vàng. Treo / CPTC ghi vào
     ghi chú. Danh sách xếp theo từng cụm nhân viên. Đã đối chiếu với sheet 20/09: 160/167 HĐ khớp, 7 HĐ lệch đều
     đúng là phải bỏ (đã online / không còn trong file). Giao diện (rà soát 24/09/2026): 4 ô số = 4 nút lọc,
     bảng **Theo nhân viên** (dòng ghim cuối "Cả phòng", bấm một dòng là tick người đó ở ô Nhân viên) chỉ hiện
     trên laptop - điện thoại đã có dòng tóm tắt đầu mỗi cụm thẻ. Ô bắt buộc chưa điền dùng viền nhạt + chữ gợi
     ý trong ô (`#nt-luoi .ag-cell.o-thieu ... ::after`), KHÔNG tô khối cam đậm: 30 ca trống sẽ thành một bức
     tường cam. Xem đúng một người thì bỏ dòng tiêu đề cụm. 4 ô số đếm theo ô Nhân viên đang tick, nên PHẢI có
     dòng phạm vi `#nt-pham-vi` ngay trên (chủ app đọc "Tổng tồn 16" tưởng là cả phòng). Chữ cảnh báo giữ dưới
     ~34 ký tự, cột hẹp nên dài hơn là dòng cao 5 hàng (có test chặn). Laptop nhập bằng Tab: ghi chú → mốc →
     ngày → phương án, mỗi ô tự lưu. **Rà soát UX 27/09/2026:** cột gọi "Ngày tồn" (đừng đổi về "Chờ", có
     test chặn), lọc theo số ngày tồn bằng ô `nt-ton` trên thanh lọc chứ không bằng bộ lọc cột của ag-grid -
     bảng có chèn dòng tiêu đề cụm nhân viên nên để ag-grid tự lọc / tự xếp là dòng tiêu đề trôi lẫn vào
     dữ liệu. Hai phương án đã chốt hướng xử lý được tô cả dòng, HAI MÀU KHÁC NHAU: Huỷ xám, KH đang suy
     nghĩ tím (không dùng vàng - vàng đang là "đến hạn hôm nay"). Thứ tự CSS: `dong-suy-nghi` → `dong-do` /
     `dong-vang` → `dong-huy`, vì ca huỷ không còn việc nên đè lên cảnh báo, còn ca suy nghĩ vẫn phải
     quay lại chốt nên cảnh báo đè lên nó (có test chặn thứ tự).
   - *Báo cáo đầu ngày* (`app/bao_cao_ngay.py`, chốt 24/09/2026, bật theo phòng ở `config/rules.yml` →
     `bao_cao_ngay`, hiện chỉ IBB7): sale nhập 7 ô (mục tiêu bán hôm nay, KHTN đang có, số bán thực
     hiện, dự kiến online
     sáng, dự kiến online chiều, đã online, ghi chú). PTTB luỹ kế tháng và số V.VIP ("Pay" trong ảnh mẫu)
     app tự lấy từ file - để không có hai nguồn số. Dự kiến tổng = sáng + chiều; còn phải online = tổng
     dự kiến - đã online. **Số V.VIP đếm THẲNG từ file FPT Play** (`_vvip_theo_acc`: mỗi dòng `la_vvip`
     là một V.VIP, theo ngày online của chính gói đó) đúng như Báo cáo Tổng / Báo cáo phòng; đừng đếm
     gián tiếp qua cờ `co_vvip` của hợp đồng Internet - gói V.VIP online khác ngày hoặc bán thêm trên
     hợp đồng tháng trước sẽ làm lệch (đã đo 24/09: 201 thay vì 199, 4 người sai). Người chỉ bán V.VIP
     cũng phải có dòng, nếu không dòng TỔNG thiếu. **"Đã online" là ô sale TỰ GÕ như một ô Google Sheet, KHÔNG liên quan tới file Internet** (nhưng từ 13/10/2026 hôm nay và ngày đã qua của người có ca thì tự đếm từ ca ở Theo dõi Online, xem khối ONL sáng / chiều / Đã online TỰ ĐẾM bên dưới)
     (đổi 06/10/2026, cột `da_online`; chưa gõ thì tính 0). Trước đó (25/09) app hiển thị số LỚN HƠN giữa số gõ
     và số file; sale gõ 1 mà file ghi 4 thì ô nhảy 4, gõ lại vẫn 4 nên tưởng lỗi nhập liệu - chủ app bỏ hẳn
     việc trộn, đừng dựng lại. Cả khối "Dự kiến online" (DK ONL, ONL sáng / chiều, Đã online, Còn phải ONL) là
     số sale khai báo; chỉ PTTB tháng và V.VIP lấy từ file. **Cột "Thực hiện"** (thêm 26/09/2026, cột `da_ban`,
     hiện ngay sau KHTN) là số bán sale **TỰ NHẬP**, KHÔNG lấy gì từ file và KHÔNG đối chiếu
     `ngay_tao_hd` - chủ app chốt đây là ô khai báo của sale, để so thẳng với ô "MT ngày" của chính
     họ. Ảnh PNG vẫn giữ đúng 8 cột cũ, không thêm cột này vào ảnh. Bảng chia **ba khối cột** (chủ app chốt 26/09/2026, `_dau_khoi` + lớp `khoi-dau` /
     `nhom-khoi`): *Báo cáo số bán* (MT ngày · KHTN · Thực hiện) · *Dự kiến online* (DK ONL · ONL sáng ·
     ONL chiều · Đã online · Còn phải ONL) · *Số Net / Pay* (PTTB tháng · MT tháng · V.VIP); DK ONL
     đứng TRƯỚC ONL sáng. Mục tiêu tháng TỪNG NGƯỜI nhập ngay trong bảng
     này, lưu vào `target_monthly` với `doi_tuong = "NHAN_VIEN"` (mọi truy vấn khác đều lọc `= 'PHONG'` nên
     không đụng nhau); mục tiêu PTTB/ngày của phòng mặc định TỰ CHIA mục tiêu tháng cho số ngày của tháng (làm tròn gần nhất),
     nhưng BGĐ đặt tay được cho cả tháng ở hộp "Sửa mục tiêu" (`chi_tieu = "bcn_ngay"`, chốt 08/10/2026: tháng 750
     tự chia ra 24 mà muốn giao 25/ngày); để trống là quay về tự chia. Ô để TRỐNG nghĩa
     là người đó chưa báo cáo, khác hẳn với số 0 đã nhập - đừng hiển thị 0 cho người chưa nhập (có test). **"Còn phải ONL" = dự kiến − đã online, KHÔNG kẹp ở 0**: người online
     vượt dự kiến để SỐ ÂM (tô xanh). Chủ app chốt 26/09/2026 là mọi con số phải cộng được cả hai
     chiều - kẹp ở 0 thì cộng dọc cột ra số lớn hơn dòng TỔNG, còn ép dòng TỔNG bằng tổng trừ tổng
     thì cộng dọc lại không khớp. Để số âm là cách duy nhất khớp cả hai. `tom_tat` (ảnh báo cáo) cũng
     bỏ `max(..., 0)` cho cùng một số. **Báo cáo của các ngày đã qua được GIỮ LẠI** (đổi 12/10/2026, chủ app chọn "giữ lịch sử từng ngày"; trước đó `don_ngay_cu()` xoá
     ngày đã qua, đã bỏ hẳn - đừng dựng lại) để vẽ xu hướng ở cửa sổ "Hiệu quả & xu hướng". **Bảng nhập không được để số vừa gõ "nhảy về 0"** (rà soát 13/10/2026, `assets/bang_nhap.js`): (1) mỗi ô vừa gõ vào SỔ CHỜ LƯU của trình duyệt cho tới khi `bn-da-luu.xong` báo đã xử lý; quá 8 giây chưa thấy thì gửi lại (tối đa 4 lần, không sợ lưu đôi vì cùng một số), hết lượt thì dòng đỏ "Chưa lưu được N ô" bấm để thử lại, đóng tab khi còn ô chờ thì có cảnh báo; (2) số máy chủ gửi về để làm mới bảng (nhịp tự nạp, `_va_dong`) đi qua Store `bn-cap-nhat` và trình duyệt BỎ QUA dòng còn ô chờ lưu / đang gõ - trước đây database chưa kịp lưu thì đọc lại ra số cũ rồi ghi đè lên số vừa gõ; (3) `_luu_o` bắt mọi lỗi bất ngờ (database chập chờn) và KHÔNG báo xong để trình duyệt tự gửi lại; (4) `bc.luu` xử lý hai lần lưu đầu tiên cùng lúc của một người (IntegrityError rồi đọc lại và cập nhật, có test chạy hai luồng) - trước đây một ô MẤT; (4b) ô bị từ chối theo luật (thấp hơn số ca ở Theo dõi Online) quay về số đã lưu NGAY qua `bo_cho` trong `bn-cap-nhat`, dòng báo ghi tên người; Dash BỎ phản hồi của lượt gửi cũ khi đã có lượt gửi mới cùng callback nên sổ chờ lưu tự gửi lại ô chưa được báo ngay khi có phản hồi khác về; (5) lần tự lưu của mình KHÔNG được cập nhật `bn-moc`, nếu không nhịp kế tiếp tưởng không ai sửa và bỏ qua số của người khác xen giữa; (6) [đã gỡ] việc Theo dõi Online ghi đè số ở bảng; nay bảng chỉ ĐỌC số đếm từ ca (xem khối ONL sáng / chiều / Đã online TỰ ĐẾM). **Trang tự nạp lại** mỗi `NHIP_MS` (60 giây; 15 giây
     làm Vercel Hobby cạn 4 giờ CPU, thực tế 9 giờ trong một chu kỳ - 09/10/2026) và `assets/nhip_an.js` TẮT nhịp
     khi tab ẩn, bật lại + nạp ngay khi quay về. Chỉ dựng lại bảng khi `moc_cap_nhat()` đổi, để không cắt ngang ô
     người khác đang gõ. Thêm nhịp tự hỏi máy chủ ở trang khác thì phải tính CPU: mỗi lượt là một lần gọi hàm.
     **Theo dõi Online trong ngày** (mục dưới bảng, cùng tab, chốt 12/10/2026; `app/online_ca.py`, khung giờ ở `rules.yml` →
     `bao_cao_ngay.khung_online`): mỗi mã HĐ là MỘT phiếu (nhân viên + khung giờ + trạng thái Dự kiến → Đang triển khai → Đã online, sale
     tự cập nhật, không lấy từ file; không lưu tên khách; dời khung / dời sang mai ghi lịch sử, huỷ ca = xoá phiếu). Mỗi mã HĐ là một phiếu (xem trên). **[ĐANG TẠM DỪNG từ 15/10/2026, công tắc `rules.yml` → `bao_cao_ngay.onl_tu_ca: false`: ba ô ONL sáng / chiều / Đã online của bảng sale TỰ GÕ TAY mọi ngày như trước, mục Theo dõi Online giữ nguyên logic + giao diện nhưng thu gọn thành MỘT thanh nhỏ dưới bảng (`onl-gap`, mặc định đóng, nhớ trạng thái trên máy) và đóng thì máy chủ KHÔNG nạp gì (`_nap` chặn khi `onl-mo` = false); bật lại = đổi công tắc thành true, mọi phần dưới đây chạy lại; `bc.che_do_onl` trả rỗng khi tắt, test bật bằng fixture `tu_ca_bat`; liên kết với Nhập tồn vẫn chạy]** **ONL sáng / ONL chiều / Đã online của bảng TỰ ĐẾM TỪ CA từ hôm nay trở về trước** (chủ app chốt 13/10/2026, phương án A; trước đó 13/10 đã từng tách rời hẳn hai nơi vì nhập hai chỗ nhọc và hay lệch số). `bc.che_do_onl(ngay)`:
     ngày CHƯA TỚI = sale GÕ TAY (dự kiến cho ngày mai thường nhập vào tối hôm trước, lúc đó chưa có mã HĐ nào); HÔM NAY = cả phòng tự đếm từ ca ở Theo dõi Online, ô xám, KHÔNG gõ tay (người chưa có ca thì 0);
     ngày ĐÃ QUA = người có ca thì tự đếm, người không có ca (ngày trước khi có mục này) giữ số đã gõ và vẫn sửa được. Cách đếm `online_ca.dem_theo_nguoi`: ca ở khung `buoi: sang` vào ONL sáng, `chieu` vào ONL chiều, "Đã online" = số ca đã bấm Đã online;
     ca "Chưa hẹn giờ" CHƯA tính vào sáng / chiều (đếm riêng `chua_xep`, bảng báo "Còn N ca chưa xếp khung giờ") cho tới khi đã online, lúc đó tính vào buổi của giờ bấm (trước 12h là sáng) để Đã online luôn nằm trong DK ONL; ca dời sang ngày khác không tính.
     Số sale gõ tối hôm trước KHÔNG bị xoá: vẫn nằm trong cột `onl_sang` / `onl_chieu` của database, bảng hiện thành `dk_toi_qua` để câu mô tả nói "Dự kiến đã nhập từ trước: X ca, hiện mới xếp Y". Máy chủ chặn ghi tay ba ô đó khi ô đang tự đếm (`bc.luu` ném `LoiBaoCao`, `bc.khoa_onl`;
     điện thoại và giọng nói tự bỏ ba ô này và báo), cột `tu_ca` của dòng quyết định ô có sửa được. Mỗi lần ca ở Theo dõi Online đổi, `_su_kien` báo `bn-da-luu` để bảng vá dòng + dòng TỔNG (cả người cũ lẫn người nhận ca);
     `bc.moc_cap_nhat` gộp thêm dấu vết của ca để nhịp tự nạp kéo số mới về khi NGƯỜI KHÁC sửa ca. Ca từ Nhập tồn CHƯA tự vào Theo dõi Online (vẫn bấm "Thêm tất cả" ở hộp xanh nhắc; làm tự vào thì phải tính chuyện sale huỷ ca rồi bị tạo lại).
     Đã gỡ từ lần tách rời trước và KHÔNG dựng lại: luật chặn "không thấp hơn số ca" (`bc._kiem_voi_ca` / `kiem_ca`), `dong_bo_bang`, `thieu_gio`, cột `co_ca`, thanh nhắc `onl-nhac`.
     Khung phụ (`phu: true`: Sau 17h30, Chưa hẹn giờ) chỉ hiện cột khi đang có ca. Phiếu được GIỮ qua các ngày (khác báo cáo
     đầu ngày). Giao diện vẽ ở trình duyệt (`assets/online.js`, thẻ đổi trạng thái / dời khung tức thì rồi mới báo máy chủ, giống Danh bạ);
     `thongKe` bên JS phải giống `online_ca.thong_ke` (có test đối chiếu bằng Node).
     **Tiến độ nhập** (`_tien_do`): thanh đầu trang "x/y người đã nhập", tên người chưa nhập bấm là cuộn tới dòng + mở ô (`assets/tien_do_nhap.js`); chỉ hiện hôm nay và
     ngày nhập trước. **Cửa sổ "Hiệu quả & xu hướng"** (thiết kế lại 13/10/2026; số liệu + nhận định ở `app/online_ca_phan_tich.py`, giao diện `baocaongay_hq.py` = tổng quan cả phòng, `baocaongay_hq_nv.py` = chi tiết một người mở bằng cách bấm dòng người đó, `baocaongay_hq_ve.py` = thành phần chung): ngoài là năm ô chỉ số so với khoảng liền trước, thanh kết quả các ca, nhận định, bốn biểu đồ, bảng nhân viên bấm được; nhận định do LUẬT cố định sinh ra (không dùng AI), người dưới `TOI_THIEU_CA` ca đã xét thì chỉ ghi "Ít dữ liệu", ngưỡng đánh giá Tốt ≥ 80% / Cần chú ý ≥ 50%. Tỷ lệ ca lên ĐÚNG hẹn = online khi còn trong
     hạn của khung giờ HẸN LÚC TẠO (`khung_dau`), theo giờ sale BẤM Đã online (`online_luc`); trễ / chưa lên / dời ngày là các nhóm còn lại (dời ngày tách riêng nhưng VẪN nằm dưới mẫu số), ca "Chưa hẹn
     giờ" và ca chưa tới hạn không tính vào tỷ lệ; một ca dời tạo phiếu ở cả hai ngày nên "số ca" là ca theo kế hoạch từng ngày. Dời sang ngày khác (`doi_ngay`; nút "Dời sang ngày mai" hoặc chọn một ngày, tối đa tới `bc.ngay_xa_nhat()` = 7 ngày như Báo cáo ngày cho nhập trước) KHÔNG xoá ca cũ mà đổi thành `doi_mai` (không hiện trên bảng, vẫn tính là chưa lên) và tạo
     ca mới ở ngày đích; menu ⋯ → "Dời ca" là MỘT form: chọn Khung + Ngày rồi bấm MỘT nút xác nhận nói rõ sẽ dời tới đâu (13/10/2026; chọn ô nào cũng chưa dời, tránh bấm nhầm; đừng dựng lại hộp thoại hỏi khung giờ lần hai; ghi chú giữ nguyên) nằm cùng hàng với nút "Hủy ca"; bấm "Dời ca" hỏi xác nhận rồi hiện thông báo kèm nút "Hoàn tác" 12 giây. Dời NHẦM rồi dời VỀ LẠI ngày cũ thì phiếu `doi_mai` của ngày đó SỐNG LẠI (không tạo phiếu thứ hai) với đúng trạng thái trước khi dời (Dự kiến / Đang lắp / Đã online, nhớ trong lịch sử phiếu) và ngày hẹn Nhập tồn về đúng ngày cũ; danh sách ngày dời chạy từ hôm nay tới ngày xa nhất, trừ ngày đang xem, và thẻ ca đang ở "Chưa hẹn giờ" có sẵn ô "Xếp khung giờ…" để xếp ngay trên thẻ. **Liên kết với Nhập tồn và bảng** (chủ app yêu cầu 12/10/2026 để hai nơi cùng một sự thật; code ở `app/online_ton.py`): (1) Nhập tồn có mốc "Hẹn thi công" đúng ngày
     đang xem mà chưa có ca thì hộp xanh nhắc xếp khung giờ (`hen_cho_ngay`, bỏ ca Huỷ / Đã triển khai);
     (2) thêm ca mà Nhập tồn đang hẹn / trả về NGÀY KHÁC thì PHẢI hỏi sale trước (`them_nhieu` trả `hoi`, trình duyệt `confirm` rồi gửi lại `xn`), đồng ý thì ca được thêm và ngày hẹn
     ở Nhập tồn tự đổi; chưa có mốc thì tự điền Hẹn thi công theo ngày ca; (3) dời ca sang ngày khác → Nhập tồn đổi ngày hẹn theo; (3b) CHIỀU NGƯỢC LẠI: sale đổi mốc Hẹn thi công của HĐ ở Nhập tồn sang ngày D (từ hôm nay tới ngày xa nhất) thì ca còn sống (Dự kiến / Đang triển khai) của HĐ đó được DỜI về D vào "Chưa hẹn giờ" để sale xếp lại khung giờ (`online_ca.keo_ca_theo_ton`, gọi từ trang Nhập tồn sau mỗi lần sửa mốc / ngày; chủ app 13/10/2026), HĐ chưa có ca thì hộp xanh nhắc (phiếu đã dời đi `doi_mai` KHÔNG tính là "đã có ca"; thêm lại thì phiếu cũ sống lại). Mỗi lần nạp mục Theo dõi Online còn tự kéo về (`keo_ca_ve_ngay`) những ca Nhập tồn đang hẹn đúng ngày đang xem mà đang nằm ngày khác, trừ HĐ đã chọn Huỷ / Đã triển khai (ca Lưu Quốc Trường Sơn 13/10/2026). **Chỉ kéo khi HĐ còn trong tồn VÀ Nhập tồn được sửa SAU lần cuối ca đổi**: sale vừa dời ca ở Theo dõi Online mà bị kéo ngược thì ca "nhảy về chỗ cũ" sau khi tải lại (lỗi thật 13/10/2026, DNG.Anhtu dời ca sang 15/10 không được; HĐ không còn tồn thì Nhập tồn không ghi được nên còn ngày cũ) - có test chặn; `online_ca.moc` gồm cả HĐ Nhập tồn đang hẹn ngày đó nên trang đang mở tự nạp lại; (4) bấm Đã online → phương án Nhập tồn "Đã triển khai", bỏ Đã online
     → "Đang chờ triển khai"; (5) thẻ ca mà ngày hẹn Nhập tồn lệch hiện nhãn "Nhập tồn: dd/mm" + nút cập nhật; (6) [đã gỡ 13/10/2026] luật kiểm số ONL / Đã online của bảng theo số ca. HĐ không còn trong tồn thì bỏ qua, không báo lỗi. **Ghi chú liên kết HAI CHIỀU** (chủ app 13/10/2026): ghi chú của ca (Theo dõi Online) và "Ghi chú tình trạng" của HĐ (Nhập tồn) là CÙNG MỘT chữ, sửa bên nào thì bên kia đổi theo, bản ghi sau cùng thắng (`online_ton.ca_sang_ton` khi sửa ghi chú ca / tạo ca có ghi chú; `online_ca.ghi_chu_tu_ton` gọi từ trang Nhập tồn mỗi lần sửa ghi chú, chép sang các ca còn sống từ hôm nay). Mỗi lần nạp mục Theo dõi Online còn tự KÉO ghi chú các ca về khớp Nhập tồn (`dong_bo_ghi_chu_ngay`: Nhập tồn có chữ thì ca lấy chữ đó; Nhập tồn trống mà ca có chữ thì chép sang Nhập tồn) nên ca tạo trước khi có liên kết cũng tự khớp, chỉ ghi khi có chỗ lệch. Ca mới không gõ ghi chú thì lấy sẵn chữ Nhập tồn; gõ ghi chú riêng khi Nhập tồn đã có chữ thì NỐI vào cuối (`gop_ghi_chu`) để không xoá lịch sử tình trạng. Hai giới hạn độ dài phải BẰNG nhau (500), nếu ca ngắn hơn thì ghi chú dài từ Nhập tồn bị cắt rồi ghi ngược lại là mất chữ.
     **Giao diện Theo dõi Online (làm lại 12/10/2026 vì chủ app báo bản trước "khó xài": khung giờ lặp hai lần, phải chọn 3 ô mới thêm được ca)**: chọn
     NHÂN VIÊN một lần ở đầu mục (đã chọn "Tôi là" thì tự chọn sẵn); mỗi khung giờ là MỘT cột (đã qua / đang diễn ra / sắp tới / quá giờ thể hiện ở
     viền đầu cột), gõ hoặc dán NHIỀU mã HĐ ngay ở cuối cột rồi Enter là thêm đúng khung đó (`them_nhieu`), "Từ HĐ tồn" ở cuối cột liệt kê HĐ tồn của người đang chọn
     (`ton_tat_ca`, gửi cả phòng trong gói dữ liệu) bấm là thêm. Mỗi ca một THẺ (chủ app thấy bản dạng dòng chữ "không trực quan như ảnh mẫu"): mã HĐ + nhãn trạng thái màu ở góc, người phụ trách, nút "Đang lắp" / "✓ Đã online", ⋯ = dời khung / dời ngày / sửa ghi chú / huỷ (đổi SALE PHỤ TRÁCH: chủ app từng bỏ 12/10/2026 rồi đòi lại 13/10/2026 vì một acc có ca của hai người, vd 6 ca của Ngọc Khái có 4 ca là của DNG.Tu; nằm trong form "Dời ca" của menu ⋯ cùng Khung / Ngày, một nút xác nhận, có Hoàn tác; chỉ đổi người của phiếu đó, `online_ca.doi_nguoi`); đầu mục là năm ô số liệu lớn (ca dự kiến, chờ lắp, đang triển khai, đã online, và "Ca bị dời" = số ca của ngày này đã dời sang ngày khác, bấm vào mở thanh chi tiết "Ca dời ngày"; theo bộ lọc nhân viên) + thanh tiến độ.
     Ca PHÁT SINH trong ngày chưa kịp có ở Nhập tồn thêm bằng nút "+ Thêm ca" (ngoài trang chỉ một nút, bấm mới mở hộp thoại `onl-tm` đúng 4 ô: mã HĐ, người phụ trách, khung giờ, ghi chú; chủ app yêu cầu 12/10/2026). Nội dung hộp vẽ ở `online.js`, nằm NGOÀI `#onl-goc` nên sự kiện của nó phải gắn riêng.
     Thanh đỏ "quá giờ" dời cả nhóm ca một cú bấm (`doi_nhieu`), cuối ngày hỏi dời hết ca chưa online sang mai; ca dời từ 3 lần có nhãn cảnh báo.
     Thống kê ca dời (`ca_doi`: dời đi sang ngày nào / dời đến từ ngày nào) cũng chỉ là MỘT thanh xám gập ẩn sẵn, bấm mới gom theo ngày (chủ app 13/10/2026: không trải ra toàn bộ).
     **Mở được báo cáo của ngày CHƯA TỚI** (chốt 26/09/2026, `TRUOC_TOI_DA` = 7 ngày,
     `ngay_xa_nhat()`): sale hay điền trước cho hôm sau. Ngày tương lai vẫn hiện các cột app tự lấy từ
     file nhưng đó là số của hôm nay, nên tiêu đề phải có nhãn "Nhập trước" và một dòng nói rõ - bỏ đi
     là người đọc tưởng số đã có thật.
     **Nhập bằng giọng nói** (`app/giong_noi.py`, chốt 08/10/2026, chỉ phòng ghi ở `config/rules.yml` →
     `bao_cao_ngay.giong_noi`, hiện IBB7; đúng người vào được Báo cáo ngày): sale nói, trình duyệt chuyển thành chữ
     (MẶC ĐỊNH MIỄN PHÍ bằng nhận dạng sẵn của trình duyệt; Quản trị → Trợ lý AI đổi sang OpenAI nếu nghe chưa
     chuẩn, ghi âm khi đó mới gửi máy chủ), AI CHỈ tách người + số, CODE khớp tên (`khop_ten`, bỏ dấu, trùng tên gọi thì
     bắt chọn) và kiểm số, sale xem lại ở hộp "Nhập báo cáo bằng giọng nói" rồi mới bấm Lưu (`luu_nhieu`: chỉ ghi ô có
     giá trị, ô trống là KHÔNG ĐỔI, không ghi đè thành 0; chỉ ghi người thuộc phòng). Không lưu ghi âm. Cần AI đã mở
     quyền cho tài khoản (Quản trị → Trợ lý AI, sale được dùng cả Fox - chủ app đồng ý 08/10/2026), có trần
     `TOI_DA_NGAY` lượt/ngày (tài khoản sale dùng chung cả phòng; superadmin không giới hạn). Đừng để AI tự chọn
     nhân sự hay ghi dữ liệu; đừng đưa tên khách hàng vào lời gửi AI.
     Ảnh PNG ở `app/export_png_ngay.py`. **Ba khối chữ do người dùng TỰ NHẬP rồi bấm Lưu** - nút
     "Fox viết giúp" đã bỏ hẳn cùng module `bao_cao_ngay_ai.py` (chủ app chốt 28/09/2026). Dòng TỔNG trong ảnh lấy mục tiêu tháng CỦA PHÒNG, không cộng mục tiêu từng người.
     Ảnh phải giữ đúng mẫu chủ app đưa (nền xanh chuyển màu + vệt chéo + góc cam + tia sét, ba khối số có
     biểu tượng tròn, dòng TỔNG nền cam, ba khối chữ, dải nguồn cuối ảnh) và đúng 8 cột: Nhân sự · MT ngày ·
     KHTN · ONL sáng · ONL chiều · DK ONL · PTTB tháng · Pay (Pay = số V.VIP). Font đi kèm app không có bản
     nghiêng nên chữ nghiêng làm bằng `_nghieng()` (kéo xiên), đừng thêm file font mới. Cỡ chữ trong ảnh
     phải ĐỌC ĐƯỢC TRÊN ĐIỆN THOẠI: đừng giảm xuống dưới mức hiện tại (dòng số 19, bảng 17, ba khối chữ
     16,5 ở tỷ lệ vẽ 1). Nút gọi AI hoặc vẽ ảnh phải có `running=` khoá nút + đổi chữ trong lúc chạy,
     nếu không người dùng bấm lại nhiều lần - mỗi lần là một lượt gọi AI tốn tiền.
   - *Soạn email + Danh bạ* (`app/soan_mail.py`, `app/danh_ba.py`, chốt 10/10/2026; **chỉ admin + nvkd IBB7**:
     `duoc_soan_mail`, phòng bật ở `config/rules.yml` → `soan_mail`; trưởng phòng KHÔNG dùng): sale chọn một trong 3 thẻ mail
     mẫu (ca hot triển khai · xin xuất hoá đơn DN · xin đầu tư hạ tầng; thẻ hạ tầng gộp HAI mẫu `ha_tang` = nâng cấp tập điểm và `ha_tang_moi` = hỗ trợ đầu tư tập điểm mới, đổi qua lại bằng hai nút nhỏ `.sm-con-the` đầu biểu mẫu, mã HĐ / địa chỉ / SĐT đã gõ tự chép sang mẫu kia nếu ô bên đó trống; chủ app 16/10/2026; mẫu khai `nhom` trong `LOAI` thì chung một thẻ, `sm.nhom_mau()`); thẻ thứ năm "Tranh chấp HĐ" (`tranh_chap`, 17/10/2026): hai HĐ của hai sale cùng một khách, mã phiếu / giờ lên HĐ / nghi vấn tiêu đề / đề nghị xử lý đều KHÔNG bắt buộc (khuôn dùng đoạn tuỳ chọn `[[ ... {khoa} ... ]]`: bỏ riêng đoạn đó khi ô trống, không báo thiếu), diễn biến do sale gõ / bấm gợi ý nhanh / Fox viết (giọng khách quan, không tự quy kết), gợi ý người nhận để TRỐNG, nhắc đính kèm ảnh Zalo; thẻ thứ tư "Xin thêm bộ phát" (`bo_phat`, 17/10/2026) cho NHIỀU tình huống: ô tình huống bắt buộc (không có câu mẫu để khỏi gửi nhầm), hàng nút "Gợi ý nhanh" `goi_y_cau` bấm là thêm một câu có sẵn (nhà nhiều tầng, thiết bị cũ yếu, khách không muốn mua thêm...), ô "Xin hỗ trợ thêm" để trống = bộ phát phụ; gợi ý người nhận để TRỐNG vì danh bạ không cho biết ai duyệt thiết bị, điền các ô thay đổi, KHUÔN (`LOAI[...]["than"]`) tự
     điền phần cố định, xem trước rồi **Copy dán vào Outlook** - app KHÔNG gửi mail, KHÔNG mở Outlook (mailto bị giới hạn độ
     dài, mất chữ đậm), KHÔNG lưu nội dung mail và KHÔNG xử lý ảnh CCCD (sale tự đính kèm; có dòng nhắc). Chỉ ghi nhật ký
     `soan_mail` (loại + mã HĐ) và `soan_mail_fox`. **Người nhận chỉ GỢI Ý, sale tự chọn Đến / CC** (chủ app chốt):
     đừng tự điền người nhận. Quy tắc gợi ý ở `LOAI[...]["goi_y"]` theo nhóm chức danh (`danh_ba.nhom_chuc`) và chi nhánh
     nơi lắp (ô chọn, hoặc đoán từ địa chỉ, hoặc chi nhánh của sale): ca hot → đội trưởng phụ trách khu vực trong địa chỉ
     (cột ghi chú là chữ tự do "Block Sơn Trà" nên khớp cụm với địa chỉ, không có bảng phân vùng) + TP kỹ thuật; hoá đơn →
     PGĐ nơi lắp, CC giám đốc nơi lắp + giám đốc Đà Nẵng; hạ tầng → TP hạ tầng, CC giám đốc. Chi nhánh có trong cả hai
     file thì chỉ gợi ý người của bản MỚI (PNC T10) vì TIN (T8) có thể đã cũ (giám đốc Đà Nẵng lệch giữa hai file).
     **CC bắt buộc theo phòng** (`rules.yml` → `soan_mail.cc_bat_buoc`, 10/10/2026: nvkd IBB7 luôn CC PhucVHD@fpt.com; admin không bị áp): gộp lúc hiển thị / dựng mail (`gop_cc_bat_buoc`), chip có cờ `khoa` không có nút gỡ, không lưu vào danh sách của sale. **Fox chỉ viết MỘT đoạn "tình huống" từ ý chính của sale**; địa chỉ, SĐT, MST, tên khách KHÔNG gửi AI (số dài ≥ 6 chữ
     số và email bị che trong `_che`), có trần `TOI_DA_NGAY` lượt/ngày, nút `running=` khoá khi đang chạy, có "Hoàn tác".
     **Giao diện (chốt 10/10/2026):** bên trái chọn loại (năm thẻ, mỗi thẻ một icon xám `BIEU_TUONG`, thẻ đang chọn tô xanh FPT phẳng, KHÔNG dùng nhiều màu / gradient (chủ app chê "AI-generated quá" 17/10/2026), không có dòng mô tả; bấm là đổi ngay trên trình duyệt) + điền ô + ô "Thêm ý riêng" (đoạn `{?y_them}` nằm
     trước câu cảm ơn); bên phải là MỘT lá thư kiểu Outlook: Đến / CC, gợi ý người nhận (MỘT nút xổ xuống, mỗi người một dòng có nút Đến / CC; chủ app muốn gọn 12/10/2026, đừng trải thành danh sách thẻ), tiêu đề, lời chào, nội dung. **Tiêu đề và nội dung sửa được trực tiếp**
     (chủ app hỏi "muốn thêm ý ngoài khuôn thì sao"): máy chủ chỉ gửi `kq` vào `dcc.Store` `sm-kq`, `assets/soan_mail.js` tự vẽ vào `#sm-tieu`
     / `#sm-than` (hai khối này KHÔNG có con do Dash dựng, nếu dựng bằng Dash thì chữ sale gõ sẽ bị xoá hoặc lệch khi Dash cập nhật). Phần sale đã sửa tay được GIỮ khi đổi ô
     bên trái (hiện thanh vàng + nút "Dựng lại từ các ô"); nút Copy đọc thẳng chữ đang hiện nên luôn là bản đã sửa. Dán vào thư luôn là chữ trơn. **Đưa sang Outlook (chủ app dùng Outlook WEB, 10/10/2026):** nút "Mở thư trong Outlook" mở thư mới trên Outlook web (`outlook.office.com/mail/deeplink/compose?mailtouri=<mailto>`; KHÔNG dùng riêng `to=` / `cc=` vì Outlook web bỏ qua CC, chủ app báo 10/10/2026) đã điền sẵn Đến / CC / tiêu đề / NỘI DUNG CHỮ TRƠN (chủ app muốn mở ra là đủ, không phải dán; mất chữ đậm), đồng thời copy bản có chữ đậm vào clipboard để ai cần thì Ctrl+V. Link dài quá `LINK_TOI_DA` thì bỏ nội dung khỏi link (còn clipboard). Đã thử `mailto:` và file `.eml`: không dùng được vì máy không đặt Outlook làm chương trình mail mặc định, và chủ app chỉ muốn MỘT nút tiện nhất nên đừng thêm lại. Code ở `assets/sao_chep.js` (có test Node). Lời chào (Dear …) là ô sale TỰ GÕ (chủ app bỏ ô chọn anh / chị, 10/10/2026: mail hay gửi cả một phòng, vd "phòng kỹ thuật DNG"); đừng
     dựng lại ô chọn xưng hô hay tự đoán lời chào theo người nhận. Thêm loại mail mới = thêm một mục vào `LOAI` (có test chặn ô trong khuôn không có nguồn). Danh bạ: file PNC (Đà
     Nẵng vào Nam, mới hơn) và TIN (Đà Nẵng ra Bắc) do admin nạp lại hằng tháng, **mỗi file là bản chụp mới nhất** (thay
     toàn bộ dòng của nguồn đó), bộ đọc nhận cột theo TÊN chứ không theo vị trí vì hai file khác nhau (`_doc_sheet`); trùng
     người (tên + chi nhánh) gộp lúc ĐỌC theo TAY > PNC > TIN, email lệch giữ thành "email khác". Người ngoài file (vd
     người CC trong mail mẫu) do sale tự thêm (nguồn TAY, sửa / xoá được). Có số di động nội bộ: không đưa file Excel
     danh bạ vào git, không in ra log.
     **Tốc độ (10/10/2026): danh bạ lọc NGAY TRÊN TRÌNH DUYỆT** (`assets/danh_ba.js`; máy chủ chỉ gửi MỘT lần `cho_trinh_duyet()`, khoảng 350 KB cho 1.100 người).
     Mỗi lần gõ tìm hay đổi nhóm chức danh từng là một lượt hỏi máy chủ + dựng 60 thẻ Dash nên trễ, có lúc nhóm đã đổi mà danh sách chưa kịp đổi (chủ app báo);
     nay mỗi lần lọc ~60-120 ms và không tốn CPU Vercel. Đổi cách lọc / xếp thì sửa `loc` ở JS (có test chạy đúng hàm đó bằng Node). Soạn email dựng sẵn CẢ BA
     biểu mẫu và chỉ ẩn / hiện bằng CSS (đổi loại tức thì, ô đã gõ không mất) nên id mọi ô mang cả tên loại (`l`). Bảng nhiều thẻ dựng bằng Dash thì nghĩ tới cách này.
     Trang Danh bạ CHỈ xem từng chi nhánh dạng **Sơ đồ** (chủ app chốt 10/10/2026: bỏ dạng thẻ, bỏ nút Thẻ / Sơ đồ, bỏ lọc nhóm chức danh, bỏ "Mọi chi nhánh"; mở trang là Đà Nẵng, ô "Tìm" chỉ tìm TRONG chi nhánh đang chọn; tra người trong toàn danh bạ ở hộp Tra danh bạ của Soạn email, vẫn dạng thẻ): CÂY theo PHÒNG BAN, căn giữa, đường nối đầy đủ - gốc là ban giám đốc, mỗi phòng ban một nhánh
     (Kỹ thuật và hạ tầng, trong đó có đội trưởng theo khu vực · DVKH · Kế toán · Hành chính nhân sự, theo `danh_ba.nhom_chuc`; KHÔNG gộp các phòng ban với nhau, chủ app sửa
     10/10/2026). Đường nối chỉ nói "phòng ban này thuộc chi nhánh": file KHÔNG có cột "báo cáo cho" nên đừng nối từng người với cấp trên (sẽ phải đoán và dễ sai).
     **Thứ tự người trong mỗi nhóm theo CẤP BẬC rồi tên gọi** (`danh_ba.cap_bac`: giám đốc → phó giám đốc → trưởng phòng / trưởng nhóm / đội trưởng / kế toán trưởng → phó phòng → còn lại; cùng cấp xếp theo tên gọi, vd Bình, Hưng, Vũ):
     trưởng phòng phải đứng trên phó phòng (chủ app báo 10/10/2026), nên người chỉ có trong file TIN cũ chỉ bị đẩy xuống CUỐI TRONG CÙNG CẤP, không được vượt cấp. **Chi nhánh gom theo khu vực**
     (`nhom_chi_nhanh`): Miền Bắc → Miền Trung - Tây Nguyên → Miền Nam → Miền Tây → Khối văn phòng và trung tâm (từ Bắc xuống Nam), và trong mỗi miền xếp TỈNH TỪ BẮC XUỐNG NAM
     (`THU_TU_TINH`, vd Quảng Bình → Huế → Đà Nẵng → Quảng Nam → Quảng Ngãi; chi nhánh có số như Sài Gòn, HN xếp theo số); Đà Nẵng, Quảng Nam nằm đúng khu vực, KHÔNG tách nhóm
     riêng (chủ app chốt 10/10/2026), chỉ là chi nhánh chọn sẵn khi mở trang (`chi_nhanh_mac_dinh`); miền lấy theo TÊN
     SHEET của hai file trước (`MIEN_THEO_SHEET`; file xếp Thanh Hóa / Nghệ An vào miền Bắc, Ninh Thuận / Lâm Đồng vào miền Nam thì theo file), sheet đô thị lớn (TĐĐT...) thì theo tên tỉnh (`TINH_THEO_MIEN`).
     Ô chọn chi nhánh gõ chữ để tìm (combobox dựng bằng JS, tiêu đề khu vực là thanh xanh dính đầu danh sách, mở ra là cuộn tới chi nhánh đang chọn). Màn dưới 900 px chuyển thành cây dọc. Người chỉ có trong file TIN cũ mà chi nhánh đã có bản PNC thì gắn nhãn "có thể cũ" và xếp cuối nhóm.
   - *Tra cứu giá* (`app/gia_fpt.py`, chốt 22/10/2026, mọi tài khoản khối Kinh doanh, nằm trong `TRANG_NVKD`): giá lấy THẲNG từ dịch vụ mà
     website fpt.vn gọi (`apis.fpt.vn/ecp/public`, POST `/v1/locations/provinces|wards/list`, `/v1.1/packages/list|get`, header `client-id: fptvn`,
     không cần đăng nhập), gửi mã tỉnh + mã phường nên số khớp website (đã đối chiếu 22/10: Meta F1 340.000đ ở các phường nội đô Đà Nẵng,
     330.000đ ở phần lớn Quảng Nam cũ; từ khi sáp nhập Quảng Nam nằm trong tỉnh Đà Nẵng, mã 511). **Đây KHÔNG phải API chính thức**: FPT đổi
     cách gọi thì hỏng, nên mọi lỗi đổi thành `LoiGia` (trang báo bằng lời dễ hiểu) và `goi_theo_phuong` giữ bản lần trước làm dự phòng.
     Không lưu giá vào database; nhớ tạm 15 phút / khu vực (danh sách tỉnh, phường một ngày). Giá đã gồm VAT. Điều cần nhớ khi sửa:
     (1) `price.price` của dịch vụ `get` là giá theo thời hạn NGẮN NHẤT (990.000 cho 3 tháng), không phải giá tháng - giá tháng lấy từ `list`
     và truyền vào `chi_tiet_goi(gia_thang)`; (2) tổng tiền trả trước / giá tháng = số tháng thực phải đóng, phần còn lại là tặng (13 tháng chỉ
     đóng 12); chính sách có `effective_to` đã qua thì bỏ, giờ của dịch vụ là UTC; (3) khách cá nhân / doanh nghiệp chỉ đoán từ tên gói (Biz, Lux,
     "doanh nghiệp") vì dịch vụ không có cột riêng: gói mới có tên khác thì phải bổ sung `_la_doanh_nghiep`; (4) quét cả tỉnh gọi mỗi phường một
     lần (94 phường Đà Nẵng ~25 giây với 8 luồng, quá `HAN_QUET` thì trả phần đã quét) nên CHỈ chạy khi người dùng bấm, kết quả giữ ở trình duyệt
     (`dcc.Store` session) chứ không ở máy chủ vì Vercel có thể đổi máy giữa hai lượt; (5) ô chọn tỉnh / phường có `persistence` PHẢI có danh sách
     ngay từ lúc dựng trang, nếu để trống rồi nạp bằng callback thì Dash coi giá trị nhớ là sai và xoá mất. Không có tên khách trong dữ liệu này.
     **Giao diện tab Tra giá (làm lại 22/10/2026 theo góp ý "chán, không trực quan", rồi đơn giản hoá cùng ngày):** CHỈ lấy gói Internet (kể cả combo kèm Camera / V.VIP); Camera lẻ, FPT Play lẻ, Smart TV, Tăng tốc, Smart Home, thiết bị mạng KHÔNG lấy và không còn nhóm riêng (`_doc_goi` lọc `type == "internet"`). Gói hiện thành THẺ, bấm cả thẻ để xem chi tiết (`giafpt_the.py`, id thẻ dạng pattern-matching `gf-the`). **MỘT hàng nút tròn phẳng như trang gói cước của fpt.vn, nhóm CHIA ĐÚNG NHƯ WEBSITE** (đổi 23/10/2026, thay cách đoán theo tên gói bằng regex; `app/gia_fpt_nhom.py`, id `gf-muc`). Nguồn: cấu hình CMS nằm trong HTML của ba trang (dữ liệu Next.js, dấu nháy bị escape `\"`, thay `\"` thành `"` thì đọc được): `fpt.vn/vi` (4 tab: Internet cá nhân · Internet gia đình · Internet game thủ · Combo Internet Camera), `fpt.vn/internet/doanh-nghiep` (khối `spdv-internet-doanh-nghiep` → Internet doanh nghiệp), `fpt.vn/internet/ca-nhan` (khối `spdv-internet-truyen-hinh` → Combo Internet + V.VIP). Mã `product_code` ở đó TRÙNG `code` của `packages/list` nên ghép thẳng. Thứ tự nút do app đặt (`THU_TU_NUT`, CEO chốt 23/10/2026): Internet cá nhân, Combo Internet + V.VIP, Internet gia đình, Internet game thủ, Internet doanh nghiệp, Combo Internet Camera. **KHÔNG còn nhóm "Wifi 7" và "Gói khác"** (gói không thuộc nhóm nào trên website thì không hiện; tab Wifi 7 đã bỏ khỏi `NGUON` / `BAN_CHUP`). **Trong mỗi nhóm xếp giá THẤP -> CAO (trái -> phải)**, giá thiếu xếp cuối, bằng giá thì theo tên; đây là quy tắc chung cho mọi nhóm, đừng quay lại thứ tự `items` của website. `AN_TRONG_NHOM` ẩn riêng một gói khỏi một nhóm (hiện: SpeedX1 `goi-speedx1` khỏi "Internet cá nhân", vẫn hiện ở "Internet game thủ"). Nhóm không có gói ở phường đó thì không hiện nút; mặc định "Internet cá nhân"; nút hiện "Tên (số gói)". **Một gói được nằm ở NHIỀU nhóm nếu website đặt nó ở nhiều nhóm** (Lux800 nằm cả "Internet doanh nghiệp" lẫn "Combo Internet + V.VIP", CEO chốt hiện cả hai) nên số trên các nút KHÔNG cộng ra tổng số gói; đừng dựng lại quy tắc "mỗi gói đúng một nhóm". Gói website liệt kê mà phường đó không bán thì bỏ qua. Hệ quả so với bản cũ: **Internet Meta F1 nay chỉ ở "Internet gia đình"** (trước nằm ở game thủ). Đây không phải API chính thức nên: (a) có `BAN_CHUP` (bản chụp 23/10/2026) làm dự phòng, `_phan_tich` chỉ nhận kết quả khi ĐỦ cả 6 nhóm và mỗi nhóm có ít nhất một mã, không thì dùng NGUYÊN bản chụp (không trộn nửa thật nửa chụp); **FPT đổi cấu hình trang chủ thì cập nhật `BAN_CHUP`** (và `NGUON` nếu đổi tên tab / khối); (b) `cau_hinh()` nhớ tạm 6 giờ nhưng hàm được nhớ (`_tai_cau_hinh`) NÉM LỖI khi tải hỏng, vì `@nho` không nhớ ngoại lệ - nếu trả bản chụp ngay trong hàm đó thì bản chụp bị ghim 6 giờ chỉ vì website lỗi thoáng qua; hàm ngoài bắt lỗi rồi trả bản chụp; (c) tải hỏng thì nghỉ `NGHI_SAU_LOI` (5 phút) không gọi lại để website chặn thì khỏi tốn 5 giây x 3 trang mỗi callback; (d) khoá `threading.Lock` kiểu double-check để nhiều callback cùng lúc nguội chỉ tải MỘT lần, nút "Làm mới giá" (xoá nhớ tạm `gia_fpt`) cũng không làm tải lại website; (e) mỗi lượt callback lấy cấu hình MỘT lần rồi truyền xuống (`theo_nhom(goi, ch)`), tab Giá cả tỉnh gán nhóm một lần ở cuối `quet_tinh`, tab So giá hai phường ghi các nhóm nối bằng " · " ở cột Nhóm; (f) `cau_hinh()["nguon"] == "luu_san"` thì chữ cạnh "Giá lấy lúc" thêm "· nhóm theo danh sách lưu sẵn". Test của vùng này phải chặn mạng của `gia_fpt_nhom` (fixture autouse trong `tests/test_gia_fpt.py`), đừng để test gọi fpt.vn thật. **Phí hòa mạng luôn ghi trên thẻ và ở cửa sổ chi tiết**, KHÔNG hiện các dòng mô tả dành cho khách (modem, phủ sóng...). Chủ app (22/10/2026) bỏ hết hàng ô số (gói đang bán, rẻ nhất...), dòng gợi ý bấm thẻ, nút Copy bảng giá gửi khách (code `van_ban_bao_gia` đã xoá, đừng dựng lại; tab So giá vẫn có copy riêng) và số gói ở tiêu đề nhóm; giờ lấy giá chỉ là dòng chữ nhỏ cạnh nút Làm mới; dải điều kiện chung đổi tên "Chính sách chung". "Lux" (kể cả Lux500) là gói doanh nghiệp. Điều kiện giống hệt ở mọi gói cùng nhóm (cách thanh toán, số tháng tặng, phí hòa mạng nếu mọi gói cùng một mức ở mọi cách thanh toán, hạn chính sách...) nằm ở dải
     "Chính sách chung" dưới tiêu đề nhóm; thẻ và cửa sổ chi tiết (`giafpt_ct.py`) chỉ ghi chỗ KHÁC (`gia_fpt.phan_chung` / `khac_biet`). Dựng hai lượt: lượt một chỉ cần danh sách gói, lượt hai (`gf-pha`)
     nạp chi tiết CẢ phường song song (39 gói ~5 giây, đã nhớ tạm từng gói) để tính phần chung; chưa nạp xong thì thẻ ghi "…" và dải chung ghi "Đang nạp chính sách chung". Mọi gói là giá mỗi tháng (đơn vị "/ tháng").
     **Phí hòa mạng chính xác (đo 22/10/2026, hỏng ở đây là sale báo sai khách):** phí = `summary.fee_price` của chính sách, chính là dòng "Phí lắp đặt Internet" trong `sku_prices` (đối chiếu 700+ chính sách ở 19 phường: luôn khớp; 300.000 Sky / Giga, 500.000 Sky F1 / Meta F1, 700.000 Sky F2 / Meta F2, 399.000 SpeedX2 / X10 / Lux, 660.000 SpeedX2 Pro / X10 Pro). Phí có thể KHÁC theo cách thanh toán (gói Biz: trả theo tháng 1.000.000 hoặc 1.500.000, trả trước 6 / 13 tháng 600.000 hoặc 840.000) nên thẻ ghi từng cách (`dong_phi`, `_nhom_phi`) và dải chung chỉ ghi phí khi MỌI gói cùng một mức ở MỌI cách thanh toán. **Dịch vụ `packages/get` thỉnh thoảng trả THIẾU** (khoảng 1 trong 5 lượt, đo ở 19 phường; cùng một gói gọi lại lượt sau lại đủ): danh sách chính sách rỗng, hoặc chỉ có một chính sách "Combo Cam / Combo Thể thao" không có hình thức thanh toán, hoặc mất dòng phí lắp đặt (phí hòa mạng ra "trống" ở khoảng 15% lượt, rải đều khắp các gói và phường, không theo khu vực). Vì vậy **mất dòng phí KHÔNG có nghĩa là miễn phí** (bản cũ ghi "Miễn phí" khi không thấy số: sai); `chi_tiet_goi` gọi lại tới `LAN_THU` lần (`_lay_day_du`, chọn lượt đầy đủ nhất), hết lượt mà vẫn thiếu thì ghi "Chưa rõ" (chi tiết: "Chưa rõ, xem trên fpt.vn"), chưa có chính sách nào dùng được thì ném `LoiGia`. **"Miễn phí" CHỈ khi dịch vụ ghi rõ phí bằng 0** (chưa gặp gói nào), và chỉ cần một cách thanh toán không ghi phí là cả gói ghi "Chưa rõ". Đừng đổi `_khoang` / `_nhom_phi` thành bỏ số 0. Chưa đối chiếu được từng gói với trang đăng ký của fpt.vn vì trang chỉ hiện phí sau khi nhập họ tên và số điện thoại; đối chiếu bằng chính dữ liệu của dịch vụ mà website gọi.
     **Link sale cá nhân (https://fpt.vn/sale/duynt121) KHÔNG đổi giá hay chính sách** (so ngày 23/10/2026): link chuyển về fpt.vn/vi và đặt cookie `_ph_cid = fptvn-am` (website gửi header `client-id: fptvn-am` thay cho `fptvn`) cùng tên sale. Gọi `packages/list` và `packages/get` bằng hai client-id cho 74 gói Internet ở 2 phường: giá, mã chính sách, hình thức thanh toán, tổng tiền, phí hòa mạng, hạn chính sách GIỐNG HỆT 74/74 (chỉ khác: kênh `fptvn-am` không có vài thiết bị Smart Home / Hyper Fast, app không dùng). Nên app vẫn dùng `client-id: fptvn`; nếu sau này FPT cho kênh sale giá riêng thì đổi header ở `_goi_dich_vu` (kiểm lại bằng cách gọi hai client-id rồi so như trên). **Kiểm lại phí hòa mạng 23/10/2026:** 143 lượt (gói x phường: Hải Châu, Hội An, Tam Kỳ, xã Trà My) không có lượt nào "Chưa rõ", không có (hình thức, thời hạn) nào có hai mức phí khác nhau, dòng "Phí lắp đặt Internet" trong `sku_prices` luôn bằng `fee_price`, và phí của một gói giống nhau ở mọi phường.
   - *Nhân viên AI* (chốt 22/10/2026, chủ app là CEO): **agent theo vai trò** là các file `.claude/agents/*.md` (CHỈ còn `coder`: tự lên kế hoạch, viết code + test, sửa lỗi, xem giao diện; **chủ app bỏ hết agent khác ngày 23/10/2026**: 4 agent làm việc đơn giản chậm và đốt token, 2 agent vẫn thừa vì việc chủ yếu là sửa lỗi / thêm chức năng),
     nằm trong git (`.gitignore` mở riêng `.claude/agents/`, `.claude/settings.json` và `.claude/quy_tac_ngan.md`, phần còn lại của `.claude/` vẫn bị bỏ qua). **Phần `description` trong frontmatter PHẢI đặt trong
     dấu nháy kép**: câu có ": " (hai chấm + cách) làm YAML hỏng và agent bị bỏ qua lặng lẽ (lỗi thật lúc làm). Agent mới chỉ dùng được SAU KHI mở lại phiên Claude Code. Quy trình:
     Quy trình tuỳ độ phức tạp của việc (chốt 23/10/2026, xem mục 7): việc ĐƠN GIẢN trợ lý sửa thẳng rồi đẩy Vercel; việc lớn trợ lý tự làm hoặc giao trọn gói cho `coder`, rồi báo CEO; kiểm bằng CÔNG CỤ (ruff + pytest), không dùng AI đi test AI. Ghi / xoá dữ liệu thật (Supabase) và đổi công thức đã chốt thì vẫn phải chờ CEO đồng ý rõ ràng.
     **Hook** (`scripts/claude_hook.py`, cấu hình `.claude/settings.json`): sau khi sửa file .py báo ngay lỗi cú pháp / tên chưa định nghĩa; trước mỗi lệnh Bash chặn `git add -A` / `git add .` (chữ trong dấu nháy và
     heredoc không tính) và chặn `git commit` nếu `ruff` còn cảnh báo hoặc có test lỗi (không còn lỗi cũ nào được bỏ qua; mỗi lần commit
     mất ~90 giây vì chạy cả bộ test); ghi nhật ký hoạt động vào `data/van_phong/su_kien.jsonl` (không lên GitHub, mỗi dòng một sự kiện: giao việc, agent bắt đầu / xong, công cụ vừa dùng, lệnh của CEO; đã che mật khẩu / token /
     đường dẫn kết nối). Hook `gioi_han` chặn lần giao việc cho `coder` thứ 4 trong cùng một lệnh của CEO (lần đầu + 2 vòng sửa; lệnh mới của CEO thì đếm lại, trạng thái ở `data/van_phong/vong_coder.json`): dừng lại báo CEO thay vì để agent sửa qua sửa lại. Hook đọc stdin bằng UTF-8 (Windows mặc định cp1252 làm vỡ đường dẫn có dấu của dự án). **Chủ app KHÔNG muốn giao diện văn phòng AI nằm trong app này** (gỡ trang `/vanphong` ngày 22/10/2026, đừng
     dựng lại): đó là giao diện pixel riêng của CEO, dùng chung cho mọi dự án, đọc nhật ký trên.
   - *Bản tin 8h* (`app/ban_tin.py`, giai đoạn 1 chốt 29/10/2026: chỉ Ban Giám đốc + nhắc Admin): n8n/cron chỉ làm
     đồng hồ, gọi `POST /api/ban-tin/chay` (header `X-Ban-Tin-Khoa` = biến `BAN_TIN_KHOA`, sai/thiếu → 403) mỗi 15 phút từ 8h tới 11h
     giờ VN; app tự quyết gửi hay không. **Chốt số** = `overview.trang_thai_ngay` hết "đang cập nhật" VÀ lần nạp cuối sau 06:00 sáng HÔM SAU
     ngày số (file nạp 14:30 cùng ngày chỉ là số tạm). Trước 08:00 hoặc chưa chốt thì không gửi; quá 10:30 mà chưa chốt thì nhắc
     người nhận loại `admin` đúng một lần. Mỗi (ngày số, người nhận, loại tin) một dòng `BanTinNhatKy` có khoá duy nhất: lượt nào chèn
     được dòng là lượt được gửi (hai lượt cùng lúc không trùng), gửi lỗi thì được giành lại tối đa `TOI_DA_LAN` lần ở lượt sau, đã `ok`
     thì KHÔNG gửi lại dù file nạp lại và số đổi. Nội dung do code dựng bằng khuôn chữ cố định (không gọi AI), lấy số từ
     `bang_tong_quan` + `du_bao_thang` (hai số dự báo "3.892 (4.134)", phòng `tong_chi_nhanh.khong_cong` không xếp hạng), không có tên
     khách, tối đa 1.900 ký tự (dài thì bỏ mục chất lượng bán rồi bớt phòng). Token Zalo chỉ ở biến `ZALO_BOT_TOKEN`; `zalo_bot.LoiZalo`
     luôn là câu tiếng Việt đã làm sạch, KHÔNG chứa token / địa chỉ gọi. Người nhận quản ở Quản trị → Bản tin Zalo (chỉ admin, mọi thao tác
     ghi nhật ký). `?kho=1` = chạy thử: dựng nội dung, không gửi, không ghi nhật ký. Trưởng phòng đã thêm (xem dưới); nhân viên để giai đoạn sau.
     **Thêm người nhận bằng cách nhắn bot** (`app/ban_tin_cho_duyet.py`, 29/10/2026): Zalo gọi `POST /api/ban-tin/zalo-webhook` (header
     `X-Bot-Api-Secret-Token`; khoá = HMAC-SHA256(`APP_SECRET_KEY`, "zalo-webhook") hex nên không lưu gì thêm; sai / thiếu → 403 giống hệt,
     đúng khoá thì LUÔN 200 kể cả sự kiện lạ / lỗi để Zalo khỏi gửi lại). Chỉ nhận `message.*.received` từ chat riêng (`chat_type`
     PRIVATE) và không phải bot; người mới được ghi vào `BanTinChoDuyet` (chat_id duy nhất, tên hiển thị, lần nhắn đầu / cuối; KHÔNG lưu nội dung
     tin) và bot chào đúng một lần; chat_id đã là người nhận thì không vào chờ. Quản trị duyệt (chọn tên + loại, tạo người nhận bật) hoặc
     bỏ qua ở tab Bản tin Zalo; thẻ "Kết nối Zalo" gọi setWebhook / deleteWebhook / getWebhookInfo, cần `APP_URL` (không đoán địa chỉ). Webhook
     bật thì `getUpdates` cũ không chạy nữa (Zalo chỉ cho một trong hai).
     **Bản tin trưởng phòng** (`app/ban_tin_phong.py`, CEO chốt 29/10/2026): loại người nhận `truong_phong`; phòng do admin CHỌN TAY (không liên kết tài khoản
     app) và lưu ở bảng phụ `ban_tin_nguoi_nhan_phong` (không sửa bảng người nhận đang chạy; một người nhiều phòng; chỉ phòng `LOAI_PHONG_KD`, mã tối đa 12 ký tự;
     loại này bắt buộc có phòng, loại khác không lưu phòng, xoá người nhận xoá cả dòng phụ). Mỗi phòng có tin `tq` (tiến độ + hạng cùng cách xếp "Số online tháng" của
     Báo cáo phòng + dự báo hai số + nhận định luật cố định + nhân sự cần trao đổi + V.VIP / Camera so toàn chi nhánh + tồn từ 7 ngày) **Mục "Cần trao đổi" (CEO chốt 29/10/2026) KHÔNG giới hạn số người**: gồm người có mức cảnh báo chung (`canh_bao`) VÀ người có online luỹ kế thấp hơn cùng kỳ tháng trước (nhãn "Giảm so cùng kỳ", `ban_tin_phong.can_trao_doi`); `rules.yml` → `ban_tin.khong_trao_doi.<phòng>` loại riêng vài người khỏi danh sách này theo `acc_norm` (hiện IBB7: Gia Khánh, Trúc Duy; họ vẫn có trong bảng từng nhân sự). Danh sách dài quá để nằm chung tin 1 thì tách ra tin riêng `td1`, `td2`... (KHÔNG cắt bớt người). Tin `ns1`, `ns2`... (mỗi người một dòng,
     online luỹ kế / trong ngày / chênh so CÙNG KỲ THÁNG TRƯỚC, không dùng mục tiêu cá nhân; tên nhân sự được nêu, không có tên khách). **Trưởng phòng, người đã nghỉ và acc tạm
     KHÔNG vào bảng nhân sự và không bị cảnh báo, nhưng số của họ vẫn nằm trong số phòng** (như Báo cáo phòng). Số lấy từ `bang_tong_quan`, `du_bao_thang`, `bang_nhan_su`,
     không viết lại công thức. Mã loại ở `BanTinNhatKy.loai` (cột 20 ký tự): `tp:<phòng>:tq`, `tp:<phòng>:ns1`... cộng dòng `tp:<phòng>:ht` ghi khi đã gửi ĐỦ mọi phần
     (người nhận đã `ht` thì không dựng lại tin; gửi dở thì lượt sau chỉ gửi phần còn thiếu, theo thứ tự). Gửi trong cùng lượt, sau bản BGĐ, cùng cổng chốt số + từ 8h, ngắt sớm khi quá
     `han_giay`; một phòng dựng lỗi thì ghi lỗi rồi làm tiếp phòng khác, lỗi bên này không làm hỏng bản BGĐ. `?kho=1&phong=<mã>` trả thêm tin của phòng đó; Gửi thử của
     người nhận trưởng phòng gửi mọi tin của phòng họ (nhãn BẢN THỬ, không ghi nhật ký ngày).
   - *Ads:* chi tiêu về trễ 1 ngày → CP / PTTB chỉ tính tới ngày đa số page đã có chi tiêu (`cuoi_tu_bang`).
     Tracking ngày: tiền hiện **hai dòng trong cùng một ô** - USD đậm ở trên, VNĐ quy đổi nhỏ và nhạt kèm ₫ ở
     dưới (`_hai_dong()` + CSS `.o-hai-dong` dùng `::first-line`; chủ app chốt 24/09/2026). Chỉ có MỘT cột tiền
     "Tổng tháng", không tách "Tổng ($)" và "≈ VNĐ". Các dòng tổng để nền phẳng, KHÔNG tô màu nhiệt: tổng luôn
     vượt thang màu của các page nên màu không nói gì mà lại làm dòng VNĐ khó đọc.
     Cột của bảng này phải có `colId` kèm tên chỉ số: dash-ag-grid giữ `valueFormatter` đã biên dịch theo
     colId, đổi chỉ số mà colId không đổi thì Tin nhắn / PTTB vẫn hiện ra "$". Tiền nhập tay tổng tháng không vẽ theo ngày. Page Trung lập = tài khoản công ty, không chia cho sale.
   - *Khối DVKH* (`app/dvkh/`, chốt 21/10/2026, nguồn là file Excel "Báo cáo DVKH" gồm các sheet SR bị động, SR chủ động, rời mạng,
     công nợ, data): **SR lưu từng dòng, khoá là Mã SR**; nạp lại file luỹ kế mới hơn thì dòng cũ được thay bằng trạng thái mới
     nhất, KHÔNG cộng dồn. Rời mạng / công nợ là số đã tổng hợp trong file, lưu theo ngày chốt / ngày thu. Quy tắc đã đối chiếu
     với các sheet BC của file: **nhân sự (Account IS) = cột "Người xử lý"** (không phải "Nhân sự AU": đã thử 4 người, chỉ cột này khớp
     BC); phân công = SR có người xử lý; tồn = Chưa xử lý + Đang xử lý (SR chủ động thêm Chưa phân công); quá hạn = "Hoàn tất quá hạn" +
     "Quá hạn đang xử lý" của cột Quá hạn trong file; SR chủ động chia như bảng BC (SOS = Ngưng kết nối + Dự đoán RM + nợ cước CTBDV,
     KSRM T = "CSKH không PSLL vết T", KSRM T-1 = "vết T-", CLL = Checklist lặp); "không liên lạc được" chỉ tính trên SR đã thử liên hệ;
     tài khoản `autocall` (máy gọi) tách khỏi bảng nhân sự; bảng nhân sự SR bị động chỉ lấy người của phòng dịch vụ khách hàng (SR
     chuyển sang kỹ thuật / hỗ trợ chỉ vài SR mỗi người). **"Đồng ý" trong kết quả tư vấn phải khớp câu BẮT ĐẦU bằng "Khách hàng đồng ý"**:
     "không đồng ý" cũng chứa chữ "đồng ý" (lỗi thật khi làm: tỷ lệ giữ khách ra 81% thay vì 32%, có test chặn). Số SR trong file có thể cũ
     hơn ngày nạp (T10: SR tới 07-08/10, nạp 21/10): luôn hiện các chip "tới ngày" ở đầu trang. Cùng kỳ tháng trước chỉ hiện khi file đã
     nạp tháng đó, không có thì để "–". Hợp đồng tính "lặp" khi có từ 2 SR trở lên. Nhận định tự động (`insight.py`) do LUẬT cố định
     viết, ngưỡng nằm đầu file, mẫu dưới 30 thì bỏ qua. QNM chưa có nguồn dữ liệu (hiện chữ "chưa có nguồn"). Aggregation trên hàng nghìn
     nhóm phải dùng gộp vector hoá (`groupby().agg("size")`, `" · ".join`), không `groupby + lambda` (đo: 7,6 giây so với 0,3 giây). File thật
     nặng 15 MB nên trên Vercel (giới hạn vài MB mỗi yêu cầu) nạp bằng `python scripts/nap_dvkh.py <file> --ngay YYYY-MM-DD`; chạy app
     trên máy chủ riêng thì tải thẳng ở trang Cập nhật Excel. Đọc file theo kiểu dừng sau 200 dòng trống liên tiếp (file khai báo hơn 1 triệu dòng
     mỗi sheet SR nhưng chỉ vài nghìn dòng có chữ).
     **Nâng cấp phân tích sâu (22/10/2026, chủ app yêu cầu "chưa sâu, nhiều biểu đồ hơn, thấy được xu hướng tốt hay xấu"):**
     (1) **Ngày công nợ phải theo NGÀY TRONG THÁNG** (`so_ngay = ngay.dt.day`), không đếm theo số dòng có số: tháng 9 có số từ ngày 3, tháng 10 từ ngày 1 nên đếm theo dòng làm "ngày 14" của hai tháng
     lệch nhau 2 ngày lịch (lỗi thật: báo nhầm "thu nợ chậm hơn 3,5 điểm" trong khi cùng ngày 14 là 89,93% so với 89,76%, nhỉnh hơn; có test chặn). (2) **Bảng bổ sung** `dv_sr_bd_them` (gói Net / Pay / Cam hiện tại, đơn vị tạo SR, duyệt đề xuất,
     số lần trùng) và `dv_au_kh` (số khách mỗi CSKH phụ trách, từ bảng "Count of Acc NVVP" ở sheet BC SR bị động) nằm RIÊNG để không phải sửa bảng SR đã có trên Supabase; chỉ được tạo ở `nap.nap` (`dam_bao_bang(them=True)`), còn
     trang đọc qua `nap.co_bang()` nên chưa nạp lại file thì phần đó để trống chứ không lỗi. Thêm cột nào cho dữ liệu đã có sẵn thì làm kiểu này (bảng phụ khoá cùng Mã SR), không `ALTER TABLE` từ app. (3) **Luồng vào - ra - tồn** (`xu_huong.luong_theo_ngay`): vào = SR phát sinh / đổ về
     trong ngày, ra = SR đã rời hàng chờ (xong, tự đóng, chuyển, không thành công) theo ngày cập nhật lần cuối, tồn cuối ngày = vào luỹ kế trừ ra luỹ kế. Hướng đi (`xu_huong.huong`) = trung bình 3 ngày gần nhất so với các ngày trước đó, chênh dưới 7% là đi ngang; màu tốt / xấu theo
     chiều của chỉ số (`danh_gia_huong`: tồn tăng là xấu). **Dự báo cuối tháng** chỉ là "giữ nhịp trung bình các ngày đã có" kèm khoảng phân vị 25 - 75 và số ngày dữ liệu, dưới 14 ngày ghi "độ tin cậy thấp"; **dự báo thu nợ cuối kỳ** cho phần chưa thu giảm theo đúng hình dạng đường thu của kỳ trước đã chạy hết
     (`du_bao_cong_no`). Đổi cách dự báo thì phải thử lại trên một kỳ đã biết kết quả. (4) **Tải việc CSKH so trên số khách phụ trách** (`khai_thac.gan_so_khach`, SR trên 1.000 khách) để so công bằng; nhãn "Cần hỗ trợ / Cần nhắc / Làm tốt" theo trung vị tải và phân vị 75 / 25 của % quá hạn,
     người dưới 30 SR không gắn nhãn (`cho_nao_tot_xau`). Biểu đồ chấm KHÔNG ghi tên mọi người (bản cũ ghi hết nên rối): chỉ ghi nhóm cần hỗ trợ và làm tốt, còn lại rê chuột. (5) **Dòng chảy giữ chân khách** (Sankey, `dong_giu_chan`): thanh lý → kết quả tư vấn → hợp đồng hiện nay
     còn dùng hay đã chấm dứt (cột "Tình trạng NET hiện tại"). Số thật T10: 56% khách nói không ở lại đã chấm dứt thật, khách đang suy nghĩ chỉ 1/70 chấm dứt (còn cứu được); khách đồng ý ở lại không ai chấm dứt. (6) **Phí và miễn giảm** (`phi_mien_giam`): miễn giảm có thể vượt phí của chính loại việc đó
     (khôi phục dịch vụ 112%). **Nguồn tạo SR** (`nguon_tao_nhom`): SR do phòng Kinh doanh tạo 90% là khiếu nại, phản ánh chất lượng bán, báo khối Kinh doanh. (7) **Biểu đồ thay bảng (chủ app 22/10/2026):** cái gì thống kê và vẽ được thì vẽ (bản đồ nhiệt `ve.nhiet_bang`, cột xếp chồng `ve.xep_chong`, Sankey); chỉ DANH SÁCH chi tiết (SR tồn, hợp đồng gọi lặp, hợp đồng hai nguồn, thanh lý tồn), bảng hiệu suất từng CSKH, bảng phường của Rời mạng và bốn bảng chỉ số theo phòng ở Tổng quan (khớp bảng BC của file) mới để bảng. Tên trên biểu đồ chấm ghi bằng `ve.ghi_ten` (chú thích có đường dẫn, mỗi tên lệch một hướng) vì ghi chữ trực tiếp cạnh chấm sẽ đè lên chấm. Tiền hiện đầy đủ `2.844.588.000 đ` (`ch.vnd`), không rút gọn "triệu". Vòng tròn nhiều lớp (sunburst) đã bỏ vì chữ nhỏ khó đọc. **Tốc độ / dữ liệu đi ra của Supabase:** mỗi lần đọc bảng SR kéo ~2-3 MB nên kết quả đọc nhớ tạm `so_lieu.TTL` = 300 giây
     (gói free giới hạn 5 GB dữ liệu đi ra mỗi tháng và đã vượt); hệ quả: nạp file bằng script ở máy ngoài thì các máy chủ Vercel cần tới 5 phút mới thấy số mới. `nap.dam_bao_bang` chỉ kiểm tra bảng một lần mỗi tiến trình. Sau khi thêm tính năng đọc cột mới phải NẠP LẠI file thì phần mới mới hiện.
3. **Số hiện ra phải có ngữ cảnh**: khoảng ngày, phạm vi, so với gì. Hai số trông mâu thuẫn (VD "bán" và "online") thì ghi rõ cách hiểu ngay cạnh.
4. Định dạng kiểu Việt Nam: `1.234`, `5,40 $`, `45%`. Khi tự `.replace(",", ".")` thì **chỉ áp lên con số**, không áp lên cả câu.

---

## 5. Quyền và dữ liệu nhạy cảm

1. **Ẩn trên giao diện là chưa đủ.** Callback trả dữ liệu hạn chế phải kiểm quyền ở máy chủ: dùng `callback_can_quyen(app, "duoc_cau_hinh")`, hoặc kiểm `current_user` đầu callback rồi `raise PreventUpdate`.
2. **Hai lớp dữ liệu:**
   - *Số chung* (`phong_duoc_xem()`): theo phòng / bầy / chi nhánh.
   - *Chi tiết nhân sự* (`phong_nhan_su()`, `loc_nhan_su()`): tên, acc, số từng người.
   Dữ liệu từng người luôn đi qua lớp thứ hai.
3. **Chỉ Quản trị:** Cấu hình, file NSLĐ / danh mục nhân viên, và mọi thao tác SỬA của Ads IBB7
   (tỷ giá, page, tab Cấu hình). **Xem** Ads IBB7: Quản trị + Nhân viên KD của IBB7 (`duoc_xem_ads`): callback đọc
   dùng `callback_can_quyen(app, "duoc_xem_ads")`, callback ghi vẫn `"duoc_cau_hinh"`.
   **Bán theo tỉnh** (thẻ ở Phân tích bán hàng, `phantich_tinh.py`): Quản trị xem đủ ba cách xem; **nvkd của phòng bật ở `rules.yml` → `ban_tinh` (hiện IBB7, chủ app chốt 22/10/2026) chỉ thấy
   hai phần "Bán theo tỉnh" và "Ai bán ở tỉnh nào"** (`duoc_xem_ban_tinh`; không có gói cước theo tỉnh, không có "Một ngày", không có Excel). Số theo tỉnh và theo phòng là số chung (như Quản trị); **chi tiết nhân viên (bảng Ai bán ở tỉnh nào, danh sách nhân viên trong cửa sổ một tỉnh, cửa sổ một nhân viên)
   cũng thấy MỌI phòng như Quản trị** (chủ app chốt 22/10/2026, thay quy tắc ban đầu "chỉ phòng mình"; `_pham_vi_nv()` trả None cho người có `duoc_xem_ban_tinh`, vai trò khác vẫn theo `phong_nhan_su`). Với nvkd, mọi phần còn lại của trang `/phantich` bị ẩn VÀ callback của chúng trả rỗng / `PreventUpdate`
   (ẩn trên giao diện là chưa đủ, nếu không số vẫn đi tới trình duyệt). Thêm phần nào cho nvkd thì phải gỡ cả hai lớp đó.
4. **Nhập tồn và Báo cáo ngày là chỗ NHẬP LIỆU của đúng một phòng** (chốt 26/09/2026,
   `_phong_bat`): ngoài Quản trị (BGĐ), chỉ vào được khi phạm vi nhân sự của tài khoản nằm **TRỌN**
   trong danh sách phòng đã bật ở `config/rules.yml`. Tài khoản được mở rộng xem nhiều phòng (cấp
   trên, giám sát) tuy có IBB7 trong phạm vi nhưng không phải người vận hành phòng đó nên KHÔNG vào.
   Trước đây chỉ giao phạm vi với danh sách bật nên ai có IBB7 trong phạm vi là vào được (chủ app
   phát hiện qua tài khoản LongPH). Bật thêm phòng thì thêm mã phòng vào `rules.yml`, đừng nới quyền.
5. **Nhân viên KD** (`role = "nvkd"`, chốt 21/09/2026): tài khoản DÙNG CHUNG của một phòng, bắt buộc gán phòng.
   Chỉ vào `TRANG_NVKD` (Báo cáo ngày, Nhập tồn, Soạn email, Danh bạ, Tra cứu giá, Báo cáo phòng của phòng mình, Ads nếu là IBB7, Phân tích bán hàng nếu là IBB7 (chỉ phần Bán theo tỉnh, xem trên), Tài khoản,
   Hướng dẫn) - kiểm ở `vao_duoc()` trong router và menu; mở địa chỉ gốc thì tự sang Báo cáo ngày. Không nạp file, không xuất Excel.
   **AI (đổi 28/09/2026):** KHÔNG còn quyền AI nào. Trước đây có một đường mở riêng để bấm nút
   "Fox viết giúp" ở Báo cáo ngày (`VAI_TRO_VIET_BAO_CAO` + tham số `chi_viet`); nút đó đã bỏ nên
   đường này xoá hẳn - đừng dựng lại. Muốn cho nvkd dùng AI thì Quản trị mở thẳng theo vai trò
   hoặc theo tài khoản ở Quản trị → Trợ lý AI, và nhớ tài khoản dùng chung cả phòng nên hạn mức
   "Số câu mỗi người / ngày" là của CẢ PHÒNG.
   Ở Nhập tồn phải chọn tên mình ở bộ lọc mới sửa được, chỉ sửa ca của người đó, và "cập nhật bởi" ghi tên
   người đó (nhật ký ghi tài khoản thật). **Đổi 24/09/2026:** tài khoản sale có FULL quyền sửa ở Nhập tồn và
   Báo cáo ngày - sửa được mọi dòng, không còn phải tick tên mình trước. Ô "Nhân viên" / "Tôi là" giờ chỉ để
   lọc và để ghi "cập nhật bởi": chọn đúng một tên thì ghi tên người đó, không chọn thì ghi tên tài khoản.
   Thêm trang mới mà Nhân viên KD cần vào thì phải thêm vào `TRANG_NVKD`.
6. **Ghi nhật ký** (`ghi_log` / `AuditLog`): xuất Excel / file, nạp / gỡ file, sửa cấu hình, xoá, gọi AI.
7. **Không gửi lên AI** tên khách hàng hay dữ liệu vượt quyền của người hỏi. Tên khách hàng chỉ được LƯU cho
   phòng bật Nhập tồn (`ingest/commit.phong_luu_ten_kh`, file Internet) và chỉ HIỆN ở trang Nhập tồn
   (`phan_tich.hop_dong_ton(ten_kh=True)`). Thêm chỗ nào dùng tên khách hàng thì phải hỏi chủ app.
8. **Không in ra** chuỗi kết nối database, mật khẩu, token, API key: kể cả trong log, thông báo lỗi hay câu trả lời. Khoá OpenAI chỉ nằm ở máy chủ.

9. **Khối làm việc** (chốt 21/10/2026, `app/ui/khoi.py`): app có ba khối Kinh doanh (KD), Dịch vụ khách hàng (DVKH), Kỹ thuật (KT, chưa có
   trang). Đường dẫn quyết định khối: `/dvkh...`, `/kt...`; trang dùng chung (`/taikhoan`, `/huongdan`, `/quantri`) giữ khối đang xem
   (Store `ui-khoi`). **Quản trị (BGĐ, role `admin`) chuyển được giữa mọi khối** bằng nút chữ nằm cạnh "Thoát" ở chân menu (thẻ `details` xổ lên trên, `assets/khoi_doi.js` đóng khi bấm ra ngoài). Chủ app chê thanh ba nút ở đầu menu là thô, rồi chê bản ô lớn có biểu tượng màu là "AI quá" (21/10/2026): giữ phẳng, chỉ chữ, không gradient / thẻ kính; vai trò `dvkh` chỉ thấy khối DVKH
   (đăng nhập vào `/dvkh`, không vào được trang KD, `phong_duoc_xem()` và `phong_nhan_su()` đều rỗng); các vai trò cũ vẫn chỉ ở khối KD
   (`SessionUser.khoi_duoc_xem()`, `vao_duoc()` kiểm theo khối). Cập nhật file DVKH: `duoc_nap_dvkh` (admin + `dvkh`), callback phải dùng
   `callback_can_quyen(app, "duoc_nap_dvkh")`. Thêm khối mới = thêm mục vào `KHOI`, mảng menu, vai trò, và trang dưới `/<khối>/`.
   **Cookie đăng nhập dùng chung giữa các cổng của `localhost`**: khi mở hai bản xem thử (vd 8053 và 8054), trình duyệt gửi cùng cookie nên
   tài khoản bị lẫn; thử vai trò khác thì mở bằng `127.0.0.1` thay vì `localhost`.

---

## 6. Giao diện

- **Bảng dài** thì đặt `cao` cố định để cuộn trong khung. Bảng Ads / tỉnh dùng lớp `luoi-ke` (kẻ ô).
- **Ô bấm được để mở chi tiết:** `cellClass: "o-bam"` + dòng gợi ý `goi-y-bam`.
- **Chú thích trong bảng:** `headerTooltip` viết mỗi câu một dòng bằng `
` (CSS `.ag-tooltip` đã đặt `white-space: pre-line`). Cột khó hiểu thì thêm `ⓘ` vào `headerName` và `headerClass` kèm `co-chu-thich` (con trỏ dấu hỏi + gạch chân chấm). Bảng phải dựng bằng `bang()` của `app/ui/luoi.py`: tự dựng `dag.AgGrid` là mất `tooltipShowDelay` nên chú thích chỉ hiện sau 2 giây, người dùng tưởng không có.
- **Khối giải thích dài** dùng `chu_giai(tiêu đề, [(tên mục, nội dung)])`: gập được, mặc định đóng, mỗi mục một ô ngắn. Không viết một đoạn chữ dài.
- **Màu đánh giá** tối đa 3 mức: xanh tốt · vàng trung bình · đỏ cần xử lý. Chi tiêu (không tốt không xấu) dùng thang xanh dương.
- **dash-ag-grid:**
  - chuỗi `valueFormatter` / `styleConditions` **không dùng** `typeof`, `===`, `isNaN`;
  - `getRowId` hay ra "undefined": chọn dòng bằng `rowSelection` + `selectedRows`;
  - `cellDoubleClicked` không có dữ liệu dòng: ghép với `selectedRows`;
  - đặt `cellClass` cho cột có `type: "numericColumn"` thì **mất** lớp căn phải của kiểu cột: phải tự viết
    `"cellClass": "ag-right-aligned-cell <lớp của mình>"`;
  - `cellValueChanged` **chỉ bắn khi giá trị đổi**. Ô nhập mà để sẵn số 0 thì người dùng gõ 0 vào sẽ
    không lưu được (phải gõ 1 rồi sửa lại 0 mới ăn - chủ app báo 26/09/2026). Ô "chưa nhập" phải đưa
    `None` vào `rowData`, đừng đưa 0;
  - **bảng nhập liệu: sau khi tự mình sửa một ô thì ĐỪNG dựng lại `rowData`** (chốt 27/09/2026). Dựng lại
    là dòng nhảy chỗ khi thứ tự xếp đổi theo giá trị vừa nhập - chủ app báo "nhập ngày xong, click sang chỗ
    khác thì hàng bị nhảy". Vá đúng dòng đó bằng `rowTransaction = {"update": [...]}`, dòng sẽ đứng yên;
  - **ag-grid XOÁ SẠCH undo stack mỗi lần nhận transaction** (đo 27/09/2026: undo tụt từ 2 về 0 đúng lúc
    transaction về; `applyTransaction` gọi thẳng cũng vậy, không phải lỗi dash-ag-grid). Nên `undoRedoCellEditing`
    và việc vá dòng XUNG KHẮC tại cùng một thời điểm: phải HOÃN bản vá tới khi người dùng ngừng gõ `CHO_VA`
    giây (`_va_dong` ở `pages/nhapton.py` và `pages/baocaongay.py`). Nhịp hoãn dùng `dcc.Interval` **có
    `disabled=True` sẵn**, chỉ bật sau khi có người vừa sửa - để trống là mỗi người mở trang bắn một request
    rỗng mỗi 2 giây;
  - **gửi `dashGridOptions` từ máy chủ cũng xoá undo stack** (Dash nạp lại trọn gói tuỳ chọn), nhưng đổi
    riêng một tuỳ chọn bằng `api.setGridOption(...)` thì KHÔNG. Nên dòng TỔNG của Báo cáo ngày đi qua
    `dcc.Store` `bn-ghim` + một `clientside_callback` gọi `setGridOption("pinnedBottomRowData", ...)`,
    nhờ vậy dòng TỔNG cập nhật ngay mà Ctrl+Z vẫn sống (có test chặn). `refreshCells()` cũng an toàn.
    **`dash_ag_grid.getApi(id)` NÉM LỖI khi bảng chưa dựng xong**, không trả rỗng. Lúc mở trang, số về
    trước khi bảng kịp dựng, nên callback này phải bắt lỗi **và thử lại** (`setTimeout`, tối đa ~4 giây):
    chỉ bọc try/catch rồi bỏ qua là dòng TỔNG mất hẳn, vì số chỉ được gửi đúng một lần (lỗi thật
    28/09/2026, có test chặn);
  - **cột chỉ là cộng trừ của các cột khác thì để trình duyệt tự tính** bằng `valueGetter`, đừng chờ máy
    chủ: DK ONL và Còn phải ONL ở Báo cáo ngày đổi NGAY lúc gõ (chủ app chốt 27/09/2026). Hai lưu ý:
    (a) ô vừa gõ trả về **chuỗi**, không bọc `Number(...)` thì `"5" + 0` ra `"50"`;
    (b) cột **đang cho sửa** thì đừng gắn `valueGetter` - ag-grid sẽ đòi thêm `valueSetter`, dễ mất dữ liệu.
    Công thức JS phải khớp đúng công thức Python (`bao_cao_ngay.bang`, `tom_tat`, ảnh PNG) - có test đối chiếu;
  - ag-grid chỉ tự nhận **Ctrl+Z** và **Ctrl+Y**. Ctrl+Shift+Z (người dùng quen từ Word/Excel) do
    `assets/lam_lai_o.js` gắn thêm, chạy cho mọi bảng có bật undo - đừng gắn riêng từng trang;
  - bảng có chèn dòng tiêu đề nhóm (Nhập tồn) thì **không bật `sortable` / bộ lọc cột của ag-grid**: dòng
    tiêu đề sẽ trôi lẫn vào dữ liệu. Lọc bằng ô riêng trên thanh lọc rồi lọc ở Python.
- **Bảng liệt kê nhân sự phải bấm đúp được để xem chi tiết** (chốt 05/10/2026): bảng mới có dòng nhân sự thì
  gắn `nn.lop()` vào `className` (`from app.ui import ngan_nhan_su as nn`; `nn.lop("mot")` bấm một lần cho bảng chỉ
  để xem, `nn.lop("ten")` chỉ ô tên mở ngăn cho bảng có ô sửa được) và đặt `nn.goi_y()` gần bảng. Mỗi dòng dữ
  liệu phải có `acc_norm` (hoặc `acc`), cột tên đặt `field` là `ho_ten` hoặc `ten` để có chữ xanh + mũi tên gợi ý;
  cột chỉ có `acc` thì thêm `cellClass: "o-bam"`. Ngăn là MỘT cái dùng chung ở khung app, máy chủ tự tìm phòng của
  người đó và kiểm quyền (`phong_nhan_su()`): đừng dựng ngăn riêng từng trang. Có test chặn số bảng gắn lớp.
- **Báo "đang tải" là việc của `assets/dang_tai.js`, không phải của từng trang**: mọi lượt hỏi máy chủ đều hiện thanh
  chạy trên đầu trang, và khối sắp đổi (bảng, biểu đồ, thẻ chỉ số, cả vùng nội dung khi đổi trang) tự mờ đi kèm
  vòng xoay sau 150 ms. Bỏ qua Interval và `cellValueChanged` để bảng nhập liệu không nháy khi đang gõ. Thêm
  callback mới thì không cần bọc `dcc.Loading`; chỉ bọc khi cần chỗ trống có vòng xoay (như thân ngăn chi tiết).
- **Component Dash** là falsy (có `__len__`): kiểm bằng `is not None`, không dùng `if comp`.
- **Mọi trang phải dùng được ở màn laptop hẹp** (khoảng 800 px): lưới 2-3 cột phải tự xuống 1 cột.

---

## 7. Quy trình mỗi lần sửa

### 7.0 Chọn đường: việc đơn giản hay phức tạp (chốt 23/10/2026, chủ app muốn nhanh và tiết kiệm token mà chất lượng vẫn tốt)

**Việc ĐƠN GIẢN: trợ lý TỰ SỬA THẲNG, không gọi nhân viên AI, rồi đẩy Vercel luôn (không chờ hỏi).** Thoả TẤT CẢ:
- sửa khoảng 3 file trở xuống, chỗ sửa rõ ràng (chữ, lời giải thích, tên gọi, màu / CSS nhỏ, bố cục nhỏ, lỗi một chỗ, thêm / chỉnh test cho đúng chỗ đó);
- KHÔNG đổi công thức, cách đếm, quyền xem, cấu trúc database, đường nạp file, và KHÔNG ghi dữ liệu thật.
Cách làm: sửa → `ruff check app --select F,E9` + chỉ chạy test của vùng vừa sửa → nhìn nhanh giao diện nếu thay đổi nhìn thấy được (vùng đã đổi, một độ rộng laptop) → commit từng file (mục 7.7; hook commit đã tự chạy ruff + cả bộ test, đừng chạy tay thêm lần nữa ngay trước đó) → `git push origin main` → báo ngắn.

**Việc PHỨC TẠP vẫn do trợ lý tự làm là chính, KHÔNG còn chuỗi nhiều agent** (chủ app chốt 23/10/2026: chỉ giữ MỘT agent `coder`, tự tư duy, tự code, tự sửa lỗi như trước để nhanh; việc chủ yếu là sửa lỗi hoặc thêm chức năng). Là việc phức tạp khi có BẤT KỲ điều nào: đụng công thức / số liệu / quyền / database / nạp file; hơn ~3 file; tính năng hoặc trang mới; dựng lại giao diện; chưa rõ nguyên nhân lỗi. Cách làm:
1. Trợ lý đọc code, tự lên kế hoạch ngắn; chỗ nghiệp vụ chưa rõ thì hỏi CEO trước khi viết.
2. Làm tay hoặc giao TRỌN việc cho `coder` (một lần, brief ngắn: yêu cầu, file liên quan, thế nào là xong): coder tự viết test, code, chạy ruff + pytest vùng sửa, tự sửa lỗi, tự xem giao diện khi có thay đổi nhìn thấy. Kẹt một lỗi sau 3 lần thử khác nhau thì coder dừng báo; hook chặn lần giao việc cho coder thứ 4 trong cùng một lệnh của CEO.
3. **Kiểm bằng công cụ thật, không bằng AI:** trợ lý chạy ruff + CẢ BỘ `pytest` đúng MỘT lần (hook commit đã tự chạy cả hai, đừng chạy tay thêm ngay trước đó); đỏ thì sửa tiếp.
4. Có thay đổi nhìn thấy thì xem nhanh vùng đã đổi (1300 và 800 px).
Sau đó commit + đẩy Vercel luôn; **ngoại lệ vẫn PHẢI hỏi chủ app trước:** ghi / xoá dữ liệu thật (Supabase), và đổi công thức / quy tắc nghiệp vụ đã chốt (mục 4).

**Tiết kiệm thời gian và token:**
- Mặc định trợ lý tự làm. Chạy lệnh, đọc file, trả lời câu hỏi, sửa chữ / màu / một chỗ thì KHÔNG gọi agent; chỉ giao `coder` khi việc đủ lớn để đáng.
- Đừng chạy hai lượt `pytest` cùng lúc (chung `data/kiemthu.db` nên đỏ giả). Trước khi mở bản xem thử, tắt tiến trình xem thử cũ còn giữ cổng 8053.
- Báo cáo của coder ngắn (tối đa 10 dòng): đã đổi gì, kiểm thế nào, còn gì; không dán lại code.

1. Đọc code liên quan và quy tắc nghiệp vụ. Không chắc về số / quy tắc → hỏi chủ app **trước** khi viết.
2. Sửa ít nhất có thể, đúng chỗ theo bản đồ ở mục 1.
3. **Thêm / sửa test** cho công thức hoặc hàm dữ liệu mới (`tests/`).
4. Chạy:
   - `ruff check app --select F,E9`: không có lỗi;
   - `python -m pytest -q`: toàn bộ pass (22/10/2026: 579 test, không còn lỗi cũ); không được có test lỗi.
5. **Nhìn thật trên giao diện** (bản xem thử `xem-thu`, cổng 8051, tự đăng nhập admin): trang mở được, bảng / biểu đồ ra số, không có lỗi console hay server. Sửa code Python thì phải khởi động lại bản xem thử.
6. **Dữ liệu thật (Supabase):** chỉ đọc để đối chiếu. Mọi thao tác ghi / xoá phải được chủ app đồng ý rõ ràng, và phải sao lưu các dòng sẽ xoá trước.
7. **Commit:**
   - `git add` **từng file cụ thể**, không bao giờ `git add -A` / `git add .`;
   - không đưa lên `data/`, `*.csv`, `*.xlsx`, `*.db`, `.env`, file bí mật;
   - tác giả `git -c user.name=khanhg2003 commit`;
   - lời commit nói rõ *đổi gì, vì sao*;
   - cuối lời commit có dòng: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`;
   - đẩy lên: `git push origin main` (Vercel tự triển khai sau khoảng nửa phút; kiểm bằng `/healthz` và một lớp CSS mới ở `/assets/style.css`). Việc đơn giản và việc phức tạp đã qua tester đều đẩy luôn, xem 7.0.
8. **Báo lại cho chủ app** bằng tiếng Việt ngắn gọn: đã đổi gì, kiểm tra thế nào, còn gì chưa làm hoặc cần họ quyết.
