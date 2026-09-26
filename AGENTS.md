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

---

## 4. Số liệu đúng

1. **Đổi công thức hay cách đếm nào thì phải đối chiếu số thật** (sheet, hoặc số cũ đã khớp) trước và sau khi sửa. Báo cáo Tổng đã đối chiếu khớp với sheet: đừng làm lệch.
2. **Quy tắc đã chốt** (xem thêm docstring và `config/rules.yml`):
   - *Kỳ:* luỹ kế so cùng kỳ tháng trước; khoảng tự chọn so khoảng liền trước cùng số ngày. Cùng kỳ tính tới ngày có số cuối cùng.
   - *Trưởng phòng:* **không** vào chỉ số cá nhân (xếp hạng, bảng nhân viên, cảnh báo...); số bán vẫn cộng cho phòng (`acc_truong_phong()`).
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
     ngày → phương án, mỗi ô tự lưu.
   - *Báo cáo đầu ngày* (`app/bao_cao_ngay.py`, chốt 24/09/2026, bật theo phòng ở `config/rules.yml` →
     `bao_cao_ngay`, hiện chỉ IBB7): sale nhập 7 ô (mục tiêu bán hôm nay, KHTN đang có, số bán thực
     hiện, dự kiến online
     sáng, dự kiến online chiều, đã online, ghi chú). PTTB luỹ kế tháng và số V.VIP ("Pay" trong ảnh mẫu)
     app tự lấy từ file - để không có hai nguồn số. Dự kiến tổng = sáng + chiều; còn phải online = tổng
     dự kiến - đã online. **Số V.VIP đếm THẲNG từ file FPT Play** (`_vvip_theo_acc`: mỗi dòng `la_vvip`
     là một V.VIP, theo ngày online của chính gói đó) đúng như Báo cáo Tổng / Báo cáo phòng; đừng đếm
     gián tiếp qua cờ `co_vvip` của hợp đồng Internet - gói V.VIP online khác ngày hoặc bán thêm trên
     hợp đồng tháng trước sẽ làm lệch (đã đo 24/09: 201 thay vì 199, 4 người sai). Người chỉ bán V.VIP
     cũng phải có dòng, nếu không dòng TỔNG thiếu. **"Đã online" sale gõ tay được** (chốt 25/09/2026,
     cột `da_online`, để trống = chưa đếm tay): file Internet chỉ về vào hôm sau nên buổi sáng số từ
     file luôn 0, không gõ được thì "còn phải online" vô nghĩa. Hiển thị = số LỚN HƠN giữa số gõ tay
     và số từ file, vì file chỉ có thể chậm chứ không đếm dư. **Cột "Thực hiện"** (thêm 26/09/2026, cột `da_ban`,
     hiện ngay sau KHTN) là số bán sale **TỰ NHẬP**, KHÔNG lấy gì từ file và KHÔNG đối chiếu
     `ngay_tao_hd` - chủ app chốt đây là ô khai báo của sale, để so thẳng với ô "MT ngày" của chính
     họ. Ảnh PNG vẫn giữ đúng 8 cột cũ, không thêm cột này vào ảnh. Bảng chia **ba khối cột** (chủ app chốt 26/09/2026, `_dau_khoi` + lớp `khoi-dau` /
     `nhom-khoi`): *Báo cáo số bán* (MT ngày · KHTN · Thực hiện) · *Dự kiến online* (DK ONL · ONL sáng ·
     ONL chiều · Đã online · Còn phải ONL) · *Số Net / Pay* (PTTB tháng · MT tháng · V.VIP); DK ONL
     đứng TRƯỚC ONL sáng. Mục tiêu tháng TỪNG NGƯỜI nhập ngay trong bảng
     này, lưu vào `target_monthly` với `doi_tuong = "NHAN_VIEN"` (mọi truy vấn khác đều lọc `= 'PHONG'` nên
     không đụng nhau); mục tiêu PTTB/ngày của phòng dùng chung ô `chi_tieu = "ngay"` đã có. Ô để TRỐNG nghĩa
     là người đó chưa báo cáo, khác hẳn với số 0 đã nhập - đừng hiển thị 0 cho người chưa nhập (có test). **Mở được báo cáo của ngày CHƯA TỚI** (chốt 26/09/2026, `TRUOC_TOI_DA` = 7 ngày,
     `ngay_xa_nhat()`): sale hay điền trước cho hôm sau. Ngày tương lai vẫn hiện các cột app tự lấy từ
     file nhưng đó là số của hôm nay, nên tiêu đề phải có nhãn "Nhập trước" và một dòng nói rõ - bỏ đi
     là người đọc tưởng số đã có thật.
     Ảnh PNG ở `app/export_png_ngay.py`, ba khối chữ do Fox viết (`bao_cao_ngay_ai.py`) và Trưởng phòng sửa
     lại trước khi tạo ảnh. Dòng TỔNG trong ảnh lấy mục tiêu tháng CỦA PHÒNG, không cộng mục tiêu từng người.
     Ảnh phải giữ đúng mẫu chủ app đưa (nền xanh chuyển màu + vệt chéo + góc cam + tia sét, ba khối số có
     biểu tượng tròn, dòng TỔNG nền cam, ba khối chữ, dải nguồn cuối ảnh) và đúng 8 cột: Nhân sự · MT ngày ·
     KHTN · ONL sáng · ONL chiều · DK ONL · PTTB tháng · Pay (Pay = số V.VIP). Font đi kèm app không có bản
     nghiêng nên chữ nghiêng làm bằng `_nghieng()` (kéo xiên), đừng thêm file font mới. Cỡ chữ trong ảnh
     phải ĐỌC ĐƯỢC TRÊN ĐIỆN THOẠI: đừng giảm xuống dưới mức hiện tại (dòng số 19, bảng 17, ba khối chữ
     16,5 ở tỷ lệ vẽ 1). Nút gọi AI hoặc vẽ ảnh phải có `running=` khoá nút + đổi chữ trong lúc chạy,
     nếu không người dùng bấm lại nhiều lần - mỗi lần là một lượt gọi AI tốn tiền.
   - *Ads:* chi tiêu về trễ 1 ngày → CP / PTTB chỉ tính tới ngày đa số page đã có chi tiêu (`cuoi_tu_bang`).
     Tracking ngày: tiền hiện **hai dòng trong cùng một ô** - USD đậm ở trên, VNĐ quy đổi nhỏ và nhạt kèm ₫ ở
     dưới (`_hai_dong()` + CSS `.o-hai-dong` dùng `::first-line`; chủ app chốt 24/09/2026). Chỉ có MỘT cột tiền
     "Tổng tháng", không tách "Tổng ($)" và "≈ VNĐ". Các dòng tổng để nền phẳng, KHÔNG tô màu nhiệt: tổng luôn
     vượt thang màu của các page nên màu không nói gì mà lại làm dòng VNĐ khó đọc.
     Cột của bảng này phải có `colId` kèm tên chỉ số: dash-ag-grid giữ `valueFormatter` đã biên dịch theo
     colId, đổi chỉ số mà colId không đổi thì Tin nhắn / PTTB vẫn hiện ra "$". Tiền nhập tay tổng tháng không vẽ theo ngày. Page Trung lập = tài khoản công ty, không chia cho sale.
3. **Số hiện ra phải có ngữ cảnh**: khoảng ngày, phạm vi, so với gì. Hai số trông mâu thuẫn (VD "bán" và "online") thì ghi rõ cách hiểu ngay cạnh.
4. Định dạng kiểu Việt Nam: `1.234`, `5,40 $`, `45%`. Khi tự `.replace(",", ".")` thì **chỉ áp lên con số**, không áp lên cả câu.

---

## 5. Quyền và dữ liệu nhạy cảm

1. **Ẩn trên giao diện là chưa đủ.** Callback trả dữ liệu hạn chế phải kiểm quyền ở máy chủ: dùng `callback_can_quyen(app, "duoc_cau_hinh")`, hoặc kiểm `current_user` đầu callback rồi `raise PreventUpdate`.
2. **Hai lớp dữ liệu:**
   - *Số chung* (`phong_duoc_xem()`): theo phòng / bầy / chi nhánh.
   - *Chi tiết nhân sự* (`phong_nhan_su()`, `loc_nhan_su()`): tên, acc, số từng người.
   Dữ liệu từng người luôn đi qua lớp thứ hai.
3. **Chỉ Quản trị:** Bán theo tỉnh, Cấu hình, file NSLĐ / danh mục nhân viên, và mọi thao tác SỬA của Ads IBB7
   (tỷ giá, page, tab Cấu hình). **Xem** Ads IBB7: Quản trị + Nhân viên KD của IBB7 (`duoc_xem_ads`): callback đọc
   dùng `callback_can_quyen(app, "duoc_xem_ads")`, callback ghi vẫn `"duoc_cau_hinh"`.
4. **Nhân viên KD** (`role = "nvkd"`, chốt 21/09/2026): tài khoản DÙNG CHUNG của một phòng, bắt buộc gán phòng.
   Chỉ vào `TRANG_NVKD` (Báo cáo ngày, Nhập tồn, Báo cáo phòng của phòng mình, Ads nếu là IBB7, Tài khoản,
   Hướng dẫn) - kiểm ở `vao_duoc()` trong router và menu; mở địa chỉ gốc thì tự sang Báo cáo ngày. Không nạp file, không xuất Excel.
   **AI (đổi 25/09/2026):** bấm được đúng nút "Fox viết giúp" ở Báo cáo ngày (`tro_ly.VAI_TRO_VIET_BAO_CAO`
   + tham số `chi_viet=True` của `duoc_dung` / `kiem_tra` / `tao_nhan_xet`), KHÔNG có khung chat Hỏi Fox và
   không bấm được nút nhận xét ở trang khác. Tài khoản dùng chung nên hạn mức "Số câu mỗi người / ngày" là
   của CẢ PHÒNG - Quản trị nâng ô đó lên cho đủ. Thêm nơi gọi AI cho nvkd thì phải truyền `chi_viet=True`,
   đừng nới `ch["vai_tro"]` (nới là mở luôn cả chat).
   Ở Nhập tồn phải chọn tên mình ở bộ lọc mới sửa được, chỉ sửa ca của người đó, và "cập nhật bởi" ghi tên
   người đó (nhật ký ghi tài khoản thật). **Đổi 24/09/2026:** tài khoản sale có FULL quyền sửa ở Nhập tồn và
   Báo cáo ngày - sửa được mọi dòng, không còn phải tick tên mình trước. Ô "Nhân viên" / "Tôi là" giờ chỉ để
   lọc và để ghi "cập nhật bởi": chọn đúng một tên thì ghi tên người đó, không chọn thì ghi tên tài khoản.
   Thêm trang mới mà Nhân viên KD cần vào thì phải thêm vào `TRANG_NVKD`.
5. **Ghi nhật ký** (`ghi_log` / `AuditLog`): xuất Excel / file, nạp / gỡ file, sửa cấu hình, xoá, gọi AI.
6. **Không gửi lên AI** tên khách hàng hay dữ liệu vượt quyền của người hỏi. Tên khách hàng chỉ được LƯU cho
   phòng bật Nhập tồn (`ingest/commit.phong_luu_ten_kh`, file Internet) và chỉ HIỆN ở trang Nhập tồn
   (`phan_tich.hop_dong_ton(ten_kh=True)`). Thêm chỗ nào dùng tên khách hàng thì phải hỏi chủ app.
7. **Không in ra** chuỗi kết nối database, mật khẩu, token, API key: kể cả trong log, thông báo lỗi hay câu trả lời. Khoá OpenAI chỉ nằm ở máy chủ.

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
    `None` vào `rowData`, đừng đưa 0.
- **Component Dash** là falsy (có `__len__`): kiểm bằng `is not None`, không dùng `if comp`.
- **Mọi trang phải dùng được ở màn laptop hẹp** (khoảng 800 px): lưới 2-3 cột phải tự xuống 1 cột.

---

## 7. Quy trình mỗi lần sửa

1. Đọc code liên quan và quy tắc nghiệp vụ. Không chắc về số / quy tắc → hỏi chủ app **trước** khi viết.
2. Sửa ít nhất có thể, đúng chỗ theo bản đồ ở mục 1.
3. **Thêm / sửa test** cho công thức hoặc hàm dữ liệu mới (`tests/`).
4. Chạy:
   - `ruff check app --select F,E9`: không có lỗi;
   - `python -m pytest -q`: toàn bộ pass. Hiện có 3 lỗi cũ ở `tests/test_he_thong_hoa.py`, không liên quan; không được có lỗi mới.
5. **Nhìn thật trên giao diện** (bản xem thử `xem-thu`, cổng 8051, tự đăng nhập admin): trang mở được, bảng / biểu đồ ra số, không có lỗi console hay server. Sửa code Python thì phải khởi động lại bản xem thử.
6. **Dữ liệu thật (Supabase):** chỉ đọc để đối chiếu. Mọi thao tác ghi / xoá phải được chủ app đồng ý rõ ràng, và phải sao lưu các dòng sẽ xoá trước.
7. **Commit:**
   - `git add` **từng file cụ thể**, không bao giờ `git add -A` / `git add .`;
   - không đưa lên `data/`, `*.csv`, `*.xlsx`, `*.db`, `.env`, file bí mật;
   - tác giả `git -c user.name=khanhg2003 commit`;
   - lời commit nói rõ *đổi gì, vì sao*;
   - cuối lời commit có dòng: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
8. **Báo lại cho chủ app** bằng tiếng Việt ngắn gọn: đã đổi gì, kiểm tra thế nào, còn gì chưa làm hoặc cần họ quyết.
