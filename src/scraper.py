"""
Heviton REMS 모니터링 시스템 데이터 수집 (REST API 기반)
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

import requests

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config.settings import HEVITON_CONFIG, API_ENDPOINTS, REQUEST_CONFIG

logger = logging.getLogger(__name__)


class HevitonScraper:
    """Heviton 발전량 데이터 수집 (REST API 기반)"""

    def __init__(self, session: requests.Session):
        """
        Args:
            session: 인증된 requests.Session (HevitonAuth.get_session())
        """
        self.session = session
        self.api_base = HEVITON_CONFIG["api_base"]
        self._plant_id: Optional[str] = None
        self._plant_name: Optional[str] = None
        self._energy_code: Optional[str] = None

    def _api_get(self, endpoint: str, url_suffix: str = "") -> Optional[Dict]:
        """API GET 요청"""
        url = f"{self.api_base}/{endpoint}"
        if url_suffix:
            url = f"{url}/{url_suffix}"
        try:
            response = self.session.get(url, timeout=REQUEST_CONFIG["timeout"])
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"API 오류 ({endpoint}): HTTP {response.status_code} - {response.text[:300]}")
            return None
        except Exception as e:
            logger.error(f"API 요청 실패 ({endpoint}): {e}")
            return None

    def _api_post(self, endpoint: str, payload: Optional[Dict] = None) -> Optional[Dict]:
        """API POST 요청"""
        url = f"{self.api_base}/{endpoint}"
        try:
            response = self.session.post(url, json=payload or {}, timeout=REQUEST_CONFIG["timeout"])
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"API 오류 ({endpoint}): HTTP {response.status_code} - {response.text[:300]}")
            return None
        except Exception as e:
            logger.error(f"API 요청 실패 ({endpoint}): {e}")
            return None

    def _get_response_data(self, response: Optional[Dict]) -> Any:
        """표준 응답 envelope에서 data 추출: { result: {...}, data: {...} }"""
        if not response or not isinstance(response, dict):
            return None
        # 표준 구조: result.code == 0이면 성공
        result = response.get("result", {})
        if isinstance(result, dict) and result.get("code", -1) != 0:
            msg = result.get("message", "")
            if msg:
                logger.warning(f"API 응답 오류: code={result.get('code')}, message={msg}")
            return None
        return response.get("data")

    def _extract_value(self, data: dict, *keys) -> Optional[Any]:
        """여러 키 이름으로 값 추출 시도"""
        for key in keys:
            val = data.get(key)
            if val is not None:
                return val
        return None

    def _extract_list(self, data: Any) -> list:
        """응답에서 리스트 데이터 추출"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # data.list 패턴 (가장 흔함)
            for key in ("list", "data", "items", "content", "result"):
                inner = data.get(key)
                if isinstance(inner, list):
                    return inner
        return []

    def _get_plant_info(self) -> bool:
        """발전소 정보 조회 (최초 1회 후 캐시) - endUserInfo GET 사용"""
        if self._plant_id and self._plant_name:
            return True

        # 1차: endUserInfo (GET) - 일반 사용자 전용
        data = self._api_get(API_ENDPOINTS["end_user_info"])
        if data:
            payload = self._get_response_data(data)
            if not payload:
                # envelope 없이 직접 data인 경우
                payload = data.get("data", data)

            # 응답이 { "list": [...] } 형태인 경우 첫 번째 항목 추출
            if isinstance(payload, dict) and "list" in payload:
                items = payload.get("list", [])
                if isinstance(items, list) and items:
                    payload = items[0]

            if isinstance(payload, dict):
                self._plant_id = str(payload.get("plantId", payload.get("plant_id", "")))
                self._plant_name = payload.get("plantName", payload.get("plant_name", ""))
                self._energy_code = str(payload.get("energyCode", payload.get("energy_code", "501")))
                if self._plant_id and self._plant_name:
                    logger.info(f"발전소 정보: id={self._plant_id}, name={self._plant_name}, energy={self._energy_code}")
                    return True

        # 2차: plantInfo (GET with plantId suffix) - plantId를 이미 알고 있는 경우
        if self._plant_id:
            info_data = self._api_get(API_ENDPOINTS["plant_info"], url_suffix=self._plant_id)
            if info_data:
                payload = self._get_response_data(info_data) or info_data.get("data", info_data)
                if isinstance(payload, dict):
                    self._plant_name = self._plant_name or payload.get("plantName", payload.get("name", ""))
                    self._energy_code = self._energy_code or str(payload.get("energyCode", "501"))
                    if self._plant_name:
                        logger.info(f"발전소 정보 (plantInfo): name={self._plant_name}, energy={self._energy_code}")
                        return True

        logger.error("발전소 정보를 조회할 수 없음")
        return False

    def _get_plant_id(self) -> Optional[str]:
        """하위 호환성: 발전소 ID만 반환"""
        self._get_plant_info()
        return self._plant_id

    def _make_plant_payload(self, **extra) -> Dict:
        """발전소 기본 POST payload 생성

        주의: API의 'plant_name' 필드에는 사람이 읽는 이름이 아닌
        plantId (시스템 ID)를 전달해야 함
        """
        payload = {
            "plant_name": self._plant_id,  # plantId를 plant_name으로 전달 (API 규칙)
            "energy": self._energy_code,
        }
        payload.update(extra)
        return payload

    def get_monitoring_data(self) -> Dict[str, Any]:
        """
        대시보드 발전량 데이터 조회

        Returns:
            발전량 데이터 (현재, 오늘, 이번달, 누적, 발전시간, 가동일수 등)
        """
        logger.info("모니터링 데이터 조회")

        data = {
            "current_power": None,
            "today_generation": None,
            "month_generation": None,
            "total_generation": None,
            "day_avg_time": None,
            "month_avg_time": None,
            "tot_avg_time": None,
            "day_diff": None,
            "month_diff": None,
            "oper_day": None,
            "recent_date": None,
        }

        try:
            if not self._get_plant_info():
                return {"collected_at": datetime.now().isoformat(), "data": data}

            # plantDetailStatus (POST) - 발전소 운영 정보
            resp = self._api_post(
                API_ENDPOINTS["plant_operation_info"],
                self._make_plant_payload()
            )
            if resp:
                payload = self._get_response_data(resp)
                if not payload:
                    payload = resp.get("data", resp)
                if isinstance(payload, dict):
                    data["current_power"] = self._extract_value(
                        payload, "power", "currentPower", "current_power", "nowPower", "realPower"
                    )
                    data["today_generation"] = self._extract_value(
                        payload, "day_gen", "todayGeneration", "today_generation", "todayGen", "dayGen"
                    )
                    data["month_generation"] = self._extract_value(
                        payload, "month_gen", "monthGeneration", "month_generation", "monthGen"
                    )
                    data["total_generation"] = self._extract_value(
                        payload, "tot_gen", "totalGeneration", "total_generation", "totalGen", "accumGen"
                    )
                    data["day_avg_time"] = payload.get("day_avg_time")
                    data["month_avg_time"] = payload.get("month_avg_time")
                    data["tot_avg_time"] = payload.get("tot_avg_time")
                    data["day_diff"] = payload.get("day_diff")
                    data["month_diff"] = payload.get("month_diff")
                    data["oper_day"] = payload.get("oper_day")
                    data["recent_date"] = payload.get("recentDate")

            # 소수점 2자리 반올림 (숫자 필드만)
            for key in data:
                if isinstance(data[key], (int, float)) and key not in ("oper_day",):
                    data[key] = round(data[key], 2)

            # 0.0 값도 유효한 데이터로 취급 (발전소 미가동 시)
            # 핵심 4개 필드가 모두 None일 때 대안 시도
            core_keys = ("current_power", "today_generation", "month_generation", "total_generation")
            if all(data[k] is None for k in core_keys):
                resp2 = self._api_post(API_ENDPOINTS["device_status"])
                if resp2:
                    payload = self._get_response_data(resp2) or resp2.get("data", resp2)
                    if isinstance(payload, dict):
                        gen = payload.get("gen", {})
                        if isinstance(gen, dict):
                            data["total_generation"] = gen.get("primary")

            logger.info(f"추출된 모니터링 데이터: {data}")
            return {
                "collected_at": datetime.now().isoformat(),
                "data": data,
            }

        except Exception as e:
            logger.error(f"모니터링 데이터 조회 실패: {e}")
            return {"error": str(e), "data": data}

    def get_converter_status(self) -> Dict[str, Any]:
        """
        설비(컨버터/인버터) 상태 확인

        Returns:
            컨버터 상태 정보
        """
        logger.info("컨버터 상태 조회")

        status_data = {
            "is_normal": True,
            "converters": [],
            "error_messages": [],
        }

        try:
            if not self._get_plant_info():
                return status_data

            # plantDetailComposition (POST) - 설비 구성
            resp = self._api_post(
                API_ENDPOINTS["plant_devices"],
                self._make_plant_payload()
            )
            if resp:
                payload = self._get_response_data(resp) or resp.get("data", resp)
                devices = self._extract_list(payload) if payload else []
                for device in devices:
                    if not isinstance(device, dict):
                        continue
                    # 실제 응답 필드: serialNo, instanceId, power, gen, capacity, status, imei
                    serial = device.get("serialNo", device.get("instanceId", ""))
                    name = f"인버터 {serial}" if serial else self._extract_value(
                        device, "deviceName", "name", "inverterName"
                    ) or "Unknown"
                    status_code = str(device.get("status", ""))

                    # 상태 코드: "000"=정상/대기, "001"=경고, "002"=발전중, "003"=미운영
                    is_ok = status_code in ("000", "001", "002", "")
                    power = device.get("power", 0)
                    gen = device.get("gen", 0)
                    status_text = "정상"
                    if power and float(power) > 0:
                        status_text = f"발전중 ({power}kW)"
                    elif status_code == "003":
                        status_text = "미운영"
                        is_ok = False

                    status_data["converters"].append({
                        "name": str(name),
                        "status": status_text,
                        "generation": gen,
                    })

                    if not is_ok:
                        status_data["is_normal"] = False

            # dashboardEvent (POST) - 오늘의 이벤트에서 에러 확인
            # 참고: 이 엔드포인트는 특수한 DTO 구조 필요, 실패 시 무시
            event_resp = self._api_post(
                API_ENDPOINTS["event_today"],
                {"energy": [self._energy_code], "page": 0, "size": 20}
            )
            if event_resp:
                payload = self._get_response_data(event_resp) or event_resp.get("data", event_resp)
                events = self._extract_list(payload) if payload else []
                for evt in events:
                    if not isinstance(evt, dict):
                        continue
                    grade = str(self._extract_value(evt, "grade", "level", "severity", "type") or "").lower()
                    if grade in ("error", "critical", "fault", "danger"):
                        status_data["is_normal"] = False
                        msg = self._extract_value(
                            evt, "message", "description", "eventName", "content"
                        ) or "이벤트 감지"
                        status_data["error_messages"].append(str(msg))

            logger.info(f"컨버터 상태: {'정상' if status_data['is_normal'] else '이상'}")
            return status_data

        except Exception as e:
            logger.error(f"컨버터 상태 조회 실패: {e}")
            return {"is_normal": None, "error": str(e)}

    def get_recent_daily_data(self, days: int = 5) -> tuple:
        """
        최근 N일간 일별 발전량 데이터 및 오늘 날씨 조회

        Args:
            days: 조회할 일수 (기본 5일)

        Returns:
            (최근 N일간 발전량 리스트, 오늘 날씨 dict)
        """
        logger.info(f"최근 {days}일 발전량 조회")

        recent_data = []
        today_weather = {}
        today = datetime.now()
        today_str = today.strftime("%Y%m%d")
        start_date = (today - timedelta(days=days - 1)).strftime("%Y%m%d")
        end_date = today_str

        try:
            if not self._get_plant_info():
                return self._empty_daily_data(days), today_weather

            # plantDetailTrendPrimary (POST) - 일별 추이
            resp = self._api_post(
                API_ENDPOINTS["plant_detail_ranged"],
                self._make_plant_payload(
                    date_type="day",
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            if resp:
                payload = self._get_response_data(resp) or resp.get("data", resp)
                items = self._extract_list(payload) if payload else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    date_str = self._extract_value(
                        item, "date", "genDate", "collectDate", "statDate"
                    ) or ""
                    gen_value = self._extract_value(
                        item, "gen", "generation", "genAmount", "dayGen", "value", "totalGen"
                    )

                    # 오늘 날씨 정보 추출
                    raw_date = str(date_str).replace("-", "")[:8]
                    if raw_date == today_str:
                        today_weather = {
                            "weather": item.get("weth"),
                            "high_temp": item.get("highTemp"),
                            "low_temp": item.get("lowTemp"),
                            "humidity": item.get("reh"),
                            "radiation": item.get("rad"),
                        }

                    if date_str:
                        try:
                            parsed = datetime.strptime(raw_date, "%Y%m%d")
                            date_formatted = parsed.strftime("%m/%d")
                        except ValueError:
                            date_formatted = str(date_str)
                        if gen_value is not None:
                            try:
                                gen_value = round(float(gen_value), 2)
                            except (ValueError, TypeError):
                                pass
                        recent_data.append({
                            "date": date_formatted,
                            "generation": str(gen_value) if gen_value is not None else "-",
                        })

            # 폴백: 빈 데이터
            if not recent_data:
                return self._empty_daily_data(days), today_weather

            logger.info(f"최근 {days}일 발전량 데이터: {len(recent_data)} 건")
            return recent_data[:days], today_weather

        except Exception as e:
            logger.error(f"최근 발전량 조회 실패: {e}")
            return [], today_weather

    def _empty_daily_data(self, days: int) -> list:
        """빈 일별 데이터 생성"""
        today = datetime.now()
        return [
            {
                "date": (today - timedelta(days=i)).strftime("%m/%d"),
                "generation": "-",
            }
            for i in range(days - 1, -1, -1)
        ]

    def get_today_hourly_data(self) -> list:
        """
        오늘 시간별 발전량 조회

        Returns:
            [{"hour": 0~23, "generation": float}, ...]
        """
        logger.info("오늘 시간별 발전량 조회")

        hourly_data = []
        today_str = datetime.now().strftime("%Y%m%d")

        try:
            if not self._get_plant_info():
                return hourly_data

            resp = self._api_post(
                API_ENDPOINTS["plant_detail_ranged"],
                self._make_plant_payload(
                    date_type="hour",
                    start_date=today_str,
                    end_date=today_str,
                )
            )
            if not resp:
                return hourly_data

            payload = self._get_response_data(resp) or resp.get("data", resp)
            items = self._extract_list(payload) if payload else []

            for item in items:
                if not isinstance(item, dict):
                    continue

                hour_val = self._extract_value(
                    item, "hour", "hh", "time", "tm", "collectTime", "statTime", "date"
                )
                gen_val = self._extract_value(
                    item, "gen", "generation", "genAmount", "hourGen", "value", "totalGen"
                )
                if hour_val is None or gen_val is None:
                    continue

                hour_str = str(hour_val).strip()
                hour = None
                # 0~23 형태
                if hour_str.isdigit():
                    hour = int(hour_str)
                # HH:mm 또는 YYYYMMDDHH 등에서 시각 추출
                elif ":" in hour_str:
                    part = hour_str.split(":", 1)[0]
                    if part.isdigit():
                        hour = int(part)
                elif len(hour_str) >= 10 and hour_str[-2:].isdigit():
                    hour = int(hour_str[-2:])

                if hour is None or not (0 <= hour <= 23):
                    continue

                try:
                    gen = round(float(gen_val), 4)
                except (TypeError, ValueError):
                    continue

                hourly_data.append({"hour": hour, "generation": gen})

            # 동일 시간 중복 시 마지막 값 유지
            uniq = {}
            for row in hourly_data:
                uniq[row["hour"]] = row["generation"]

            normalized = [{"hour": h, "generation": uniq[h]} for h in sorted(uniq.keys())]
            logger.info(f"시간별 발전량 데이터: {len(normalized)} 건")
            return normalized

        except Exception as e:
            logger.error(f"시간별 발전량 조회 실패: {e}")
            return []

    def get_daily_generation_range(self, start_date: str, end_date: str) -> list:
        """
        기간별 일 발전량 조회

        Args:
            start_date: YYYYMMDD
            end_date: YYYYMMDD

        Returns:
            [{"date": "YYYY-MM-DD", "generation": float}, ...]
        """
        logger.info(f"일 발전량 범위 조회: {start_date} ~ {end_date}")
        rows = []

        try:
            if not self._get_plant_info():
                return rows

            resp = self._api_post(
                API_ENDPOINTS["plant_detail_ranged"],
                self._make_plant_payload(
                    date_type="day",
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            if not resp:
                return rows

            payload = self._get_response_data(resp) or resp.get("data", resp)
            items = self._extract_list(payload) if payload else []

            for item in items:
                if not isinstance(item, dict):
                    continue
                date_str = self._extract_value(item, "date", "genDate", "collectDate", "statDate")
                gen_val = self._extract_value(item, "gen", "generation", "genAmount", "dayGen", "value", "totalGen")
                if date_str is None or gen_val is None:
                    continue

                raw = str(date_str).replace("-", "")[:8]
                try:
                    dt = datetime.strptime(raw, "%Y%m%d")
                    date_out = dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

                try:
                    gen = round(float(gen_val), 4)
                except (TypeError, ValueError):
                    continue

                rows.append({"date": date_out, "generation": gen})

            # 날짜 오름차순 정렬 및 중복 제거
            dedup = {}
            for row in rows:
                dedup[row["date"]] = row["generation"]
            normalized = [{"date": d, "generation": dedup[d]} for d in sorted(dedup.keys())]
            logger.info(f"일 발전량 범위 데이터: {len(normalized)} 건")
            return normalized

        except Exception as e:
            logger.error(f"일 발전량 범위 조회 실패: {e}")
            return []

    def get_statistics_data(self) -> Dict[str, Any]:
        """
        통계 데이터 조회

        Returns:
            일별/월별 통계 데이터
        """
        logger.info("통계 데이터 조회")

        data = {"daily": [], "monthly": []}

        try:
            if not self._get_plant_info():
                return {"collected_at": datetime.now().isoformat(), "data": data}

            today = datetime.now()
            start_of_month = today.replace(day=1).strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")

            resp = self._api_post(
                API_ENDPOINTS["plant_detail_ranged"],
                self._make_plant_payload(
                    date_type="day",
                    start_date=start_of_month,
                    end_date=end_date,
                )
            )
            if resp:
                payload = self._get_response_data(resp) or resp.get("data", resp)
                items = self._extract_list(payload) if payload else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    date_str = self._extract_value(item, "date", "genDate", "statDate") or ""
                    gen_value = self._extract_value(item, "gen", "generation", "genAmount", "value") or ""
                    data["daily"].append({
                        "date": str(date_str),
                        "generation": str(gen_value),
                    })

            logger.info(f"추출된 통계 데이터: {len(data['daily'])} 건")
            return {"collected_at": datetime.now().isoformat(), "data": data}

        except Exception as e:
            logger.error(f"통계 데이터 조회 실패: {e}")
            return {"error": str(e), "data": data}

    def get_year_statistics(self) -> Dict[str, Any]:
        """
        연도별 발전 통계 조회 (발전량, 발전시간, 일사량, 온도)

        Returns:
            연도별 통계 데이터
        """
        logger.info("연도별 통계 데이터 조회")

        result = {"years": [], "this_year": {}}

        try:
            if not self._get_plant_info():
                return result

            today = datetime.now()
            resp = self._api_post(
                API_ENDPOINTS["plant_detail_ranged"],
                self._make_plant_payload(
                    date_type="year",
                    start_date=str(today.year - 2),
                    end_date=str(today.year),
                )
            )
            if resp:
                payload = self._get_response_data(resp)
                if isinstance(payload, dict):
                    items = payload.get("list", [])
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        year_data = {
                            "date": item.get("date", ""),
                            "gen": round(item.get("gen", 0), 2),
                            "genTime": round(item.get("genTime", 0), 3),
                            "rad": round(item.get("rad", 0), 4) if item.get("rad") is not None else None,
                            "temp": round(item.get("temp", 0), 2) if item.get("temp") is not None else None,
                        }
                        result["years"].append(year_data)
                        if str(year_data["date"]) == str(today.year):
                            result["this_year"] = year_data

            logger.info(f"연도별 통계: {len(result['years'])}년")
            return result

        except Exception as e:
            logger.error(f"연도별 통계 조회 실패: {e}")
            return result

    def get_all_data(self) -> Dict[str, Any]:
        """
        모든 발전량 데이터 조회

        Returns:
            통합 데이터 (기존 구조 호환)
        """
        logger.info("전체 발전량 데이터 조회 시작")

        # 1. 모니터링 데이터 (발전량, 발전시간, 가동일수 포함)
        monitoring = self.get_monitoring_data()
        mon_data = monitoring.get("data", {})

        # 2. 컨버터 상태
        converter_status = self.get_converter_status()

        # 3. 최근 5일 발전량 + 오늘 날씨
        recent_5days, today_weather = self.get_recent_daily_data(5)

        # 4. 오늘 시간별 발전량
        today_hourly = self.get_today_hourly_data()

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
            "operation": {
                "day_avg_time": mon_data.get("day_avg_time"),
                "month_avg_time": mon_data.get("month_avg_time"),
                "tot_avg_time": mon_data.get("tot_avg_time"),
                "day_diff": mon_data.get("day_diff"),
                "month_diff": mon_data.get("month_diff"),
                "oper_day": mon_data.get("oper_day"),
                "recent_date": mon_data.get("recent_date"),
            },
            "today_weather": today_weather,
            "converter_status": converter_status,
            "recent_5days": recent_5days,
            "today_hourly": today_hourly,
        }


def discover_api(session: requests.Session):
    """API 엔드포인트 탐색 (개발/디버깅용)"""
    api_base = HEVITON_CONFIG["api_base"]

    # GET 엔드포인트 (JS 번들에서 확인)
    get_endpoints = {"end_user_info", "plant_info", "user_profile"}
    skip = {"login", "logout", "token_reissue"}

    # 먼저 endUserInfo로 발전소 정보 조회
    print(f"\n{'='*60}")
    print("[end_user_info] GET - 발전소 기본 정보 조회")
    url = f"{api_base}/{API_ENDPOINTS['end_user_info']}"
    plant_name = None
    energy_code = None
    plant_id = None
    try:
        resp = session.get(url, timeout=30)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {resp.text[:500]}")
        payload = data.get("data", data)
        # 응답이 { "list": [...] } 형태인 경우 첫 번째 항목 추출
        if isinstance(payload, dict) and "list" in payload:
            items = payload.get("list", [])
            if isinstance(items, list) and items:
                payload = items[0]
        if isinstance(payload, dict):
            plant_name = payload.get("plantName", payload.get("plant_name"))
            energy_code = str(payload.get("energyCode", payload.get("energy_code", "501")))
            plant_id = str(payload.get("plantId", payload.get("plant_id", "")))
            print(f"\n  -> plantId={plant_id}, plantName={plant_name}, energyCode={energy_code}")
    except Exception as e:
        print(f"Error: {e}")

    # 나머지 엔드포인트 탐색
    for name, endpoint in API_ENDPOINTS.items():
        if name in skip or name == "end_user_info":
            continue

        url = f"{api_base}/{endpoint}"
        is_get = name in get_endpoints
        method = "GET" if is_get else "POST"

        print(f"\n{'='*60}")
        print(f"[{name}] {method} {url}")

        try:
            if is_get:
                suffix = f"/{plant_id}" if name == "plant_info" and plant_id else ""
                resp = session.get(url + suffix, timeout=30)
            else:
                # POST: plant_name 필드에 plantId 전달 (API 규칙)
                payload = {}
                if plant_id and energy_code:
                    payload = {"plant_name": plant_id, "energy": energy_code}
                    if name == "plant_detail_ranged":
                        today = datetime.now()
                        payload.update({
                            "date_type": "day",
                            "start_date": (today - timedelta(days=5)).strftime("%Y-%m-%d"),
                            "end_date": today.strftime("%Y-%m-%d"),
                        })
                resp = session.post(url, json=payload, timeout=30)

            print(f"Status: {resp.status_code}")
            try:
                data = resp.json()
                if isinstance(data, dict):
                    print(f"Keys: {list(data.keys())}")
                    result = data.get("result", {})
                    if isinstance(result, dict):
                        print(f"  result: code={result.get('code')}, message={result.get('message', '')}")
                    inner = data.get("data")
                    if isinstance(inner, dict):
                        print(f"  data Keys: {list(inner.keys())}")
                    elif isinstance(inner, list):
                        print(f"  data: list[{len(inner)}]")
                        if inner and isinstance(inner[0], dict):
                            print(f"  first item keys: {list(inner[0].keys())}")
                print(f"Body: {resp.text[:500]}")
            except Exception:
                print(f"Body (non-JSON): {resp.text[:300]}")
        except Exception as e:
            print(f"Error: {e}")


# 테스트용
if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.DEBUG)

    from auth import HevitonAuth

    with HevitonAuth() as auth:
        if auth.is_logged_in:
            scraper = HevitonScraper(auth.get_session())
            data = scraper.get_all_data()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("로그인 실패!")
