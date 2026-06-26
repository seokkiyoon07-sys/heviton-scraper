"""
Heviton REMS 모니터링 시스템 설정 (v2.0 REST API)
"""
import os
import json
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


def _load_json_env(name: str, default: dict) -> dict:
    """JSON 환경변수 로드 (파싱 실패 시 기본값)"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return default


# 요금/절감액 추정 설정
SAVINGS_CONFIG = {
    "enabled": os.getenv("TOU_SAVINGS_ENABLED", "true").lower() == "true",
    "currency": os.getenv("TOU_CURRENCY", "원"),
    "tariff_name": os.getenv("TOU_TARIFF_NAME", "일반용전력(갑) II / 고압A / 선택II"),
    "contract_power_kw": float(os.getenv("TOU_CONTRACT_POWER_KW", "250")),
    "basic_charge_per_kw": float(os.getenv("TOU_BASIC_CHARGE_PER_KW", "8230")),
    # 계절별 시간대별 단가(원/kWh) - 일반용전력(갑) II, 고압A, 선택II
    "tou_rates": _load_json_env(
        "TOU_RATES_JSON",
        {
            "summer": {"off_peak": 84.1, "mid_peak": 135.3, "on_peak": 157.8},
            "winter": {"off_peak": 92.8, "mid_peak": 123.2, "on_peak": 138.0},
            "spring_fall": {"off_peak": 84.1, "mid_peak": 91.5, "on_peak": 102.8},
        },
    ),
    # 태양광 발전의 시간대 분포 비율(합계 1, 또는 자동정규화)
    "tou_ratios": _load_json_env(
        "TOU_RATIOS_JSON",
        {
            "summer": {"off_peak": 0.05, "mid_peak": 0.35, "on_peak": 0.60},
            "winter": {"off_peak": 0.08, "mid_peak": 0.42, "on_peak": 0.50},
            "spring_fall": {"off_peak": 0.06, "mid_peak": 0.40, "on_peak": 0.54},
        },
    ),
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
