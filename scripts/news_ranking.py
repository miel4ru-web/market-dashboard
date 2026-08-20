"""뉴스 중요도 판단 — fetch_sector_data.py / fetch_sector_data_kr.py가 공유하는
규칙 기반 순위 로직 (LLM·유료 API 없음, "완전 무료" 원칙 유지).

yfinance Ticker.news는 최신순으로만 정렬돼 있고, 실제로 받아본 데이터를
보면 최신순만으로는 부족한 문제가 두 가지 있었다:

1. MT Newswires 같은 자동 시황 요약 wire가 "Sector Update: Tech Stocks
   Fall Late Afternoon", "Exchange-Traded Funds Higher as US Equities
   Gain After Midday" 처럼 거의 동일한 정형 기사를 거의 매일, 그것도
   서로 다른 여러 템플릿으로 반복 게재한다. 제목 패턴 하나만으로 잡으려
   하면 템플릿이 바뀔 때마다 놓친다는 걸 실제로 확인했다 — 그래서
   **발행사 자체를 저우선순위로 취급**하는 걸 주 신호로 삼고, 제목
   패턴 매칭은 보조 신호로만 둔다.
2. 여러 매체가 동시에 다룬 사건(제목이 겹치는 기사가 여럿 있는 경우)은
   단독 보도보다 시장에 더 널리 알려졌을 가능성이 높다.

이 두 가지를 규칙 기반으로만 반영해 정렬 순서를 바꾼다. 완전한 "중요도"
판단(감성분석 등)은 아니며, 정형 기사를 뒤로 미루고(완전히 제외하지는
않음 — 그 사건 하나뿐이면 그거라도 보여주는 게 낫다) 여러 소스가 겹치는
기사를 앞으로 당기는 정도의 개선이다.
"""

import re

# 관찰된 자동 시황 요약 wire. 소문자로 비교한다. 새로운 저품질 발행사가
# 보이면 여기에 추가하면 된다 — 제목 템플릿을 일일이 쫓는 것보다 안정적.
_LOW_PRIORITY_PUBLISHERS = {"mt newswires"}

# 발행사만으로 못 잡는 경우를 위한 보조 신호 (알려진 정형 제목 패턴).
_BOILERPLATE_TITLE_PATTERNS = [
    re.compile(r"^sector update:", re.IGNORECASE),
    re.compile(r"^exchange-traded funds (higher|lower)", re.IGNORECASE),
]

_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is",
    "are", "as", "at", "by", "with", "from", "stock", "stocks", "sector",
    "update", "news", "market", "markets", "after", "amid", "over", "into",
}


def _is_boilerplate(item: dict) -> bool:
    publisher = (item.get("publisher") or "").strip().lower()
    if publisher in _LOW_PRIORITY_PUBLISHERS:
        return True
    title = item.get("title", "").strip()
    return any(p.match(title) for p in _BOILERPLATE_TITLE_PATTERNS)


def _keywords(title: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9%]+", title.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def rank_news(items: list[dict]) -> list[dict]:
    """news 항목 리스트(각 항목은 "title"·"publisher"·"published_at"(datetime)을
    가짐)를 중요도 순으로 재정렬해서 새 리스트로 돌려준다 (원본은 변경하지 않음).

    정렬 기준: (1) 정형 기사가 아닌 것 우선 (2) 같은 소식을 다룬 다른
    기사가 많을수록(제목 키워드 2개 이상 겹치는 항목 수) 우선 (3) 최신순.
    """
    keyword_sets = [_keywords(n["title"]) for n in items]

    def corroboration(i: int) -> int:
        kws = keyword_sets[i]
        if not kws:
            return 0
        return sum(
            1
            for j, other_kws in enumerate(keyword_sets)
            if j != i and len(kws & other_kws) >= 2
        )

    scored = [
        (
            _is_boilerplate(n),
            -corroboration(idx),
            -n["published_at"].timestamp(),
            n,
        )
        for idx, n in enumerate(items)
    ]
    scored.sort(key=lambda t: t[:3])
    return [n for *_, n in scored]
