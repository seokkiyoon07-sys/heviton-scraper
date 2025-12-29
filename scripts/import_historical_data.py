#!/usr/bin/env python3
"""
과거 발전량 데이터를 Google Sheets에 일괄 입력하는 스크립트

Usage:
    python scripts/import_historical_data.py
"""
import os
import sys
import logging
import time
from datetime import datetime, timedelta

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

from src.auth import HevitonAuth
from src.google_sheets import GoogleSheetsClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_daily_data(driver, base_url: str) -> list:
    """통계 페이지에서 모든 일별 데이터 수집"""
    logger.info("일별 데이터 수집 중...")

    url = f"{base_url}/monitoring/stat/statistics.do?ua=m&inType=web&energyCode=501"
    driver.get(url)
    time.sleep(5)

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')

    daily_records = []
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')
        if rows:
            header = rows[0].get_text(strip=True)
            if '기간' in header and '발전량' in header:
                for row in rows[1:]:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        date_text = cols[0].get_text(strip=True)
                        value_text = cols[1].get_text(strip=True)

                        # YYYY.MM.DD 형식인지 확인
                        if date_text and value_text and '.' in date_text:
                            if '합계' in date_text or '기간' in date_text:
                                continue

                            # YYYY.MM.DD -> YYYY-MM-DD 변환
                            try:
                                parts = date_text.split('.')
                                if len(parts) == 3:
                                    formatted_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
                                    daily_records.append({
                                        "date": formatted_date,
                                        "generation": value_text,
                                        "status": "정상",
                                    })
                            except:
                                pass
                break

    # 날짜순 정렬
    daily_records.sort(key=lambda x: x["date"])
    logger.info(f"일별 데이터 {len(daily_records)}건 수집 완료")
    return daily_records


def get_all_monthly_data(driver, base_url: str) -> list:
    """통계 페이지에서 모든 월별 데이터 수집"""
    logger.info("월별 데이터 수집 중...")

    # 모니터링 페이지에서 월별 발전량 히스토리 조회
    url = f"{base_url}/monitoring/stat/statistics.do?ua=m&inType=web&energyCode=501"
    driver.get(url)
    time.sleep(5)

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')

    monthly_records = []

    # 월별 테이블 찾기 (캘린더 형태)
    tables = soup.find_all('table')

    # 월별 데이터는 보통 캘린더 형태로 표시됨
    # 각 셀에서 월과 발전량 추출
    current_year = datetime.now().year

    for table in tables:
        rows = table.find_all('tr')
        header = rows[0].get_text(strip=True) if rows else ""

        # 년도 확인
        if str(current_year) in header or str(current_year - 1) in header:
            year_match = None
            for y in range(current_year - 5, current_year + 1):
                if str(y) in header:
                    year_match = y
                    break

            if year_match:
                # 각 셀에서 월별 데이터 추출
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        # "1월", "2월" 등의 형식
                        for month in range(1, 13):
                            month_str = f"{month}월"
                            if month_str == text:
                                # 다음 셀에서 발전량 확인 필요
                                pass

    # 월별 데이터가 캘린더 형태로 복잡하면 일별 데이터에서 집계
    logger.info(f"월별 데이터 {len(monthly_records)}건 수집 완료")
    return monthly_records


def calculate_weekly_from_daily(daily_records: list) -> list:
    """일별 데이터에서 주별 데이터 계산"""
    logger.info("주별 데이터 계산 중...")

    weekly_records = []

    if not daily_records:
        return weekly_records

    # 날짜별로 그룹화
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
    auth = HevitonAuth(headless=True)
    if not auth.login():
        logger.error("로그인 실패")
        auth.close()
        return 1

    try:
        driver = auth.get_driver()
        base_url = "https://monitoring.heviton.com"

        # 1. 일별 데이터 수집
        daily_records = get_all_daily_data(driver, base_url)

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
