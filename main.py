import datetime
import json
import os
import re
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

historial: list[dict] = []
MAX_HISTORIAL = 25

HTML_INSPECTOR = """
<!doctype html>
<html lang="en">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POST Inspector - Build Logic</title>
  <style>
    body { font-family: monospace; max-width: 820px; margin: 24px auto; padding: 0 14px 60px; background: #0f172a; color: #e2e8f0; }
    h2 { margin-bottom: 6px; }
    .meta { color: #94a3b8; font-size: 13px; margin-bottom: 18px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 14px; }
    .tag { display: inline-block; padding: 2px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; background: #2563eb; color: #fff; }
    pre { white-space: pre-wrap; word-break: break-all; background: #0b1120; padding: 10px; border-radius: 8px; font-size: 12px; }
    a { color: #60a5fa; }
  </style>
</head>
<body>
  <h2>Build Logic POST Inspector</h2>
  <div class="meta">
    Point HTTP Transmitter to <code>/teclado</code> or any path. View JSON at <a href="/ultimo">/ultimo</a>.
  </div>
  {% if not items %}
    <div class="card">No requests captured yet. Trigger a POST from Roblox or refresh.</div>
  {% endif %}
  {% for item in items %}
    <div class="card">
      <div><span class="tag">{{ item.method }}</span> <strong>{{ item.path }}</strong> — <span style="color:#94a3b8">{{ item.ts }}</span></div>
      <p><strong>Content-Type:</strong> {{ item.content_type or "(none)" }}</p>
      <p><strong>Detected 8-bit strings:</strong> {{ item.bits_8_found or "(none)" }}</p>
      <p><strong>Raw body:</strong></p>
      <pre>{{ item.raw_body }}</pre>
      <p><strong>JSON / Form / Args / Headers:</strong></p>
      <pre>{{ item.parsed_dump }}</pre>
    </div>
  {% endfor %}
</body>
</html>
"""


def capturar_peticion() -> dict:
    raw_bytes = request.get_data() or b""
    try:
        raw_text = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        raw_text = repr(raw_bytes)

    json_data = request.get_json(silent=True)
    form_data = dict(request.form or {})
    args_data = dict(request.args or {})
    headers_data = {k: v for k, v in request.headers.items()}
    cookies_data = dict(request.cookies or {})

    blob_busqueda = " ".join([
        raw_text,
        json.dumps(json_data, ensure_ascii=False) if json_data is not None else "",
        json.dumps(form_data, ensure_ascii=False),
        json.dumps(args_data, ensure_ascii=False),
    ])
    bits_8 = re.findall(r"(?<![01])[01]{8}(?![01])", blob_busqueda)
    if not bits_8:
        bits_8 = re.findall(r"[01]{8}", blob_busqueda)

    registro = {
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "method": request.method,
        "path": request.full_path,
        "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
        "content_type": request.content_type or "",
        "raw_body": raw_text,
        "raw_bytes_len": len(raw_bytes),
        "json": json_data,
        "form": form_data,
        "args": args_data,
        "headers": headers_data,
        "cookies": cookies_data,
        "bits_8_found": bits_8,
    }

    print(
        f"[POST-TEST] {registro['ts']} method={registro['method']} path={registro['path']} "
        f"ct={registro['content_type']!r} raw={registro['raw_body']!r} json={registro['json']!r} "
        f"form={registro['form']!r} args={registro['args']!r} bits8={registro['bits_8_found']!r} "
        f"headers={registro['headers']!r}",
        flush=True,
    )

    historial.insert(0, registro)
    del historial[MAX_HISTORIAL:]
    return registro


@app.route("/", methods=["GET"])
def home():
    preparados = []
    for r in historial:
        copia = dict(r)
        copia["parsed_dump"] = json.dumps(
            {
                "json": r["json"],
                "form": r["form"],
                "args": r["args"],
                "headers": r["headers"],
                "cookies": r["cookies"],
            },
            indent=2,
            ensure_ascii=False,
        )
        preparados.append(copia)
    return render_template_string(HTML_INSPECTOR, items=preparados)


@app.route("/ultimo", methods=["GET"])
def ultimo():
    return jsonify({
        "count": len(historial),
        "latest": historial[0] if historial else None,
        "history": historial,
    })


@app.route("/teclado", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.route("/post", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.route("/test", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.route("/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def atrapar_todo(subpath=""):
    reg = capturar_peticion()
    return jsonify({
        "value": "00000000",
        "ok": True,
        "captured": {
            "method": reg["method"],
            "path": reg["path"],
            "content_type": reg["content_type"],
            "raw_body": reg["raw_body"],
            "json": reg["json"],
            "form": reg["form"],
            "args": reg["args"],
            "bits_8_found": reg["bits_8_found"],
        },
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)