#!/usr/bin/env python3
"""
Heviton REMS 태양광 발전량 모니터링 데이터 수집기
일 1회 실행하여 REST API로 발전량 데이터를 수집하고 잔디로 전송

Usage:
    python main.py                      # 전체 데이터 수집 및 전송
    python main.py --report-period daily    # 일별 절감 리포트
    python main.py --report-period weekly   # 주별 절감 리포트
    python main.py --report-period monthly  # 월별 절감 리포트
    python main.py --test       # 테스트 메시지 전송
    python main.py --discover   # API 엔드포인트 탐색 (개발용)
"""
import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import LOGGING_CONFIG, LOGS_DIR
from src.auth import HevitonAuth
from src.scraper import HevitonScraper, discover_api
from src.jandi_webhook import JandiWebhook
from src.google_sheets import GoogleSheetsClient
from src.tariff import (
    estimate_savings,
    estimate_daily_savings_from_hourly,
    estimate_period_savings_from_daily_records,
)
from config.settings import SAVINGS_CONFIG

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
        # 로그인 및 데이터 수집 (REST API)
        auth = HevitonAuth()
        if not auth.login():
            error_msg = "로그인 실패 - 인증 정보를 확인하세요."
            logger.error(error_msg)
            jandi.send_error_alert(error_msg)
            return 1

        scraper = HevitonScraper(auth.get_session())

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


def run_savings_report(period: str) -> int:
    """절감액 리포트 실행 (daily/weekly/monthly)"""
    logger = logging.getLogger(__name__)
    period = str(period).lower().strip()
    if period not in {"daily", "weekly", "monthly"}:
        logger.error(f"지원하지 않는 report period: {period}")
        return 1

    try:
        jandi = get_jandi_webhook()
    except ValueError as e:
        logger.error(str(e))
        return 1

    auth = None
    try:
        auth = HevitonAuth()
        if not auth.login():
            error_msg = "로그인 실패 - 인증 정보를 확인하세요."
            logger.error(error_msg)
            jandi.send_error_alert(error_msg)
            return 1

        scraper = HevitonScraper(auth.get_session())
        tou_rates = SAVINGS_CONFIG.get("tou_rates", {})
        tou_ratios = SAVINGS_CONFIG.get("tou_ratios", {})
        currency = SAVINGS_CONFIG.get("currency", "원")
        tariff_name = SAVINGS_CONFIG.get("tariff_name", "")

        if period == "daily":
            data = scraper.get_all_data()
            dashboard = data.get("dashboard", {}) if isinstance(data.get("dashboard"), dict) else {}
            hourly = data.get("today_hourly", [])

            hourly_result = estimate_daily_savings_from_hourly(hourly, tou_rates)
            weighted_result = estimate_savings(
                today_generation=dashboard.get("today_generation"),
                month_generation=dashboard.get("month_generation"),
                tou_rates=tou_rates,
                tou_ratios=tou_ratios,
            )
            result = hourly_result or weighted_result
            if not result:
                jandi.send_error_alert("일별 절감액 계산 실패: 발전량/요금 데이터가 없습니다.")
                return 1

            today_gen = result.get("today_generation")
            if today_gen is None:
                try:
                    today_gen = float(dashboard.get("today_generation"))
                except (TypeError, ValueError):
                    today_gen = None

            parts = []
            if today_gen is not None:
                parts.append(f"발전량 {today_gen:,.2f}kWh")
            parts.append(f"절감액 {result.get('today_saving', 0):,.0f}{currency}")
            parts.append(f"적용단가 {result.get('weighted_unit_price', 0):,.2f}{currency}/kWh")
            if tariff_name:
                parts.append(f"요금제 {tariff_name}")
            if hourly_result:
                period_kwh = hourly_result.get("kwh_by_period", {})
                parts.append(
                    "실측 경/중/최 "
                    f"{period_kwh.get('off_peak', 0.0):.2f}/"
                    f"{period_kwh.get('mid_peak', 0.0):.2f}/"
                    f"{period_kwh.get('on_peak', 0.0):.2f}kWh"
                )
            else:
                parts.append("시간대 비율 추정")

            return 0 if jandi.send_message(
                body=f"💰 일별 절감 리포트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
                color="#2ECC71",
                connect_info=[{
                    "title": f"📅 일별 절감 ({datetime.now().strftime('%Y-%m-%d')})",
                    "description": " | ".join(parts),
                }],
            ) else 1

        today = datetime.now()
        if period == "weekly":
            end = today
            start = today - timedelta(days=6)
            title = f"📆 주별 절감 ({start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')})"
        else:
            first_this = today.replace(day=1)
            end = first_this - timedelta(days=1)
            start = end.replace(day=1)
            title = f"🗓️ 월별 절감 ({start.strftime('%Y-%m')})"

        records = scraper.get_daily_generation_range(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        result = estimate_period_savings_from_daily_records(records, tou_rates, tou_ratios)
        if not result:
            jandi.send_error_alert(f"{period} 절감액 계산 실패: 기간 발전량 데이터가 없습니다.")
            return 1

        parts = [
            f"발전량 {result['total_generation']:,.2f}kWh",
            f"절감액 {result['total_saving']:,.0f}{currency}",
            f"평균단가 {result['avg_unit_price']:,.2f}{currency}/kWh",
            f"산정일수 {result['days']}일",
            "일별 합계 기준 추정",
        ]
        if tariff_name:
            parts.append(f"요금제 {tariff_name}")

        emoji = "📈" if period == "weekly" else "📊"
        return 0 if jandi.send_message(
            body=f"💰 {period} 절감 리포트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            color="#1ABC9C",
            connect_info=[{
                "title": title.replace("📆", emoji).replace("🗓️", emoji),
                "description": " | ".join(parts),
            }],
        ) else 1

    except Exception as e:
        error_msg = f"절감 리포트 실행 중 오류 발생: {str(e)}"
        logger.exception(error_msg)
        try:
            jandi.send_error_alert(error_msg)
        except Exception:
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


def run_discover():
    """API 엔드포인트 탐색"""
    logger = logging.getLogger(__name__)
    logger.info("API 엔드포인트 탐색 모드")

    auth = None
    try:
        auth = HevitonAuth()
        if not auth.login():
            print("로그인 실패 - 인증 정보를 확인하세요.")
            return 1

        discover_api(auth.get_session())
        return 0

    except Exception as e:
        logger.exception(f"탐색 중 오류: {e}")
        return 1

    finally:
        if auth:
            auth.logout()


def main():
    parser = argparse.ArgumentParser(
        description="Heviton 태양광 발전량 모니터링 크롤러"
    )
    parser.add_argument(
        "--daily", action="store_true",
        help="일별 절감 리포트 전송"
    )
    parser.add_argument(
        "--weekly", action="store_true",
        help="주별 절감 리포트 전송"
    )
    parser.add_argument(
        "--monthly", action="store_true",
        help="월별 절감 리포트 전송"
    )
    parser.add_argument(
        "--report-period",
        choices=["daily", "weekly", "monthly"],
        help="절감 리포트 주기 선택",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="잔디 웹훅 테스트 메시지 전송"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="디버그 모드"
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="API 엔드포인트 탐색 (개발/디버깅용)"
    )

    args = parser.parse_args()

    # 로깅 설정
    if args.debug or args.discover:
        LOGGING_CONFIG["level"] = "DEBUG"
    setup_logging()

    # 실행
    if args.test:
        return test_webhook()
    elif args.discover:
        return run_discover()
    elif args.report_period:
        return run_savings_report(args.report_period)
    elif args.daily:
        return run_savings_report("daily")
    elif args.weekly:
        return run_savings_report("weekly")
    elif args.monthly:
        return run_savings_report("monthly")
    else:
        return run_scraper(args)


if __name__ == "__main__":
    sys.exit(main())
