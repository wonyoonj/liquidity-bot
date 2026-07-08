# 원뎅이 유동성 봇 — 매일 자동 카드뉴스 + 텔레그램 게시

Selenium 로그인 자동화 대신, **공식 API(Telegram Bot API)** 기반으로 안전하게
매일 "오늘의 시장 유동성 요약 카드"를 자동 생성/게시하는 파이썬 프로젝트입니다.

계산 로직은 웹사이트(index.html)의 `updateLiquidityFlowAnimation()` 함수 안
"시장 Total 유동 공급량" 공식을 파이썬으로 1:1 재구현했고, 데이터는 사이트가
이미 쓰고 있는 Netlify 함수(`/.netlify/functions/get-csv-data`)를 그대로
호출하므로 **웹사이트에 표시되는 숫자와 100% 동일**합니다.

```
liquidity_bot/
├── daily_post.py              # 메인 실행 스크립트
├── requirements.txt
├── .env.example
├── fonts/                     # 나눔고딕 (한글 카드 렌더링용, 이미 포함됨)
├── lib/
│   ├── fetch_data.py          # 데이터 수집
│   ├── compute_liquidity.py   # 유동성 공식 계산 (JS 로직 이식)
│   ├── generate_card.py       # 카드뉴스 이미지 생성 (Pillow)
│   └── post_telegram.py       # 텔레그램 전송
└── .github/workflows/
    └── daily_post.yml         # GitHub Actions 매일 자동 실행 설정
```

---

## 1. 로컬에서 먼저 테스트하기

```bash
cd liquidity_bot
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="여기에_봇토큰"
export TELEGRAM_CHAT_ID="여기에_채팅ID"
python daily_post.py
```

### 텔레그램 봇 만들기 (5분)
1. 텔레그램 앱에서 `@BotFather` 검색 → 대화 시작
2. `/newbot` 입력 → 봇 이름/아이디 설정 → **토큰**이 즉시 발급됩니다 (승인 절차 없음, 무료)
3. 게시할 **채널**(또는 그룹)을 만들고, 방금 만든 봇을 **관리자(admin)**로 추가
4. chat_id 확인 방법:
   - 채널에 아무 메시지나 하나 보낸 뒤
   - 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 접속
   - 응답 JSON에서 `"chat":{"id": -100xxxxxxxxxx, ...}` 값이 chat_id (채널은 보통 `-100`으로 시작)

### ⚠️ 확인 필요
`lib/fetch_data.py`의 `SITE_API_BASE`가 실제 배포 도메인과 일치하는지 확인해주세요.
(예: `https://americayoudongsung.netlify.app`) 도메인이 다르면 `.env`나 GitHub Secrets의
`SITE_API_BASE`로 덮어쓸 수 있습니다.

---

## 2. GitHub Actions로 "완전 자동" 매일 실행하기

### 질문하신 부분: GitHub에 스케줄 실행 기능이 있나요? 무료인가요?

**네, `GitHub Actions`의 `schedule` (cron) 트리거로 가능하고, 이 프로젝트 규모라면 완전 무료입니다.**

| 항목 | 내용 |
|---|---|
| **Public 저장소** | Actions 실행 시간 **무제한 무료** |
| **Private 저장소 (무료 GitHub 계정)** | 매월 **2,000분** 무료 제공 (이 스크립트는 1회 실행에 1~2분 내외라 매일 돌려도 월 60분 정도 → 충분) |
| **실행 위치** | GitHub 클라우드 서버에서 실행 → **본인 노트북이 꺼져있거나 외출 중이어도 정상 작동** (지금 겪으신 문제 완전 해결) |
| **정확도** | cron 시각은 "정확히 그 시각"이 아니라 **±수분~20분 정도 지연**될 수 있음 (특히 매 정시는 트래픽이 몰려 더 밀림 → `5 0 * * *`처럼 애매한 분으로 걸어두는 걸 권장) |
| **자동 비활성화 주의** | **60일간 저장소에 아무 커밋도 없으면 스케줄이 자동으로 꺼집니다.** 이 경우 Actions 탭에서 수동으로 다시 켜주거나, 가끔 커밋을 하나 만들어주면 됩니다 |
| **수동 실행** | Actions 탭 → 워크플로우 선택 → `Run workflow` 버튼으로 즉시 테스트 가능 (`workflow_dispatch` 설정해둠) |

즉, **Private 저장소 무료 플랜도 충분히 가능**합니다 (하루 1회, 몇 분짜리 스크립트라 2,000분 한도에 전혀 안 걸림). Public으로 돌려도 되지만, 사이트 소스/토큰 노출 우려가 있으면 **Private + Secrets**를 추천드려요.

### 설정 순서
1. 이 폴더를 GitHub 저장소로 push (Private 추천)
2. 저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서 아래 3개 등록
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ADMIN_CHAT_ID` (선택, 실패 시 본인에게 알림 받고 싶으면)
   - `SITE_API_BASE` (선택, 도메인이 다르면)
3. `.github/workflows/daily_post.yml` 이 이미 포함되어 있으므로, push하는 순간부터
   Actions 탭에 워크플로우가 보이고 매일 자동 실행됩니다.
4. Actions 탭 → `Run workflow` 버튼으로 지금 바로 1회 테스트 실행 가능

---

## 3. 실패 시 알림 받기

`ADMIN_CHAT_ID`를 설정해두면(본인 개인 텔레그램 챗 아이디), FRED 응답 오류/네트워크
오류 등으로 게시가 실패했을 때 자동으로 알림 메시지를 받습니다. (`daily_post.py`의
`_notify_admin_on_error` 참고) Actions 탭에서도 실행 로그와 그날 생성된 카드 이미지를
Artifact로 7일간 보관하니, 실패 원인 디버깅이 쉽습니다.

---

## 4. 다음 확장 아이디어 (원할 때 추가하면 됨)

- **Threads / 카카오톡 채널**: `lib/post_telegram.py`와 같은 패턴으로
  `lib/post_threads.py`, `lib/post_kakao.py`를 추가하고 `daily_post.py`에서
  같이 호출하면 됩니다. (각 플랫폼 앱 등록 후 액세스 토큰만 발급받으면 구조는 동일)
- **티스토리 자동 발행**: Open API로 그 주 데이터를 표/문장으로 정리한 블로그
  글을 자동 발행 → SEO 콘텐츠 확장(2번 아이디어)과 자연스럽게 연결됩니다.
- **주간 요약(월요일에만 지난 4주 추세 포함)**: `compute_trend_text`를 확장해서
  요일별로 다른 카드 템플릿을 쓰면 콘텐츠 다양성을 줄 수 있습니다.
