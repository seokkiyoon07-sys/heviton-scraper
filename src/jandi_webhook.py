"""
잔디(Jandi) 웹훅 전송 모듈
"""
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config.settings import REQUEST_CONFIG

logger = logging.getLogger(__name__)


class JandiWebhook:
    """잔디 Incoming Webhook 클래스"""

    def __init__(self, webhook_url: str):
        """
        Args:
            webhook_url: 잔디 Incoming Webhook URL
        """
        self.webhook_url = webhook_url
        self.headers = {
            "Accept": "application/vnd.tosslab.jandi-v2+json",
            "Content-Type": "application/json",
        }

    def send_message(
        self,
        body: str,
        title: Optional[str] = None,
        color: str = "#2ECC71",
        connect_info: Optional[List[Dict]] = None
    ) -> bool:
        """
        잔디 메시지 전송

        Args:
            body: 메시지 본문
            title: 메시지 제목 (선택)
            color: 메시지 색상 (기본: 초록색)
            connect_info: 추가 연결 정보 리스트

        Returns:
            bool: 전송 성공 여부
        """
        payload = {
            "body": body,
            "connectColor": color,
        }

        if title:
            payload["connectInfo"] = [{
                "title": title,
                "description": body,
            }]

        if connect_info:
            payload["connectInfo"] = connect_info

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=self.headers,
                timeout=REQUEST_CONFIG["timeout"]
            )
            response.raise_for_status()
            logger.info("잔디 메시지 전송 성공")
            return True

        except requests.RequestException as e:
            logger.error(f"잔디 메시지 전송 실패: {e}")
            return False

    def send_generation_report(self, data: Dict[str, Any]) -> bool:
        """
        발전량 리포트 전송

        Args:
            data: 발전량 데이터 (daily, weekly, monthly, dashboard 포함)

        Returns:
            bool: 전송 성공 여부
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 메시지 구성
        connect_info = []

        # 대시보드 요약 (새로운 구조)
        dashboard = data.get("dashboard", {})
        if isinstance(dashboard, dict) and not dashboard.get("data"):
            # 새로운 구조: dashboard가 직접 데이터를 담고 있음
            current_power = dashboard.get("current_power")
            today_gen = dashboard.get("today_generation")
            month_gen = dashboard.get("month_generation")
            total_gen = dashboard.get("total_generation")

            if current_power:
                # 현재 발전량 (W -> kW 변환)
                try:
                    power_kw = float(current_power) / 1000
                    power_str = f"{power_kw:.2f} kW"
                except:
                    power_str = f"{current_power} W"

                connect_info.append({
                    "title": "⚡ 현재 발전량",
                    "description": power_str,
                })

            if today_gen:
                connect_info.append({
                    "title": f"📅 오늘 발전량 ({data.get('daily', {}).get('date', datetime.now().strftime('%Y-%m-%d'))})",
                    "description": f"{today_gen} kWh",
                })

            if month_gen:
                connect_info.append({
                    "title": f"📊 이번달 발전량 ({data.get('monthly', {}).get('year_month', datetime.now().strftime('%Y-%m'))})",
                    "description": f"{month_gen} kWh",
                })

            if total_gen:
                connect_info.append({
                    "title": "📈 누적 발전량",
                    "description": f"{total_gen} MWh",
                })

        # 기존 구조 지원 (호환성)
        else:
            # 일별 발전량
            if "daily" in data:
                daily = data["daily"]
                daily_total = daily.get("total")
                if daily_total:
                    connect_info.append({
                        "title": f"📅 오늘 발전량 ({daily.get('date', '오늘')})",
                        "description": f"{daily_total} kWh",
                    })

            # 월별 발전량
            if "monthly" in data:
                monthly = data["monthly"]
                monthly_total = monthly.get("total")
                if monthly_total:
                    connect_info.append({
                        "title": f"📊 이번달 발전량 ({monthly.get('year_month', '이번 달')})",
                        "description": f"{monthly_total} kWh",
                    })

        # 컨버터 상태 추가
        converter_status = data.get("converter_status", {})
        if converter_status:
            is_normal = converter_status.get("is_normal")
            if is_normal is True:
                connect_info.append({
                    "title": "🟢 설비 상태",
                    "description": "컨버터 정상 작동 중",
                })
            elif is_normal is False:
                error_msgs = converter_status.get("error_messages", [])
                error_text = ", ".join(error_msgs) if error_msgs else "상태 확인 필요"
                connect_info.append({
                    "title": "🔴 설비 상태",
                    "description": f"이상 감지: {error_text}",
                })

        # 최근 5일 발전량 추가
        recent_5days = data.get("recent_5days", [])
        if recent_5days:
            # 최근 5일 데이터를 한 줄로 표시
            recent_text_parts = []
            for day_data in recent_5days:
                date = day_data.get("date", "")
                gen = day_data.get("generation", "-")
                if date and gen != "-":
                    recent_text_parts.append(f"{date}: {gen}kWh")
                elif date:
                    recent_text_parts.append(f"{date}: -")

            if recent_text_parts:
                connect_info.append({
                    "title": "📋 최근 5일 발전량",
                    "description": " | ".join(recent_text_parts),
                })

        if not connect_info:
            connect_info.append({
                "title": "⚠️ 알림",
                "description": "수집된 발전량 데이터가 없습니다.",
            })

        payload = {
            "body": f"🌞 Heviton 발전량 리포트 ({now})",
            "connectColor": "#F5A623",
            "connectInfo": connect_info,
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=self.headers,
                timeout=REQUEST_CONFIG["timeout"]
            )
            response.raise_for_status()
            logger.info("발전량 리포트 전송 성공")
            return True

        except requests.RequestException as e:
            logger.error(f"발전량 리포트 전송 실패: {e}")
            return False

    def send_error_alert(self, error_message: str) -> bool:
        """
        에러 알림 전송

        Args:
            error_message: 에러 메시지

        Returns:
            bool: 전송 성공 여부
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        payload = {
            "body": f"🚨 Heviton 크롤러 에러 발생 ({now})",
            "connectColor": "#E74C3C",
            "connectInfo": [{
                "title": "에러 내용",
                "description": error_message,
            }],
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=self.headers,
                timeout=REQUEST_CONFIG["timeout"]
            )
            response.raise_for_status()
            logger.info("에러 알림 전송 성공")
            return True

        except requests.RequestException as e:
            logger.error(f"에러 알림 전송 실패: {e}")
            return False


# 테스트용
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.DEBUG)

    webhook_url = os.getenv("JANDI_WEBHOOK_URL")
    if webhook_url:
        jandi = JandiWebhook(webhook_url)

        # 테스트 메시지
        jandi.send_message("테스트 메시지입니다.", title="테스트")

        # 테스트 발전량 리포트
        test_data = {
            "daily": {"date": "2024-12-26", "total": "150 kWh", "data": [{"time": "12:00", "generation": "50 kWh"}]},
            "weekly": {"start_date": "2024-12-23", "total": "1,050 kWh", "data": []},
            "monthly": {"year_month": "2024-12", "total": "4,500 kWh", "data": []},
        }
        jandi.send_generation_report(test_data)
    else:
        print("JANDI_WEBHOOK_URL 환경변수를 설정해주세요.")
