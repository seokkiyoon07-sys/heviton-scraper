"""
Heviton 모니터링 시스템 크롤러 설정
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
    "base_url": os.getenv("HEVITON_BASE_URL", "https://monitoring.heviton.com"),
    "login_url": "/monitoring/login/loginProc.do",  # 실제 로그인 처리 URL
    "login_page": "/monitoring/login/login.do",
    "user_id": os.getenv("HEVITON_USER_ID", ""),
    "password": os.getenv("HEVITON_PASSWORD", ""),
}

# 크롤링 대상 URL (로그인 후 확인 필요 - 예상 경로)
DATA_URLS = {
    "dashboard": "/monitoring/dashboard/main.do",
    "daily": "/monitoring/stat/daily.do",      # 일별 발전량
    "weekly": "/monitoring/stat/weekly.do",    # 주별 발전량
    "monthly": "/monitoring/stat/monthly.do",  # 월별 발전량
}

# 요청 설정
REQUEST_CONFIG = {
    "timeout": 30,
    "headers": {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
}

# 로깅 설정
LOGGING_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": LOGS_DIR / "scraper.log",
}
