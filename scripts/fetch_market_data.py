#!/usr/bin/env python3
"""국내·미국 주요 지수 시황을 yfinance로 조회해 웹페이지용 JSON을 생성한다.

Desktop\\Claude Code\\market_summary.py 의 티커 목록·등락 계산 로직을 기반으로
하되, 이메일 대신 정적 웹페이지(index.html)가 읽는 data/latest.json을 만든다.
GitHub Actions가 매일 이 스크립트를 실행해 결과를 커밋한다.
"""

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_PATH = DATA_DIR / "latest.json"
LOG_PATH = SCRIPT_DIR.parent / "fetch_market_data.log"

KST = timezone(timedelta(hours=9))

MARKETS = [
    {"label": "코스피", "ticker": "^KS11", "category": "국내증시"},
    {"label": "코스닥", "ticker": "^KQ11", "category": "국내증시"},
    {"label": "S&P 500", "ticker": "^GSPC", "category": "미국증시"},
    {"label": "나스닥", "ticker": "^IXIC", "category": "미국증시"},
    {"label": "다우존스", "ticker": "^DJI", "category": "미국증시"},
]
CATEGORY_ORDER = ["국내증시", "미국증시"]

MONTH_TRADING_DAYS = 22


def setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def fetch_one(ticker: str) -> dict | None:
    """1년치 일봉을 한 번만 조회해 최신 등락/1개월·1년 추이를 함께 뽑아낸다."""
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if hist.empty or len(hist) < 2:
            return None

        latest = hist.iloc[-1]
        latest_date = hist.index[-1].date()
        prev_close = float(hist.iloc[-2]["Close"])
        latest_close = float(latest["Close"])
        change = latest_close - prev_close
        pct = (change / prev_close * 100) if prev_close else None
        volume = int(latest["Volume"]) if "Volume" in latest and latest["Volume"] == latest["Volume"] else None

        def series(df):
            return [
                {"date": idx.date().isoformat(), "close": round(float(row["Close"]), 4)}
                for idx, row in df.iterrows()
            ]

        return {
            "close": latest_close,
            "change": change,
            "pct": pct,
            "volume": volume,
            "date": latest_date.isoformat(),
            "history_1mo": series(hist.tail(MONTH_TRADING_DAYS)),
            "history_1y": series(hist),
        }
    except Exception as e:
        logging.warning(f"{ticker} 조회 실패: {e}")
        return None


def classify_move(pct: float | None) -> str:
    if pct is None:
        return "알수없음"
    direction = "상승" if pct > 0 else "하락" if pct < 0 else "보합"
    a = abs(pct)
    if a < 0.3:
        return "보합"
    if a < 1:
        return f"소폭 {direction}"
    if a < 2:
        return direction
    return "급등" if direction == "상승" else "급락" if direction == "하락" else "보합"


def category_phrase(label_data: list[tuple[str, dict | None]]) -> str:
    valid = [(label, d) for label, d in label_data if d is not None and d["pct"] is not None]
    if not valid:
        return "데이터 없음"
    ups = sum(1 for _, d in valid if d["pct"] > 0)
    downs = sum(1 for _, d in valid if d["pct"] < 0)
    names = "·".join(label for label, _ in valid)
    if ups == len(valid):
        return f"{names} 동반 상승"
    if downs == len(valid):
        return f"{names} 동반 하락"
    return f"{names} 혼조"


def build_summary(results: dict[str, dict | None]) -> str:
    parts = []
    for category in CATEGORY_ORDER:
        items = [(m["label"], results[m["label"]]) for m in MARKETS if m["category"] == category]
        parts.append(f"{category}: {category_phrase(items)}")

    ranked = [
        (label, d["pct"]) for label, d in results.items() if d is not None and d["pct"] is not None
    ]
    if ranked:
        ranked.sort(key=lambda x: x[1], reverse=True)
        best_label, best_pct = ranked[0]
        worst_label, worst_pct = ranked[-1]
        parts.append(
            f"최고 {best_label} ({'+' if best_pct >= 0 else ''}{best_pct:.2f}%), "
            f"최저 {worst_label} ({'+' if worst_pct >= 0 else ''}{worst_pct:.2f}%)"
        )
    return " / ".join(parts)


def main() -> None:
    setup_logging()
    logging.info("=== 시황 데이터 수집 시작 ===")
    DATA_DIR.mkdir(exist_ok=True)

    results = {m["label"]: fetch_one(m["ticker"]) for m in MARKETS}
    ok_count = sum(1 for v in results.values() if v is not None)

    if ok_count == 0:
        logging.error("모든 티커 조회 실패 — 데이터 파일을 생성하지 않음")
        print("모든 데이터 조회에 실패했습니다. fetch_market_data.log를 확인하세요.")
        sys.exit(1)

    ranked = sorted(
        (label for label, d in results.items() if d is not None and d["pct"] is not None),
        key=lambda label: results[label]["pct"],
        reverse=True,
    )

    markets_out = []
    for m in MARKETS:
        d = results[m["label"]]
        if d is None:
            continue
        markets_out.append(
            {
                "label": m["label"],
                "ticker": m["ticker"],
                "category": m["category"],
                "close": round(d["close"], 2),
                "change": round(d["change"], 2),
                "pct": round(d["pct"], 2) if d["pct"] is not None else None,
                "volume": d["volume"],
                "date": d["date"],
                "move": classify_move(d["pct"]),
                "history_1mo": d["history_1mo"],
                "history_1y": d["history_1y"],
            }
        )

    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "markets": markets_out,
        "ranking": ranked,
        "summary_text": build_summary(results),
    }

    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logging.info(f"데이터 생성 완료 (성공 {ok_count}/{len(MARKETS)}) -> {OUTPUT_PATH}")
    print(f"data/latest.json 생성 완료 (성공 {ok_count}/{len(MARKETS)})")


if __name__ == "__main__":
    main()
