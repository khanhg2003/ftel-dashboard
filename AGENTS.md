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
| Danh bạ liên hệ (đọc hai file PNC / TIN, gộp trùng, tra cứu, người sale tự thêm) | `app/danh_ba.py` + `app/ui/pages/danhba.py` |
| Soạn email (khuôn 3 loại mail, gợi ý người nhận, Fox viết đoạn tình huống) + nút copy dùng chung | `app/soan_mail.py` + `app/ui/pages/soanmail.py` + `assets/sao_chep.js` |
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
     cũng phải có dòng, nếu không dòng TỔNG thiếu. **"Đã online" là ô sale TỰ GÕ như một ô Google Sheet, KHÔNG liên quan tới file Internet**
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
     bỏ `max(..., 0)` cho cùng một số. **Báo cáo của ngày ĐÃ QUA bị xoá** (`don_ngay_cu()`, gọi từ `layout()` chứ
     KHÔNG gọi trong `dam_bao_bang()` - gọi ở đó thì database kiểm thử tháng 9 bị dọn mất khi chạy
     test); chỉ giữ hôm nay và các ngày nhập trước. **Trang tự nạp lại** mỗi `NHIP_MS` (60 giây; 15 giây
     làm Vercel Hobby cạn 4 giờ CPU, thực tế 9 giờ trong một chu kỳ - 09/10/2026) và `assets/nhip_an.js` TẮT nhịp
     khi tab ẩn, bật lại + nạp ngay khi quay về. Chỉ dựng lại bảng khi `moc_cap_nhat()` đổi, để không cắt ngang ô
     người khác đang gõ. Thêm nhịp tự hỏi máy chủ ở trang khác thì phải tính CPU: mỗi lượt là một lần gọi hàm.
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
     `duoc_soan_mail`, phòng bật ở `config/rules.yml` → `soan_mail`; trưởng phòng KHÔNG dùng): sale chọn một trong 3 loại mail
     mẫu (ca hot triển khai · xin xuất hoá đơn DN · xin đầu tư hạ tầng), điền các ô thay đổi, KHUÔN (`LOAI[...]["than"]`) tự
     điền phần cố định, xem trước rồi **Copy dán vào Outlook** - app KHÔNG gửi mail, KHÔNG mở Outlook (mailto bị giới hạn độ
     dài, mất chữ đậm), KHÔNG lưu nội dung mail và KHÔNG xử lý ảnh CCCD (sale tự đính kèm; có dòng nhắc). Chỉ ghi nhật ký
     `soan_mail` (loại + mã HĐ) và `soan_mail_fox`. **Người nhận chỉ GỢI Ý, sale tự chọn Đến / CC** (chủ app chốt):
     đừng tự điền người nhận. Quy tắc gợi ý ở `LOAI[...]["goi_y"]` theo nhóm chức danh (`danh_ba.nhom_chuc`) và chi nhánh
     nơi lắp (ô chọn, hoặc đoán từ địa chỉ, hoặc chi nhánh của sale): ca hot → đội trưởng phụ trách khu vực trong địa chỉ
     (cột ghi chú là chữ tự do "Block Sơn Trà" nên khớp cụm với địa chỉ, không có bảng phân vùng) + TP kỹ thuật; hoá đơn →
     PGĐ nơi lắp, CC giám đốc nơi lắp + giám đốc Đà Nẵng; hạ tầng → TP hạ tầng, CC giám đốc. Chi nhánh có trong cả hai
     file thì chỉ gợi ý người của bản MỚI (PNC T10) vì TIN (T8) có thể đã cũ (giám đốc Đà Nẵng lệch giữa hai file).
     **Fox chỉ viết MỘT đoạn "tình huống" từ ý chính của sale**; địa chỉ, SĐT, MST, tên khách KHÔNG gửi AI (số dài ≥ 6 chữ
     số và email bị che trong `_che`), có trần `TOI_DA_NGAY` lượt/ngày, nút `running=` khoá khi đang chạy, có "Hoàn tác".
     **Giao diện (chốt 10/10/2026):** bên trái chọn loại (ba thẻ, bấm là đổi ngay trên trình duyệt) + điền ô + ô "Thêm ý riêng" (đoạn `{?y_them}` nằm
     trước câu cảm ơn); bên phải là MỘT lá thư kiểu Outlook: Đến / CC, gợi ý, tiêu đề, nội dung. **Tiêu đề và nội dung sửa được trực tiếp**
     (chủ app hỏi "muốn thêm ý ngoài khuôn thì sao"): máy chủ chỉ gửi `kq` vào `dcc.Store` `sm-kq`, `assets/soan_mail.js` tự vẽ vào `#sm-tieu`
     / `#sm-than` (hai khối này KHÔNG có con do Dash dựng, nếu dựng bằng Dash thì chữ sale gõ sẽ bị xoá hoặc lệch khi Dash cập nhật). Phần sale đã sửa tay được GIỮ khi đổi ô
     bên trái (hiện thanh vàng + nút "Dựng lại từ các ô"); nút Copy đọc thẳng chữ đang hiện nên luôn là bản đã sửa. Dán vào thư luôn là chữ trơn. **Đưa sang Outlook (chủ app dùng Outlook WEB, 10/10/2026):** nút "Mở thư trong Outlook" mở thư mới trên Outlook web (`outlook.office.com/mail/deeplink/compose?mailtouri=<mailto>`; KHÔNG dùng riêng `to=` / `cc=` vì Outlook web bỏ qua CC, chủ app báo 10/10/2026) đã điền sẵn Đến / CC / tiêu đề / NỘI DUNG CHỮ TRƠN (chủ app muốn mở ra là đủ, không phải dán; mất chữ đậm), đồng thời copy bản có chữ đậm vào clipboard để ai cần thì Ctrl+V. Link dài quá `LINK_TOI_DA` thì bỏ nội dung khỏi link (còn clipboard). Đã thử `mailto:` và file `.eml`: không dùng được vì máy không đặt Outlook làm chương trình mail mặc định, và chủ app chỉ muốn MỘT nút tiện nhất nên đừng thêm lại. Code ở `assets/sao_chep.js` (có test Node). Đừng đưa lại
     ô "Lời chào": lời chào tự theo người nhận và sửa thẳng trong thư. Thêm loại mail mới = thêm một mục vào `LOAI` (có test chặn ô trong khuôn không có nguồn). Danh bạ: file PNC (Đà
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
4. **Nhập tồn và Báo cáo ngày là chỗ NHẬP LIỆU của đúng một phòng** (chốt 26/09/2026,
   `_phong_bat`): ngoài Quản trị (BGĐ), chỉ vào được khi phạm vi nhân sự của tài khoản nằm **TRỌN**
   trong danh sách phòng đã bật ở `config/rules.yml`. Tài khoản được mở rộng xem nhiều phòng (cấp
   trên, giám sát) tuy có IBB7 trong phạm vi nhưng không phải người vận hành phòng đó nên KHÔNG vào.
   Trước đây chỉ giao phạm vi với danh sách bật nên ai có IBB7 trong phạm vi là vào được (chủ app
   phát hiện qua tài khoản LongPH). Bật thêm phòng thì thêm mã phòng vào `rules.yml`, đừng nới quyền.
5. **Nhân viên KD** (`role = "nvkd"`, chốt 21/09/2026): tài khoản DÙNG CHUNG của một phòng, bắt buộc gán phòng.
   Chỉ vào `TRANG_NVKD` (Báo cáo ngày, Nhập tồn, Soạn email, Danh bạ, Báo cáo phòng của phòng mình, Ads nếu là IBB7, Tài khoản,
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
