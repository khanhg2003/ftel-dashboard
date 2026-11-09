#!/usr/bin/env bash
# Cài và cập nhật app FTEL trên máy chủ Ubuntu 24.04 riêng (thay Vercel + Supabase). Chạy bằng root.
# Thường không gõ tay: deploy/day_len.ps1 trên máy Windows đóng gói code, gửi lên rồi gọi script này.
#
#   bash may_chu.sh cai_dat <ten-mien>   cài mới lần đầu (Postgres, Caddy HTTPS, dịch vụ, sao lưu đêm)
#   bash may_chu.sh dat_bien             nhập các khoá bí mật vào /opt/ftel/.env (gõ ẩn, không hiện lên màn hình)
#   bash may_chu.sh chuyen_du_lieu       chép database từ Supabase về (hỏi chuỗi kết nối, gõ ẩn)
#   bash may_chu.sh cap_nhat             chép code mới + cài thư viện + khởi động lại
set -euo pipefail

GOC=/opt/ftel
NGUON="$(cd "$(dirname "$0")/.." && pwd)"
[ "$(id -u)" = 0 ] || { echo "Cần chạy bằng root."; exit 1; }

dong_bo_code() {
  id ftel >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin ftel
  mkdir -p "$GOC"
  # không đụng .env, data, sao lưu, nhật ký, venv: đó là phần của máy chủ, không nằm trong git
  rsync -a --delete --exclude /.env --exclude /data --exclude /backups --exclude /logs --exclude /venv "$NGUON/" "$GOC/"
  mkdir -p "$GOC/data" "$GOC/logs" "$GOC/backups"
  chown -R ftel:ftel "$GOC"
}

cai_thu_vien() {
  [ -d "$GOC/venv" ] || sudo -u ftel python3 -m venv "$GOC/venv"
  sudo -u ftel "$GOC/venv/bin/pip" install -q --upgrade pip
  sudo -u ftel "$GOC/venv/bin/pip" install -q -r "$GOC/requirements.txt"
}

doi_khoi_dong() {
  systemctl restart ftel
  for _ in $(seq 1 20); do
    sleep 2
    if curl -fs http://127.0.0.1:8050/healthz >/dev/null; then echo "App đã chạy: $(curl -s http://127.0.0.1:8050/healthz)"; return; fi
  done
  echo "App chưa trả lời. Xem lỗi: journalctl -u ftel -n 50 --no-pager"; exit 1
}

cai_dat() {
  local ten_mien="${1:-}"
  [ -n "$ten_mien" ] || { echo "Dùng: bash may_chu.sh cai_dat ten-mien.duckdns.org"; exit 1; }
  export DEBIAN_FRONTEND=noninteractive

  # Giữ múi giờ UTC như Vercel: app tính giờ Việt Nam từ UTC, đổi múi giờ máy là lệch số.
  timedatectl set-timezone UTC
  if ! swapon --show | grep -q .; then   # RAM 4 GB: thêm 2 GB đệm để nạp file lớn không bị tràn
    fallocate -l 2G /swapfile; chmod 600 /swapfile; mkswap /swapfile >/dev/null; swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi

  apt-get update -y && apt-get upgrade -y
  apt-get install -y python3-venv python3-pip rsync ufw fail2ban curl gnupg openssl postgresql-common \
    debian-keyring debian-archive-keyring apt-transport-https
  # Postgres 17 từ kho chính thức (cùng đời hoặc mới hơn Supabase, để pg_dump chép dữ liệu không bị từ chối)
  /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
  apt-get install -y postgresql-17
  # Caddy: tự xin và gia hạn chứng chỉ HTTPS
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy

  dong_bo_code

  if [ ! -f "$GOC/.env" ]; then
    local mk_db; mk_db="$(openssl rand -hex 16)"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='ftel'" | grep -q 1 \
      && sudo -u postgres psql -c "ALTER ROLE ftel PASSWORD '$mk_db'" \
      || sudo -u postgres psql -c "CREATE ROLE ftel LOGIN PASSWORD '$mk_db'"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='ftel'" | grep -q 1 \
      || sudo -u postgres createdb -O ftel ftel
    cat > "$GOC/.env" <<EOF
DATABASE_URL=postgresql://ftel:${mk_db}@127.0.0.1:5432/ftel
APP_SECRET_KEY=$(openssl rand -hex 32)
APP_URL=https://${ten_mien}
EOF
    chown ftel:ftel "$GOC/.env"; chmod 600 "$GOC/.env"
  fi
  cai_thu_vien

  cat > /etc/systemd/system/ftel.service <<EOF
[Unit]
Description=FTEL Dashboard
After=network.target postgresql.service

[Service]
User=ftel
WorkingDirectory=$GOC
EnvironmentFile=$GOC/.env
Environment=TZ=UTC
ExecStart=$GOC/venv/bin/python serve.py --host 127.0.0.1 --port 8050 --threads 8
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  cat > /etc/caddy/Caddyfile <<EOF
${ten_mien} {
    encode gzip
    reverse_proxy 127.0.0.1:8050
}
EOF
  cat > "$GOC/sao_luu.sh" <<'EOF'
#!/usr/bin/env bash
# Sao lưu database mỗi đêm, giữ 14 bản gần nhất. Bản nằm cùng máy: nên tải về máy khác định kỳ.
set -euo pipefail
cd /opt/ftel/backups
f="ftel_$(date +%Y%m%d_%H%M).sql.gz"
sudo -u postgres pg_dump ftel | gzip > "$f"
ls -1t ftel_*.sql.gz | tail -n +15 | xargs -r rm --
EOF
  chmod +x "$GOC/sao_luu.sh"
  echo '0 19 * * * root /opt/ftel/sao_luu.sh >> /opt/ftel/logs/sao_luu.log 2>&1' > /etc/cron.d/ftel-sao-luu   # 19:00 UTC = 02:00 giờ VN

  # Nhà cung cấp có thể đổi cổng SSH khỏi 22 (máy này dùng 24700): lấy cổng THẬT đang chạy, mở tường lửa đúng cổng đó, kẻo tự khoá mình ngoài.
  local cong_ssh; cong_ssh="$(sshd -T | awk '/^port /{p=$2} END{print p}')"; cong_ssh="${cong_ssh:-22}"
  ufw allow "${cong_ssh}/tcp" >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable
  printf '[sshd]\nenabled = true\nport = %s\n' "$cong_ssh" > /etc/fail2ban/jail.d/ftel-ssh.local
  systemctl enable fail2ban; systemctl restart fail2ban
  systemctl daemon-reload; systemctl enable ftel; systemctl restart caddy
  doi_khoi_dong
  echo
  echo "XONG phần cài đặt. Việc tiếp theo: dat_bien (khoá bí mật), chuyen_du_lieu (database), rồi thử https://${ten_mien}"
}

dat_bien() {
  echo "Nhập từng giá trị (gõ ẩn với khoá bí mật). Bấm Enter để bỏ qua mục không đổi."
  local -a bi_mat=(ZALO_BOT_TOKEN ZALO_GIA_TOKEN BAN_TIN_KHOA OPENAI_API_KEY)
  local -a thuong=(ADMIN_USERNAME ZALO_GIA_CHO_PHEP ZALO_GIA_TEN_BOT ZALO_GIA_TAI_KHOAN LUU_TEN_KHACH_HANG)
  local k v
  for k in "${bi_mat[@]}" "${thuong[@]}"; do
    if [[ " ${bi_mat[*]} " == *" $k "* ]]; then read -rsp "$k: " v; echo; else read -rp "$k: " v; fi
    [ -n "$v" ] || continue
    grep -v "^${k}=" "$GOC/.env" > "$GOC/.env.tam" || true
    printf '%s=%s\n' "$k" "$v" >> "$GOC/.env.tam"
    mv "$GOC/.env.tam" "$GOC/.env"
  done
  chown ftel:ftel "$GOC/.env"; chmod 600 "$GOC/.env"
  doi_khoi_dong
}

chuyen_du_lieu() {
  local url pg f=/root/supabase.url
  if [ -s "$f" ]; then         # chuỗi kết nối đặt sẵn trong file (dán bằng Notepad rồi gửi lên); đọc xong xoá ngay
    url="$(tr -d '[:space:]' < "$f")"; shred -u "$f" 2>/dev/null || rm -f "$f"
  else
    read -rsp "Chuỗi kết nối Supabase (cổng 5432, gõ ẩn): " url; echo
  fi
  [ -n "$url" ] || { echo "Chưa nhập."; exit 1; }
  pg="$(grep '^DATABASE_URL=' "$GOC/.env" | cut -d= -f2-)"
  systemctl stop ftel
  sudo -u postgres psql -d ftel -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE" -c "CREATE SCHEMA public AUTHORIZATION ftel"
  pg_dump "$url" -n public --no-owner --no-acl | psql "$pg" -q
  echo "--- Số dòng sau khi chép ---"
  psql "$pg" -tc "SELECT 'users', count(*) FROM users UNION ALL SELECT 'fact_internet', count(*) FROM fact_internet"
  doi_khoi_dong
}

case "${1:-}" in
  cai_dat) cai_dat "${2:-}" ;;
  dat_bien) dat_bien ;;
  chuyen_du_lieu) chuyen_du_lieu ;;
  cap_nhat) dong_bo_code; cai_thu_vien; doi_khoi_dong ;;
  *) echo "Dùng: bash may_chu.sh cai_dat <ten-mien> | dat_bien | chuyen_du_lieu | cap_nhat"; exit 1 ;;
esac
