import hmac
import os
import re
import threading
import time
import unicodedata

from flask import Flask, jsonify, redirect, render_template_string, request, url_for
from groq import Groq

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.environ.get("MODELO_GROQ", "").strip() or "llama-3.1-8b-instant"
ACCESS_KEY = os.environ.get("ACCESS_KEY", "cambia-esta-clave-123").strip()
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

DEFAULT_PASSWORD = "1234"
RESET_TIMEOUT_SEG = 8  # si el juego no llama a /status, el reset se cancela solo
DEBOUNCE_SEG = 1.2     # el bloque repite el mismo POST varias veces/seg: se cuenta una vez
# Paquete que significa "ENVIAR a la IA" (valid=1, shift=0, 6 bits = 111111).
# Es un codigo que no usa ninguna letra. Puedes cambiarlo con la variable SEND_PACKET.
SEND_PACKET = os.environ.get("SEND_PACKET", "10111111").strip()
LOCK = threading.RLock()

# ---------------------------------------------------------------------------
# Tabla de caracteres: (6 bits, shift)
# ---------------------------------------------------------------------------
_BASE = " abcdefghijklmnopqrstuvwxyz1234567890-=.,;/"  # el indice = codigo
_SHIFT = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%?&*()_+"      # indice + 1 = codigo

MAPA_CARACTERES = {ch: (format(i, "06b"), "0") for i, ch in enumerate(_BASE)}
MAPA_CARACTERES.update({ch: (format(i + 1, "06b"), "1") for i, ch in enumerate(_SHIFT)})
MAPA_CARACTERES[":"] = ("101001", "1")

INVERSO_6BITS = {
    (bits_char, bit_shift): ch
    for ch, (bits_char, bit_shift) in MAPA_CARACTERES.items()
}

CODIGOS_SIMPLES = {str(i + 1): chr(97 + i) for i in range(26)}
CODIGOS_SIMPLES["0"] = " "


def normalizar_8bits(codigo: str) -> str:
    limpio = "".join(c for c in codigo if c in ("0", "1"))
    return limpio[:8].ljust(8, "0")


def limpiar_texto(texto: str) -> str:
    """Quita acentos y cambia a espacio lo que la pantalla no puede mostrar."""
    texto = texto.replace("¿", "?").replace("¡", "!")
    for comilla in ("'", '"', "’", "‘", "“", "”", "`"):
        texto = texto.replace(comilla, "")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = "".join(c if c in MAPA_CARACTERES else " " for c in texto)
    return " ".join(texto.split())


def texto_a_8bits(texto: str) -> list[str]:
    salida = []
    for ch in limpiar_texto(texto):
        bits_char, bit_shift = MAPA_CARACTERES.get(ch, ("000000", "0"))
        salida.append(normalizar_8bits(f"1{bit_shift}{bits_char}"))
    return salida


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------
def crear_canal() -> dict:
    return {
        "ultimo_enviado": "",
        "borrador_teclado": "",
        "ultimo_packet_teclado": "",
        "respuesta": "Ready",
        "cola": [],
        "cursor": 0,
        "reset_pendiente": False,
        "reset_pulsos": 0,
        "reset_deadline": 0.0,
        "ultimo_paquete": "",
        "ultimo_paquete_t": 0.0,
    }


canales: dict[str, dict] = {
    DEFAULT_PASSWORD: crear_canal(),
    "5467": crear_canal(),
}
ui_state = {"active_password": "5467", "toast": ""}


def get_canal(password: str, crear_si_no_existe: bool = True) -> dict | None:
    pwd = (password or "").strip() or ui_state["active_password"] or DEFAULT_PASSWORD
    with LOCK:
        if pwd not in canales:
            if not crear_si_no_existe:
                return None
            canales[pwd] = crear_canal()
        return canales[pwd]


def extraer_password_peticion() -> str:
    header_pwd = (
        request.headers.get("Password")
        or request.headers.get("X-Password")
        or ""
    ).strip()
    if header_pwd:
        ui_state["active_password"] = header_pwd
        return header_pwd
    query_pwd = (
        request.args.get("password")
        or request.args.get("code")
        or request.args.get("id")
        or ""
    ).strip()
    if query_pwd:
        ui_state["active_password"] = query_pwd
        return query_pwd
    return ui_state["active_password"] or DEFAULT_PASSWORD


def extraer_valor_post(data: dict, form: dict) -> str:
    raw_body = (request.get_data(as_text=True) or "").strip()
    for candidato in (
        data.get("value"),
        data.get("bits8"),
        data.get("code"),
        data.get("char"),
        form.get("value"),
        form.get("bits8"),
        form.get("code"),
        form.get("char"),
        request.args.get("value"),
        request.args.get("bits8"),
        request.args.get("code"),
        request.args.get("char"),
        raw_body,
    ):
        if candidato is not None and str(candidato).strip() != "":
            texto = str(candidato).strip()
            match_8bits = re.search(r"[01]{8}", texto)
            if match_8bits:
                return match_8bits.group(0)
            return texto
    return ""


# ---------------------------------------------------------------------------
# IA
# ---------------------------------------------------------------------------
def pedir_respuesta_ia(mensaje: str) -> str:
    for intento in range(2):
        chat = client.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Reply in English, max 35 characters, one short line. "
                        "Use only letters, numbers and basic punctuation. "
                        "No emojis, no quotes, no weird symbols."
                    ),
                },
                {"role": "user", "content": mensaje},
            ],
            max_tokens=60,
            timeout=15,
        )
        raw = chat.choices[0].message.content if (chat.choices and chat.choices[0].message) else ""
        limpio = limpiar_texto(raw or "")
        print(f"[GROQ] intento={intento + 1} modelo={MODELO_GROQ} raw={raw!r} limpio={limpio!r}", flush=True)
        if limpio:
            return limpio[:40]
    return ""


def enviar_a_ia(canal: dict, pwd: str, mensaje: str) -> str:
    canal["ultimo_enviado"] = mensaje
    print(f"[IA-SEND] pwd={pwd} mensaje={mensaje!r} client_ok={bool(client)} model={MODELO_GROQ}", flush=True)
    if not client:
        canal["respuesta"] = "Missing GROQ_API_KEY"
        print("[IA-ERROR] GROQ_API_KEY no configurada en el entorno", flush=True)
        return "Error: Missing GROQ_API_KEY"
    try:
        texto = pedir_respuesta_ia(mensaje)  # llamada lenta: fuera del lock
        if texto:
            with LOCK:
                canal["respuesta"] = texto
                canal["cola"] = texto_a_8bits(texto)
                canal["cursor"] = 0
                canal["reset_pendiente"] = True
                canal["reset_pulsos"] = 0
                canal["reset_deadline"] = time.time() + RESET_TIMEOUT_SEG
            print(f"[IA-OK] pwd={pwd} respuesta={texto!r} bits_len={len(canal['cola'])}", flush=True)
            return f"AI replied for [{pwd}]! Auto-reset queued & bits ready."
        canal["respuesta"] = "Empty reply"
        print(f"[IA-WARN] pwd={pwd} Groq devolvio vacio", flush=True)
        return "AI returned empty reply; queue unchanged."
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        canal["respuesta"] = f"Error: {err_msg[:45]}"
        print(f"[IA-EXCEPTION] pwd={pwd} {err_msg}", flush=True)
        return f"Request failed: {err_msg[:60]}"


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------
HTML_CHAT = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Receiver & Sender - Build Logic</title>
  <style>
    body { font-family: sans-serif; max-width: 540px; margin: 36px auto; padding: 0 16px 80px 16px; background: #111; color: #eee; }
    label { display: block; margin-top: 12px; font-size: 14px; color: #bbb; }
    input, button { width: 100%; padding: 12px; margin-top: 6px; font-size: 16px; border-radius: 8px; border: none; box-sizing: border-box; }
    input { background: #222; color: #fff; }
    button { background: #2563eb; color: white; font-weight: bold; cursor: pointer; margin-top: 14px; }
    .hint { font-size: 12px; color: #9ca3af; margin-top: 4px; }
    .box { margin-top: 20px; padding: 14px; background: #1e1e1e; border-radius: 8px; word-break: break-all; }
    .toast {
      position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%);
      background: #16a34a; color: #fff; padding: 12px 18px; border-radius: 10px;
      font-weight: bold; box-shadow: 0 6px 20px rgba(0,0,0,0.45); z-index: 999;
    }
  </style>
</head>
<body>
  <h2>AI Receiver & Sender</h2>
  <form method="POST" action="/preguntar" onsubmit="showSending()">
    <label for="access_key">Owner Access Key</label>
    <input type="password" id="access_key" name="access_key" placeholder="Enter your private access key" required>

    <label for="password">Screen Password (Header: Password: ...)</label>
    <input type="text" id="password" name="password" value="{{ password }}" placeholder="e.g. 5467" required>
    <div class="hint">Build Logic Header: Password: {{ password }}</div>

    <label for="mensaje">Send Message</label>
    <input type="text" id="mensaje" name="mensaje" placeholder="Type your question here..." required autofocus>

    <button type="submit" id="sendBtn">Send to Roblox</button>
  </form>

  <div class="box">
    <strong>Screen Password:</strong><p>{{ password }}</p>
    <strong>Last keypad packet / code:</strong><p>{{ ultimo_packet_teclado }}</p>
    <strong>Keypad draft:</strong><p>{{ borrador_teclado }}</p>
    <strong>Last sent:</strong><p>{{ ultimo_enviado }}</p>
    <strong>Latest received response:</strong><p>{{ respuesta }}</p>
    <strong>Queue progress:</strong><p>{{ cursor }} / {{ total }}</p>
    <strong>8 bits:</strong><p>{{ bits }}</p>
  </div>

  <div id="liveToast" class="toast" style="{% if not toast %}display:none;{% endif %}">{{ toast }}</div>

  <script>
    function showSending() {
      const btn = document.getElementById("sendBtn");
      setTimeout(() => { btn.disabled = true; }, 0);
      btn.innerText = "Waiting for AI...";
      const t = document.getElementById("liveToast");
      t.style.background = "#2563eb";
      t.innerText = "Sent! Waiting for AI response before auto-resetting and sending bits...";
      t.style.display = "block";
    }
    const initialToast = document.getElementById("liveToast");
    if (initialToast && initialToast.style.display !== "none") {
      setTimeout(() => { initialToast.style.display = "none"; }, 3500);
    }
  </script>
</body>
</html>
"""


def render_page(password: str, toast_msg: str = ""):
    pwd = (password or "").strip() or ui_state["active_password"] or DEFAULT_PASSWORD
    canal = get_canal(pwd, crear_si_no_existe=True)
    return render_template_string(
        HTML_CHAT,
        password=pwd,
        ultimo_packet_teclado=canal["ultimo_packet_teclado"] or "(none)",
        borrador_teclado=canal["borrador_teclado"] or "(empty)",
        ultimo_enviado=canal["ultimo_enviado"] or "(none)",
        respuesta=canal["respuesta"],
        cursor=canal["cursor"],
        total=len(canal["cola"]),
        bits=" ".join(canal["cola"]) if canal["cola"] else "(empty)",
        toast=toast_msg,
    )


@app.route("/", methods=["GET"])
def web_chat():
    pwd = request.args.get("password", "").strip() or ui_state["active_password"]
    msg = ui_state["toast"]
    ui_state["toast"] = ""
    return render_page(pwd, msg)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "groq": bool(client), "model": MODELO_GROQ})


@app.route("/status", methods=["GET"])
def leer_status():
    pwd = extraer_password_peticion()
    canal = get_canal(pwd, crear_si_no_existe=False)
    if canal:
        with LOCK:
            if canal["reset_pendiente"]:
                canal["reset_pulsos"] += 1
                if canal["reset_pulsos"] >= 2:
                    canal["reset_pendiente"] = False
                    canal["reset_pulsos"] = 0
                return jsonify({"value": "10000000"})
    return jsonify({"value": "00000000"})


@app.route("/preguntar", methods=["POST"])
def preguntar_desde_web():
    key_introducida = request.form.get("access_key", "").strip()
    pwd = request.form.get("password", "").strip() or ui_state["active_password"] or DEFAULT_PASSWORD
    mensaje = request.form.get("mensaje", "").strip()
    ui_state["active_password"] = pwd
    canal = get_canal(pwd, crear_si_no_existe=True)

    if ACCESS_KEY and not hmac.compare_digest(key_introducida, ACCESS_KEY):
        ui_state["toast"] = "Invalid access key! Prompt blocked."
    elif mensaje:
        ui_state["toast"] = enviar_a_ia(canal, pwd, mensaje)

    # Redirect: evita que al recargar la pagina se reenvie el formulario
    return redirect(url_for("web_chat", password=pwd))


@app.route("/teclado", methods=["GET", "POST"])
def recibir_teclado():
    data = request.get_json(silent=True) or {}
    form = request.form or {}
    pwd = (
        request.headers.get("Password")
        or request.headers.get("X-Password")
        or data.get("password")
        or form.get("password")
        or request.args.get("password")
        or ui_state["active_password"]
        or DEFAULT_PASSWORD
    )
    pwd = str(pwd).strip() or DEFAULT_PASSWORD

    canal = get_canal(pwd, crear_si_no_existe=True)
    valor = extraer_valor_post(data, form)
    bits_limpios = "".join(c for c in valor if c in ("0", "1"))

    if valor:
        canal["ultimo_packet_teclado"] = valor

    texto_envio = ""
    with LOCK:
        if len(bits_limpios) == 8 and len(valor) == 8:
            pin_valid = bits_limpios[0]   # 1 = "hay tecla" (igual que en /ia)
            pin_shift = bits_limpios[1]
            bits_char = bits_limpios[2:]
            ahora = time.time()

            # El bloque repite el MISMO paquete varias veces por segundo mientras
            # esta activo. Solo contamos la primera vez; un paquete de reposo
            # (00000000) o una pausa larga "rearman" la tecla.
            if bits_limpios == "00000000":
                canal["ultimo_paquete"] = ""
            elif (bits_limpios == canal["ultimo_paquete"]
                  and ahora - canal["ultimo_paquete_t"] < DEBOUNCE_SEG):
                canal["ultimo_paquete_t"] = ahora   # repetido: se ignora
            else:
                canal["ultimo_paquete"] = bits_limpios
                canal["ultimo_paquete_t"] = ahora

                if bits_limpios == SEND_PACKET:
                    texto_envio = canal["borrador_teclado"].strip()
                    canal["borrador_teclado"] = ""
                    if not texto_envio:
                        print(f"[TECLADO] enviar pulsado pero borrador vacio en pwd={pwd}", flush=True)
                elif pin_shift == "1" and bits_char == "000000":
                    canal["borrador_teclado"] = canal["borrador_teclado"][:-1]
                elif pin_valid == "0" and bits_char == "000000":
                    pass  # reposo
                else:
                    ch_decoded = INVERSO_6BITS.get((bits_char, pin_shift), "")
                    if ch_decoded:
                        canal["borrador_teclado"] = (canal["borrador_teclado"] + ch_decoded)[:60]
                    else:
                        print(f"[TECLADO] codigo sin caracter: {bits_limpios}", flush=True)
        elif valor == "100":
            texto_envio = canal["borrador_teclado"].strip()
            canal["borrador_teclado"] = ""
        elif valor == "99":
            canal["borrador_teclado"] = canal["borrador_teclado"][:-1]
        elif valor in CODIGOS_SIMPLES:
            canal["borrador_teclado"] = (canal["borrador_teclado"] + CODIGOS_SIMPLES[valor])[:60]
        elif len(valor) == 1 and valor in MAPA_CARACTERES:
            canal["borrador_teclado"] = (canal["borrador_teclado"] + valor)[:60]

    # La llamada a la IA va fuera del lock para no bloquear a los demas
    if texto_envio:
        enviar_a_ia(canal, pwd, texto_envio)

    print(
        f"[TECLADO] method={request.method} pwd={pwd} raw_val={valor!r} "
        f"bits={bits_limpios!r} draft={canal['borrador_teclado']!r}",
        flush=True,
    )

    return jsonify({"value": "00000000"})


@app.route("/ia", methods=["GET"])
def leer_en_roblox():
    pwd = extraer_password_peticion()
    canal = get_canal(pwd, crear_si_no_existe=False)
    if not canal:
        return jsonify({"value": "00000000"})

    with LOCK:
        # Si el juego nunca llama a /status, no nos quedamos bloqueados para siempre
        if canal["reset_pendiente"] and time.time() > canal["reset_deadline"]:
            canal["reset_pendiente"] = False
            canal["reset_pulsos"] = 0

        if canal["reset_pendiente"]:
            return jsonify({"value": "00000000"})

        idx = canal["cursor"]
        cola = canal["cola"]
        if idx < len(cola):
            codigo = normalizar_8bits(cola[idx])
            canal["cursor"] = idx + 1
            return jsonify({"value": codigo})
    return jsonify({"value": "00000000"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)