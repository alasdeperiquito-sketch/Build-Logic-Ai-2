import os
from flask import Flask, jsonify, render_template_string, request
from groq import Groq

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.environ.get("MODELO_GROQ", "").strip()
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Cada entrada: (6_bits_caracter, bit_shift)
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
        # Pin 1: Turn on when writing (1) | Pin 2: Shift | Pines 3-8: 6 bits carácter
        salida.append(normalizar_8bits(f"1{bit_shift}{bits_char}"))
    return salida


def construir_cola(texto: str) -> list[str]:
    # Pin 1 en 0 (no escribiendo), Pin 2 en 0, Pines 3-8 en 0
    return [normalizar_8bits("00000000")] + texto_a_8bits(texto)


estado = {
    "respuesta": "Hola",
    "cola": construir_cola("Hola"),
    "cursor": 0,
}

HTML_CHAT = """
<!doctype html>
<html lang="es">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chat IA - Build Logic</title>
  <style>
    body { font-family: sans-serif; max-width: 520px; margin: 40px auto; padding: 0 16px; background: #111; color: #eee; }
    input, button { width: 100%; padding: 12px; margin-top: 10px; font-size: 16px; border-radius: 8px; border: none; }
    input { background: #222; color: #fff; }
    button { background: #2563eb; color: white; font-weight: bold; cursor: pointer; }
    .box { margin-top: 20px; padding: 14px; background: #1e1e1e; border-radius: 8px; word-break: break-all; }
  </style>
</head>
<body>
  <h2>Hablar con la IA en Build Logic</h2>
  <form method="POST" action="/preguntar">
    <input type="text" name="mensaje" placeholder="Escribe tu pregunta aquí..." required autofocus>
    <button type="submit">Enviar a Roblox</button>
  </form>
  <div class="box">
    <strong>Última respuesta:</strong>
    <p>{{ respuesta }}</p>
    <strong>Progreso cola:</strong>
    <p>{{ cursor }} / {{ total }}</p>
    <strong>8 bits:</strong>
    <p>{{ bits }}</p>
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def web_chat():
    return render_template_string(
        HTML_CHAT,
        respuesta=estado["respuesta"],
        cursor=estado["cursor"],
        total=len(estado["cola"]),
        bits=" ".join(estado["cola"]),
    )


@app.route("/preguntar", methods=["POST"])
def preguntar_desde_web():
    mensaje = request.form.get("mensaje", "").strip()
    if mensaje:
        if not client:
            texto = "Configura GROQ_API_KEY"
        elif not MODELO_GROQ:
            texto = "Configura MODELO_GROQ"
        else:
            try:
                chat = client.chat.completions.create(
                    model=MODELO_GROQ,
                    messages=[
                        {
                            "role": "system",
                            "content": "Responde en espanol, maximo 60 caracteres, sin emojis ni simbolos raros.",
                        },
                        {"role": "user", "content": mensaje},
                    ],
                    max_tokens=50,
                )
                texto = chat.choices[0].message.content.strip()
            except Exception as e:
                texto = f"Error: {str(e)[:50]}"
        estado["respuesta"] = texto
        estado["cola"] = construir_cola(texto)
        estado["cursor"] = 0
    return render_template_string(
        HTML_CHAT,
        respuesta=estado["respuesta"],
        cursor=estado["cursor"],
        total=len(estado["cola"]),
        bits=" ".join(estado["cola"]),
    )


@app.route("/ia", methods=["GET"])
def leer_en_roblox():
    idx = estado["cursor"]
    cola = estado["cola"]
    if idx < len(cola):
        codigo = normalizar_8bits(cola[idx])
        estado["cursor"] = idx + 1
        return jsonify({"value": codigo})
    return jsonify({"value": "00000000"})
