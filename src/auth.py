"""
Heviton 모니터링 시스템 로그인 인증 모듈 (Selenium 기반)
"""
import logging
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config.settings import HEVITON_CONFIG

logger = logging.getLogger(__name__)


class HevitonAuth:
    """Heviton 모니터링 시스템 인증 클래스 (Selenium 기반)"""

    def __init__(self, headless: bool = True):
        """
        Args:
            headless: 헤드리스 모드 사용 여부 (기본: True)
        """
        self.base_url = HEVITON_CONFIG["base_url"]
        self.driver: Optional[webdriver.Chrome] = None
        self.is_logged_in = False
        self.headless = headless

    def _init_driver(self):
        """Chrome WebDriver 초기화"""
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        # 기본 옵션
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # 모바일 에뮬레이션 (모바일 버전이 더 간단)
        mobile_emulation = {
            "deviceMetrics": {"width": 375, "height": 812, "pixelRatio": 3.0},
            "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        }
        options.add_experimental_option("mobileEmulation", mobile_emulation)

        # 자동 알림 비활성화
        options.add_argument("--disable-notifications")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.implicitly_wait(10)
            logger.info("Chrome WebDriver 초기화 완료")
        except WebDriverException as e:
            logger.error(f"WebDriver 초기화 실패: {e}")
            raise

    def login(self, user_id: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        로그인 수행

        Args:
            user_id: 사용자 ID (미제공시 환경변수 사용)
            password: 비밀번호 (미제공시 환경변수 사용)

        Returns:
            bool: 로그인 성공 여부
        """
        user_id = user_id or HEVITON_CONFIG["user_id"]
        password = password or HEVITON_CONFIG["password"]

        if not user_id or not password:
            logger.error("로그인 정보가 설정되지 않았습니다. .env 파일을 확인하세요.")
            return False

        try:
            # WebDriver 초기화
            if self.driver is None:
                self._init_driver()

            # 1. 로그인 페이지 접속
            login_url = f"{self.base_url}/monitoring/login/login.do?ua=m&inType=web"
            logger.info(f"로그인 페이지 접속: {login_url}")
            self.driver.get(login_url)

            # 페이지 로드 대기
            time.sleep(2)

            # 2. 로그인 폼 입력
            wait = WebDriverWait(self.driver, 15)

            # ID 입력
            id_input = wait.until(
                EC.presence_of_element_located((By.ID, "loginId"))
            )
            id_input.clear()
            id_input.send_keys(user_id)
            logger.debug(f"ID 입력 완료: {user_id}")

            # 비밀번호 입력
            pw_input = self.driver.find_element(By.ID, "password")
            pw_input.clear()
            pw_input.send_keys(password)
            logger.debug("비밀번호 입력 완료")

            # 3. 로그인 버튼 클릭
            login_btn = self.driver.find_element(By.CSS_SELECTOR, "a.btn76.c1")
            login_btn.click()
            logger.info("로그인 버튼 클릭")

            # 4. 로그인 결과 확인 - 페이지 전환 대기
            # URL이 변경될 때까지 대기 (최대 10초)
            for _ in range(20):
                time.sleep(0.5)
                current_url = self.driver.current_url
                # loginProc.do에서 벗어나면 결과 확인
                if "loginProc" not in current_url:
                    break

            logger.debug(f"현재 URL: {current_url}")

            # 에러 메시지 팝업 확인 (swal - SweetAlert)
            try:
                # SweetAlert 팝업이 있는지 확인 (짧은 대기)
                time.sleep(1)
                swal_container = self.driver.find_elements(By.CLASS_NAME, "swal-overlay")
                if swal_container and swal_container[0].is_displayed():
                    swal_text = self.driver.find_element(By.CLASS_NAME, "swal-text")
                    error_msg = swal_text.text
                    logger.error(f"로그인 실패 (알림): {error_msg}")
                    return False
            except:
                pass

            # URL 기반 실패 판단
            if "ret=idNotFound" in current_url:
                logger.error("로그인 실패: 등록된 ID가 없습니다.")
                return False
            elif "ret=passNotEq" in current_url:
                logger.error("로그인 실패: 비밀번호가 올바르지 않습니다.")
                return False

            # 페이지 소스로 로그인 성공 확인 (가장 신뢰할 수 있는 방법)
            page_source = self.driver.page_source

            # 로그인 성공 확인: 페이지에 사용자 정보나 로그아웃 링크가 있는지
            if "user_id" in page_source or "user in" in page_source:
                logger.info("로그인 성공! (사용자 정보 확인)")
                self.is_logged_in = True
                return True

            if "모니터링" in page_source and "설비상태" in page_source:
                logger.info("로그인 성공! (메뉴 확인)")
                self.is_logged_in = True
                return True

            if "님" in page_source and ("로그아웃" in page_source or "logout" in page_source.lower()):
                logger.info("로그인 성공! (페이지 내용 확인)")
                self.is_logged_in = True
                return True

            # URL 기반 성공 확인
            if ("dashboard" in current_url or
                "main" in current_url or
                "monitoring" in current_url or
                "status" in current_url):
                logger.info("로그인 성공! (URL 기반 확인)")
                self.is_logged_in = True
                return True

            logger.error(f"로그인 실패: 알 수 없는 상태 (URL: {current_url})")
            return False

        except TimeoutException:
            logger.error("로그인 타임아웃: 페이지 로드 실패")
            return False
        except Exception as e:
            logger.error(f"로그인 중 오류 발생: {e}")
            return False

    def logout(self):
        """로그아웃 및 드라이버 종료"""
        try:
            if self.driver and self.is_logged_in:
                logout_url = f"{self.base_url}/monitoring/login/logoutProc.do"
                self.driver.get(logout_url)
                logger.info("로그아웃 완료")
        except Exception as e:
            logger.warning(f"로그아웃 중 오류: {e}")
        finally:
            self.close()

    def close(self):
        """WebDriver 종료"""
        if self.driver:
            try:
                self.driver.quit()
                logger.debug("WebDriver 종료")
            except:
                pass
            self.driver = None
        self.is_logged_in = False

    def get_driver(self) -> webdriver.Chrome:
        """WebDriver 인스턴스 반환"""
        return self.driver

    def get_page_source(self) -> str:
        """현재 페이지 소스 반환"""
        if self.driver:
            return self.driver.page_source
        return ""

    def navigate_to(self, url: str) -> bool:
        """
        지정된 URL로 이동

        Args:
            url: 이동할 URL (상대 경로 또는 절대 경로)

        Returns:
            bool: 이동 성공 여부
        """
        if not self.driver:
            logger.error("WebDriver가 초기화되지 않았습니다.")
            return False

        try:
            full_url = url if url.startswith("http") else f"{self.base_url}{url}"
            self.driver.get(full_url)
            time.sleep(2)  # 페이지 로드 대기
            return True
        except Exception as e:
            logger.error(f"페이지 이동 실패: {e}")
            return False

    def __enter__(self):
        """Context manager 진입"""
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        self.logout()


# 테스트용
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # 헤드리스 모드 비활성화하여 브라우저 확인
    auth = HevitonAuth(headless=False)
    if auth.login():
        print("로그인 성공!")
        input("Enter를 눌러 종료...")
        auth.logout()
    else:
        print("로그인 실패!")
        auth.close()
