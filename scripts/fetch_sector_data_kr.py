#!/usr/bin/env python3
"""오늘 가장 크게 움직인 국내(코스피) 섹터를 골라 관련 뉴스와 함께 저장한다.

fetch_sector_data.py(미국 섹터)의 2단계 확장이지만, 국내 섹터는 yfinance에서
쓸 수 있는 데이터가 근본적으로 달라 같은 방식을 그대로 옮길 수 없었다:

- 미국은 SPY.funds_data.sector_weightings로 실제 S&P500 섹터 비중을 구할 수
  있지만, 국내 ETF(TIGER 200 섹터 시리즈)는 이 fund 데이터 자체가 없다
  (yfinance: "No Fund data found"). totalAssets/marketCap 등 .info 필드도
  전부 비어 있어 시가총액 비중을 구할 free 소스가 없다.
  대안으로 평균 거래대금(거래량 × 종가) 비중을 시도해봤으나, 실제 측정
  결과 TIGER 200 IT 한 종목의 거래대금이 나머지 8개를 합친 것보다도
  훨씬 커서(예: IT 928억 vs 나머지 대부분 3~15억 원대) 가중치가 항상
  90% 넘게 IT로 쏠리는 왜곡된 결과가 나왔다 — 이는 실제 코스피 내 IT
  섹터 비중(삼성전자 혼자 대략 20~25% 수준)과 무관하게 "이 ETF 상품이
  얼마나 인기 있는가"만 반영하는 잘못된 신호였다. 잘못된 숫자를 그럴듯하게
  보여주는 것보다는, 명시적으로 균등 가중치(1/N)를 쓰고 그 사실을
  weight_source·프론트엔드 캡션에 정직하게 밝히는 쪽을 택했다 — 결과적으로
  "주요 섹터" 선정은 사실상 순수 등락률 상위 랭킹과 같아진다.
- 섹터 ETF 티커 자체는 yfinance Ticker.news가 항상 0건을 반환한다(확인됨).
  대신 각 섹터를 대표하는 개별 종목(news_ticker, 예: IT→삼성전자)의
  뉴스를 가져온다.

market-dashboard의 기존 파이프라인(지수 대시보드, 미국 섹터)과 완전히
독립적으로 동작한다 — 이 스크립트가 실패해도 나머지 데이터 갱신에는
영향이 없도록 GitHub Actions에서 별도 스텝(continue-on-error)으로 격리한다.
"""

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

from news_ranking import rank_news

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_PATH = DATA_DIR / "sectors_kr.json"
LOG_PATH = SCRIPT_DIR.parent / "fetch_sector_data_kr.log"
SECTORS_CONFIG_PATH = SCRIPT_DIR.parent / "config" / "sectors_kr.json"

KST = timezone(timedelta(hours=9))
WEIGHT_SOURCE = "equal_kr"


def setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def load_config() -> dict:
    return json.loads(SECTORS_CONFIG_PATH.read_text(encoding="utf-8"))


def fetch_sector_prices(tickers: list[str]) -> dict[str, dict | None]:
    """배치 요청으로 조회해 {ticker: {close, pct, date}}를 돌려준다."""
    try:
        df = yf.download(
            tickers=" ".join(tickers),
            period="5d",
            group_by="ticker",
            progress=False,
            auto_adjust=False,
        )
    except Exception as e:
        logging.warning(f"섹터 가격 배치 조회 실패: {e}")
        return {t: None for t in tickers}

    results: dict[str, dict | None] = {}
    for ticker in tickers:
        try:
            closes = df[ticker]["Close"].dropna()
            if len(closes) < 2:
                results[ticker] = None
                continue
            latest_close = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])
            pct = (latest_close - prev_close) / prev_close * 100 if prev_close else None

            results[ticker] = {
                "close": latest_close,
                "pct": pct,
                "date": closes.index[-1].date().isoformat(),
            }
        except Exception as e:
            logging.warning(f"{ticker} 가격/거래대금 추출 실패: {e}")
            results[ticker] = None
    return results


def fetch_sector_news(news_ticker: str, max_age_hours: int, limit: int) -> list[dict]:
    try:
        items = yf.Ticker(news_ticker).news
    except Exception as e:
        logging.warning(f"{news_ticker} 뉴스 조회 실패: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    seen_urls = set()
    news = []
    for item in items:
        content = item.get("content", {})
        title = content.get("title")
        pub_date = content.get("pubDate")
        url = (content.get("canonicalUrl") or {}).get("url")
        publisher = (content.get("provider") or {}).get("displayName")
        if not title or not pub_date or not url:
            continue
        try:
            published_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        if published_at < cutoff:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        news.append(
            {
                "title": title,
                "publisher": publisher or "알 수 없음",
                "url": url,
                "published_at": published_at,
            }
        )

    news = rank_news(news)[:limit]
    for n in news:
        n["published_at"] = n["published_at"].isoformat()
    return news


def main() -> None:
    setup_logging()
    logging.info("=== 국내 섹터 데이터 수집 시작 ===")
    DATA_DIR.mkdir(exist_ok=True)

    config = load_config()
    sectors = config["sectors"]
    top_n = config["top_n"]
    news_per_sector = config["news_per_sector"]
    news_max_age_hours = config["news_max_age_hours"]

    tickers = [s["ticker"] for s in sectors]
    prices = fetch_sector_prices(tickers)

    ok_count = sum(1 for v in prices.values() if v is not None)
    if ok_count == 0:
        logging.error("모든 섹터 가격 조회 실패 — data/sectors_kr.json 갱신을 건너뜀")
        print("섹터 가격 조회에 모두 실패해 data/sectors_kr.json을 갱신하지 않았습니다.")
        return

    # 실측 결과 거래대금 비중은 TIGER 200 IT 한 종목으로 90%+ 쏠려 가중치로
    # 쓸 수 없었다 (모듈 docstring 참고) — 균등 가중치를 명시적으로 사용한다.
    equal_weight_pct = 100 / len(sectors)

    scored = []
    for s in sectors:
        price = prices.get(s["ticker"])
        pct = price["pct"] if price else None
        contribution = (equal_weight_pct / 100 * pct) if pct is not None else None
        scored.append({**s, "weight_pct": equal_weight_pct, "price": price, "contribution": contribution})

    rankable = [s for s in scored if s["contribution"] is not None]
    rankable.sort(key=lambda s: abs(s["contribution"]), reverse=True)
    top_labels = [s["label"] for s in rankable[:top_n]]

    sectors_out = []
    for s in scored:
        rank = top_labels.index(s["label"]) + 1 if s["label"] in top_labels else None
        news = (
            fetch_sector_news(s["news_ticker"], news_max_age_hours, news_per_sector)
            if rank is not None
            else []
        )
        price = s["price"]
        sectors_out.append(
            {
                "label": s["label"],
                "ticker": s["ticker"],
                "weight_pct": round(s["weight_pct"], 2),
                "pct": round(price["pct"], 2) if price and price["pct"] is not None else None,
                "contribution": round(s["contribution"], 4) if s["contribution"] is not None else None,
                "rank": rank,
                "news": news,
            }
        )

    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "weight_source": WEIGHT_SOURCE,
        "top_n": top_n,
        "top_sectors": top_labels,
        "sectors": sectors_out,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"국내 섹터 데이터 생성 완료 (가격 성공 {ok_count}/{len(sectors)}) -> {OUTPUT_PATH}")
    print(f"data/sectors_kr.json 생성 완료 (가격 성공 {ok_count}/{len(sectors)}, 주요 섹터: {', '.join(top_labels)})")


if __name__ == "__main__":
    main()
