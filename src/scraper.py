"""
Heviton 모니터링 시스템 데이터 크롤러 (Selenium 기반)
"""
import logging
import time
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config.settings import HEVITON_CONFIG

logger = logging.getLogger(__name__)


class HevitonScraper:
    """Heviton 발전량 데이터 크롤러 (Selenium 기반)"""

    def __init__(self, driver: webdriver.Chrome):
        """
        Args:
            driver: 인증된 Selenium WebDriver
        """
        self.driver = driver
        self.base_url = HEVITON_CONFIG["base_url"]

    def get_monitoring_data(self) -> Dict[str, Any]:
        """
        모니터링 페이지에서 발전량 데이터 추출

        Returns:
            발전량 데이터 (현재, 오늘, 이번달, 누적)
        """
        logger.info("모니터링 데이터 조회")

        try:
            # 모니터링 페이지로 이동
            url = f"{self.base_url}/monitoring/status/monitoring.do?ua=m&inType=web"
            self.driver.get(url)
            time.sleep(3)  # 페이지 및 JavaScript 로드 대기

            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')

            data = {
                "current_power": None,      # 현재 발전량 (kW)
                "today_generation": None,   # 오늘 발전량 (kWh)
                "month_generation": None,   # 이번달 발전량 (kWh)
                "total_generation": None,   # 누적 발전량 (kWh)
            }

            # JavaScript 변수에서 데이터 추출 시도
            # 페이지 소스에서 발전량 관련 값 찾기

            # 방법 1: JavaScript 실행하여 값 추출
            try:
                # 페이지 로드 후 추가 대기 (API 호출 완료 대기)
                time.sleep(5)

                # JavaScript로 데이터 추출 시도
                scripts = [
                    "return document.querySelector('.now .num')?.innerText;",
                    "return document.querySelector('.today .num')?.innerText;",
                    "return document.querySelector('.month .num')?.innerText;",
                    "return document.querySelector('.accrue .num')?.innerText;",
                ]

                for i, script in enumerate(scripts):
                    try:
                        value = self.driver.execute_script(script)
                        if value:
                            if i == 0:
                                data["current_power"] = value
                            elif i == 1:
                                data["today_generation"] = value
                            elif i == 2:
                                data["month_generation"] = value
                            elif i == 3:
                                data["total_generation"] = value
                    except:
                        pass

            except Exception as e:
                logger.debug(f"JavaScript 데이터 추출 실패: {e}")

            # 방법 2: HTML에서 직접 추출
            if not any(data.values()):
                # .num 클래스 요소들 찾기
                num_elements = soup.find_all(class_='num')
                for elem in num_elements:
                    text = elem.get_text(strip=True)
                    if text:
                        logger.debug(f"발견된 값: {text}")

                # 발전량 섹션 찾기
                sections = soup.find_all(class_=['now', 'today', 'month', 'accrue'])
                for section in sections:
                    num = section.find(class_='num')
                    if num:
                        value = num.get_text(strip=True)
                        section_class = section.get('class', [])
                        if 'now' in section_class:
                            data["current_power"] = value
                        elif 'today' in section_class:
                            data["today_generation"] = value
                        elif 'month' in section_class:
                            data["month_generation"] = value
                        elif 'accrue' in section_class:
                            data["total_generation"] = value

            logger.info(f"추출된 모니터링 데이터: {data}")
            return {
                "collected_at": datetime.now().isoformat(),
                "data": data,
            }

        except Exception as e:
            logger.error(f"모니터링 데이터 조회 실패: {e}")
            return {"error": str(e), "data": {}}

    def get_converter_status(self) -> Dict[str, Any]:
        """
        설비상태 페이지에서 컨버터/인버터 상태 확인

        Returns:
            컨버터 상태 정보
        """
        logger.info("컨버터 상태 조회")

        try:
            # 설비상태 페이지로 이동
            url = f"{self.base_url}/monitoring/status/inverter.do?ua=m&inType=web&energyCode=501"
            self.driver.get(url)
            time.sleep(3)

            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')

            status_data = {
                "is_normal": True,
                "converters": [],
                "error_messages": [],
            }

            # 컨버터 상태 확인 - JavaScript로 실행
            try:
                time.sleep(3)

                # 에러 상태 확인
                error_elements = self.driver.find_elements(By.CLASS_NAME, "error")
                if error_elements:
                    for elem in error_elements:
                        if elem.is_displayed():
                            status_data["is_normal"] = False
                            status_data["error_messages"].append(elem.text)

                # 정상 상태 아이콘 확인
                normal_icons = self.driver.find_elements(By.CSS_SELECTOR, ".status.normal, .status.on, .ico_on")
                error_icons = self.driver.find_elements(By.CSS_SELECTOR, ".status.error, .status.off, .ico_off, .ico_error")

                if error_icons:
                    for icon in error_icons:
                        if icon.is_displayed():
                            status_data["is_normal"] = False

                # 컨버터 정보 추출
                converter_sections = soup.find_all(class_=['converter', 'device_box', 'inverter_box'])
                for section in converter_sections:
                    name = section.find(class_=['name', 'title', 'device_name'])
                    status = section.find(class_=['status', 'state'])
                    if name:
                        converter_info = {
                            "name": name.get_text(strip=True),
                            "status": "정상" if status and "error" not in str(status.get('class', [])) else "확인필요"
                        }
                        status_data["converters"].append(converter_info)

            except Exception as e:
                logger.debug(f"컨버터 상태 상세 조회 실패: {e}")

            # 페이지에서 에러 텍스트 확인
            if "에러" in page_source or "오류" in page_source or "Error" in page_source:
                # 실제 에러인지 확인 (단순 UI 텍스트가 아닌)
                if "에러 발생" in page_source or "통신 오류" in page_source:
                    status_data["is_normal"] = False

            logger.info(f"컨버터 상태: {'정상' if status_data['is_normal'] else '이상'}")
            return status_data

        except Exception as e:
            logger.error(f"컨버터 상태 조회 실패: {e}")
            return {"is_normal": None, "error": str(e)}

    def get_recent_daily_data(self, days: int = 5) -> list:
        """
        최근 N일간 일별 발전량 데이터 조회

        Args:
            days: 조회할 일수 (기본 5일)

        Returns:
            최근 N일간 발전량 리스트
        """
        logger.info(f"최근 {days}일 발전량 조회")

        try:
            # 이력 페이지로 이동
            url = f"{self.base_url}/monitoring/stat/history.do?ua=m&inType=web"
            self.driver.get(url)
            time.sleep(3)

            recent_data = []

            # JavaScript로 차트 데이터 추출 시도
            try:
                time.sleep(3)

                # 차트 데이터나 테이블 데이터 추출
                # 방법 1: JavaScript 변수에서 추출
                chart_data = self.driver.execute_script("""
                    if (typeof chartData !== 'undefined') return chartData;
                    if (typeof dayData !== 'undefined') return dayData;
                    if (typeof dailyData !== 'undefined') return dailyData;
                    return null;
                """)

                if chart_data and isinstance(chart_data, list):
                    for item in chart_data[-days:]:
                        if isinstance(item, dict):
                            recent_data.append(item)

            except Exception as e:
                logger.debug(f"차트 데이터 추출 실패: {e}")

            # 방법 2: 통계 페이지에서 테이블 데이터 추출
            if not recent_data:
                url = f"{self.base_url}/monitoring/stat/statistics.do?ua=m&inType=web&energyCode=501"
                self.driver.get(url)
                time.sleep(3)

                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, 'lxml')

                # 테이블에서 데이터 추출 (일별 발전량 테이블 찾기)
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    # 헤더 확인: "기간"과 "총발전량" 컬럼이 있는 테이블 찾기
                    if rows:
                        header = rows[0].get_text(strip=True)
                        if '기간' in header and '발전량' in header:
                            # 최근 N일 데이터 추출 (역순으로 저장 - 최근순)
                            for row in rows[1:days+1]:
                                cols = row.find_all(['td', 'th'])
                                if len(cols) >= 2:
                                    date_text = cols[0].get_text(strip=True)
                                    value_text = cols[1].get_text(strip=True)
                                    # 날짜 형식 확인 (YYYY.MM.DD 또는 MM/DD)
                                    if date_text and value_text and ('.' in date_text or '/' in date_text):
                                        # 날짜를 MM/DD 형식으로 변환
                                        if '.' in date_text:
                                            parts = date_text.split('.')
                                            if len(parts) >= 3:
                                                date_text = f"{parts[1]}/{parts[2]}"
                                        recent_data.append({
                                            "date": date_text,
                                            "generation": value_text,
                                        })
                            break  # 일별 테이블 찾았으면 종료

            # 방법 3: 모니터링 페이지의 시간별 그래프 데이터로 일별 합산
            if not recent_data:
                # 최근 5일 날짜 생성
                today = datetime.now()
                for i in range(days):
                    date = today - timedelta(days=i)
                    recent_data.append({
                        "date": date.strftime("%m/%d"),
                        "generation": "-",  # 데이터 없음
                    })

            logger.info(f"최근 {days}일 발전량 데이터: {len(recent_data)} 건")
            return recent_data[:days]

        except Exception as e:
            logger.error(f"최근 발전량 조회 실패: {e}")
            return []

    def get_statistics_data(self) -> Dict[str, Any]:
        """
        통계 페이지에서 발전량 데이터 추출

        Returns:
            일별/월별 통계 데이터
        """
        logger.info("통계 데이터 조회")

        try:
            # 통계 페이지로 이동
            url = f"{self.base_url}/monitoring/stat/statistics.do?ua=m&inType=web&energyCode=501"
            self.driver.get(url)
            time.sleep(3)

            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')

            data = {
                "daily": [],
                "monthly": [],
            }

            # 테이블 데이터 추출
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # 헤더 제외
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        date_text = cols[0].get_text(strip=True)
                        value_text = cols[1].get_text(strip=True)
                        if date_text and value_text:
                            data["daily"].append({
                                "date": date_text,
                                "generation": value_text,
                            })

            logger.info(f"추출된 통계 데이터: {len(data['daily'])} 건")
            return {
                "collected_at": datetime.now().isoformat(),
                "data": data,
            }

        except Exception as e:
            logger.error(f"통계 데이터 조회 실패: {e}")
            return {"error": str(e), "data": {}}

    def get_all_data(self) -> Dict[str, Any]:
        """
        모든 발전량 데이터 조회

        Returns:
            통합 데이터
        """
        logger.info("전체 발전량 데이터 조회 시작")

        # 1. 모니터링 데이터 (현재/오늘/월별/누적 발전량)
        monitoring = self.get_monitoring_data()
        mon_data = monitoring.get("data", {})

        # 2. 컨버터 상태 확인
        converter_status = self.get_converter_status()

        # 3. 최근 5일 발전량
        recent_5days = self.get_recent_daily_data(5)

        return {
            "collected_at": datetime.now().isoformat(),
            "daily": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "total": mon_data.get("today_generation"),
                "current": mon_data.get("current_power"),
                "data": [],
            },
            "weekly": {
                "start_date": (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d"),
                "total": None,
                "data": [],
            },
            "monthly": {
                "year_month": datetime.now().strftime("%Y-%m"),
                "total": mon_data.get("month_generation"),
                "data": [],
            },
            "dashboard": {
                "current_power": mon_data.get("current_power"),
                "today_generation": mon_data.get("today_generation"),
                "month_generation": mon_data.get("month_generation"),
                "total_generation": mon_data.get("total_generation"),
            },
            "converter_status": converter_status,
            "recent_5days": recent_5days,
        }


# 테스트용
if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.DEBUG)

    from auth import HevitonAuth

    with HevitonAuth(headless=True) as auth:
        if auth.is_logged_in:
            scraper = HevitonScraper(auth.get_driver())
            data = scraper.get_all_data()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("로그인 실패!")
