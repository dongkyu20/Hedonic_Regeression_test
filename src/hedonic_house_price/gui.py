from __future__ import annotations

import html
import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .law_codes import CITY_DISTRICT_CODES, SEOUL_DISTRICT_CODES, city_code_for_lawd_cd
from .modeling import PredictionInput, load_model, predict_price


DEFAULT_SEOUL_MODEL_PATH = "artifacts/best_models/seoul_best_model.pkl"
DEFAULT_BUSAN_MODEL_PATH = "artifacts/best_models/busan_best_model.pkl"


@dataclass(frozen=True)
class CityModelRouter:
    models: dict[str, object]
    model_paths: dict[str, str]
    fallback_model: object | None = None
    fallback_model_path: str | None = None

    def model_for(self, prediction_input: PredictionInput) -> object:
        city_code = self.city_code_for(prediction_input)
        model = self.models.get(city_code)
        if model is not None:
            return model
        if self.fallback_model is not None:
            return self.fallback_model
        raise ValueError(f"model is not configured for city_code: {city_code}")

    def city_code_for(self, prediction_input: PredictionInput) -> str:
        return city_code_for_lawd_cd(prediction_input.lawd_cd)

    def model_path_for(self, prediction_input: PredictionInput) -> str:
        city_code = self.city_code_for(prediction_input)
        if city_code in self.model_paths:
            return self.model_paths[city_code]
        if self.fallback_model_path:
            return self.fallback_model_path
        return ""

    def predict(self, prediction_input: PredictionInput) -> dict[str, int | float | str]:
        prediction = dict(predict_price(self.model_for(prediction_input), prediction_input))
        prediction["model_city_code"] = self.city_code_for(prediction_input)
        prediction["model_path"] = self.model_path_for(prediction_input)
        return prediction


def render_index_html(
    model_path: str | None = None,
    *,
    model_label: str | None = None,
    model_paths: dict[str, str] | None = None,
) -> str:
    city_names = {
        "seoul": "서울",
        "busan": "부산",
    }
    city_options = "\n".join(
        [
            '<option value="seoul">서울</option>',
            '<option value="busan">부산</option>',
        ]
    )
    district_options = "\n".join(
        (
            f'<option data-city="{html.escape(city_code)}" value="{html.escape(district)}" selected>{html.escape(district)}</option>'
            if city_code == "seoul" and district == "강남구"
            else f'<option data-city="{html.escape(city_code)}" value="{html.escape(district)}">{html.escape(district)}</option>'
        )
        for city_code, district_codes in CITY_DISTRICT_CODES.items()
        for district in district_codes
    )
    display_model_label = model_label or "단일 모델"
    if model_paths:
        model_title = " · ".join(
            f"{city_code}: {path}"
            for city_code, path in model_paths.items()
        )
        model_summary = " · ".join(
            f"{city_names.get(city_code, city_code)} 개선 모델"
            for city_code in model_paths
        )
    else:
        model_title = model_path or ""
        model_summary = model_path or "모델 파일 미지정"
    escaped_model_label = html.escape(display_model_label)
    escaped_model_title = html.escape(model_title)
    escaped_model_summary = html.escape(model_summary)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>서울·부산 아파트 매매가 예측</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --surface: #ffffff;
      --text: #1d2430;
      --muted: #667085;
      --line: #d8dee8;
      --accent: #2563eb;
      --accent-strong: #1e40af;
      --danger: #b42318;
      --success: #047857;
      --shadow: 0 16px 36px rgba(29, 36, 48, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    .app {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}
    header {{
      display: grid;
      gap: 8px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.25;
      font-weight: 700;
    }}
    .model {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
      gap: 18px;
      align-items: start;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    form.panel {{
      padding: 20px;
    }}
    .result.panel {{
      padding: 20px;
      min-height: 222px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
      font-weight: 600;
    }}
    input, select {{
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 11px;
      color: var(--text);
      background: #fff;
      font-size: 15px;
      letter-spacing: 0;
    }}
    input:focus, select:focus {{
      outline: 2px solid rgba(37, 99, 235, 0.2);
      border-color: var(--accent);
    }}
    .actions {{
      display: flex;
      justify-content: flex-end;
      margin-top: 18px;
    }}
    button {{
      min-height: 42px;
      border: 0;
      border-radius: 6px;
      padding: 0 18px;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      font-size: 15px;
      cursor: pointer;
    }}
    button:hover {{ background: var(--accent-strong); }}
    button:disabled {{ opacity: 0.62; cursor: wait; }}
    .result h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      line-height: 1.3;
    }}
    .price {{
      font-size: 30px;
      line-height: 1.2;
      font-weight: 800;
      margin: 8px 0 4px;
    }}
    .subprice {{
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 18px;
    }}
    .meta {{
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }}
    .error {{
      color: var(--danger);
      font-weight: 700;
      line-height: 1.45;
    }}
    .ready {{
      color: var(--success);
      font-size: 14px;
    }}
    @media (max-width: 820px) {{
      main {{ grid-template-columns: 1fr; }}
      .grid {{ grid-template-columns: 1fr; }}
      .price {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <header>
      <h1>서울·부산 아파트 매매가 예측</h1>
      <div class="model" title="{escaped_model_title}">{escaped_model_label} · {escaped_model_summary}</div>
    </header>
    <main>
      <form id="prediction-form" class="panel">
        <input type="hidden" name="property_type" value="apartment">
        <div class="grid">
          <label>도시
            <select name="city_code" required>
              {city_options}
            </select>
          </label>
          <label>자치구
            <select name="district" required>
              {district_options}
            </select>
          </label>
          <label>법정동
            <input name="legal_dong" type="text" value="역삼동" required>
          </label>
          <label>전용면적 m²
            <input name="area" type="number" inputmode="decimal" step="0.01" min="1" value="84.95" required>
          </label>
          <label>층
            <input name="floor" type="number" inputmode="numeric" step="1" value="15" required>
          </label>
          <label>건축년도
            <input name="build_year" type="number" inputmode="numeric" min="1900" value="1981" required>
          </label>
          <label>계약년도
            <input name="deal_year" type="number" inputmode="numeric" min="2000" value="2026" required>
          </label>
          <label>계약월
            <input name="deal_month" type="number" inputmode="numeric" min="1" max="12" value="6" required>
          </label>
          <label>계약일
            <input name="deal_day" type="number" inputmode="numeric" min="1" max="31" value="15">
          </label>
        </div>
        <div class="actions">
          <button type="submit">예측</button>
        </div>
      </form>
      <section class="result panel" aria-live="polite">
        <h2>예측 결과</h2>
        <div id="result" class="ready">입력값을 확인하고 예측을 실행하세요.</div>
      </section>
    </main>
  </div>
  <script>
    const form = document.getElementById("prediction-form");
    const result = document.getElementById("result");
    const button = form.querySelector("button");
    const citySelect = form.elements.city_code;
    const districtSelect = form.elements.district;

    function syncDistrictOptions() {{
      const city = citySelect.value;
      let firstVisible = "";
      for (const option of districtSelect.options) {{
        const visible = option.dataset.city === city;
        option.hidden = !visible;
        option.disabled = !visible;
        if (visible && !firstVisible) {{
          firstVisible = option.value;
        }}
      }}
      if (districtSelect.selectedOptions.length && districtSelect.selectedOptions[0].dataset.city !== city) {{
        districtSelect.value = firstVisible;
      }}
    }}

    citySelect.addEventListener("change", syncDistrictOptions);
    syncDistrictOptions();

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      button.disabled = true;
      result.className = "ready";
      result.textContent = "계산 중";
      const payload = Object.fromEntries(new FormData(form).entries());
      try {{
        const response = await fetch("/api/predict", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await response.json();
        if (!response.ok) {{
          throw new Error(data.error || "예측에 실패했습니다.");
        }}
        result.className = "";
        result.innerHTML = `
          <div class="price">${{Number(data.price_krw).toLocaleString("ko-KR")}}원</div>
            <div class="subprice">${{Number(data.price_manwon).toLocaleString("ko-KR")}}만원</div>
          <div class="meta">
            <div>로그 가격 ${{Number(data.log_price).toFixed(4)}}</div>
            <div>모델 ${{modelLabel(data.model_city_code || payload.city_code)}}</div>
            <div>자치구 ${{payload.district}} · 법정동 ${{payload.legal_dong}} · ${{payload.floor}}층</div>
          </div>
        `;
      }} catch (error) {{
        result.className = "error";
        result.textContent = error.message;
      }} finally {{
        button.disabled = false;
      }}
    }});

    function modelLabel(cityCode) {{
      if (cityCode === "seoul") {{
        return "서울 개선 모델";
      }}
      if (cityCode === "busan") {{
        return "부산 개선 모델";
      }}
      return "단일 모델";
    }}
  </script>
</body>
</html>
"""


def build_prediction_input(payload: dict[str, Any]) -> PredictionInput:
    district = _required_text(payload, "district")
    lawd_cd = str(payload.get("lawd_cd") or _lawd_cd_for_payload(payload, district)).strip()
    if not lawd_cd:
        raise ValueError("lawd_cd is required for unknown district")

    return PredictionInput(
        district=district,
        lawd_cd=lawd_cd,
        deal_year=_required_int(payload, "deal_year"),
        deal_month=_required_int(payload, "deal_month"),
        deal_day=_optional_int(payload, "deal_day", default=15),
        legal_dong=_required_text(payload, "legal_dong"),
        apartment_name="",
        property_type=str(payload.get("property_type") or "apartment").strip(),
        house_type=str(payload.get("house_type") or "").strip(),
        land_area_m2=_optional_float(payload, "land_area"),
        exclusive_area_m2=_required_float(payload, "area"),
        floor=_required_int(payload, "floor"),
        build_year=_required_int(payload, "build_year"),
    )


def run_gui_server(
    model_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    seoul_model_path: str = DEFAULT_SEOUL_MODEL_PATH,
    busan_model_path: str = DEFAULT_BUSAN_MODEL_PATH,
) -> None:
    router = load_city_model_router(
        model_path=model_path,
        seoul_model_path=seoul_model_path,
        busan_model_path=busan_model_path,
    )
    handler = _make_handler(router)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"GUI running at http://{host}:{port}", flush=True)
    server.serve_forever()


def load_city_model_router(
    *,
    model_path: str | None = None,
    seoul_model_path: str = DEFAULT_SEOUL_MODEL_PATH,
    busan_model_path: str = DEFAULT_BUSAN_MODEL_PATH,
) -> CityModelRouter:
    if model_path:
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"model file does not exist: {model_path}")
        return CityModelRouter(models={}, model_paths={}, fallback_model=load_model(model_file), fallback_model_path=model_path)

    model_paths = {
        "seoul": seoul_model_path,
        "busan": busan_model_path,
    }
    models: dict[str, object] = {}
    for city_code, path in model_paths.items():
        model_file = Path(path)
        if not model_file.exists():
            raise FileNotFoundError(f"{city_code} model file does not exist: {path}")
        models[city_code] = load_model(model_file)
    return CityModelRouter(models=models, model_paths=model_paths)


def _make_handler(router: CityModelRouter) -> type[BaseHTTPRequestHandler]:
    class GuiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                _send_text(
                    self,
                    200,
                    render_index_html(
                        model_label="서울/부산 개선 모델" if router.models else "단일 모델",
                        model_paths=router.model_paths,
                        model_path=router.fallback_model_path,
                    ),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/api/health":
                _send_json(self, 200, {"ok": True})
                return
            _send_json(self, 404, {"error": "not found"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/api/predict":
                _send_json(self, 404, {"error": "not found"})
                return

            try:
                payload = _read_json_body(self)
                prediction_input = build_prediction_input(payload)
                prediction = router.predict(prediction_input)
                _send_json(self, 200, prediction)
            except Exception as exc:
                _send_json(self, 400, {"error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            return

    return GuiHandler


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(length).decode("utf-8")
    if not raw_body:
        raise ValueError("request body is empty")
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _lawd_cd_for_payload(payload: dict[str, Any], district: str) -> str:
    city_code = str(payload.get("city_code") or "").strip().lower()
    if city_code:
        district_codes = CITY_DISTRICT_CODES.get(city_code)
        if district_codes is None:
            raise ValueError(f"unsupported city_code: {city_code}")
        return district_codes.get(district, "")

    matches = [
        lawd_cd
        for district_codes in CITY_DISTRICT_CODES.values()
        for candidate_district, lawd_cd in district_codes.items()
        if candidate_district == district
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("city_code is required for ambiguous district")
    return SEOUL_DISTRICT_CODES.get(district, "")


def _send_text(handler: BaseHTTPRequestHandler, status: int, text: str, content_type: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    _send_text(handler, status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name, "")).strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_int(payload: dict[str, Any], name: str) -> int:
    value = _required_text(payload, name)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_int(payload: dict[str, Any], name: str, default: int) -> int:
    value = str(payload.get(name, "")).strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_float(payload: dict[str, Any], name: str) -> float | None:
    value = str(payload.get(name, "")).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _required_float(payload: dict[str, Any], name: str) -> float:
    value = _required_text(payload, name)
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
