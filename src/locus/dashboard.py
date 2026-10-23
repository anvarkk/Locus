"""Self-contained Leaflet dashboard generator (no JS build step)."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .config import get_business_type
from .geo import cell_boundary_lonlat
from .models import PipelineResult

TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<style>
  :root {
    --bg: #0b1220;
    --panel: #111a2e;
    --panel-2: #17233c;
    --text: #e6edf7;
    --muted: #8fa3c0;
    --line: #24324d;
    --green: #22c55e;
    --lime: #84cc16;
    --amber: #f59e0b;
    --red: #ef4444;
    --blue: #38bdf8;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text); overflow: hidden;
  }
  #app { display: flex; height: 100vh; }
  aside {
    width: 400px; min-width: 340px; background: var(--panel);
    border-right: 1px solid var(--line); display: flex; flex-direction: column;
    z-index: 500;
  }
  header { padding: 18px 18px 12px; border-bottom: 1px solid var(--line); }
  .brand { display: flex; align-items: center; gap: 10px; }
  .logo {
    width: 34px; height: 34px; border-radius: 10px;
    background: linear-gradient(135deg, #22c55e, #38bdf8);
    display: grid; place-items: center; font-weight: 800; color: #06111f;
  }
  h1 { font-size: 19px; margin: 0; letter-spacing: .2px; }
  .sub { color: var(--muted); font-size: 12px; margin-top: 8px; line-height: 1.45; }
  .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 12px 18px; }
  .card { background: var(--panel-2); border: 1px solid var(--line); border-radius: 10px; padding: 9px 11px; }
  .card .k { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .7px; }
  .card .v { font-size: 20px; font-weight: 700; margin-top: 3px; }
  .hypo {
    margin: 0 18px 12px; padding: 10px 12px; border-radius: 10px;
    background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.35);
    font-size: 12px; line-height: 1.5;
  }
  .hypo b { color: var(--green); }
  .controls { padding: 0 18px 10px; display: flex; gap: 8px; }
  input[type=search] {
    width: 100%; background: var(--panel-2); color: var(--text);
    border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;
    outline: none; font-size: 13px;
  }
  input[type=search]:focus { border-color: var(--blue); }
  .list { flex: 1; overflow-y: auto; padding: 0 10px 14px; }
  .item {
    display: flex; gap: 10px; padding: 10px; border-radius: 10px;
    border: 1px solid transparent; cursor: pointer; align-items: center;
  }
  .item:hover { background: var(--panel-2); border-color: var(--line); }
  .rank {
    width: 30px; height: 30px; border-radius: 8px; display: grid;
    place-items: center; font-size: 12px; font-weight: 700; flex: none;
    background: var(--panel-2); color: var(--muted); border: 1px solid var(--line);
  }
  .item .meta { min-width: 0; flex: 1; }
  .item .name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .item .details { color: var(--muted); font-size: 11px; margin-top: 3px; }
  .score { font-size: 16px; font-weight: 800; flex: none; }
  footer { padding: 10px 18px 14px; border-top: 1px solid var(--line); color: var(--muted); font-size: 10px; line-height: 1.5; }
  main { position: relative; flex: 1; min-width: 0; }
  #map { position: absolute; inset: 0; background: #0e1728; }
  .legend {
    position: absolute; right: 14px; bottom: 18px; z-index: 450;
    background: rgba(17,26,46,.94); border: 1px solid var(--line);
    border-radius: 10px; padding: 10px 12px; font-size: 11px; line-height: 1.8;
  }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }
  .layers {
    position: absolute; left: 12px; top: 12px; z-index: 450;
    background: rgba(17,26,46,.94); border: 1px solid var(--line);
    border-radius: 10px; padding: 9px 12px; font-size: 12px;
    display: flex; gap: 14px; align-items: center;
  }
  .layers label { display: flex; gap: 6px; align-items: center; cursor: pointer; color: var(--muted); }
  .leaflet-popup-content-wrapper, .leaflet-popup-tip { background: #111a2e; color: var(--text); }
  .leaflet-popup-content { font-size: 12px; line-height: 1.55; margin: 12px 14px; }
  .popup-title { font-weight: 700; font-size: 13px; margin-bottom: 4px; }
  .popup-grid { display: grid; grid-template-columns: 1fr auto; gap: 2px 18px; }
  .popup-grid span:nth-child(odd) { color: var(--muted); }
  .leaflet-container { font-family: inherit; }
  @media (max-width: 820px) {
    #app { flex-direction: column; }
    aside { width: 100%; min-width: 0; height: 46vh; }
    main { height: 54vh; }
    .cards { grid-template-columns: repeat(4, 1fr); }
    .card .v { font-size: 15px; }
  }
</style>
</head>
<body>
<div id="app">
  <aside>
    <header>
      <div class="brand">
        <div class="logo">L</div>
        <div>
          <h1>Locus · __CITY__</h1>
          <div class="sub">__BUSINESS__ · H3 res __RES__ · радиус __RADIUS__ м</div>
        </div>
      </div>
      <div class="sub">Индекс инвестиционной привлекательности: спрос, транспорт,
        разнообразие POI и штраф за конкуренцию.</div>
    </header>
    <div class="cards">
      <div class="card"><div class="k">Ячеек</div><div class="v" id="stat-cells">—</div></div>
      <div class="card"><div class="k">Средний индекс</div><div class="v" id="stat-mean">—</div></div>
      <div class="card"><div class="k">Максимум</div><div class="v" id="stat-max">—</div></div>
      <div class="card"><div class="k">Источник</div><div class="v" id="stat-source" style="font-size:13px;padding-top:5px">—</div></div>
    </div>
    <div class="hypo" id="hypo" style="display:none"></div>
    <div class="controls">
      <input id="search" type="search" placeholder="Поиск по H3 / рекомендации">
    </div>
    <div class="list" id="list"></div>
    <footer>
      __SOURCE_NOTE__<br>
      Индекс — эвристика для приоритизации, не финансовая модель.
      Пайплайн: Python → H3 → PostGIS → dbt → Dagster.
    </footer>
  </aside>
  <main>
    <div id="map"></div>
    <div class="layers">
      <label><input type="checkbox" id="toggle-cells" checked> Сетка</label>
      <label><input type="checkbox" id="toggle-pois" checked> POI</label>
      <label><input type="checkbox" id="toggle-borders"> Границы</label>
    </div>
    <div class="legend">
      <div><span class="dot" style="background:#22c55e"></span>70–100 · открывать</div>
      <div><span class="dot" style="background:#84cc16"></span>55–70 · рассмотреть</div>
      <div><span class="dot" style="background:#f59e0b"></span>40–55 · наблюдать</div>
      <div><span class="dot" style="background:#ef4444"></span>0–40 · не рекомендуется</div>
      <div style="margin-top:4px;color:#8fa3c0"><span class="dot" style="background:#38bdf8;border-radius:50%"></span>POI</div>
    </div>
  </main>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
const DATA = __PAYLOAD__;
const cells = DATA.cells;
const pois = DATA.pois;
const summary = DATA.summary;
const competitorCategories = new Set(DATA.competitor_categories);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}
function fmt(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString("ru-RU", {maximumFractionDigits: digits});
}
function color(index) {
  if (index >= 70) return "#22c55e";
  if (index >= 55) return "#84cc16";
  if (index >= 40) return "#f59e0b";
  return "#ef4444";
}

const map = L.map("map", {zoomControl: true, preferCanvas: true}).setView(
  [DATA.center.lat, DATA.center.lon], 12
);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

const cellLayer = L.geoJSON({type: "FeatureCollection", features: cells.map((c) => ({
  type: "Feature", id: c.h3,
  geometry: {type: "Polygon", coordinates: [c.polygon]},
  properties: c
}))}, {
  style: (feature) => ({
    color: color(feature.properties.investment_index),
    weight: 1,
    opacity: 0.75,
    fillColor: color(feature.properties.investment_index),
    fillOpacity: 0.42
  }),
  onEachFeature: (feature, layer) => {
    layer.bindPopup(popupHtml(feature.properties));
    layer.on("click", () => selectCell(feature.properties.h3));
  }
}).addTo(map);

const poiLayer = L.layerGroup();
pois.forEach((p) => {
  const isComp = competitorCategories.has(p.category);
  L.circleMarker([p.lat, p.lon], {
    radius: isComp ? 4 : 3,
    color: isComp ? "#fb7185" : "#38bdf8",
    weight: 1,
    fillColor: isComp ? "#fb7185" : "#38bdf8",
    fillOpacity: 0.85
  }).bindPopup(`<div class="popup-title">${esc(p.name)}</div>
    <div style="color:#8fa3c0">${esc(p.category)}${isComp ? " · конкурент" : ""}</div>`)
    .addTo(poiLayer);
});
poiLayer.addTo(map);

// Base map tiles can fail offline; keep the H3 layer usable anyway.
map.fitBounds(cellLayer.getBounds(), {padding: [20, 20]});

const layerByH3 = {};
cellLayer.eachLayer((layer) => { layerByH3[layer.feature.properties.h3] = layer; });

const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
let activeH3 = null;

function popupHtml(p) {
  return `<div class="popup-title">#${p.rank} · индекс ${fmt(p.investment_index)}</div>
    <div style="color:${color(p.investment_index)};margin-bottom:6px">${esc(p.recommendation)}</div>
    <div class="popup-grid">
      <span>Спрос</span><b>${fmt(p.demand_score * 100, 0)}</b>
      <span>Транспорт</span><b>${fmt(p.access_score * 100, 0)}</b>
      <span>Разнообразие</span><b>${fmt(p.diversity_score * 100, 0)}</b>
      <span>Конкуренция</span><b>${fmt(p.competition_score * 100, 0)}</b>
      <span>Новостройки</span><b>${p.new_buildings} (${p.new_residential_units} кв.)</b>
      <span>Конкуренты</span><b>${p.competitor_count} (${fmt(p.competitor_density_km2, 2)}/км²)</b>
      <span>Транспорт</span><b>${p.transport_stops}</b>
      <span>До центра</span><b>${fmt(p.distance_to_center_m / 1000, 1)} км</b>
      <span>Уверенность</span><b>${fmt(p.confidence * 100, 0)}%</b>
    </div>
    <div style="margin-top:7px;color:#8fa3c0">${esc(p.explanation)}</div>
    <div style="margin-top:6px;font-size:10px;color:#5f728e">${p.h3}</div>`;
}

function renderList(filter = "") {
  const query = filter.trim().toLowerCase();
  const rows = cells.filter((c) =>
    !query ||
    c.h3.toLowerCase().includes(query) ||
    c.recommendation.toLowerCase().includes(query)
  ).slice(0, 80);
  listEl.innerHTML = rows.map((c) => `
    <div class="item" data-h3="${c.h3}" onclick="focusCell('${c.h3}')">
      <div class="rank">${c.rank}</div>
      <div class="meta">
        <div class="name">${esc(c.recommendation)}</div>
        <div class="details">${c.new_buildings} новостр. · ${c.competitor_count} конкур. · ${c.transport_stops} транспорт</div>
      </div>
      <div class="score" style="color:${color(c.investment_index)}">${fmt(c.investment_index)}</div>
    </div>`).join("");
  if (!rows.length) {
    listEl.innerHTML = '<div style="padding:20px;color:#8fa3c0;font-size:12px">Ничего не найдено</div>';
  }
}

function selectCell(h3) {
  if (activeH3 && layerByH3[activeH3]) {
    const prev = layerByH3[activeH3];
    prev.setStyle({weight: 1, opacity: 0.75});
  }
  activeH3 = h3;
  const layer = layerByH3[h3];
  if (layer) layer.setStyle({weight: 3, opacity: 1});
}

function focusCell(h3) {
  const layer = layerByH3[h3];
  if (!layer) return;
  selectCell(h3);
  map.flyTo(layer.getBounds().getCenter(), 15, {duration: 0.7});
  layer.openPopup();
}

searchEl.addEventListener("input", (e) => renderList(e.target.value));

document.getElementById("stat-cells").textContent = fmt(summary.cells, 0);
document.getElementById("stat-mean").textContent = fmt(summary.mean_index);
document.getElementById("stat-max").textContent = fmt(summary.max_index);
document.getElementById("stat-source").textContent = DATA.source === "synthetic" ? "Синтетика" : "OSM";

if (summary.hypothesis && summary.hypothesis.n) {
  const h = summary.hypothesis;
  const el = document.getElementById("hypo");
  el.style.display = "block";
  el.innerHTML = `<b>Проверка гипотезы (демо)</b><br>
    Верхний квартиль индекса: <b>${fmt(h.top_quartile_growth_pct)}%</b> роста выручки
    против <b>${fmt(h.bottom_quartile_growth_pct)}%</b> в нижнем.<br>
    Uplift <b>${fmt(h.uplift_pp)} п.п.</b> · Spearman ρ = <b>${fmt(h.spearman_rho, 2)}</b>
    <span style="color:#8fa3c0">(синтетическая выручка, только проверка пайплайна)</span>`;
}

document.getElementById("toggle-cells").addEventListener("change", (e) => {
  if (e.target.checked) cellLayer.addTo(map); else map.removeLayer(cellLayer);
});
document.getElementById("toggle-pois").addEventListener("change", (e) => {
  if (e.target.checked) poiLayer.addTo(map); else map.removeLayer(poiLayer);
});
document.getElementById("toggle-borders").addEventListener("change", (e) => {
  cellLayer.eachLayer((layer) => layer.setStyle({
    fillOpacity: e.target.checked ? 0.05 : 0.42,
    weight: e.target.checked ? 1.6 : 1
  }));
});

renderList();
</script>
</body>
</html>
"""


def render_dashboard(result: PipelineResult, path: Path) -> Path:
    summary = result.summary
    business = get_business_type(result.business_type)
    cells = []
    for score in result.scores:
        payload = score.as_dict()
        payload["h3"] = score.h3
        payload["polygon"] = cell_boundary_lonlat(score.h3)
        cells.append(payload)
    pois = [
        {
            "name": poi.display_name,
            "category": poi.category,
            "lat": poi.lat,
            "lon": poi.lon,
        }
        for poi in result.dataset.pois
    ]
    data = {
        "cells": cells,
        "pois": pois,
        "summary": summary,
        "center": {
            "lat": result.dataset.city.lat,
            "lon": result.dataset.city.lon,
        },
        "source": result.dataset.source,
        "competitor_categories": list(business.competitor_categories),
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    title = f"Locus · {summary.get('city_name', '')} · {business.title}"
    source_note = (
        "Демо-данные синтетические (детерминированная генерация)."
        if result.dataset.source == "synthetic"
        else "Данные: OpenStreetMap / открытые данные города."
    )
    page = (
        TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__CITY__", html.escape(str(summary.get("city_name", ""))))
        .replace("__BUSINESS__", html.escape(business.title))
        .replace("__RES__", str(summary.get("h3_resolution", "")))
        .replace("__RADIUS__", str(summary.get("radius_m", "")))
        .replace("__SOURCE_NOTE__", html.escape(source_note))
        .replace("__PAYLOAD__", payload)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
