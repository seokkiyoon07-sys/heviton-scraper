"""
잔디(Jandi) 웹훅 전송 모듈
"""
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config.settings import REQUEST_CONFIG, SAVINGS_CONFIG
from src.tariff import estimate_savings, estimate_daily_savings_from_hourly

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
            data: 발전량 데이터 (daily, weekly, monthly, dashboard, operation, year_statistics 포함)

        Returns:
            bool: 전송 성공 여부
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 메시지 구성
        connect_info = []

        # 대시보드 요약 (새로운 구조)
        dashboard = data.get("dashboard", {})
        if isinstance(dashboard, dict) and not dashboard.get("data"):
            current_power = dashboard.get("current_power")
            today_gen = dashboard.get("today_generation")
            month_gen = dashboard.get("month_generation")
            total_gen = dashboard.get("total_generation")

            if current_power is not None:
                connect_info.append({
                    "title": "⚡ 현재 발전량",
                    "description": f"{current_power} kW",
                })

            if today_gen is not None:
                # 발전시간 포함
                operation = data.get("operation", {})
                day_time = operation.get("day_avg_time")
                day_diff = operation.get("day_diff")
                desc_parts = [f"{today_gen} kWh"]
                if day_time is not None:
                    desc_parts.append(f"발전시간 {day_time}h")
                if day_diff is not None:
                    sign = "+" if day_diff > 0 else ""
                    desc_parts.append(f"전일대비 {sign}{day_diff}%")
                connect_info.append({
                    "title": f"📅 오늘 발전량 ({data.get('daily', {}).get('date', datetime.now().strftime('%Y-%m-%d'))})",
                    "description": " | ".join(desc_parts),
                })

            if month_gen is not None:
                operation = data.get("operation", {})
                month_time = operation.get("month_avg_time")
                desc_parts = [f"{month_gen} kWh"]
                if month_time is not None:
                    desc_parts.append(f"평균 발전시간 {month_time}h")
                connect_info.append({
                    "title": f"📊 이번달 발전량 ({data.get('monthly', {}).get('year_month', datetime.now().strftime('%Y-%m'))})",
                    "description": " | ".join(desc_parts),
                })

            if total_gen is not None:
                operation = data.get("operation", {})
                oper_day = operation.get("oper_day")
                try:
                    total_mwh = float(total_gen) / 1000
                    gen_str = f"{total_mwh:,.2f} MWh"
                except (ValueError, TypeError):
                    gen_str = f"{total_gen} kWh"
                desc_parts = [gen_str]
                if oper_day is not None:
                    desc_parts.append(f"가동 {oper_day}일")
                connect_info.append({
                    "title": "📈 누적 발전량",
                    "description": " | ".join(desc_parts),
                })

        # 기존 구조 지원 (호환성)
        else:
            if "daily" in data:
                daily = data["daily"]
                daily_total = daily.get("total")
                if daily_total:
                    connect_info.append({
                        "title": f"📅 오늘 발전량 ({daily.get('date', '오늘')})",
                        "description": f"{daily_total} kWh",
                    })

            if "monthly" in data:
                monthly = data["monthly"]
                monthly_total = monthly.get("total")
                if monthly_total:
                    connect_info.append({
                        "title": f"📊 이번달 발전량 ({monthly.get('year_month', '이번 달')})",
                        "description": f"{monthly_total} kWh",
                    })

        # 발전 절감액 (시간대 요금)
        if SAVINGS_CONFIG.get("enabled"):
            dashboard = data.get("dashboard", {}) if isinstance(data.get("dashboard"), dict) else {}
            weighted_savings = estimate_savings(
                today_generation=dashboard.get("today_generation"),
                month_generation=dashboard.get("month_generation"),
                tou_rates=SAVINGS_CONFIG.get("tou_rates", {}),
                tou_ratios=SAVINGS_CONFIG.get("tou_ratios", {}),
            )
            hourly_savings = estimate_daily_savings_from_hourly(
                hourly_data=data.get("today_hourly", []),
                tou_rates=SAVINGS_CONFIG.get("tou_rates", {}),
            )
            savings = hourly_savings or weighted_savings
            if savings:
                today_saving = savings.get("today_saving")
                month_saving = weighted_savings.get("month_saving") if weighted_savings else None
                weighted = savings.get("weighted_unit_price")
                season = savings.get("season")

                season_text = {
                    "summer": "하계",
                    "winter": "동계",
                    "spring_fall": "봄가을",
                }.get(str(season), str(season))

                desc_parts = [f"가중단가 {weighted:,.2f}{SAVINGS_CONFIG['currency']}/kWh ({season_text})"]
                if today_saving is not None:
                    desc_parts.append(f"오늘 {today_saving:,.0f}{SAVINGS_CONFIG['currency']}")
                if month_saving is not None:
                    desc_parts.append(f"이번달 {month_saving:,.0f}{SAVINGS_CONFIG['currency']}")
                if hourly_savings:
                    period_kwh = hourly_savings.get("kwh_by_period", {})
                    off = period_kwh.get("off_peak", 0.0)
                    mid = period_kwh.get("mid_peak", 0.0)
                    onp = period_kwh.get("on_peak", 0.0)
                    desc_parts.append(f"실측분배 경/중/최 {off:.2f}/{mid:.2f}/{onp:.2f}kWh")
                    desc_parts.append("오늘값 기준: 시간별 실측")
                else:
                    desc_parts.append("오늘값 기준: 시간대 비율 추정")
                tariff_name = SAVINGS_CONFIG.get("tariff_name")
                if tariff_name:
                    desc_parts.append(f"요금제 {tariff_name}")

                contract_power = SAVINGS_CONFIG.get("contract_power_kw")
                basic_per_kw = SAVINGS_CONFIG.get("basic_charge_per_kw")
                if isinstance(contract_power, (int, float)) and isinstance(basic_per_kw, (int, float)):
                    basic_monthly = contract_power * basic_per_kw
                    desc_parts.append(
                        f"월 기본요금 {basic_monthly:,.0f}{SAVINGS_CONFIG['currency']} "
                        f"({contract_power:g}kW×{basic_per_kw:,.0f})"
                    )

                connect_info.append({
                    "title": "💰 예상 절감액",
                    "description": " | ".join(desc_parts),
                })

        # 오늘 날씨
        today_weather = data.get("today_weather", {})
        if today_weather:
            weather_parts = []
            if today_weather.get("weather") is not None:
                weather_parts.append(f"{today_weather['weather']}")
            high = today_weather.get("high_temp")
            low = today_weather.get("low_temp")
            if high is not None and low is not None:
                weather_parts.append(f"{low}~{high}°C")
            elif high is not None:
                weather_parts.append(f"{high}°C")
            if today_weather.get("humidity") is not None:
                weather_parts.append(f"습도 {today_weather['humidity']}%")
            if today_weather.get("radiation") is not None:
                radiation = today_weather.get("radiation")
                try:
                    radiation_text = f"{float(radiation):.5f}"
                except (ValueError, TypeError):
                    radiation_text = str(radiation)
                weather_parts.append(f"일사량 {radiation_text}kWh/m²")
            if weather_parts:
                connect_info.append({
                    "title": "🌤️ 오늘 날씨",
                    "description": " | ".join(weather_parts),
                })

        # 컨버터 상태
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

        # 최근 5일 발전량
        recent_5days = data.get("recent_5days", [])
        if recent_5days:
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
