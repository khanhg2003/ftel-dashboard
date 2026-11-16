#!/usr/bin/env bash
# Cài / cập nhật bản DEMO liên khối công khai, TÁCH HẲN app đang chạy thật (chạy trên máy chủ, bằng root; code đã giải nén ở /root/ftel_demo_moi).
#   thư mục /opt/ftel-demo · người dùng hệ thống ftel-demo · dịch vụ ftel-demo · cổng 8060 · database SQLite riêng · KHÔNG đọc .env của app thật
# Dùng lại thư viện Python (venv) của app thật ở chế độ chỉ đọc. Không đụng Caddy, Postgres hay dịch vụ ftel.
set -euo pipefail
GOC=/opt/ftel-demo
NGUON=/root/ftel_demo_moi
id ftel-demo >/dev/null 2>&1 || useradd --system --home "$GOC" --shell /usr/sbin/nologin ftel-demo
mkdir -p "$GOC"
rsync -a --delete --exclude data --exclude .env --exclude logs "$NGUON"/ "$GOC"/
mkdir -p "$GOC/data" "$GOC/logs"
if [ ! -f "$GOC/.env" ]; then
  printf 'APP_SECRET_KEY=%s\nTZ=UTC\n' "$(openssl rand -hex 32)" > "$GOC/.env"
fi
chown -R ftel-demo:ftel-demo "$GOC"; chmod 600 "$GOC/.env"
cat > /etc/systemd/system/ftel-demo.service <<UNIT
[Unit]
Description=FTEL Dieu hanh lien khoi - DEMO cong khai (du lieu minh hoa)
After=network.target

[Service]
User=ftel-demo
WorkingDirectory=$GOC
EnvironmentFile=$GOC/.env
ExecStart=/opt/ftel/venv/bin/python scripts/chay_demo_cong_khai.py --host 0.0.0.0 --port 8060
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable ftel-demo >/dev/null 2>&1
systemctl restart ftel-demo
ufw allow 8060/tcp >/dev/null
for i in $(seq 1 30); do curl -fs -o /dev/null http://127.0.0.1:8060/healthz && break; sleep 2; done
echo "Demo: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8060/lienkhoi) · $(systemctl is-active ftel-demo)"
