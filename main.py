#!/usr/bin/env python3
"""
Heviton 태양광 발전량 모니터링 크롤러
일 1회 실행하여 발전량 데이터를 수집하고 잔디로 전송

Usage:
    python main.py              # 전체 데이터 수집 및 전송
    python main.py --daily      # 일별 데이터만
    python main.py --weekly     # 주별 데이터만
    python main.py --monthly    # 월별 데이터만
    python main.py --test       # 테스트 메시지 전송
"""
import os
import sys
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import LOGGING_CONFIG, LOGS_DIR
from src.auth import HevitonAuth
from src.scraper import HevitonScraper
from src.jandi_webhook import JandiWebhook
from src.google_sheets import GoogleSheetsClient

# 환경변수 로드
load_dotenv()


def setup_logging():
    """로깅 설정"""
    log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=getattr(logging, LOGGING_CONFIG["level"]),
        format=LOGGING_CONFIG["format"],
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_jandi_webhook() -> JandiWebhook:
    """잔디 웹훅 인스턴스 생성"""
    webhook_url = os.getenv("JANDI_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("JANDI_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
    return JandiWebhook(webhook_url)


def run_scraper(args):
    """크롤러 실행"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("Heviton 발전량 크롤러 시작")
    logger.info("=" * 50)

    try:
        jandi = get_jandi_webhook()
    except ValueError as e:
        logger.error(str(e))
        return 1

    auth = None
    try:
        # 로그인 및 데이터 수집 (Selenium 기반)
        auth = HevitonAuth(headless=True)
        if not auth.login():
            error_msg = "로그인 실패 - 인증 정보를 확인하세요."
            logger.error(error_msg)
            jandi.send_error_alert(error_msg)
            return 1

        scraper = HevitonScraper(auth.get_driver())

        # 데이터 수집
        data = scraper.get_all_data()

        logger.info("데이터 수집 완료")
        logger.info(f"수집된 데이터: {data}")

        # 잔디로 전송
        if jandi.send_generation_report(data):
            logger.info("잔디 전송 완료")
        else:
            logger.warning("잔디 전송 실패")

        # Google Sheets에 기록
        try:
            sheets = GoogleSheetsClient()
            if sheets.service:
                if sheets.record_all(data):
                    logger.info("Google Sheets 기록 완료")
                else:
                    logger.warning("Google Sheets 기록 일부 실패")
            else:
                logger.info("Google Sheets 연동 미설정 (선택사항)")
        except Exception as e:
            logger.warning(f"Google Sheets 기록 실패: {e}")

        logger.info("크롤러 정상 종료")
        return 0

    except Exception as e:
        error_msg = f"크롤러 실행 중 오류 발생: {str(e)}"
        logger.exception(error_msg)
        try:
            jandi.send_error_alert(error_msg)
        except:
            pass
        return 1

    finally:
        if auth:
            auth.logout()


def test_webhook():
    """웹훅 테스트"""
    logger = logging.getLogger(__name__)
    logger.info("잔디 웹훅 테스트")

    try:
        jandi = get_jandi_webhook()

        # 테스트 데이터
        test_data = {
            "daily": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "total": "테스트: 150.5 kWh",
                "data": [{"time": "12:00", "generation": "50 kWh"}]
            },
            "weekly": {
                "start_date": "2024-12-23",
                "total": "테스트: 1,050 kWh",
                "data": [{"day": "월", "generation": "150 kWh"}]
            },
            "monthly": {
                "year_month": datetime.now().strftime("%Y-%m"),
                "total": "테스트: 4,500 kWh",
                "data": [{"date": "2024-12-01", "generation": "145 kWh"}]
            },
        }

        if jandi.send_generation_report(test_data):
            logger.info("테스트 메시지 전송 성공!")
            print("✅ 잔디 테스트 메시지가 전송되었습니다.")
            return 0
        else:
            logger.error("테스트 메시지 전송 실패")
            print("❌ 잔디 테스트 메시지 전송 실패")
            return 1

    except ValueError as e:
        logger.error(str(e))
        print(f"❌ {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Heviton 태양광 발전량 모니터링 크롤러"
    )
    parser.add_argument(
        "--daily", action="store_true",
        help="일별 발전량만 수집"
    )
    parser.add_argument(
        "--weekly", action="store_true",
        help="주별 발전량만 수집"
    )
    parser.add_argument(
        "--monthly", action="store_true",
        help="월별 발전량만 수집"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="잔디 웹훅 테스트 메시지 전송"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="디버그 모드"
    )

    args = parser.parse_args()

    # 로깅 설정
    if args.debug:
        LOGGING_CONFIG["level"] = "DEBUG"
    setup_logging()

    # 실행
    if args.test:
        return test_webhook()
    else:
        return run_scraper(args)


if __name__ == "__main__":
    sys.exit(main())
