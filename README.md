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

## 사용법

```bash
# 전체 데이터 수집 및 전송
python main.py

# 테스트 메시지 전송
python main.py --test

# 디버그 모드
python main.py --debug
```

## 프로젝트 구조

```
heviton-scraper/
├── config/
│   └── settings.py          # 설정
├── src/
│   ├── auth.py               # 로그인 인증 (Selenium)
│   ├── scraper.py            # 데이터 크롤링
│   └── jandi_webhook.py      # 잔디 전송
├── .github/workflows/
│   └── daily-scraper.yml     # GitHub Actions
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
