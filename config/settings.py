"""
Heviton REMS 모니터링 시스템 설정 (v2.0 REST API)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 기본 경로
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# 디렉토리 생성
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Heviton 사이트 설정
HEVITON_CONFIG = {
    "base_url": os.getenv("HEVITON_BASE_URL", "https://rems.heviton.com"),
    "api_root": os.getenv("HEVITON_API_ROOT", "https://rems.heviton.com:9443"),
    "api_base": os.getenv("HEVITON_API_BASE", "https://rems.heviton.com:9443/api/2.0"),
    "user_id": os.getenv("HEVITON_USER_ID", ""),
    "password": os.getenv("HEVITON_PASSWORD", ""),
    "login_type": os.getenv("HEVITON_LOGIN_TYPE", "collector"),
}

# REST API 엔드포인트
API_ENDPOINTS = {
    "login": "auth/login",
    "logout": "auth/logout",
    "token_reissue": "auth/token/reissue",
    "device_status": "collect/devices/status",
    "gen_status": "collect/gen/status",
    "plant_list": "collect/plant/list",
    "plant_info": "collect/plant/info",
    "plant_devices": "collect/plant/operation/devices",
    "plant_operation_info": "collect/plant/operation/info",
    "plant_detail_ranged": "collect/plant/detail/ranged",
    "plant_operation_status": "collect/plant/operation/status",
    "device_stat": "collect/devices/stat",
    "event_list": "collect/event/list",
    "event_today": "collect/event/today/list",
    "end_user_info": "collect/end/plantInfo",
    "user_profile": "commons/user/profile",
}

# 요청 설정
REQUEST_CONFIG = {
    "timeout": 30,
    "headers": {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
}

# 로깅 설정
LOGGING_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": LOGS_DIR / "scraper.log",
}
