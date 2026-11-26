import os
from flask import Flask, jsonify, request
from groq import Groq

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.environ.get("MODELO_GROQ", "").strip() or "llama-3.1-8b-instant"
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Pin 1 = Send, Pin 2 = Shift, Pins 3-8 = 6-bit char
MAPA_6BITS = {
    "000000": " ",
    "000001": "a", "000010": "b", "000011": "c", "000100": "d", "000101": "e",
    "000110": "f", "000111": "g", "001000": "h", "001001": "i", "001010": "j",
    "001011": "k", "001100": "l", "001101": "m", "001110": "n", "001111": "o",
    "010000": "p", "010001": "q", "010010": "r", "010011": "s", "010100": "t",
    "010101": "u", "010110": "v", "010111": "w", "011000": "x", "011001": "y",
    "011010": "z",
    "011011": "1", "011100": "2", "011101": "3", "011110": "4", "011111": "5",
    "100000": "6", "100001": "7", "100010": "8", "100011": "9", "100100": "0",
    "100101": "-", "100110": "=", "100111": ".", "101000": ",", "101001": ";",
    "101010": "/",
}

INVERSO_CHAR = {v: k for k, v in MAPA_6BITS.items()}

estado = {
    "borrador": "",
    "ultimo_enviado": "",
    "respuesta": "Ready",
    "cola": [],
    "cursor": 0,
    "reset": False,
}


def texto_a_cola(texto: str) -> list[str]:
    cola = []
    for ch in texto:
        shift = "1" if ch.isupper() else "0"
        bits6 = INVERSO_CHAR.get(ch.lower(), "000000")
        cola.append(f"1{shift}{bits6}")
    return cola


def preguntar_ia(prompt: str) -> str:
    if not client:
        return "Missing GROQ_API_KEY"
    chat = client.chat.completions.create(
        model=MODELO_GROQ,
        messages=[
            {"role": "system", "content": "Reply in English, max 35 chars, one line, no emojis."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=120,
        timeout=15,
    )
    texto = (chat.choices[0].message.content or "").strip()
    return " ".join(texto.split())[:35] or "Empty"


@app.route("/teclado", methods=["GET", "POST"])
def teclado():
    data = request.get_json(silent=True) or {}
    val = str(
        data.get("value")
        or request.form.get("value")
        or request.args.get("value")
        or request.get_data(as_text=True)
        or ""
    ).strip()

    bits = "".join(c for c in val if c in "01")
    if len(bits) == 8:
        pin_send = bits[0]
        pin_shift = bits[1]
        bits6 = bits[2:]

        if pin_send == "1" and estado["borrador"].strip():
            msg = estado["borrador"].strip()
            estado["borrador"] = ""
            estado["ultimo_enviado"] = msg
            estado["respuesta"] = preguntar_ia(msg)
            estado["cola"] = texto_a_cola(estado["respuesta"])
            estado["cursor"] = 0
            estado["reset"] = True
        elif pin_shift == "1" and bits6 == "000000":
            estado["borrador"] = estado["borrador"][:-1]
        else:
            ch = MAPA_6BITS.get(bits6, "")
            if ch:
                if pin_shift == "1":
                    ch = ch.upper()
                estado["borrador"] = (estado["borrador"] + ch)[:60]

    return jsonify({"value": "00000000"})


@app.route("/status", methods=["GET"])
def status():
    if estado["reset"]:
        estado["reset"] = False
        return jsonify({"value": "10000000"})
    return jsonify({"value": "00000000"})


@app.route("/ia", methods=["GET"])
def ia():
    if estado["cursor"] < len(estado["cola"]):
        codigo = estado["cola"][estado["cursor"]]
        estado["cursor"] += 1
        return jsonify({"value": codigo})
    return jsonify({"value": "00000000"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))