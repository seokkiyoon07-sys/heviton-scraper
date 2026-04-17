"""
산업용(을) 고압 시간대별 요금 기반 태양광 절감액 계산
"""
from datetime import datetime
from typing import Any, Dict, Optional


def _to_float(value: Any) -> Optional[float]:
    """숫자 변환 (문자열/숫자 모두 허용)"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_season_key(month: int) -> str:
    """
    한전 계절 구분에 맞춘 기본 키
    - summer: 7~8월
    - winter: 11~2월
    - spring_fall: 3~6월, 9~10월
    """
    if month in (7, 8):
        return "summer"
    if month in (11, 12, 1, 2):
        return "winter"
    return "spring_fall"


def _normalize_ratio(raw_ratio: Dict[str, Any]) -> Dict[str, float]:
    """
    시간대 비율 정규화
    키: off_peak, mid_peak, on_peak
    """
    ratio = {
        "off_peak": _to_float(raw_ratio.get("off_peak")) or 0.0,
        "mid_peak": _to_float(raw_ratio.get("mid_peak")) or 0.0,
        "on_peak": _to_float(raw_ratio.get("on_peak")) or 0.0,
    }
    total = ratio["off_peak"] + ratio["mid_peak"] + ratio["on_peak"]
    if total <= 0:
        return {"off_peak": 0.0, "mid_peak": 0.0, "on_peak": 0.0}
    return {k: v / total for k, v in ratio.items()}


def estimate_savings(
    today_generation: Any,
    month_generation: Any,
    tou_rates: Dict[str, Dict[str, float]],
    tou_ratios: Dict[str, Dict[str, float]],
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """
    시간대 요금 가중 평균으로 절감액 추정

    Returns:
        {
            "season": "summer|winter|spring_fall",
            "weighted_unit_price": float,
            "today_saving": float|None,
            "month_saving": float|None,
            "rates": {...},
            "ratios": {...},
        }
    """
    current = now or datetime.now()
    season = _get_season_key(current.month)

    rates_raw = tou_rates.get(season, {})
    ratios_raw = tou_ratios.get(season, {})

    rates = {
        "off_peak": _to_float(rates_raw.get("off_peak")),
        "mid_peak": _to_float(rates_raw.get("mid_peak")),
        "on_peak": _to_float(rates_raw.get("on_peak")),
    }
    if any(v is None for v in rates.values()):
        return None

    ratios = _normalize_ratio(ratios_raw)
    if ratios["off_peak"] == 0 and ratios["mid_peak"] == 0 and ratios["on_peak"] == 0:
        return None

    weighted = (
        rates["off_peak"] * ratios["off_peak"]
        + rates["mid_peak"] * ratios["mid_peak"]
        + rates["on_peak"] * ratios["on_peak"]
    )

    today_kwh = _to_float(today_generation)
    month_kwh = _to_float(month_generation)

    return {
        "season": season,
        "weighted_unit_price": weighted,
        "today_saving": (today_kwh * weighted) if today_kwh is not None else None,
        "month_saving": (month_kwh * weighted) if month_kwh is not None else None,
        "rates": rates,
        "ratios": ratios,
    }


def _classify_tou_period(season: str, hour: int) -> str:
    """
    계절별 시간대 구분
    반환: off_peak | mid_peak | on_peak
    """
    # 공통 경부하: 22:00~08:00
    if hour >= 22 or hour < 8:
        return "off_peak"

    if season == "winter":
        # 겨울철: 중간(08~09,12~16,19~22), 최대(09~12,16~19)
        if 8 <= hour < 9 or 12 <= hour < 16 or 19 <= hour < 22:
            return "mid_peak"
        return "on_peak"

    # 여름/봄가을: 중간(08~15,21~22), 최대(15~21)
    if 8 <= hour < 15 or 21 <= hour < 22:
        return "mid_peak"
    return "on_peak"


def _weighted_unit_price_for_season(
    season: str,
    tou_rates: Dict[str, Dict[str, float]],
    tou_ratios: Dict[str, Dict[str, float]],
) -> Optional[float]:
    """계절별 가중 단가(원/kWh) 계산"""
    rates_raw = tou_rates.get(season, {})
    ratios_raw = tou_ratios.get(season, {})

    rates = {
        "off_peak": _to_float(rates_raw.get("off_peak")),
        "mid_peak": _to_float(rates_raw.get("mid_peak")),
        "on_peak": _to_float(rates_raw.get("on_peak")),
    }
    if any(v is None for v in rates.values()):
        return None

    ratios = _normalize_ratio(ratios_raw)
    if ratios["off_peak"] == 0 and ratios["mid_peak"] == 0 and ratios["on_peak"] == 0:
        return None

    return (
        rates["off_peak"] * ratios["off_peak"]
        + rates["mid_peak"] * ratios["mid_peak"]
        + rates["on_peak"] * ratios["on_peak"]
    )


def estimate_daily_savings_from_hourly(
    hourly_data: Any,
    tou_rates: Dict[str, Dict[str, float]],
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """
    시간별 발전량 실측 기반 일일 절감액 계산

    hourly_data 형식:
    [{"hour": 0~23, "generation": kWh}, ...]
    """
    if not isinstance(hourly_data, list) or not hourly_data:
        return None

    current = now or datetime.now()
    season = _get_season_key(current.month)
    rates_raw = tou_rates.get(season, {})
    rates = {
        "off_peak": _to_float(rates_raw.get("off_peak")),
        "mid_peak": _to_float(rates_raw.get("mid_peak")),
        "on_peak": _to_float(rates_raw.get("on_peak")),
    }
    if any(v is None for v in rates.values()):
        return None

    kwh_by_period = {"off_peak": 0.0, "mid_peak": 0.0, "on_peak": 0.0}
    total_kwh = 0.0

    for row in hourly_data:
        if not isinstance(row, dict):
            continue
        hour = row.get("hour")
        gen = _to_float(row.get("generation"))
        if not isinstance(hour, int) or not (0 <= hour <= 23) or gen is None:
            continue
        period = _classify_tou_period(season, hour)
        kwh_by_period[period] += gen
        total_kwh += gen

    if total_kwh <= 0:
        return None

    saving = (
        kwh_by_period["off_peak"] * rates["off_peak"]
        + kwh_by_period["mid_peak"] * rates["mid_peak"]
        + kwh_by_period["on_peak"] * rates["on_peak"]
    )
    unit_price = saving / total_kwh

    return {
        "season": season,
        "today_saving": saving,
        "today_generation": total_kwh,
        "weighted_unit_price": unit_price,
        "kwh_by_period": kwh_by_period,
        "rates": rates,
    }


def estimate_period_savings_from_daily_records(
    daily_records: Any,
    tou_rates: Dict[str, Dict[str, float]],
    tou_ratios: Dict[str, Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    """
    일별 발전량 목록으로 기간 절감액 계산 (일별 가중단가 적용)

    daily_records 형식:
    [{"date": "YYYY-MM-DD", "generation": float}, ...]
    """
    if not isinstance(daily_records, list) or not daily_records:
        return None

    total_gen = 0.0
    total_saving = 0.0
    valid_days = 0

    for row in daily_records:
        if not isinstance(row, dict):
            continue
        date_str = str(row.get("date", "")).strip()
        gen = _to_float(row.get("generation"))
        if not date_str or gen is None:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        season = _get_season_key(dt.month)
        unit_price = _weighted_unit_price_for_season(season, tou_rates, tou_ratios)
        if unit_price is None:
            continue

        total_gen += gen
        total_saving += gen * unit_price
        valid_days += 1

    if valid_days == 0 or total_gen <= 0:
        return None

    return {
        "total_generation": total_gen,
        "total_saving": total_saving,
        "avg_unit_price": total_saving / total_gen,
        "days": valid_days,
    }
