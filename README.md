# 영상 공고 감시대

나라장터에 올라오는 **영상 관련 용역 입찰공고와 사전규격**을 하루 두 번 자동으로 훑어서,
나만 보는 대시보드에 쌓고 새 건이 있으면 카카오톡으로 알려줍니다.

- 수집: GitHub Actions (매일 08:30 / 15:00 KST)
- 화면: GitHub Pages 정적 사이트
- 알림: 카카오톡 나에게 보내기
- 비용: 0원

나라장터 화면을 크롤링하지 않고, 조달청이 공공데이터포털에 공개한 오픈API를 씁니다.

---

## 1. 리포지토리 만들기

GitHub에서 새 리포지토리를 하나 만들고(이름은 `g2b-video-watch` 정도), 이 폴더의 파일을 그대로 올립니다.

```
.github/workflows/daily.yml   자동 실행 설정
scripts/config.py             키워드 규칙  ← 주로 여기만 손봅니다
scripts/collect.py            수집 스크립트
scripts/notify_kakao.py       카카오톡 알림
docs/index.html               대시보드 화면
docs/data/notices.json        수집 결과가 쌓이는 파일
```

### 공개 여부에 대해

GitHub Pages는 **무료 플랜에서는 공개 리포지토리에서만** 켤 수 있습니다. 선택지는 셋입니다.

| 방법 | 비용 | 비고 |
|---|---|---|
| 공개 리포 + Pages | 무료 | 주소를 모르면 사실상 못 찾습니다. `robots.txt`와 `noindex`로 검색 노출은 이미 막아두었습니다. 어차피 담기는 내용은 전부 공개된 입찰정보입니다 |
| GitHub Pro + 비공개 리포 | 월 $4 | 로그인한 나만 접속 가능 |
| 비공개 리포 + Pages 미사용 | 무료 | `docs/index.html`과 `notices.json`을 내려받아 로컬에서 열어봅니다 |

인증키는 어느 쪽이든 코드가 아니라 Secrets에 들어가므로 노출되지 않습니다.

---

## 2. 공공데이터포털 인증키 받기 (약 5분)

[data.go.kr](https://www.data.go.kr) 가입 후 아래 두 개를 각각 **활용신청**합니다. 둘 다 자동 승인이고 무료입니다.

1. **조달청_나라장터 입찰공고정보서비스** — 입찰공고용
2. **조달청_나라장터 사전규격정보서비스** — 발주 예고용

마이페이지 › 오픈API › 개발계정에서 **일반 인증키(Decoding)** 값을 복사해 둡니다.
승인 직후에는 키가 먹통일 수 있는데, 보통 1시간 안에 풀립니다.

---

## 3. Secrets 등록

리포지토리 › Settings › Secrets and variables › Actions

| 이름 | 값 | 필수 |
|---|---|---|
| `G2B_SERVICE_KEY` | 입찰공고정보서비스 인증키 | ✅ |
| `G2B_PRESPEC_SERVICE_KEY` | 사전규격정보서비스 인증키 | 사전규격 쓸 때 |
| `KAKAO_REST_API_KEY` | 카카오 REST API 키 | 알림 쓸 때 |
| `KAKAO_REFRESH_TOKEN` | 카카오 리프레시 토큰 | 알림 쓸 때 |
| `GH_PAT` | `repo` 권한 개인 토큰 | 선택 (아래 6번) |

같은 화면의 **Variables** 탭에는 `SITE_URL`을 추가하고 Pages 주소
(`https://아이디.github.io/g2b-video-watch/`)를 넣습니다. 카카오톡 메시지의 버튼이 이 주소로 연결됩니다.

---

## 4. Pages 켜기

Settings › Pages › Source를 **GitHub Actions**로 지정합니다. (`Deploy from a branch` 아님)

---

## 5. 첫 실행

Actions 탭 › 영상 공고 수집 › **Run workflow**.

2분쯤 뒤 로그에 `→ 영상 관련 N건`이 찍히고, `docs/data/notices.json`이 커밋되면 성공입니다.
이후에는 하루 두 번 알아서 돕니다. 다만 GitHub 스케줄은 부하 상황에 따라 몇 분에서 한 시간까지
밀릴 수 있으니, 마감이 걸린 건은 시간을 너무 믿지 마세요.

---

## 6. 카카오톡 알림 붙이기 (약 15분)

가장 손이 많이 가는 단계입니다. 알림 없이 사이트만 써도 됩니다.

1. [developers.kakao.com](https://developers.kakao.com) › 내 애플리케이션 › **애플리케이션 추가**
2. 앱 설정 › 앱 키에서 **REST API 키** 복사
3. 카카오 로그인 › **활성화 ON**, Redirect URI에 `https://localhost:3000` 등록
4. 카카오 로그인 › 동의항목 › **카카오톡 메시지 전송(talk_message)** 을 선택 동의로 설정
5. 브라우저 주소창에 아래를 넣고 열어서, 로그인·동의합니다.

   ```
   https://kauth.kakao.com/oauth/authorize?client_id=REST키&redirect_uri=https://localhost:3000&response_type=code&scope=talk_message
   ```

6. 접속 실패 화면이 뜨지만 괜찮습니다. **주소창의 `code=` 뒤 문자열**을 복사합니다.
7. 터미널에서 토큰을 받습니다.

   ```bash
   curl -X POST "https://kauth.kakao.com/oauth/token" \
     -d "grant_type=authorization_code" \
     -d "client_id=REST키" \
     -d "redirect_uri=https://localhost:3000" \
     -d "code=6번에서_복사한_값"
   ```

8. 응답의 `refresh_token` 값을 `KAKAO_REFRESH_TOKEN` 시크릿에 넣습니다.

리프레시 토큰은 두 달짜리입니다. 남은 기간이 한 달 미만이 되면 카카오가 새 토큰을 함께 내려주는데,
이때 `GH_PAT`(repo 권한 개인 토큰)를 등록해 두면 워크플로가 시크릿을 알아서 바꿔치기합니다.
등록하지 않으면 Actions 로그에 경고만 남고, 5~8번을 다시 해줘야 합니다.

---

## 7. 키워드 조정

`scripts/config.py` 하나만 고치면 됩니다.

- `STRONG` — 거의 확실한 영상제작 건 (점수 3)
- `WEAK` — 애매한 건 (점수 1)
- `EXCLUDE` — 영상의학·CCTV·위성영상처럼 "영상"이 들어가지만 우리 일이 아닌 것
- `MIN_SCORE` — 기본 1. 잡건이 너무 많으면 **3으로 올리세요**. 강한 키워드가 있는 건만 남습니다
- `WATCH_ORGS` — 여기 적은 기관 공고에는 카드에 ★가 붙습니다

며칠 돌려보고 놓친 공고가 있으면 그 제목의 특징어를 `STRONG`에, 자꾸 끼어드는 잡건이 있으면
그 특징어를 `EXCLUDE`에 넣는 식으로 다듬는 게 가장 빠릅니다.

---

## 8. 잘 안 될 때

| 증상 | 확인할 것 |
|---|---|
| `응답을 해석할 수 없습니다` | 인증키 오타이거나 승인 직후입니다. Decoding 키를 넣었는지 보고 한 시간 뒤 다시 실행 |
| 수신은 되는데 `영상 관련 0건` | 정상일 수 있습니다. 영상 용역은 하루 0~5건 수준입니다. `MIN_SCORE`를 1로 낮춰보세요 |
| 사이트가 404 | Settings › Pages의 Source가 `GitHub Actions`인지 확인 |
| 사이트에 옛날 데이터 | 브라우저 강력 새로고침(Ctrl+Shift+R) |
| 사전규격만 실패 | 사전규격정보서비스는 별도 활용신청이 필요합니다. 안 쓰려면 `config.py`의 `COLLECT_PRESPEC = False` |
| 카카오톡 미전송 | Actions 로그의 `전송 실패` 코드 확인. `-401`은 토큰 만료, `-3`은 동의항목 미설정 |

읽음·관심 표시는 브라우저에만 저장됩니다. 기기를 바꾸면 초기화되니 참고하세요.
