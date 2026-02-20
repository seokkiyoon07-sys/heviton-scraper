#!/usr/bin/env python3
"""
과거 발전량 데이터를 Google Sheets에 일괄 입력하는 스크립트

Usage:
    python scripts/import_historical_data.py
"""
import os
import sys
import logging
from datetime import datetime, timedelta

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.auth import HevitonAuth
from src.scraper import HevitonScraper
from src.google_sheets import GoogleSheetsClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_daily_data(scraper: HevitonScraper) -> list:
    """REST API에서 모든 일별 데이터 수집"""
    logger.info("일별 데이터 수집 중...")

    daily_records = []

    if not scraper._get_plant_info():
        logger.error("발전소 정보를 조회할 수 없음")
        return daily_records

    # 최근 2년간 데이터 조회
    today = datetime.now()
    start_date = (today - timedelta(days=730)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    data = scraper._api_post(
        "collect/plant/detail/ranged",
        scraper._make_plant_payload(
            date_type="day",
            start_date=start_date,
            end_date=end_date,
        )
    )

    if data:
        payload = scraper._get_response_data(data) or data.get("data", data)
        items = scraper._extract_list(payload) if payload else []
        for item in items:
            if not isinstance(item, dict):
                continue
            date_str = scraper._extract_value(
                item, "date", "genDate", "collectDate", "statDate"
            ) or ""
            gen_value = scraper._extract_value(
                item, "generation", "genAmount", "dayGen", "value", "totalGen"
            )

            if date_str and gen_value is not None:
                try:
                    # YYYY-MM-DD 형식으로 정규화
                    parsed = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
                    formatted_date = parsed.strftime("%Y-%m-%d")
                    daily_records.append({
                        "date": formatted_date,
                        "generation": str(gen_value),
                        "status": "정상",
                    })
                except ValueError:
                    pass

    # 날짜순 정렬
    daily_records.sort(key=lambda x: x["date"])
    logger.info(f"일별 데이터 {len(daily_records)}건 수집 완료")
    return daily_records


def calculate_weekly_from_daily(daily_records: list) -> list:
    """일별 데이터에서 주별 데이터 계산"""
    logger.info("주별 데이터 계산 중...")

    weekly_records = []

    if not daily_records:
        return weekly_records

    from collections import defaultdict
    weekly_sums = defaultdict(lambda: {"dates": [], "total": 0})

    for record in daily_records:
        try:
            date = datetime.strptime(record["date"], "%Y-%m-%d")
            year = date.year
            week_num = date.isocalendar()[1]
            key = (year, week_num)

            gen = float(record["generation"])
            weekly_sums[key]["total"] += gen
            weekly_sums[key]["dates"].append(date)
        except:
            pass

    for (year, week_num), data in sorted(weekly_sums.items()):
        if data["dates"]:
            start_date = min(data["dates"]).strftime("%Y-%m-%d")
            end_date = max(data["dates"]).strftime("%Y-%m-%d")
            weekly_records.append({
                "week_label": f"{year}년 {week_num}주차",
                "start_date": start_date,
                "end_date": end_date,
                "total": f"{data['total']:.2f}",
            })

    logger.info(f"주별 데이터 {len(weekly_records)}건 계산 완료")
    return weekly_records


def calculate_monthly_from_daily(daily_records: list) -> list:
    """일별 데이터에서 월별 데이터 계산"""
    logger.info("월별 데이터 계산 중...")

    monthly_records = []

    if not daily_records:
        return monthly_records

    from collections import defaultdict
    monthly_sums = defaultdict(float)

    for record in daily_records:
        try:
            date = datetime.strptime(record["date"], "%Y-%m-%d")
            year_month = date.strftime("%Y-%m")
            gen = float(record["generation"])
            monthly_sums[year_month] += gen
        except:
            pass

    cumulative = 0
    for year_month in sorted(monthly_sums.keys()):
        total = monthly_sums[year_month]
        cumulative += total
        monthly_records.append({
            "year_month": year_month,
            "total": f"{total:.2f}",
            "cumulative": f"{cumulative / 1000:.2f}",  # MWh 변환
        })

    logger.info(f"월별 데이터 {len(monthly_records)}건 계산 완료")
    return monthly_records


def main():
    logger.info("=" * 50)
    logger.info("과거 발전량 데이터 일괄 입력 시작")
    logger.info("=" * 50)

    # 로그인
    auth = HevitonAuth()
    if not auth.login():
        logger.error("로그인 실패")
        auth.close()
        return 1

    try:
        scraper = HevitonScraper(auth.get_session())

        # 1. 일별 데이터 수집
        daily_records = get_all_daily_data(scraper)

        # 2. 주별/월별 데이터 계산
        weekly_records = calculate_weekly_from_daily(daily_records)
        monthly_records = calculate_monthly_from_daily(daily_records)

        # 3. Google Sheets에 기록
        sheets = GoogleSheetsClient()
        if not sheets.service:
            logger.error("Google Sheets 연결 실패")
            return 1

        logger.info("Google Sheets에 데이터 입력 중...")

        # 일별 데이터 입력
        if daily_records:
            sheets.bulk_insert_daily(daily_records)

        # 주별 데이터 입력
        if weekly_records:
            sheets.bulk_insert_weekly(weekly_records)

        # 월별 데이터 입력
        if monthly_records:
            sheets.bulk_insert_monthly(monthly_records)

        logger.info("=" * 50)
        logger.info("과거 데이터 입력 완료!")
        logger.info(f"  - 일별: {len(daily_records)}건")
        logger.info(f"  - 주별: {len(weekly_records)}건")
        logger.info(f"  - 월별: {len(monthly_records)}건")
        logger.info("=" * 50)

        return 0

    finally:
        auth.logout()


if __name__ == "__main__":
    sys.exit(main())
