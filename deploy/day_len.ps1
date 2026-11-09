# Đẩy code đã COMMIT lên máy chủ riêng và cập nhật (chạy trên máy Windows, trong thư mục dự án).
#   .\deploy\day_len.ps1 -May root@43.240.117.117 -Cong 24700 -TenMien ftel-dng.duckdns.org   (lần đầu: cài mới)
#   .\deploy\day_len.ps1 -May root@43.240.117.117 -Cong 24700                                  (các lần sau: cập nhật)
# -Cong là cổng SSH của máy chủ (mặc định 22; máy của nhà cung cấp hiện dùng 24700).
# Chỉ đưa file đang nằm trong git (không có data/, .env, file Excel).
param(
    [Parameter(Mandatory = $true)][string]$May,
    [int]$Cong = 22,
    [string]$TenMien = ""
)
$ErrorActionPreference = "Stop"
$tar = Join-Path $env:TEMP "ftel.tar.gz"
git archive --format=tar.gz -o $tar HEAD
if ($LASTEXITCODE -ne 0) { throw "Không đóng gói được code." }
scp -P $Cong $tar "${May}:/root/ftel.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "Không gửi được file lên máy chủ." }
$lenh = if ($TenMien) { "cai_dat $TenMien" } else { "cap_nhat" }
ssh -p $Cong $May "rm -rf /root/ftel_moi && mkdir -p /root/ftel_moi && tar -xzf /root/ftel.tar.gz -C /root/ftel_moi && bash /root/ftel_moi/deploy/may_chu.sh $lenh"
