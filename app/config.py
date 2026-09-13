"""Cấu hình chung: đường dẫn, biến môi trường, nạp file YAML."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

load_dotenv(BASE_DIR / ".env")

# Chạy trên Vercel (serverless): thư mục code chỉ đọc, mỗi yêu cầu có thể rơi vào một máy
# khác nhau -> không được dựa vào file trên đĩa, chỉ /tmp là ghi được và chỉ dùng tạm.
LA_SERVERLESS = bool(os.getenv("VERCEL"))

DATA_DIR = Path("/tmp/ftel") if LA_SERVERLESS else BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Giới hạn dung lượng một lần gửi của Vercel là 4,5 MB (tính cả phần mã hoá khi tải lên),
# nên tổng dung lượng file mỗi lượt nạp giữ dưới ~3 MB.
GIOI_HAN_NAP_MB = 3.0 if LA_SERVERLESS else 50.0

def _secret_key() -> str:
    """Khoá ký phiên đăng nhập.

    Ưu tiên biến môi trường. Nếu chưa đặt thì sinh một khoá ngẫu nhiên và ghi vào
    `data/secret.key` — giữ nguyên qua các lần khởi động lại (khởi động lại không
    đá người dùng ra ngoài) mà vẫn không dùng khoá mặc định ai cũng biết.
    """
    env = os.getenv("APP_SECRET_KEY", "").strip()
    if env:
        return env
    if LA_SERVERLESS:
        raise RuntimeError("Chưa đặt APP_SECRET_KEY trong Environment Variables của Vercel. "
                           "Không đặt thì mỗi máy chủ tự sinh một khoá khác nhau và người "
                           "dùng sẽ bị đăng xuất liên tục.")
    f = DATA_DIR / "secret.key"
    if not f.exists():
        f.write_text(os.urandom(32).hex(), encoding="utf-8")
        try:                                   # chỉ chủ máy đọc được (Linux/macOS)
            f.chmod(0o600)
        except Exception:
            pass
    return f.read_text(encoding="utf-8").strip()


SECRET_KEY = _secret_key()

_db_url = os.getenv("DATABASE_URL", "").strip()
if not _db_url:
    if LA_SERVERLESS:
        raise RuntimeError("Chưa đặt DATABASE_URL (chuỗi kết nối Supabase) trong Environment "
                           "Variables của Vercel.")
    _db_url = f"sqlite:///{(DATA_DIR / 'ftel.db').as_posix()}"
# Supabase đưa chuỗi dạng postgresql://... -> chỉ rõ driver psycopg (bản 3) cho SQLAlchemy
if _db_url.startswith(("postgres://", "postgresql://")):
    _db_url = "postgresql+psycopg://" + _db_url.split("://", 1)[1]
elif _db_url.startswith("sqlite:///") and not _db_url.startswith("sqlite:////"):
    # đường dẫn tương đối -> tuyệt đối, để chạy từ thư mục nào cũng đúng
    rel = _db_url.replace("sqlite:///", "", 1)
    if not Path(rel).is_absolute():
        _db_url = f"sqlite:///{(BASE_DIR / rel).as_posix()}"
DATABASE_URL = _db_url

AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_CHAT = os.getenv("OPENAI_MODEL_CHAT", "")
OPENAI_MODEL_INSIGHT = os.getenv("OPENAI_MODEL_INSIGHT", "")


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def org_config() -> dict:
    return load_yaml("org.yml")


def columns_config() -> dict:
    return load_yaml("columns.yml")


def rules_config() -> dict:
    return load_yaml("rules.yml")
