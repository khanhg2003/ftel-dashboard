# Hướng dẫn làm tiếp khối Kỹ thuật (cho đồng đội)

Bản demo công khai (http://43.240.117.117:8060, đăng nhập `demo` / `123456`) chạy từ nhánh **`thi-lien-khoi`**. Bạn làm trên nhánh đó rồi push lên GitHub; **chủ dự án sẽ kéo code về và cập nhật demo** (không tự động, bạn không cần quyền gì trên máy chủ).

## 1. Lấy code và chạy thử trên máy
```bash
git clone https://github.com/khanhg2003/ftel-dashboard.git
cd ftel-dashboard
git checkout thi-lien-khoi
pip install -r requirements.txt
python scripts/xem_demo_lien_khoi.py          # mở http://127.0.0.1:8060 (tự vào quyền Quản trị, chỉ trên máy bạn)
```
Muốn có đủ số liệu mẫu của Kinh doanh và DVKH như bản trên máy chủ: `python scripts/nap_so_lieu_mau.py`.
Dữ liệu minh hoạ của khối Kỹ thuật là các file CSV `demo/lien_khoi/kt.csv` và `kt_block.csv`.

## 2. Các file của khối Kỹ thuật
| Việc | File |
|---|---|
| Hàm tính số liệu (tồn, im lặng, theo giai đoạn, chậm do ai, nhận định) | `app/kt/so_lieu.py` |
| Đọc file báo cáo Kỹ thuật, rút nhãn "đang chờ ai" từ ghi chú | `app/lien_khoi/doc_kt.py` |
| Chọn nguồn dữ liệu (minh hoạ hay thật) | `app/lien_khoi/nguon.py` |
| Các trang `/kt/...` | `app/ui/pages/kt.py` (định tuyến), `kt_tq.py`, `kt_ton.py`, `kt_phau.py`, `kt_cham.py`, `kt_tk.py`, `kt_su_co.py`, `kt_nhan_su.py`, `kt_chung.py` |
| Menu bên trái của khối Kỹ thuật | `app/ui/khoi.py` (`NAV_KT`) |
| Dữ liệu minh hoạ | `demo/lien_khoi/kt.csv`, `kt_block.csv` (dựng bằng `scripts/dung_demo_lien_khoi.py`) |
| Test | `tests/test_lien_khoi_khoi_kt.py` |

Thêm một trang mới: tạo `app/ui/pages/kt_<ten>.py` có `layout()` và `register(app)` (xem `kt_ton.py` làm mẫu), rồi thêm vào `app/ui/pages/kt.py` và `NAV_KT`. Quy tắc chung của dự án ở `AGENTS.md` (mỗi file không quá khoảng 900 dòng, tìm hàm dùng chung trước khi viết mới, tiếng Việt trong giao diện).

## 3. Quy tắc bắt buộc
- **Không đưa dữ liệu thật vào git**: không commit file Excel/CSV thật, không có tên khách hàng, số điện thoại. Có test chặn dữ liệu thật lọt vào bộ minh hoạ (`tests/test_lien_khoi_ky_thuat.py`).
- Số liệu minh hoạ phải là số bịa, mã hợp đồng dạng `MH...`.
- Trước khi push chạy: `ruff check app scripts --select F,E9` (không được có cảnh báo) và `python -m pytest tests/test_lien_khoi_khoi_kt.py tests/test_lien_khoi_ky_thuat.py -q`.
- `git add` **từng file cụ thể**, không dùng `git add -A`.
- Đừng sửa `config/` hoặc các file của khối Kinh doanh / DVKH nếu không hỏi trước.

## 4. Đẩy lên và báo chủ dự án
```bash
git pull --rebase origin thi-lien-khoi      # lấy code mới nhất của cả nhóm trước
git push origin thi-lien-khoi
```
Push xong, nhắn chủ dự án "đã push, cập nhật demo giúp". Chủ dự án kéo về, chạy kiểm tra rồi đưa lên demo (`deploy/demo_cap_nhat.ps1`), khoảng 2 phút sau mở http://43.240.117.117:8060/kt (đăng nhập `demo` / `123456`) là thấy thay đổi.

Nếu cả hai cùng sửa một file, `git pull --rebase` sẽ báo xung đột: sửa tay chỗ xung đột rồi `git add <file>` và `git rebase --continue`. Bạn nên báo trước file mình sắp sửa để tránh đụng nhau.

## 5. Việc nên làm tiếp (gợi ý)
- Thêm số liệu minh hoạ cho các ca tồn theo khu vực, kỹ thuật viên, block (sửa dựng CSV rồi chạy `python scripts/dung_demo_lien_khoi.py`).
- Thêm chỉ số mới vào `app/kt/so_lieu.py` (kèm test) rồi hiển thị ở trang tương ứng.
- Thêm nhận định tự động bằng luật (ngưỡng nằm đầu file `so_lieu.py`).
