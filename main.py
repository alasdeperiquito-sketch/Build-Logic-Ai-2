import os
import re
from flask import Flask, jsonify, render_template_string, request
from groq import Groq

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.environ.get("MODELO_GROQ", "").strip() or "llama-3.1-8b-instant"
ACCESS_KEY = os.environ.get("ACCESS_KEY", "cambia-esta-clave-123").strip()
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

DEFAULT_PASSWORD = "1234"

MAPA_CARACTERES = {
    " ": ("000000", "0"),
    "a": ("000001", "0"),
    "b": ("000010", "0"),
    "c": ("000011", "0"),
    "d": ("000100", "0"),
    "e": ("000101", "0"),
    "f": ("000110", "0"),
    "g": ("000111", "0"),
    "h": ("001000", "0"),
    "i": ("001001", "0"),
    "j": ("001010", "0"),
    "k": ("001011", "0"),
    "l": ("001100", "0"),
    "m": ("001101", "0"),
    "n": ("001110", "0"),
    "o": ("001111", "0"),
    "p": ("010000", "0"),
    "q": ("010001", "0"),
    "r": ("010010", "0"),
    "s": ("010011", "0"),
    "t": ("010100", "0"),
    "u": ("010101", "0"),
    "v": ("010110", "0"),
    "w": ("010111", "0"),
    "x": ("011000", "0"),
    "y": ("011001", "0"),
    "z": ("011010", "0"),
    "1": ("011011", "0"),
    "2": ("011100", "0"),
    "3": ("011101", "0"),
    "4": ("011110", "0"),
    "5": ("011111", "0"),
    "6": ("100000", "0"),
    "7": ("100001", "0"),
    "8": ("100010", "0"),
    "9": ("100011", "0"),
    "0": ("100100", "0"),
    "-": ("100101", "0"),
    "=": ("100110", "0"),
    ".": ("100111", "0"),
    ",": ("101000", "0"),
    ";": ("101001", "0"),
    "/": ("101010", "0"),
    "A": ("000001", "1"),
    "B": ("000010", "1"),
    "C": ("000011", "1"),
    "D": ("000100", "1"),
    "E": ("000101", "1"),
    "F": ("000110", "1"),
    "G": ("000111", "1"),
    "H": ("001000", "1"),
    "I": ("001001", "1"),
    "J": ("001010", "1"),
    "K": ("001011", "1"),
    "L": ("001100", "1"),
    "M": ("001101", "1"),
    "N": ("001110", "1"),
    "O": ("001111", "1"),
    "P": ("010000", "1"),
    "Q": ("010001", "1"),
    "R": ("010010", "1"),
    "S": ("010011", "1"),
    "T": ("010100", "1"),
    "U": ("010101", "1"),
    "V": ("010110", "1"),
    "W": ("010111", "1"),
    "X": ("011000", "1"),
    "Y": ("011001", "1"),
    "Z": ("011010", "1"),
    "!": ("011011", "1"),
    "@": ("011100", "1"),
    "#": ("011101", "1"),
    "$": ("011110", "1"),
    "%": ("011111", "1"),
    "?": ("100000", "1"),
    "&": ("100001", "1"),
    "*": ("100010", "1"),
    "(": ("100011", "1"),
    ")": ("100100", "1"),
    "_": ("100101", "1"),
    "+": ("100110", "1"),
    ":": ("101001", "1"),
}

INVERSO_6BITS = {
    (bits_char, bit_shift): ch
    for ch, (bits_char, bit_shift) in MAPA_CARACTERES.items()
}

CODIGOS_SIMPLES = {str(i + 1): chr(97 + i) for i in range(26)}
CODIGOS_SIMPLES["0"] = " "


def normalizar_8bits(codigo: str) -> str:
    limpio = "".join(c for c in codigo if c in ("0", "1"))
    return limpio[:8].ljust(8, "0")


def texto_a_8bits(texto: str) -> list[str]:
    reemplazos = {
        "ñ": "n", "Ñ": "N",
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "¿": "?", "¡": "!",
    }
    salida = []
    for ch in texto:
        ch_limpio = reemplazos.get(ch, ch)
        bits_char, bit_shift = MAPA_CARACTERES.get(ch_limpio, ("000000", "0"))
        salida.append(normalizar_8bits(f"1{bit_shift}{bits_char}"))
    return salida


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
    }


canales: dict[str, dict] = {
    DEFAULT_PASSWORD: crear_canal(),
    "5467": crear_canal(),
}
ui_state = {"active_password": "5467", "toast": ""}


def get_canal(password: str, crear_si_no_existe: bool = True) -> dict | None:
    pwd = (password or "").strip() or ui_state["active_password"] or DEFAULT_PASSWORD
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


def pedir_respuesta_ia(mensaje: str) -> str:
    for _ in range(2):
        chat = client.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {
                    "role": "system",
                    "content": "Reply in English, max 35 characters, one short line, no emojis or weird symbols.",
                },
                {"role": "user", "content": mensaje},
            ],
            max_tokens=150,
            timeout=15,
        )
        raw = chat.choices[0].message.content if (chat.choices and chat.choices[0].message) else ""
        limpio = " ".join((raw or "").replace("\r", " ").replace("\n", " ").split()).strip()
        if limpio:
            return limpio[:40]
    return ""


def enviar_a_ia(canal: dict, pwd: str, mensaje: str) -> str:
    canal["ultimo_enviado"] = mensaje
    if not client:
        canal["respuesta"] = "Missing GROQ_API_KEY"
        return "Error: Missing GROQ_API_KEY"
    try:
        texto = pedir_respuesta_ia(mensaje)
        if texto:
            canal["respuesta"] = texto
            canal["cola"] = texto_a_8bits(texto)
            canal["cursor"] = 0
            canal["reset_pendiente"] = True
            canal["reset_pulsos"] = 0
            return f"AI replied for [{pwd}]! Auto-reset queued & bits ready."
        canal["respuesta"] = "Empty reply"
        return "AI returned empty reply; queue unchanged."
    except Exception as e:
        canal["respuesta"] = f"Error: {str(e)[:45]}"
        return "Request failed; queue unchanged."


HTML_CHAT = """
<!doctype html>
<html lang="en">
<head>
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
      btn.disabled = true;
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


@app.route("/status", methods=["GET"])
def leer_status():
    pwd = extraer_password_peticion()
    canal = get_canal(pwd, crear_si_no_existe=False)
    if canal and canal["reset_pendiente"]:
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
    toast_msg = ""

    if ACCESS_KEY and key_introducida != ACCESS_KEY:
        toast_msg = "Invalid access key! Prompt blocked."
        return render_page(pwd, toast_msg)

    if mensaje:
        toast_msg = enviar_a_ia(canal, pwd, mensaje)

    return render_page(pwd, toast_msg)


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
    ).strip() or DEFAULT_PASSWORD

    canal = get_canal(pwd, crear_si_no_existe=True)
    valor = extraer_valor_post(data, form)
    bits_limpios = "".join(c for c in valor if c in ("0", "1"))

    print(f"[TECLADO] method={request.method} pwd={pwd} raw_val={valor!r} bits={bits_limpios!r}", flush=True)

    if valor:
        canal["ultimo_packet_teclado"] = valor

    if len(bits_limpios) == 8 and set(bits_limpios) <= {"0", "1"}:
        pin_send = bits_limpios[0]
        pin_shift = bits_limpios[1]
        bits_char = bits_limpios[2:]

        if pin_send == "1":
            texto_envio = canal["borrador_teclado"].strip()
            if texto_envio:
                canal["borrador_teclado"] = ""
                enviar_a_ia(canal, pwd, texto_envio)
        elif pin_shift == "1" and bits_char == "000000":
            canal["borrador_teclado"] = canal["borrador_teclado"][:-1]
        else:
            ch_decoded = INVERSO_6BITS.get((bits_char, pin_shift), "")
            if ch_decoded:
                canal["borrador_teclado"] = (canal["borrador_teclado"] + ch_decoded)[:60]
    elif valor == "100":
        texto_envio = canal["borrador_teclado"].strip()
        if texto_envio:
            canal["borrador_teclado"] = ""
            enviar_a_ia(canal, pwd, texto_envio)
    elif valor == "99":
        canal["borrador_teclado"] = canal["borrador_teclado"][:-1]
    elif valor in CODIGOS_SIMPLES:
        canal["borrador_teclado"] = (canal["borrador_teclado"] + CODIGOS_SIMPLES[valor])[:60]
    elif len(valor) == 1 and valor in MAPA_CARACTERES:
        canal["borrador_teclado"] = (canal["borrador_teclado"] + valor)[:60]

    return jsonify({"value": "00000000"})


@app.route("/ia", methods=["GET"])
def leer_en_roblox():
    pwd = extraer_password_peticion()
    canal = get_canal(pwd, crear_si_no_existe=False)
    if not canal:
        return jsonify({"value": "00000000"})
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
    app.run(host="0.0.0.0", port=port)