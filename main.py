import os
from flask import Flask, jsonify, render_template_string, request
from groq import Groq

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Pon aquí el ID exacto de tu modelo activo de Groq
MODELO_GROQ = os.environ.get("openai/gpt-oss-20b", "")

MAPA_7BITS = {
    " ": "0000000",
    "a": "0000001",
    "b": "0000010",
    "c": "0000011",
    "d": "0000100",
    "e": "0000101",
    "f": "0000110",
    "g": "0000111",
    "h": "0001000",
    "i": "0001001",
    "j": "0001010",
    "k": "0001011",
    "l": "0001100",
    "m": "0001101",
    "n": "0001110",
    "o": "0001111",
    "p": "0010000",
    "q": "0010001",
    "r": "0010010",
    "s": "0010011",
    "t": "0010100",
    "u": "0010101",
    "v": "0010110",
    "w": "0010111",
    "x": "0011000",
    "y": "0011001",
    "z": "0011010",
    "1": "0011011",
    "2": "0011100",
    "3": "0011101",
    "4": "0011110",
    "5": "0011111",
    "6": "0100000",
    "7": "0100001",
    "8": "0100010",
    "9": "0100011",
    "0": "0100100",
    "-": "0100101",
    "=": "0100110",
    ".": "0100111",
    ",": "0101000",
    ";": "0101001",
    "/": "0101010",
    "à": "0101011",
    "â": "0101100",
    "ç": "0101101",
    "è": "0101110",
    "é": "0101111",
    "ê": "0110000",
    "î": "0110001",
    "ï": "0110010",
    "û": "0110011",
    "|": "0110100",
    '"': "0110111",
    "🟧": "0111000",
    "🟨": "0111001",
    "🟩": "0111010",
    "🟦": "0111011",
    "🟪": "0111100",
    "⬜": "0111101",
    "▶": "0111110",
    "A": "1000001",
    "B": "1000010",
    "C": "1000011",
    "D": "1000100",
    "E": "1000101",
    "F": "1000110",
    "G": "1000111",
    "H": "1001000",
    "I": "1001001",
    "J": "1001010",
    "K": "1001011",
    "L": "1001100",
    "M": "1001101",
    "N": "1001110",
    "O": "1001111",
    "P": "1010000",
    "Q": "1010001",
    "R": "1010010",
    "S": "1010011",
    "T": "1010100",
    "U": "1010101",
    "V": "1010110",
    "W": "1010111",
    "X": "1011000",
    "Y": "1011001",
    "Z": "1011010",
    "!": "1011011",
    "@": "1011100",
    "#": "1011101",
    "$": "1011110",
    "%": "1011111",
    "?": "1100000",
    "&": "1100001",
    "*": "1100010",
    "(": "1100011",
    ")": "1100100",
    "_": "1100101",
    "+": "1100110",
    "'": "1101000",
    ":": "1101001",
    "~": "1101010",
    "À": "1101011",
    "Â": "1101100",
    "Ç": "1101101",
    "È": "1101110",
    "É": "1101111",
    "Ê": "1110000",
    "Ì": "1110001",
    "Ï": "1110010",
    "Û": "1110011",
    "¦": "1110100",
    "^": "1110111",
    "█": "1111010",
    "➡": "1111011",
    "⬅": "1111100",
    "⬆": "1111101",
    "⬇": "1111110",
}


def texto_a_8bits(texto: str) -> list[str]:
    reemplazos = {"ñ": "n", "Ñ": "N", "¿": "?", "¡": "!"}
    salida = []
    for ch in texto:
        ch_limpio = reemplazos.get(ch, ch)
        codigo_7 = MAPA_7BITS.get(ch_limpio)
        if codigo_7 is None and ch_limpio.lower() in MAPA_7BITS:
            codigo_7 = MAPA_7BITS[ch_limpio.lower()]
        if codigo_7 is None:
            codigo_7 = "0000000"
        salida.append(codigo_7 + "0")
    return salida


def construir_cola(texto: str) -> list[str]:
    return ["00000001"] + texto_a_8bits(texto)


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
        if not MODELO_GROQ.strip():
            texto = "Configura MODELO_GROQ"
        else:
            try:
                chat = client.chat.completions.create(
                    model=MODELO_GROQ.strip(),
                    messages=[
                        {
                            "role": "system",
                            "content": "Responde en espanol, maximo 60 caracteres, sin emojis raros ni tildes complejas.",
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
        codigo = cola[idx]
        estado["cursor"] = idx + 1
        return jsonify({"value": codigo})
    return jsonify({"value": "00000000"})