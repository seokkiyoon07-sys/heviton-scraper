"""
Google Sheets 연동 모듈
발전량 데이터를 스프레드시트에 자동 기록
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# 스프레드시트 ID (URL에서 추출)
SPREADSHEET_ID = "1teGKsO3VP8m5NSP8FYnYmxTXj2a9izdOs0nhbmivr5I"

# 시트 이름
SHEET_DAILY = "일별"
SHEET_WEEKLY = "주별"
SHEET_MONTHLY = "월별"

# Google Sheets API 범위
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsClient:
    """Google Sheets API 클라이언트"""

    def __init__(self, credentials_json: Optional[str] = None):
        """
        Args:
            credentials_json: 서비스 계정 JSON 문자열 (환경변수에서 로드)
        """
        self.spreadsheet_id = SPREADSHEET_ID
        self.service = None
        self._init_service(credentials_json)

    def _init_service(self, credentials_json: Optional[str] = None):
        """Google Sheets API 서비스 초기화"""
        try:
            # 환경변수에서 credentials 로드
            creds_json = credentials_json or os.getenv("GOOGLE_SHEETS_CREDENTIALS")

            if not creds_json:
                logger.warning("GOOGLE_SHEETS_CREDENTIALS 환경변수가 설정되지 않았습니다.")
                return

            # JSON 문자열을 딕셔너리로 변환
            creds_dict = json.loads(creds_json)

            # 서비스 계정 인증
            credentials = Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )

            # Sheets API 서비스 생성
            self.service = build("sheets", "v4", credentials=credentials)
            logger.info("Google Sheets API 초기화 완료")

        except Exception as e:
            logger.error(f"Google Sheets API 초기화 실패: {e}")
            self.service = None

    def _ensure_sheet_exists(self, sheet_name: str):
        """시트가 없으면 생성"""
        try:
            # 현재 시트 목록 조회
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()

            existing_sheets = [s["properties"]["title"] for s in spreadsheet["sheets"]]

            if sheet_name not in existing_sheets:
                # 시트 생성
                request = {
                    "requests": [{
                        "addSheet": {
                            "properties": {"title": sheet_name}
                        }
                    }]
                }
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=request
                ).execute()
                logger.info(f"시트 '{sheet_name}' 생성 완료")

                # 헤더 추가
                self._add_headers(sheet_name)

        except HttpError as e:
            logger.error(f"시트 확인/생성 실패: {e}")

    def _add_headers(self, sheet_name: str):
        """시트에 헤더 추가"""
        if sheet_name == SHEET_DAILY:
            headers = [["날짜", "발전량(kWh)", "현재출력(kW)", "설비상태", "기록시간"]]
        elif sheet_name == SHEET_WEEKLY:
            headers = [["주차", "시작일", "종료일", "총발전량(kWh)", "기록시간"]]
        elif sheet_name == SHEET_MONTHLY:
            headers = [["년월", "총발전량(kWh)", "누적발전량(MWh)", "기록시간"]]
        else:
            return

        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body={"values": headers}
            ).execute()
            logger.info(f"'{sheet_name}' 헤더 추가 완료")
        except HttpError as e:
            logger.error(f"헤더 추가 실패: {e}")

    def append_daily_data(self, data: Dict[str, Any]) -> bool:
        """
        일별 발전량 데이터 추가

        Args:
            data: 크롤링된 전체 데이터

        Returns:
            성공 여부
        """
        if not self.service:
            logger.warning("Google Sheets 서비스가 초기화되지 않았습니다.")
            return False

        try:
            self._ensure_sheet_exists(SHEET_DAILY)

            dashboard = data.get("dashboard", {})
            converter_status = data.get("converter_status", {})

            # 오늘 날짜
            today = datetime.now().strftime("%Y-%m-%d")

            # 발전량 (kWh)
            today_gen = dashboard.get("today_generation", "")

            # 현재 출력 (W -> kW 변환)
            current_power = dashboard.get("current_power", "")
            if current_power:
                try:
                    current_power = f"{float(current_power) / 1000:.2f}"
                except:
                    pass

            # 설비 상태
            is_normal = converter_status.get("is_normal")
            if is_normal is True:
                status = "정상"
            elif is_normal is False:
                status = "이상"
            else:
                status = "확인필요"

            # 기록 시간
            record_time = datetime.now().strftime("%H:%M:%S")

            # 데이터 행
            row = [[today, today_gen, current_power, status, record_time]]

            # 데이터 추가
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{SHEET_DAILY}!A:E",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": row}
            ).execute()

            logger.info(f"일별 데이터 기록 완료: {today} - {today_gen} kWh")
            return True

        except HttpError as e:
            logger.error(f"일별 데이터 기록 실패: {e}")
            return False

    def append_monthly_data(self, data: Dict[str, Any]) -> bool:
        """
        월별 발전량 데이터 추가 (월 1회 또는 월말에 기록)

        Args:
            data: 크롤링된 전체 데이터

        Returns:
            성공 여부
        """
        if not self.service:
            logger.warning("Google Sheets 서비스가 초기화되지 않았습니다.")
            return False

        try:
            self._ensure_sheet_exists(SHEET_MONTHLY)

            dashboard = data.get("dashboard", {})

            # 년월
            year_month = datetime.now().strftime("%Y-%m")

            # 월 발전량
            month_gen = dashboard.get("month_generation", "")

            # 누적 발전량
            total_gen = dashboard.get("total_generation", "")

            # 기록 시간
            record_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 기존 데이터 확인 (같은 월 데이터가 있으면 업데이트)
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{SHEET_MONTHLY}!A:A"
            ).execute()

            existing_values = result.get("values", [])
            row_index = None

            for i, row in enumerate(existing_values):
                if row and row[0] == year_month:
                    row_index = i + 1  # 1-indexed
                    break

            row = [[year_month, month_gen, total_gen, record_time]]

            if row_index:
                # 기존 행 업데이트
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{SHEET_MONTHLY}!A{row_index}:D{row_index}",
                    valueInputOption="RAW",
                    body={"values": row}
                ).execute()
                logger.info(f"월별 데이터 업데이트: {year_month} - {month_gen} kWh")
            else:
                # 새 행 추가
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{SHEET_MONTHLY}!A:D",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": row}
                ).execute()
                logger.info(f"월별 데이터 기록: {year_month} - {month_gen} kWh")

            return True

        except HttpError as e:
            logger.error(f"월별 데이터 기록 실패: {e}")
            return False

    def record_all(self, data: Dict[str, Any]) -> bool:
        """
        모든 시트에 데이터 기록

        Args:
            data: 크롤링된 전체 데이터

        Returns:
            성공 여부
        """
        daily_ok = self.append_daily_data(data)
        monthly_ok = self.append_monthly_data(data)

        return daily_ok and monthly_ok


# 테스트용
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.DEBUG)

    # 테스트 데이터
    test_data = {
        "dashboard": {
            "current_power": "50000",
            "today_generation": "123.45",
            "month_generation": "3456.78",
            "total_generation": "28.90",
        },
        "converter_status": {
            "is_normal": True,
        }
    }

    client = GoogleSheetsClient()
    if client.service:
        client.record_all(test_data)
    else:
        print("Google Sheets 연결 실패 - GOOGLE_SHEETS_CREDENTIALS 환경변수를 확인하세요.")
