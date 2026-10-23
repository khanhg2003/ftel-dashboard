# Quy tắc ngắn cho nhân viên AI (đọc file này, KHÔNG đọc cả AGENTS.md)

AGENTS.md rất dài (hàng chục nghìn token). Chỉ mở đúng đoạn cần bằng `Grep` tên module / chức năng trong AGENTS.md (mục 4 chứa quy tắc nghiệp vụ từng chức năng).

## Đặt code đúng chỗ
- Số liệu / công thức không có giao diện: `app/*.py`. Trang: `app/ui/pages/<trang>.py` (có `layout()` + `register(app)`). CSS: thêm cuối `assets/style.css`.
- Thành phần dùng chung: `app/ui/components.py` (`tip`, `card`, `kpi`, `field`, `modal`, `cua_so`, `alert`, `callback_can_quyen`...), bảng: `app/ui/luoi.py` (`bang`, `SO`, `PCT`...). Tìm bằng grep trước khi viết mới; có rồi thì dùng lại.
- File không quá ~900 dòng, hàm không quá ~80 dòng. Xoá thẳng code chết, không comment-out.
- Tên: tiếng Việt không dấu, chữ thường, gạch dưới. Id Dash có tiền tố trang (`gf-`, `pt-`...). Id Dash KHÔNG chứa chữ có dấu.
- Không thêm thư viện mới. Docstring ngắn nói VÌ SAO, không kể lại code.

## Số liệu, quyền, tốc độ
- Đổi công thức / cách đếm = hỏi CEO trước. Chữ cho người dùng: tiếng Việt dễ hiểu, dùng "online", KHÔNG viết "đấu nối".
- Quyền xem dữ liệu kiểm ở MÁY CHỦ (callback), không chỉ ẩn trên giao diện: `callback_can_quyen(app, "...")` hoặc kiểm `current_user` rồi `PreventUpdate`.
- `layout()` phải nhẹ. Callback tab ẩn thì `PreventUpdate`. Không hỏi database trong vòng lặp. Hàm đọc database nhiều nơi gọi thì gắn `@nho`.
- KHÔNG ghi / xoá dữ liệu thật (Supabase), KHÔNG in chuỗi kết nối / mật khẩu / token.

## Giao diện
- Phẳng: chữ + viền mảnh, không gradient / thẻ kính / biểu tượng nhiều màu. Màu đánh giá tối đa 3 mức (xanh / vàng / đỏ).
- Dùng được ở màn laptop hẹp ~800 px. Bảng dài thì đặt chiều cao cố định.

## Cách làm (TDD, tiết kiệm)
1. Đọc đúng file nhiệm vụ được giao + đúng file code cần sửa. Không đọc lan man.
2. Viết / sửa test TRƯỚC cho phần dữ liệu (tests/, dữ liệu giả nhỏ, không gọi mạng thật, không ghi database thật), rồi mới sửa code.
3. Kiểm bằng CÔNG CỤ, không bằng đọc đoán: `ruff check app --select F,E9` rồi `python -m pytest -q <file test của vùng sửa>`. Cả bộ `pytest` để người điều phối chạy một lần ở cuối (không chạy hai pytest cùng lúc: chung `data/kiemthu.db`).
4. Tối đa 2 vòng sửa-chạy lại. Vòng thứ 3 vẫn lỗi thì DỪNG, báo nguyên văn log lỗi cuối + nghi ngờ nguyên nhân cho người điều phối. Không tự cãi đi cãi lại.
5. KHÔNG commit, KHÔNG push. Báo cáo ngắn: đã đổi file nào, kết quả ruff / pytest, còn gì dang dở. Không dán lại code.
