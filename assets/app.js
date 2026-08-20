(function () {
  "use strict";

  var WEEKDAY_KR = ["일", "월", "화", "수", "목", "금", "토"];

  // config/markets.json이 시장 목록의 단일 소스다 (fetch_market_data.py도 같은
  // 파일을 읽음). SERIES_META/CATEGORY_ORDER는 그 파일에서 채워진다 — 아래
  // 두 변수는 renderAll()이 config를 불러온 뒤 설정하기 전까지는 비어 있다.
  var SERIES_META = [];
  var CATEGORY_ORDER = [];

  var state = {
    data: null,
    range: "1mo"
  };

  function buildSeriesMeta(marketsConfig) {
    // markets 배열의 순서 = 범주형 색상 슬롯의 고정 배정 순서 (최대 8개).
    return marketsConfig.map(function (m, i) {
      return { label: m.label, varName: "--series-slot-" + (i + 1) };
    });
  }

  function seriesColor(label) {
    var meta = SERIES_META.filter(function (m) { return m.label === label; })[0];
    return meta ? "var(" + meta.varName + ")" : "var(--text-secondary)";
  }

  function fmtNum(n, digits) {
    if (n === null || n === undefined) return "-";
    return n.toLocaleString("ko-KR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  function fmtSigned(n, digits, suffix) {
    if (n === null || n === undefined) return "-";
    var sign = n > 0 ? "+" : "";
    return sign + fmtNum(n, digits) + (suffix || "");
  }

  function deltaClass(pct) {
    if (pct === null || pct === undefined) return "flat";
    if (pct > 0) return "up";
    if (pct < 0) return "down";
    return "flat";
  }

  function parseDate(s) {
    // "YYYY-MM-DD" -> Date (local, treated as day granularity)
    var parts = s.split("-");
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  function formatDateKR(s) {
    var d = parseDate(s);
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) +
      " (" + WEEKDAY_KR[d.getDay()] + ")";
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function formatDateShort(s) {
    var d = parseDate(s);
    return pad2(d.getMonth() + 1) + "/" + pad2(d.getDate());
  }

  function formatGeneratedAt(iso) {
    var d = new Date(iso);
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) +
      " (" + WEEKDAY_KR[d.getDay()] + ") " + pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + " 기준";
  }

  function showError(message) {
    var banner = document.getElementById("error-banner");
    banner.textContent = message;
    banner.style.display = "block";
    document.getElementById("cards-section").style.display = "none";
    document.getElementById("ranking-section").style.display = "none";
    document.getElementById("chart-section").style.display = "none";
  }

  function renderHeader(data) {
    document.getElementById("generated-at").textContent = formatGeneratedAt(data.generated_at);
    document.getElementById("summary-text").textContent = data.summary_text;
  }

  function renderCards(data) {
    var container = document.getElementById("cards-container");
    container.innerHTML = "";

    CATEGORY_ORDER.forEach(function (category) {
      var markets = data.markets.filter(function (m) { return m.category === category; });
      if (markets.length === 0) return;

      var block = document.createElement("div");
      block.className = "category-block";

      var h3 = document.createElement("h3");
      h3.textContent = category;
      block.appendChild(h3);

      var grid = document.createElement("div");
      grid.className = "card-grid";

      markets.forEach(function (m) {
        var card = document.createElement("div");
        card.className = "card";

        var label = document.createElement("div");
        label.className = "label";
        label.textContent = m.label;
        card.appendChild(label);

        var close = document.createElement("div");
        close.className = "close";
        close.textContent = fmtNum(m.close, 2);
        card.appendChild(close);

        var delta = document.createElement("div");
        delta.className = "delta " + deltaClass(m.pct);
        delta.textContent = fmtSigned(m.change, 2, "") + " (" + fmtSigned(m.pct, 2, "%") + ") · " + m.move;
        card.appendChild(delta);

        var meta = document.createElement("div");
        meta.className = "meta";
        var volText = m.volume ? "거래량 " + m.volume.toLocaleString("ko-KR") : "거래량 정보 없음";
        meta.textContent = formatDateShort(m.date) + " 종가 · " + volText;
        card.appendChild(meta);

        grid.appendChild(card);
      });

      block.appendChild(grid);
      container.appendChild(block);
    });
  }

  function renderRanking(data) {
    var list = document.getElementById("ranking-list");
    list.innerHTML = "";

    var byLabel = {};
    data.markets.forEach(function (m) { byLabel[m.label] = m; });

    data.ranking.forEach(function (label, i) {
      var m = byLabel[label];
      if (!m) return;

      var li = document.createElement("li");

      var badge = document.createElement("span");
      badge.className = "rank-badge";
      badge.textContent = String(i + 1);
      li.appendChild(badge);

      var name = document.createElement("span");
      name.className = "rank-label";
      name.textContent = m.label;
      li.appendChild(name);

      var pct = document.createElement("span");
      pct.className = "rank-pct " + deltaClass(m.pct);
      pct.textContent = fmtSigned(m.pct, 2, "%");
      li.appendChild(pct);

      list.appendChild(li);
    });
  }

  // ---- Chart ----

  function buildIndexedSeries(market, rangeKey) {
    var hist = market[rangeKey === "1mo" ? "history_1mo" : "history_1y"];
    if (!hist || hist.length === 0) return [];
    var base = hist[0].close;
    return hist.map(function (pt) {
      return {
        date: pt.date,
        t: parseDate(pt.date).getTime(),
        value: base ? (pt.close / base - 1) * 100 : 0
      };
    });
  }

  function niceStep(range) {
    var raw = range / 5;
    var pow10 = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var candidates = [1, 2, 5, 10];
    var best = pow10;
    for (var i = 0; i < candidates.length; i++) {
      var v = candidates[i] * pow10;
      if (v >= raw) { best = v; break; }
      best = v;
    }
    return best;
  }

  function renderChart(data) {
    var wrap = document.getElementById("chart-svg-wrap");
    var legend = document.getElementById("chart-legend");
    wrap.innerHTML = "";
    legend.innerHTML = "";

    var seriesList = SERIES_META.map(function (meta) {
      var market = data.markets.filter(function (m) { return m.label === meta.label; })[0];
      if (!market) return null;
      return {
        label: meta.label,
        color: seriesColor(meta.label),
        points: buildIndexedSeries(market, state.range)
      };
    }).filter(function (s) { return s && s.points.length > 0; });

    // legend
    seriesList.forEach(function (s) {
      var item = document.createElement("div");
      item.className = "legend-item";
      var sw = document.createElement("span");
      sw.className = "legend-swatch";
      sw.style.background = s.color;
      item.appendChild(sw);
      var txt = document.createElement("span");
      txt.textContent = s.label;
      item.appendChild(txt);
      legend.appendChild(item);
    });

    if (seriesList.length === 0) {
      wrap.textContent = "표시할 데이터가 없습니다.";
      return;
    }

    var W = 800, H = 320;
    var margin = { top: 16, right: 20, bottom: 28, left: 46 };
    var innerW = W - margin.left - margin.right;
    var innerH = H - margin.top - margin.bottom;

    var allT = [];
    var allV = [];
    seriesList.forEach(function (s) {
      s.points.forEach(function (p) { allT.push(p.t); allV.push(p.value); });
    });
    var tMin = Math.min.apply(null, allT);
    var tMax = Math.max.apply(null, allT);
    var vMin = Math.min.apply(null, allV);
    var vMax = Math.max.apply(null, allV);
    if (vMin === vMax) { vMin -= 1; vMax += 1; }
    var vPad = (vMax - vMin) * 0.12;
    vMin -= vPad; vMax += vPad;

    function x(t) {
      if (tMax === tMin) return margin.left + innerW / 2;
      return margin.left + ((t - tMin) / (tMax - tMin)) * innerW;
    }
    function y(v) {
      return margin.top + innerH - ((v - vMin) / (vMax - vMin)) * innerH;
    }

    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("class", "trend-chart");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "기간 시작 대비 등락률 추이 차트");

    // gridlines + y ticks
    var step = niceStep(vMax - vMin);
    var gStart = Math.ceil(vMin / step) * step;
    for (var gv = gStart; gv <= vMax; gv += step) {
      var gy = y(gv);
      var line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", margin.left);
      line.setAttribute("x2", margin.left + innerW);
      line.setAttribute("y1", gy);
      line.setAttribute("y2", gy);
      line.setAttribute("stroke", "var(--grid)");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);

      var label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", margin.left - 8);
      label.setAttribute("y", gy + 3);
      label.setAttribute("text-anchor", "end");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "var(--text-muted)");
      label.textContent = (gv > 0 ? "+" : "") + gv.toFixed(gv % 1 === 0 ? 0 : 1) + "%";
      svg.appendChild(label);
    }

    // zero baseline (heavier)
    var zeroY = y(0);
    var baseline = document.createElementNS(svgNS, "line");
    baseline.setAttribute("x1", margin.left);
    baseline.setAttribute("x2", margin.left + innerW);
    baseline.setAttribute("y1", zeroY);
    baseline.setAttribute("y2", zeroY);
    baseline.setAttribute("stroke", "var(--baseline)");
    baseline.setAttribute("stroke-width", "1");
    svg.appendChild(baseline);

    // x ticks (first, mid, last)
    var tickTs = [tMin, tMin + (tMax - tMin) / 2, tMax];
    tickTs.forEach(function (t) {
      var tx = x(t);
      var label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", tx);
      label.setAttribute("y", margin.top + innerH + 18);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "var(--text-muted)");
      var d = new Date(t);
      label.textContent = pad2(d.getMonth() + 1) + "/" + pad2(d.getDate());
      svg.appendChild(label);
    });

    // lines
    seriesList.forEach(function (s) {
      var d = s.points.map(function (p, i) {
        return (i === 0 ? "M" : "L") + x(p.t).toFixed(2) + "," + y(p.value).toFixed(2);
      }).join(" ");
      var path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", s.color);
      path.setAttribute("stroke-width", "2");
      path.setAttribute("stroke-linejoin", "round");
      path.setAttribute("stroke-linecap", "round");
      svg.appendChild(path);
    });

    // endpoint markers + de-collided end labels
    var ends = seriesList.map(function (s) {
      var last = s.points[s.points.length - 1];
      return { label: s.label, color: s.color, x: x(last.t), y: y(last.value), value: last.value };
    });
    ends.sort(function (a, b) { return a.y - b.y; });
    var minGap = 13;
    for (var i = 1; i < ends.length; i++) {
      if (ends[i].y - ends[i - 1].y < minGap) {
        ends[i].y = ends[i - 1].y + minGap;
      }
    }

    ends.forEach(function (e) {
      var dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("cx", e.x);
      dot.setAttribute("cy", e.y === e.y ? e.y : e.y);
      dot.setAttribute("r", "4");
      dot.setAttribute("fill", e.color);
      dot.setAttribute("stroke", "var(--surface-1)");
      dot.setAttribute("stroke-width", "2");
      svg.appendChild(dot);
    });

    ends.forEach(function (e) {
      var label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", Math.min(e.x + 8, margin.left + innerW - 4));
      label.setAttribute("y", e.y + 3);
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "var(--text-secondary)");
      if (e.x + 8 > margin.left + innerW - 4) label.setAttribute("text-anchor", "end");
      label.textContent = e.label + " " + (e.value > 0 ? "+" : "") + e.value.toFixed(1) + "%";
      svg.appendChild(label);
    });

    // crosshair layer
    var crosshair = document.createElementNS(svgNS, "line");
    crosshair.setAttribute("y1", margin.top);
    crosshair.setAttribute("y2", margin.top + innerH);
    crosshair.setAttribute("stroke", "var(--baseline)");
    crosshair.setAttribute("stroke-width", "1");
    crosshair.setAttribute("visibility", "hidden");
    svg.appendChild(crosshair);

    var hitRect = document.createElementNS(svgNS, "rect");
    hitRect.setAttribute("x", margin.left);
    hitRect.setAttribute("y", margin.top);
    hitRect.setAttribute("width", innerW);
    hitRect.setAttribute("height", innerH);
    hitRect.setAttribute("fill", "transparent");
    svg.appendChild(hitRect);

    wrap.appendChild(svg);

    var tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    wrap.appendChild(tooltip);

    // merged unique dates across all series (for snapping + table)
    var dateMap = {};
    seriesList.forEach(function (s) {
      s.points.forEach(function (p) { dateMap[p.date] = p.t; });
    });
    var mergedDates = Object.keys(dateMap).sort(function (a, b) { return dateMap[a] - dateMap[b]; });

    function nearestDate(mouseT) {
      var best = mergedDates[0], bestDiff = Infinity;
      for (var i = 0; i < mergedDates.length; i++) {
        var diff = Math.abs(dateMap[mergedDates[i]] - mouseT);
        if (diff < bestDiff) { bestDiff = diff; best = mergedDates[i]; }
      }
      return best;
    }

    var rafPending = false;
    var lastEvent = null;

    function handleMove(evt) {
      lastEvent = evt;
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(function () {
        rafPending = false;
        if (!lastEvent) return;
        var rect = svg.getBoundingClientRect();
        var mouseX = (lastEvent.clientX - rect.left) / rect.width * W;
        var mouseT = tMin + ((mouseX - margin.left) / innerW) * (tMax - tMin);
        var dstr = nearestDate(mouseT);
        var dt = dateMap[dstr];
        var cx = x(dt);

        crosshair.setAttribute("x1", cx);
        crosshair.setAttribute("x2", cx);
        crosshair.setAttribute("visibility", "visible");

        var rows = seriesList.map(function (s) {
          var pt = s.points.filter(function (p) { return p.date === dstr; })[0];
          return {
            label: s.label,
            color: s.color,
            value: pt ? pt.value : null
          };
        });

        tooltip.innerHTML = "";
        var dateEl = document.createElement("div");
        dateEl.className = "t-date";
        dateEl.textContent = formatDateShort(dstr);
        tooltip.appendChild(dateEl);
        rows.forEach(function (r) {
          var row = document.createElement("div");
          row.className = "t-row";
          var key = document.createElement("span");
          key.className = "t-key";
          key.style.background = r.color;
          row.appendChild(key);
          var name = document.createElement("span");
          name.textContent = r.label;
          row.appendChild(name);
          var val = document.createElement("span");
          val.className = "t-value";
          val.textContent = r.value === null ? "-" : (r.value > 0 ? "+" : "") + r.value.toFixed(2) + "%";
          row.appendChild(val);
          tooltip.appendChild(row);
        });

        var tipX = (cx / W) * rect.width;
        var tipY = ((margin.top) / H) * rect.height;
        tooltip.style.left = tipX + "px";
        tooltip.style.top = tipY + "px";
        tooltip.classList.add("visible");
      });
    }

    function handleLeave() {
      crosshair.setAttribute("visibility", "hidden");
      tooltip.classList.remove("visible");
    }

    hitRect.addEventListener("pointermove", handleMove);
    hitRect.addEventListener("pointerleave", handleLeave);

    renderDataTable(seriesList, mergedDates, dateMap);
  }

  function renderDataTable(seriesList, mergedDates, dateMap) {
    var tableWrap = document.getElementById("data-table-wrap");
    tableWrap.innerHTML = "";

    var table = document.createElement("table");
    table.className = "data-table";

    var thead = document.createElement("thead");
    var headRow = document.createElement("tr");
    var dateTh = document.createElement("th");
    dateTh.textContent = "날짜";
    headRow.appendChild(dateTh);
    seriesList.forEach(function (s) {
      var th = document.createElement("th");
      th.textContent = s.label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    mergedDates.forEach(function (dstr) {
      var tr = document.createElement("tr");
      var dateTd = document.createElement("td");
      dateTd.textContent = formatDateShort(dstr);
      tr.appendChild(dateTd);
      seriesList.forEach(function (s) {
        var pt = s.points.filter(function (p) { return p.date === dstr; })[0];
        var td = document.createElement("td");
        td.textContent = pt ? (pt.value > 0 ? "+" : "") + pt.value.toFixed(2) + "%" : "-";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tableWrap.appendChild(table);
  }

  function setupChartControls(data) {
    var buttons = document.querySelectorAll(".chart-controls button");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        state.range = btn.getAttribute("data-range");
        renderChart(data);
      });
    });

    document.getElementById("table-toggle").addEventListener("click", function () {
      var tw = document.getElementById("data-table-wrap");
      tw.classList.toggle("visible");
      this.textContent = tw.classList.contains("visible") ? "표 숨기기" : "표로 보기";
    });
  }

  function renderAll(data) {
    state.data = data;
    renderHeader(data);
    renderCards(data);
    renderRanking(data);
    setupChartControls(data);
    renderChart(data);
  }

  // ---- 오늘의 주요 섹터 (기존 대시보드와 독립적으로 fetch/렌더링됨 — 실패해도
  // 나머지 섹션에 영향을 주지 않는다. 아래쪽 fetchJSON 초기화 코드 참고) ----

  function relativeTimeKR(iso) {
    var diffMs = Date.now() - new Date(iso).getTime();
    var hours = Math.round(diffMs / 3600000);
    if (hours < 1) return "방금 전";
    if (hours < 24) return hours + "시간 전";
    return Math.round(hours / 24) + "일 전";
  }

  function renderSectorNews(news) {
    var ul = document.createElement("ul");
    ul.className = "sector-news";
    if (!news || news.length === 0) {
      var li = document.createElement("li");
      li.className = "no-news";
      li.textContent = "관련 뉴스 없음";
      ul.appendChild(li);
      return ul;
    }
    news.forEach(function (n) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = n.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = n.title;
      li.appendChild(a);
      var meta = document.createElement("span");
      meta.className = "news-meta";
      meta.textContent = (n.publisher || "알 수 없음") + " · " + relativeTimeKR(n.published_at);
      li.appendChild(meta);
      ul.appendChild(li);
    });
    return ul;
  }

  function renderSectors(config, data) {
    var section = document.getElementById("sector-section");
    section.innerHTML = "";

    if (!data || !data.top_sectors || data.top_sectors.length === 0) return;

    var byLabel = {};
    data.sectors.forEach(function (s) { byLabel[s.label] = s; });
    var ranked = data.top_sectors
      .map(function (label) { return byLabel[label]; })
      .filter(Boolean);
    if (ranked.length === 0) return;

    var h2 = document.createElement("h2");
    h2.textContent = "오늘의 주요 섹터 (미국)";
    section.appendChild(h2);

    var caption = document.createElement("p");
    caption.className = "sector-caption";
    caption.textContent = "가중치는 S&P500 실제 섹터 비중, 선정 기준은 가격 변동입니다. 뉴스는 선정된 섹터의 최신 기사이며 오늘 가장 중요한 뉴스 전체를 의미하지 않습니다.";
    section.appendChild(caption);

    if (state.data && state.data.generated_at && data.generated_at) {
      var sectorDate = data.generated_at.slice(0, 10);
      var marketDate = state.data.generated_at.slice(0, 10);
      if (sectorDate !== marketDate) {
        var note = document.createElement("p");
        note.className = "sector-stale-note";
        note.textContent = "이 섹터 데이터는 " + sectorDate + " 기준입니다 (지수 데이터보다 오래됨).";
        section.appendChild(note);
      }
    }

    var grid = document.createElement("div");
    grid.className = "sector-grid";

    ranked.forEach(function (s) {
      var card = document.createElement("div");
      card.className = "card sector-card";

      var rankTag = document.createElement("div");
      rankTag.className = "rank-tag";
      rankTag.textContent = s.rank + "위";
      card.appendChild(rankTag);

      var label = document.createElement("div");
      label.className = "label";
      label.textContent = s.label;
      card.appendChild(label);

      var delta = document.createElement("div");
      delta.className = "delta " + deltaClass(s.pct);
      delta.textContent = fmtSigned(s.pct, 2, "%");
      card.appendChild(delta);

      var weightMeta = document.createElement("div");
      weightMeta.className = "weight-meta";
      weightMeta.textContent = "시가총액 비중 약 " + fmtNum(s.weight_pct, 1) + "% · 기여도 " + fmtSigned(s.contribution, 3, "%p");
      card.appendChild(weightMeta);

      card.appendChild(renderSectorNews(s.news));

      grid.appendChild(card);
    });

    section.appendChild(grid);
  }

  function fetchJSON(path) {
    return fetch(path, { cache: "no-store" }).then(function (res) {
      if (!res.ok) throw new Error(path + " 요청 실패 (HTTP " + res.status + ")");
      return res.json();
    });
  }

  Promise.all([fetchJSON("config/markets.json"), fetchJSON("data/latest.json")])
    .then(function (results) {
      var config = results[0];
      var data = results[1];
      SERIES_META = buildSeriesMeta(config.markets);
      CATEGORY_ORDER = config.categories;
      renderAll(data);
    })
    .catch(function (err) {
      showError("시황 데이터를 불러오는 데 실패했습니다: " + err.message);
    });

  // 섹터 섹션은 별도 체인으로 로드 — 실패해도 위 대시보드에는 영향 없음.
  Promise.all([fetchJSON("config/sectors.json"), fetchJSON("data/sectors.json")])
    .then(function (results) {
      renderSectors(results[0], results[1]);
    })
    .catch(function (err) {
      console.warn("섹터 섹션 로드 실패:", err);
    });
})();
