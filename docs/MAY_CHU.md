# Chạy app trên máy chủ riêng (thay Vercel + Supabase)

Máy: Cloud Server Linux 4 (2 Core, 4 GB, 60 GB), Ubuntu 24.04. Mọi thứ nằm trong `deploy/`:
`may_chu.sh` (chạy trên máy chủ), `day_len.ps1` (chạy trên máy Windows).

## Cài lần đầu (máy Windows, thư mục dự án; code phải đã commit)
1. Tên miền (DuckDNS miễn phí hoặc tên phụ của tên miền sẵn có) trỏ về IP máy chủ. Phải trỏ xong TRƯỚC bước 2, nếu không Caddy không xin được HTTPS.
2. `.\deploy\day_len.ps1 -May root@<IP> -TenMien <ten-mien>` (cài Postgres 17, Caddy, dịch vụ `ftel`, sao lưu đêm, tường lửa).
3. `ssh -t root@<IP> "bash /opt/ftel/deploy/may_chu.sh dat_bien"` nhập khoá bí mật (gõ ẩn).
4. Chọn giờ ít người dùng, rồi `ssh -t root@<IP> "bash /opt/ftel/deploy/may_chu.sh chuyen_du_lieu"` chép database từ Supabase. Từ lúc chép, dữ liệu mới nhập trên Vercel KHÔNG sang máy mới: ngừng nhập liệu ở Vercel trước khi chép.
5. Mở `https://<ten-mien>/healthz` và đăng nhập thử. Đặt lại webhook Zalo (`python scripts/zalo_gia_webhook.py dat` và Quản trị → Bản tin Zalo → Kết nối) với `APP_URL` mới, đổi địa chỉ trong n8n.
6. Chạy song song với Vercel khoảng 1 tuần rồi mới tắt Vercel và Supabase.

## Cập nhật sau này
`git push origin main` rồi `.\deploy\day_len.ps1 -May root@<IP>` (đóng gói bản commit mới nhất, chép lên, cài thư viện, khởi động lại). Vercel không còn tự cập nhật.

## Việc thường gặp (trên máy chủ)
- Xem lỗi: `journalctl -u ftel -n 100 --no-pager`; khởi động lại: `systemctl restart ftel`.
- Sao lưu: `/opt/ftel/backups` (mỗi đêm 02:00 giờ VN, giữ 14 bản, cùng máy nên phải tải về máy khác định kỳ). Chạy tay: `/opt/ftel/sao_luu.sh`.
- Máy chủ để múi giờ UTC (như Vercel): đừng đổi, app tính giờ Việt Nam từ UTC.
- Nạp file trực tiếp ở trang Nạp dữ liệu được (giới hạn 50 MB, không còn giới hạn 3 MB và 60 giây của Vercel).
