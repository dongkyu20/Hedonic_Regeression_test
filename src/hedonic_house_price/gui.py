from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .law_codes import SEOUL_DISTRICT_CODES
from .modeling import PredictionInput, load_model, predict_price


def render_index_html(model_path: str) -> str:
    district_options = "\n".join(
        f'<option value="{html.escape(district)}">{html.escape(district)}</option>'
        for district in SEOUL_DISTRICT_CODES
    )
    property_type_options = "\n".join(
        [
            '<option value="apartment">아파트</option>',
            '<option value="officetel">오피스텔</option>',
            '<option value="rowhouse">연립·다세대</option>',
        ]
    )
    escaped_model_path = html.escape(model_path)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>서울 공동주택 매매가 예측</title>
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
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
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
      white-space: nowrap;
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
      header {{ align-items: flex-start; flex-direction: column; }}
      .model {{ white-space: normal; }}
      main {{ grid-template-columns: 1fr; }}
      .grid {{ grid-template-columns: 1fr; }}
      .price {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <header>
      <h1>서울 공동주택 매매가 예측</h1>
      <div class="model">모델 {escaped_model_path}</div>
    </header>
    <main>
      <form id="prediction-form" class="panel">
        <div class="grid">
          <label>주택유형
            <select name="property_type" required>
              {property_type_options}
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
          <label>연립·다세대 유형
            <input name="house_type" type="text" placeholder="예: 다세대">
          </label>
          <label>대지권면적 m²
            <input name="land_area" type="number" inputmode="decimal" step="0.01" min="0">
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
            <div>유형 ${{payload.property_type}} · 자치구 ${{payload.district}} · 법정동 ${{payload.legal_dong}} · ${{payload.floor}}층</div>
          </div>
        `;
      }} catch (error) {{
        result.className = "error";
        result.textContent = error.message;
      }} finally {{
        button.disabled = false;
      }}
    }});
  </script>
</body>
</html>
"""


def build_prediction_input(payload: dict[str, Any]) -> PredictionInput:
    district = _required_text(payload, "district")
    lawd_cd = str(payload.get("lawd_cd") or SEOUL_DISTRICT_CODES.get(district, "")).strip()
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


def run_gui_server(model_path: str = "artifacts/hedonic_model.pkl", host: str = "127.0.0.1", port: int = 8000) -> None:
    model_file = Path(model_path)
    if not model_file.exists():
        raise FileNotFoundError(f"model file does not exist: {model_path}")
    model = load_model(model_file)
    handler = _make_handler(model, model_path)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"GUI running at http://{host}:{port}", flush=True)
    server.serve_forever()


def _make_handler(model: object, model_path: str) -> type[BaseHTTPRequestHandler]:
    class GuiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                _send_text(self, 200, render_index_html(model_path), "text/html; charset=utf-8")
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
                prediction = predict_price(model, prediction_input)
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
