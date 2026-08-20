#!/usr/bin/env python3
"""오늘 가장 크게 영향을 준 미국 섹터를 골라 관련 뉴스와 함께 저장한다.

config/sectors.json(GICS 11개 섹터, SPDR Select Sector ETF)을 기준으로
- 가중치: SPY(S&P500 ETF)의 실제 섹터 비중(yf.Ticker("SPY").funds_data.sector_weightings)
- 등락률: 섹터 ETF들의 최근 종가 변화
를 곱해 "기여도"를 계산하고, 기여도 절대값 상위 N개 섹터에 한해 yfinance
Ticker.news로 관련 뉴스를 붙여 data/sectors.json을 만든다. 뉴스 정렬/필터링
규칙은 news_ranking.py(fetch_sector_data_kr.py와 공유) 참고.

market-dashboard의 기존 지수 대시보드(fetch_market_data.py, data/latest.json)와
독립적으로 동작한다 — 이 스크립트가 실패해도 기존 데이터 갱신을 막지 않도록
GitHub Actions 쪽에서 별도 스텝(continue-on-error)으로 격리한다.
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
OUTPUT_PATH = DATA_DIR / "sectors.json"
LOG_PATH = SCRIPT_DIR.parent / "fetch_sector_data.log"
SECTORS_CONFIG_PATH = SCRIPT_DIR.parent / "config" / "sectors.json"

KST = timezone(timedelta(hours=9))


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


def fetch_sector_weights(sectors: list[dict]) -> tuple[dict[str, float], str]:
    """{ticker: weight_pct}와 weight_source("sp500_index" | "equal_fallback")를 돌려준다."""
    try:
        weightings = yf.Ticker("SPY").funds_data.sector_weightings
        weights = {}
        for s in sectors:
            frac = weightings.get(s["morningstar_key"])
            if frac is None:
                raise KeyError(f"morningstar_key 없음: {s['morningstar_key']}")
            weights[s["ticker"]] = frac
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("섹터 비중 합계가 0 이하")
        return {t: w / total * 100 for t, w in weights.items()}, "sp500_index"
    except Exception as e:
        logging.warning(f"SPY 섹터 비중 조회 실패, 동일 가중치로 대체: {e}")
        equal = 100 / len(sectors)
        return {s["ticker"]: equal for s in sectors}, "equal_fallback"


def fetch_sector_prices(tickers: list[str]) -> dict[str, dict | None]:
    """티커 목록을 한 번의 배치 요청으로 조회해 {ticker: {close, pct, date}}를 돌려준다.

    배치 요청 자체가 실패하면 전체를 None으로 채워 이번 실행에서 가격 데이터를
    갱신하지 않고 넘어가게 한다 (호출 1번으로 묶어 레이트리밋 위험을 줄이는 대신,
    개별 티커 단위 격리는 포기하는 트레이드오프)."""
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
            logging.warning(f"{ticker} 가격 추출 실패: {e}")
            results[ticker] = None
    return results


def fetch_sector_news(ticker: str, max_age_hours: int, limit: int) -> list[dict]:
    try:
        items = yf.Ticker(ticker).news
    except Exception as e:
        logging.warning(f"{ticker} 뉴스 조회 실패: {e}")
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
    logging.info("=== 섹터 데이터 수집 시작 ===")
    DATA_DIR.mkdir(exist_ok=True)

    config = load_config()
    sectors = config["sectors"]
    top_n = config["top_n"]
    news_per_sector = config["news_per_sector"]
    news_max_age_hours = config["news_max_age_hours"]

    weight_by_ticker, weight_source = fetch_sector_weights(sectors)
    tickers = [s["ticker"] for s in sectors]
    prices = fetch_sector_prices(tickers)

    ok_count = sum(1 for v in prices.values() if v is not None)
    if ok_count == 0:
        logging.error("모든 섹터 가격 조회 실패 — data/sectors.json 갱신을 건너뜀")
        print("섹터 가격 조회에 모두 실패해 data/sectors.json을 갱신하지 않았습니다.")
        return

    scored = []
    for s in sectors:
        price = prices.get(s["ticker"])
        weight_pct = weight_by_ticker.get(s["ticker"], 0.0)
        pct = price["pct"] if price else None
        contribution = (weight_pct / 100 * pct) if pct is not None else None
        scored.append({**s, "weight_pct": weight_pct, "price": price, "contribution": contribution})

    rankable = [s for s in scored if s["contribution"] is not None]
    rankable.sort(key=lambda s: abs(s["contribution"]), reverse=True)
    top_labels = [s["label"] for s in rankable[:top_n]]

    sectors_out = []
    for s in scored:
        rank = top_labels.index(s["label"]) + 1 if s["label"] in top_labels else None
        news = (
            fetch_sector_news(s["ticker"], news_max_age_hours, news_per_sector)
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
        "weight_source": weight_source,
        "top_n": top_n,
        "top_sectors": top_labels,
        "sectors": sectors_out,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"섹터 데이터 생성 완료 (가격 성공 {ok_count}/{len(sectors)}, weight_source={weight_source}) -> {OUTPUT_PATH}")
    print(f"data/sectors.json 생성 완료 (가격 성공 {ok_count}/{len(sectors)}, 주요 섹터: {', '.join(top_labels)})")


if __name__ == "__main__":
    main()
