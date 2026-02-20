"""
Heviton REMS 모니터링 시스템 로그인 인증 모듈 (REST API 기반)
"""
import logging
from typing import Optional

import requests

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config.settings import HEVITON_CONFIG, API_ENDPOINTS, REQUEST_CONFIG

logger = logging.getLogger(__name__)


class HevitonAuth:
    """Heviton 모니터링 시스템 인증 클래스 (REST API + JWT)"""

    def __init__(self, headless: bool = True):
        """
        Args:
            headless: 하위 호환성을 위해 유지 (무시됨)
        """
        self.api_root = HEVITON_CONFIG["api_root"]
        self.api_base = HEVITON_CONFIG["api_base"]
        self.session: requests.Session = requests.Session()
        self.session.headers.update(REQUEST_CONFIG["headers"])
        self.session.headers["X-APP-TYPE"] = "web"
        self.session.headers["Origin"] = HEVITON_CONFIG["base_url"]
        self.session.headers["Referer"] = HEVITON_CONFIG["base_url"] + "/login"
        self.is_logged_in = False
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def login(self, user_id: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        REST API 로그인 - JWT 토큰 발급

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

        url = f"{self.api_root}/{API_ENDPOINTS['login']}"
        payload = {
            "username": user_id,
            "password": password,
            "loginType": HEVITON_CONFIG.get("login_type", "collector"),
            "rememberMe": True,
        }

        try:
            logger.info(f"REST API 로그인 시도: {url}")
            response = self.session.post(
                url, json=payload, timeout=REQUEST_CONFIG["timeout"],
            )

            if response.status_code == 200:
                return self._handle_login_response(response.json())
            else:
                logger.error(f"로그인 실패 (HTTP {response.status_code}): {response.text[:500]}")
                return False

        except requests.exceptions.SSLError as e:
            logger.warning(f"SSL 오류, verify=False로 재시도: {e}")
            try:
                response = self.session.post(
                    url, json=payload, timeout=REQUEST_CONFIG["timeout"], verify=False,
                )
                if response.status_code == 200:
                    self.session.verify = False
                    return self._handle_login_response(response.json())
                else:
                    logger.error(f"로그인 실패 (HTTP {response.status_code}): {response.text[:500]}")
                    return False
            except Exception as e2:
                logger.error(f"SSL 재시도 실패: {e2}")
                return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"서버 연결 실패: {e}")
            return False

        except Exception as e:
            logger.error(f"로그인 중 오류 발생: {e}")
            return False

    def _handle_login_response(self, data: dict) -> bool:
        """로그인 응답에서 JWT 토큰 추출"""
        logger.debug(f"로그인 응답 키: {list(data.keys())}")

        # 토큰 추출 (다양한 응답 구조 대응)
        token = (
            data.get("token")
            or data.get("accessToken")
            or (data.get("data") or {}).get("token")
            or (data.get("data") or {}).get("accessToken")
        )

        if token:
            self.token = token
            self.refresh_token = (
                data.get("refreshToken")
                or (data.get("data") or {}).get("refreshToken")
            )
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            self.is_logged_in = True
            logger.info("REST API 로그인 성공 (JWT 토큰 발급)")
            return True

        logger.error(f"로그인 응답에서 토큰을 찾을 수 없음. 응답 키: {list(data.keys())}")
        logger.debug(f"로그인 응답 전체: {data}")
        return False

    def reissue_token(self) -> bool:
        """JWT 토큰 갱신"""
        if not self.refresh_token:
            logger.warning("리프레시 토큰이 없어 갱신 불가")
            return False

        try:
            url = f"{self.api_base}/{API_ENDPOINTS['token_reissue']}"
            response = self.session.post(
                url, json={"refreshToken": self.refresh_token},
                timeout=REQUEST_CONFIG["timeout"],
            )
            if response.status_code == 200:
                data = response.json()
                new_token = (
                    data.get("token")
                    or data.get("accessToken")
                    or (data.get("data") or {}).get("token")
                    or (data.get("data") or {}).get("accessToken")
                )
                if new_token:
                    self.token = new_token
                    self.session.headers["Authorization"] = f"Bearer {self.token}"
                    logger.info("토큰 갱신 성공")
                    return True
            logger.error(f"토큰 갱신 실패 (HTTP {response.status_code})")
            return False
        except Exception as e:
            logger.error(f"토큰 갱신 실패: {e}")
            return False

    def logout(self):
        """로그아웃 및 세션 정리"""
        try:
            if self.is_logged_in and self.token:
                url = f"{self.api_base}/{API_ENDPOINTS['logout']}"
                self.session.post(url, timeout=REQUEST_CONFIG["timeout"])
                logger.info("로그아웃 완료")
        except Exception as e:
            logger.warning(f"로그아웃 중 오류: {e}")
        finally:
            self.close()

    def close(self):
        """세션 종료"""
        if self.session:
            self.session.close()
        self.is_logged_in = False
        self.token = None
        self.refresh_token = None

    def get_session(self) -> requests.Session:
        """인증된 requests 세션 반환"""
        return self.session

    def get_driver(self) -> requests.Session:
        """하위 호환성: get_driver() -> get_session() 래핑"""
        return self.session

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

    auth = HevitonAuth()
    if auth.login():
        print("로그인 성공!")
        print(f"토큰: {auth.token[:20]}...")
        auth.logout()
    else:
        print("로그인 실패!")
        auth.close()
