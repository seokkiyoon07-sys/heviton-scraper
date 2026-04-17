# Heviton 태양광 발전량 모니터링 크롤러

Heviton 모니터링 시스템에서 태양광 발전량 데이터를 수집하여 잔디(Jandi)로 전송하는 자동화 크롤러입니다.

## 기능

- 일별/월별/누적 발전량 데이터 수집
- 잔디 Webhook을 통한 알림 전송
- 자동화 실행 지원 (cron, GitHub Actions, Docker)

## 설치 및 실행

### 1. 로컬 실행

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일 편집하여 실제 값 입력

# 실행
python main.py
```

### 2. Docker 실행

```bash
# 빌드 및 실행
docker-compose up --build

# 테스트 메시지만 전송
docker-compose run --rm test-webhook
```

### 3. GitHub Actions (권장)

1. GitHub에 저장소 생성
2. Repository Settings > Secrets에 환경변수 추가:
   - `HEVITON_USER_ID`
   - `HEVITON_PASSWORD`
   - `HEVITON_BASE_URL`
   - `JANDI_WEBHOOK_URL`
3. 매일 오후 6시(KST)에 자동 실행

## 환경변수

| 변수명 | 설명 |
|--------|------|
| `HEVITON_USER_ID` | Heviton 로그인 ID |
| `HEVITON_PASSWORD` | Heviton 로그인 비밀번호 |
| `HEVITON_BASE_URL` | Heviton 사이트 URL (기본: https://monitoring.heviton.com) |
| `JANDI_WEBHOOK_URL` | 잔디 Incoming Webhook URL |
| `TOU_SAVINGS_ENABLED` | 시간대 요금 기반 절감액 계산 활성화 (`true`/`false`, 기본 `true`) |
| `TOU_TARIFF_NAME` | 요금제 표시명 (기본: `일반용전력(갑) II / 고압A / 선택II`) |
| `TOU_CONTRACT_POWER_KW` | 계약전력 kW (기본: `250`) |
| `TOU_BASIC_CHARGE_PER_KW` | 기본요금 단가 원/kW (기본: `8230`) |
| `TOU_RATES_JSON` | 계절별 시간대 단가 JSON (`summer/winter/spring_fall` → `off_peak/mid_peak/on_peak`) |
| `TOU_RATIOS_JSON` | 계절별 태양광 시간대 발전비율 JSON (`summer/winter/spring_fall` → `off_peak/mid_peak/on_peak`) |

예시:

```bash
export TOU_TARIFF_NAME='일반용전력(갑) II / 고압A / 선택II'
export TOU_CONTRACT_POWER_KW='250'
export TOU_BASIC_CHARGE_PER_KW='8230'
export TOU_RATES_JSON='{"summer":{"off_peak":84.1,"mid_peak":135.3,"on_peak":157.8},"winter":{"off_peak":92.8,"mid_peak":123.2,"on_peak":138.0},"spring_fall":{"off_peak":84.1,"mid_peak":91.5,"on_peak":102.8}}'
export TOU_RATIOS_JSON='{"summer":{"off_peak":0.05,"mid_peak":0.35,"on_peak":0.60},"winter":{"off_peak":0.08,"mid_peak":0.42,"on_peak":0.50},"spring_fall":{"off_peak":0.06,"mid_peak":0.40,"on_peak":0.54}}'
```

참고: 현재 절감액은 시간대별 실측 발전량이 아닌 시간대 비율 가중치 기반 "추정값"입니다.
최신 로직은 `collect/plant/detail/ranged`의 `date_type=hour` 조회 성공 시 오늘 절감액을 시간별 실측으로 계산하고, 실패 시 비율 추정으로 자동 폴백합니다.

## 사용법

```bash
# 전체 데이터 수집 및 전송
python main.py

# 테스트 메시지 전송
python main.py --test

# 디버그 모드
python main.py --debug

# 절감 리포트 전송 (일/주/월)
python main.py --report-period daily
python main.py --report-period weekly
python main.py --report-period monthly
```

## 절감 리포트 스케줄 (GitHub Actions)

- 일별: 발전량 리포트 1회에 절감액 포함 (중복 발송 없음)
- 주별: 매주 일요일 19:00 KST (`0 10 * * 0` UTC)
- 월별: 매월 1일 19:00 KST (`0 10 1 * *` UTC)

워크플로우 파일:
- `.github/workflows/weekly-savings-report.yml`
- `.github/workflows/monthly-savings-report.yml`

## 프로젝트 구조

```
heviton-scraper/
├── config/
│   └── settings.py          # 설정
├── src/
│   ├── auth.py               # 로그인 인증 (REST API)
│   ├── scraper.py            # 데이터 크롤링
│   ├── tariff.py             # 요금/절감액 계산
│   └── jandi_webhook.py      # 잔디 전송
├── .github/workflows/
│   ├── weekly-savings-report.yml
│   └── monthly-savings-report.yml
├── main.py                   # 메인 실행
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 수집 데이터

- **현재 발전량** (kW)
- **오늘 발전량** (kWh)
- **이번달 발전량** (kWh)
- **누적 발전량** (MWh)
