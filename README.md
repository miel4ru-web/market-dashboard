# 일일 시황 대시보드

코스피·코스닥·S&P 500·나스닥·다우존스 5개 지수의 하루 시황을 [yfinance](https://github.com/ranaroussi/yfinance)로 조회해 보여주는 정적 웹페이지입니다. GitHub Actions가 매일 자동으로 데이터를 갱신하고, GitHub Pages가 그 결과를 정적으로 서빙합니다. 서버나 API 키가 필요 없습니다.

## 구조

- `config/markets.json` — 표시할 시장 목록의 단일 소스 (라벨·티커·카테고리)
- `scripts/fetch_market_data.py` — `config/markets.json`을 읽어 yfinance로 데이터를 조회하고 `data/latest.json`을 생성
- `data/latest.json` — 최신 시황 데이터 (Actions가 매일 커밋)
- `config/sectors.json` — 미국 GICS 11개 섹터(SPDR 섹터 ETF) 목록의 단일 소스
- `scripts/fetch_sector_data.py` — S&P500 실제 섹터 비중 × 오늘 등락률로 "기여도"를 계산해 상위 섹터를 고르고, 그 섹터들의 최신 뉴스(yfinance `Ticker.news`)를 붙여 `data/sectors.json`을 생성. 기존 지수 파이프라인과 독립적으로 실패해도 무방하도록 설계됨 (아래 "오늘의 주요 섹터" 참고)
- `data/sectors.json` — 최신 주요 섹터/뉴스 데이터
- `index.html`, `assets/` — 데이터를 보여주는 정적 페이지 (`assets/app.js`도 `config/markets.json`, `config/sectors.json`을 읽음)
- `.github/workflows/update-data.yml` — 매일 데이터를 갱신하는 워크플로

## 시장 추가/삭제하기

`config/markets.json`만 수정하면 됩니다. Python·JS·CSS 어느 것도 손댈 필요 없습니다.

```json
{ "label": "표시 이름", "ticker": "yfinance 티커", "category": "카테고리명" }
```

- `markets` 배열에 항목을 추가/삭제/순서 변경 — 카드·랭킹·차트·요약 문구에 자동 반영됩니다.
- 새 카테고리를 쓰려면 `categories` 배열에도 그 이름을 추가하세요 (카드 섹션 순서를 결정).
- 차트 색상은 `markets` 배열의 **순서**대로 8개의 고정 슬롯(`--series-slot-1` ~ `-8`, `assets/style.css`)에서 배정됩니다. 9번째 시장부터는 대응하는 CSS 변수가 없어 선 색이 정상적으로 나오지 않습니다 — 색맹 접근성을 위해 슬롯을 임의로 순환시키지 않는 설계이므로, 8개를 넘기려면 `assets/style.css`에 슬롯을 추가하거나, 일부 시장을 "기타"로 묶거나 별도 소그룹 차트로 나누는 방식을 권장합니다.
- 수정 후 `py -3.12 scripts/fetch_market_data.py`를 실행해 `data/latest.json`을 다시 생성하세요.

## 오늘의 주요 섹터 (미국)

지수 대시보드 아래에 "오늘의 주요 섹터" 섹션이 별도로 붙어 있습니다.

- **가중치**: `yf.Ticker("SPY").funds_data.sector_weightings` — S&P500의 실제 섹터 비중(근사치 아님). 이 호출이 실패하면 11개 섹터에 동일 가중치를 주는 것으로 자동 대체되고 `data/sectors.json`의 `weight_source`가 `"equal_fallback"`으로 표시됩니다.
- **선정 기준**: `기여도 = 가중치 × 오늘 등락률`을 섹터별로 계산해 절대값 기준 상위 `top_n`개(`config/sectors.json`에서 조정 가능)만 카드로 보여줍니다.
- **뉴스**: 선정된 섹터에 한해서만 `yf.Ticker(ticker).news`로 최근 뉴스를 가져옵니다 — 오늘 전체에서 가장 중요한 뉴스가 아니라 "선정된 섹터와 관련된 최신 뉴스"라는 점에 유의하세요.
- 이 섹션은 지수 대시보드와 **독립적으로** fetch/렌더링됩니다. `scripts/fetch_sector_data.py`나 `data/sectors.json`에 문제가 생겨도 워크플로는 실패하지 않고(`continue-on-error: true`), 페이지에서도 이 섹션만 조용히 빠지고 나머지는 정상 동작합니다.

## 로컬에서 데이터 갱신

```
py -3.12 -m pip install -r requirements.txt
py -3.12 scripts/fetch_market_data.py
py -3.12 scripts/fetch_sector_data.py
```

`data/latest.json`, `data/sectors.json`이 갱신됩니다.

## 로컬에서 페이지 미리보기

`index.html`을 파일로 직접 열면 `fetch()`가 로컬 파일 접근 제한에 걸릴 수 있으므로, 간단한 로컬 서버로 띄워서 확인합니다.

```
py -3.12 -m http.server 8000
```

브라우저에서 `http://localhost:8000` 접속.

## GitHub에 배포하기

1. 이 폴더를 GitHub 저장소로 push합니다 (`git init` 이미 완료됨).
2. 저장소 Settings → Pages에서 Source를 "Deploy from a branch", Branch를 `main` / `/(root)`로 설정합니다.
3. Settings → Actions → General에서 워크플로에 쓰기 권한(Read and write permissions)이 있는지 확인합니다 (`update-data.yml`이 `data/latest.json`을 커밋·push하기 때문).
4. Actions 탭에서 `Update market data` 워크플로를 수동 실행(`workflow_dispatch`)해 첫 데이터를 생성할 수 있습니다.

## 참고

- 데이터 출처는 Yahoo Finance(yfinance)이며 참고용입니다. 투자 판단의 근거로 사용하지 마세요.
- 지수 등락 계산·색상 컨벤션(상승=빨강, 하락=파랑)은 같은 워크스페이스의 `market_summary.py`(이메일 버전)와 동일합니다.
