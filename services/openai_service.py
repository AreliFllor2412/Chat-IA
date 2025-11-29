import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ Falta la clave OPENAI_API_KEY en el archivo .env")

# El cliente ya usa la API key que le pasamos
client = OpenAI(api_key=api_key)


def generar_descripcion_ia(nombre: str, categoria: str = "", proveedor: str = "") -> str:
    """
    Genera una descripción breve y clara sobre un medicamento,
    pensada para un usuario final (tipo Google / Wikipedia).
    """
    contexto = ""
    if categoria or proveedor:
        contexto = f"\n📂 Categoría: {categoria}\n🏭 Proveedor: {proveedor}\n"

    prompt = f"""
Eres un asistente farmacéutico profesional que explica las cosas de forma
clara y sencilla, como si hablaras con un paciente.

Explica qué es, para qué sirve y consideraciones generales del siguiente medicamento:

💊 Medicamento: {nombre}
{contexto}

Indicaciones:
- Usa un tono natural, amable y profesional.
- No des dosis exactas ni esquemas de tratamiento, solo orientación general.
- No más de 6–8 líneas.
- Termina con una advertencia tipo: "Siempre consulta a un profesional de la salud".
"""

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un experto en farmacología y redacción médica para pacientes.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=300,
        )
        return respuesta.choices[0].message.content.strip()

    except Exception as e:
        # Devuelve un texto elegante en lugar de un traceback feo
        return (
            "⚠️ En este momento no pude generar la descripción con la IA. "
            "Inténtalo de nuevo más tarde."
        )
