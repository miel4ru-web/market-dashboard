# 일일 시황 대시보드

코스피·코스닥·S&P 500·나스닥·다우존스 5개 지수의 하루 시황을 [yfinance](https://github.com/ranaroussi/yfinance)로 조회해 보여주는 정적 웹페이지입니다. GitHub Actions가 매일 자동으로 데이터를 갱신하고, GitHub Pages가 그 결과를 정적으로 서빙합니다. 서버나 API 키가 필요 없습니다.

## 구조

- `scripts/fetch_market_data.py` — yfinance로 데이터를 조회해 `data/latest.json`을 생성
- `data/latest.json` — 최신 시황 데이터 (Actions가 매일 커밋)
- `index.html`, `assets/` — 데이터를 보여주는 정적 페이지
- `.github/workflows/update-data.yml` — 매일 데이터를 갱신하는 워크플로

## 로컬에서 데이터 갱신

```
py -3.12 -m pip install -r requirements.txt
py -3.12 scripts/fetch_market_data.py
```

`data/latest.json`이 갱신됩니다.

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
