# Cập nhật bản DEMO liên khối công khai (http://43.240.117.117:8060) từ code đã COMMIT ở nhánh thi-lien-khoi (chạy trên máy Windows của chủ dự án).
#   git pull origin thi-lien-khoi
#   .\deploy\demo_cap_nhat.ps1 -May root@43.240.117.117 -Cong 24700 -Khoa "$env:USERPROFILE\.ssh\ftel_may_chu"
# Không đụng app thật (deploy\day_len.ps1 + nhánh main). Dữ liệu, mật khẩu và token của demo trên máy chủ được giữ nguyên.
param(
    [Parameter(Mandatory = $true)][string]$May,
    [int]$Cong = 22,
    [string]$Khoa = ""
)
$ErrorActionPreference = "Stop"
$nhanh = (git rev-parse --abbrev-ref HEAD).Trim()
if ($nhanh -ne "thi-lien-khoi") { throw "Đang ở nhánh '$nhanh'. Bản demo chỉ cập nhật từ nhánh thi-lien-khoi." }
if (git status --porcelain --untracked-files=no) { throw "Còn thay đổi chưa commit. Commit (hoặc bỏ) trước khi cập nhật demo." }
$tuyChon = @("-o", "StrictHostKeyChecking=accept-new")
if ($Khoa) { $tuyChon += @("-i", $Khoa) }
$tar = Join-Path $env:TEMP "ftel_demo.tar.gz"
git archive --format=tar.gz -o $tar HEAD
if ($LASTEXITCODE -ne 0) { throw "Không đóng gói được code." }
scp @tuyChon -P $Cong $tar "${May}:/root/ftel_demo.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "Không gửi được file lên máy chủ." }
ssh @tuyChon -p $Cong $May "rm -rf /root/ftel_demo_moi && mkdir -p /root/ftel_demo_moi && tar -xzf /root/ftel_demo.tar.gz -C /root/ftel_demo_moi && sed -i 's/\r$//' /root/ftel_demo_moi/deploy/demo_cong_khai.sh && bash /root/ftel_demo_moi/deploy/demo_cong_khai.sh"
Write-Host "Đã cập nhật demo. Kiểm tra: http://43.240.117.117:8060/healthz"
