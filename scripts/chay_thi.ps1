# Chạy BẢN THI trên máy (không đụng bản đang chạy ở chi nhánh): database riêng data/thi.db, cổng 8060.
#   .\scripts\chay_thi.ps1            -> http://127.0.0.1:8060
# data/thi.db là bản sao của data/ftel.db trên máy (không phải database máy chủ). Muốn làm lại từ đầu: xoá thi.db rồi chép lại.
#   .\scripts\chay_thi.ps1 -Demo      -> http://127.0.0.1:8060/lienkhoi, dùng BỘ DỮ LIỆU MINH HOẠ (demo/lien_khoi), database riêng rỗng, tự đăng nhập Quản trị
param([switch]$Demo)
$goc = Split-Path -Parent $PSScriptRoot
if ($Demo) { Set-Location $goc; python scripts/xem_demo_lien_khoi.py 8060; exit }
Set-Location $goc
if (-not (Test-Path "data/thi.db")) { Copy-Item "data/ftel.db" "data/thi.db" }
$env:DATABASE_URL = "sqlite:///" + ((Join-Path $goc "data/thi.db") -replace "\\", "/")
python -c "from app.db import init_db; from app.ui.app import app; init_db(); print('Ban thi: http://127.0.0.1:8060'); app.run(host='127.0.0.1', port=8060, debug=False)"
