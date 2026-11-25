import os
from flask import Flask, jsonify, render_template_string, request
from groq import Groq

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Escribe aquí el ID exacto de un modelo activo en tu cuenta de Groq
MODELO_GROQ = "openai/gpt-oss-20b"

estado = {"respuesta": "Esperando pregunta..."}

HTML_CHAT = """
<!doctype html>
<html lang="es">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chat IA - Build Logic</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; background: #111; color: #eee; }
    input, button { width: 100%; padding: 12px; margin-top: 10px; font-size: 16px; border-radius: 8px; border: none; }
    input { background: #222; color: #fff; }
    button { background: #2563eb; color: white; font-weight: bold; cursor: pointer; }
    .box { margin-top: 20px; padding: 14px; background: #1e1e1e; border-radius: 8px; }
  </style>
</head>
<body>
  <h2>Hablar con la IA en Build Logic</h2>
  <form method="POST" action="/preguntar">
    <input type="text" name="mensaje" placeholder="Escribe tu pregunta aquí..." required autofocus>
    <button type="submit">Enviar a Roblox</button>
  </form>
  <div class="box">
    <strong>Última respuesta en pantalla:</strong>
    <p>{{ respuesta }}</p>
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def web_chat():
    return render_template_string(HTML_CHAT, respuesta=estado["respuesta"])


@app.route("/preguntar", methods=["POST"])
def preguntar_desde_web():
    mensaje = request.form.get("mensaje", "").strip()
    if mensaje:
        if not MODELO_GROQ.strip():
            estado["respuesta"] = "Configura MODELO_GROQ en main.py"
        else:
            try:
                chat = client.chat.completions.create(
                    model=MODELO_GROQ.strip(),
                    messages=[
                        {
                            "role": "system",
                            "content": "Responde en español, máximo 150 caracteres y sin emojis.",
                        },
                        {"role": "user", "content": mensaje},
                    ],
                    max_tokens=80,
                )
                estado["respuesta"] = chat.choices[0].message.content.strip()
            except Exception as e:
                estado["respuesta"] = f"Error Groq: {str(e)[:120]}"
    return render_template_string(HTML_CHAT, respuesta=estado["respuesta"])


@app.route("/ia", methods=["GET"])
def leer_en_roblox():
    return jsonify({"value": estado["respuesta"]})