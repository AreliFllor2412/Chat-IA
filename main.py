from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from pydantic import BaseModel

import os
import requests
from dotenv import load_dotenv
import datetime
import json
import uuid
import re
import smtplib
import ssl
from email.message import EmailMessage
import unicodedata
import string

from utils import generar_reporte          # módulo PDF
from services.openai_service import generar_descripcion_ia

# =======================
# CONFIGURACIÓN
# =======================
load_dotenv()

API_BASE_URL = os.getenv("NEST_API_URL",)

app = FastAPI(title="PharmaControl API", version="3.1")

# ⬇️ Scheduler global para tareas programadas
scheduler = BackgroundScheduler(timezone="America/Mexico_City")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos estáticos (Frontend, reportes e historiales)
app.mount("/static", StaticFiles(directory="static"), name="static")


# =======================
# MODELOS
# =======================
class ChatRequest(BaseModel):
    mensaje: str
    session_id: str


# =======================
# HISTORIAL POR SESIÓN
# =======================
sesiones: dict = {}  # {session_id: [mensajes]}


def guardar_historial_json(session_id: str, historial: list) -> str:
    """Guarda un historial por sesión dentro de /static/historial/"""
    os.makedirs("static/historial", exist_ok=True)
    fname = f"historial_{session_id}.json"
    path = os.path.join("static/historial", fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)
    return path


def limpiar_markdown(texto: str) -> str:
    """
    Convierte un texto básico de markdown a HTML sencillo:
    - Quita **negritas** y *itálicas*
    - Reemplaza saltos de línea por <br>
    """
    if not texto:
        return ""

    texto = texto.replace("**", "").replace("__", "")
    texto = re.sub(r"\*(.*?)\*", r"\1", texto)
    texto = re.sub(r"_(.*?)_", r"\1", texto)
    texto = texto.replace("\r\n", "\n").replace("\n", "<br>")
    return texto


# =======================
# NORMALIZACIÓN & INTENCIONES
# =======================
def normalizar_texto(texto: str) -> str:
    """
    Quita acentos, mayúsculas y signos para hacer más flexible la detección.
    """
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    texto = "".join(c for c in texto if c not in string.punctuation)
    texto = " ".join(texto.split())
    return texto


def detectar_intencion(texto_original: str) -> str:
    """
    Devuelve una etiqueta sencilla según lo que el usuario pide.
    """
    t = normalizar_texto(texto_original)

    # menú / ayuda
    if t in {"menu", "ayuda", "opciones"}:
        return "menu"

    # atajos numéricos del menú
    if t == "1":
        return "reporte_general"
    if t == "2":
        return "sin_stock"
    if t == "3":
        return "existencias"
    if t == "4":
        return "proveedores"
    if t == "5":
        return "usuarios"
    if t == "6":
        return "buscar_medicamento"

    # saludos
    if any(s in t for s in ["hola", "buenos dias", "buenas tardes", "buenas noches", "hi", "hello"]):
        return "saludo"

    # reporte general
    if any(frase in t for frase in [
        "reporte general",
        "reporte de medicamentos",
        "reporte inventario",
        "todo el inventario",
    ]):
        return "reporte_general"

    # sin stock
    if any(frase in t for frase in [
        "sin existencia",
        "sin existencias",
        "sin stock",
        "agotado",
        "agotados",
    ]):
        return "sin_stock"

    # con existencia
    if any(frase in t for frase in [
        "existencias",
        "existencia",
        "con stock",
        "disponibles",
        "medicamentos disponibles",
        "inventario disponible",
    ]):
        return "existencias"

    # proveedores
    if any(frase in t for frase in [
        "proveedor",
        "proveedores",
        "lista de proveedores",
    ]):
        return "proveedores"

    # usuarios
    if any(frase in t for frase in [
        "usuario",
        "usuarios",
        "lista de usuarios",
        "personal",
        "colaboradores",
    ]):
        return "usuarios"

    # por defecto, asumimos que intenta buscar un medicamento
    return "buscar_medicamento"


# =======================
# CORREO PARA REPORTES
# =======================
def enviar_reportes_por_correo(archivos_pdf: list):
    """
    Envía por correo los PDFs generados.
    'archivos_pdf' debe ser una lista de rutas.
    """
    if not archivos_pdf:
        print("ℹ️ No hay archivos PDF para enviar.")
        return

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_to = os.getenv("REPORTS_EMAIL_TO")

    if not (smtp_host and smtp_user and smtp_pass and email_to):
        print("⚠️ Faltan variables de entorno para envío de correo.")
        return

    msg = EmailMessage()
    msg["Subject"] = "Reportes automáticos · PharmaControl"
    msg["From"] = smtp_user
    msg["To"] = email_to

    cuerpo = [
        "Hola,",
        "",
        "Adjunto encontrarás los reportes generados automáticamente por PharmaControl.",
        "",
        f"Total de archivos: {len(archivos_pdf)}",
        "",
        "Saludos,",
        "PharmaControl · IA",
    ]
    msg.set_content("\n".join(cuerpo))

    for ruta in archivos_pdf:
        try:
            ruta_fs = ruta.lstrip("/")
            if not os.path.isabs(ruta_fs):
                ruta_fs = os.path.join(os.getcwd(), ruta_fs)

            if not os.path.exists(ruta_fs):
                print(f"⚠️ No se encontró el archivo para adjuntar: {ruta_fs}")
                continue

            with open(ruta_fs, "rb") as f:
                data = f.read()
                filename = os.path.basename(ruta_fs)

            msg.add_attachment(
                data,
                maintype="application",
                subtype="pdf",
                filename=filename,
            )
        except Exception as e:
            print(f"⚠️ Error adjuntando {ruta}: {e}")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print("✅ Correo de reportes enviado correctamente.")
    except Exception as e:
        print(f"❌ Error enviando correo de reportes: {e}")

@app.post("/test-correo")
async def test_correo():
    generar_reportes_diarios()
    return {"ok": True, "mensaje": "Reportes generados y correo enviado."}

# =======================
# FUNCIÓN: REPORTES DIARIOS
# =======================
from services.email_service import enviar_correo_reportes
from utils import generar_reporte

def generar_reportes_diarios():
    print("🕒 Generando reportes automáticos...")

    archivos_generados = []

    try:
        # Medicamentos
        resp_med = requests.get(f"{API_BASE_URL}/medicamentos/all")
        resp_med.raise_for_status()
        medicamentos = resp_med.json()

        # General
        archivos_generados.append(
            generar_reporte(medicamentos, "Reporte General de Medicamentos", tipo="medicamentos")
        )

        # Sin stock
        sin_stock = [m for m in medicamentos if m.get("existencias", 0) == 0]
        if sin_stock:
            archivos_generados.append(
                generar_reporte(sin_stock, "Medicamentos Sin Existencia", tipo="medicamentos")
            )

        # Proveedores
        try:
            resp_prov = requests.get(f"{API_BASE_URL}/proveedores/all")
            resp_prov.raise_for_status()
            proveedores = resp_prov.json()
            if proveedores:
                archivos_generados.append(
                    generar_reporte(proveedores, "Reporte de Proveedores", tipo="proveedores")
                )
        except:
            print("⚠️ No se pudo generar reporte de proveedores")

        # Usuarios
        try:
            resp_user = requests.get(f"{API_BASE_URL}/users/all")
            resp_user.raise_for_status()
            usuarios = resp_user.json()
            if usuarios:
                archivos_generados.append(
                    generar_reporte(usuarios, "Reporte de Usuarios", tipo="usuarios")
                )
        except:
            print("⚠️ No se pudo generar reporte de usuarios")

        # ---------- Enviar correo ----------
        enviar_correo_reportes(archivos_generados)

        print("✅ Reportes generados y enviados correctamente.")

    except Exception as e:
        print(f"❌ Error generando reportes automáticos: {e}")



# =======================
# SALUDO / MENÚ UX
# =======================
SALUDO_HTML = """
<div class="bot-card">
  <div class="bot-header">
    <span class="bot-chip">🤖 Asistente IA · PharmaControl</span>
  </div>

  <p class="title">
    ¡Hola! Soy la inteligencia artificial de <b>PharmaControl</b>.
  </p>

  <p class="subtitle">Puedo ayudarte rápidamente con:</p>

  <ol class="bot-list">
    <li><b>1)</b> Ver <b>reporte general</b> de medicamentos.</li>
    <li><b>2)</b> Ver <b>medicamentos sin stock</b>.</li>
    <li><b>3)</b> Ver <b>medicamentos con existencia</b>.</li>
    <li><b>4)</b> Ver <b>proveedores</b>.</li>
    <li><b>5)</b> Ver <b>usuarios</b>.</li>
    <li><b>6)</b> Buscar un <b>medicamento por nombre</b>.</li>
  </ol>

  <p class="hint">
    👉 Puedes escribir por ejemplo:
    <code>1</code>,
    <code>reporte general</code>,
    <code>sin stock</code>,
    <code>existencias</code>,
    <code>proveedores</code>,
    <code>usuarios</code>,
    <code>paracetamol</code>.
  </p>
</div>
"""


# =======================
# FRONTEND
# =======================
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


# =======================
# HISTORIALES
# =======================
@app.get("/historial/archivos")
async def listar_historial():
    carpeta = "static/historial"
    if not os.path.exists(carpeta):
        return []
    archivos = []
    for f in os.listdir(carpeta):
        if f.endswith(".json"):
            archivos.append(
                {
                    "archivo": f"/static/historial/{f}",
                    "nombre": f,
                }
            )
    return archivos


@app.delete("/historial/{nombre}")
async def borrar_historial(nombre: str):
    path = os.path.join("static/historial", nombre)
    if os.path.exists(path):
        os.remove(path)
        return {"mensaje": f"✅ Historial {nombre} eliminado correctamente."}
    return {"mensaje": "⚠️ No se encontró el historial solicitado."}


# =======================
# NUEVO CHAT
# =======================
@app.post("/nuevo-chat")
async def iniciar_nuevo_chat():
    """Crea un nuevo chat con session_id único y envía el saludo de la IA."""
    global sesiones

    session_id = str(uuid.uuid4())[:8]  # ID corto único
    sesiones[session_id] = []

    sesiones[session_id].append(
        {
            "rol": "bot",
            "mensaje": SALUDO_HTML,
            "fecha": str(datetime.datetime.now()),
        }
    )

    return {
        "mensaje": "✅ Nuevo chat iniciado.",
        "session_id": session_id,
        "saludo": SALUDO_HTML,
    }


# =======================
# CHAT PRINCIPAL (UX SENCILLA)
# =======================
@app.post("/chat")
async def chat(req: ChatRequest):
    global sesiones

    mensaje_usuario = req.mensaje.strip()
    session_id = req.session_id

    if session_id not in sesiones:
        return {"respuesta": "⚠️ Sesión inválida. Por favor, inicia un nuevo chat."}

    sesiones[session_id].append(
        {
            "rol": "usuario",
            "mensaje": mensaje_usuario,
            "fecha": str(datetime.datetime.now()),
        }
    )

    # Intento de conexión con la API principal
    try:
        resp_med = requests.get(f"{API_BASE_URL}/medicamentos/all")
        resp_med.raise_for_status()
        medicamentos = resp_med.json()
    except Exception as e:
        respuesta = (
            "❌ No se pudo conectar con la API de medicamentos.<br>"
            f"Detalle técnico: {str(e)}"
        )
        sesiones[session_id].append(
            {"rol": "bot", "mensaje": respuesta, "fecha": str(datetime.datetime.now())}
        )
        guardar_historial_json(session_id, sesiones[session_id])
        return {"respuesta": respuesta}

    intencion = detectar_intencion(mensaje_usuario)

    try:
        # MENÚ / SALUDO
        if intencion in {"saludo", "menu"}:
            respuesta = SALUDO_HTML

        # MEDICAMENTOS CON EXISTENCIA
        elif intencion == "existencias":
            disponibles = [m for m in medicamentos if m.get("existencias", 0) > 0]

            filas = ""
            for m in disponibles[:10]:
                filas += f"""
                <tr>
                  <td>{m.get("id", "")}</td>
                  <td>{m.get("nombre", "Sin nombre")}</td>
                  <td>{m.get("existencias", 0)}</td>
                  <td>{m.get("lote", "")}</td>
                </tr>
                """

            nombre_pdf = generar_reporte(
                disponibles, "Medicamentos en Existencia", tipo="medicamentos"
            )
            total = len(disponibles)
            respuesta = f"""
            <p>💊 <b>Medicamentos con existencia</b></p>
            <p>📦 Se encontraron <b>{total}</b> medicamentos con stock disponible.</p>

            <table class="tabla-datos">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Nombre</th>
                  <th>Existencias</th>
                  <th>Lote</th>
                </tr>
              </thead>
              <tbody>
                {filas}
              </tbody>
            </table>

            <p>
              <a href="{nombre_pdf}" target="_blank" class="pdf-btn">
                📥 Descargar reporte en PDF
              </a>
            </p>
            """

        # MEDICAMENTOS SIN EXISTENCIA
        elif intencion == "sin_stock":
            sin_stock = [m for m in medicamentos if m.get("existencias", 0) == 0]

            if not sin_stock:
                respuesta = "✅ Todos los medicamentos tienen existencias suficientes 💊."
            else:
                filas = ""
                for m in sin_stock[:10]:
                    filas += f"""
                    <tr>
                      <td>{m.get("id", "")}</td>
                      <td>{m.get("nombre", "Sin nombre")}</td>
                      <td>{m.get("existencias", 0)}</td>
                      <td>{m.get("lote", "")}</td>
                    </tr>
                    """

                nombre_pdf = generar_reporte(
                    sin_stock, "Medicamentos sin existencia", tipo="medicamentos"
                )

                respuesta = f"""
                <p>⚠️ <b>Medicamentos SIN existencia</b></p>
                <p>📄 Se encontraron <b>{len(sin_stock)}</b> productos agotados.</p>

                <table class="tabla-datos">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Nombre</th>
                      <th>Existencias</th>
                      <th>Lote</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas}
                  </tbody>
                </table>

                <p>
                  <a href="{nombre_pdf}" target="_blank" class="pdf-btn">
                    📥 Descargar reporte en PDF
                  </a>
                </p>
                """

        # REPORTE GENERAL
        elif intencion == "reporte_general":
            nombre_pdf = generar_reporte(
                medicamentos, "Reporte general de medicamentos", tipo="medicamentos"
            )
            total = len(medicamentos)

            respuesta = f"""
            <p>📑 <b>Reporte general generado exitosamente.</b></p>
            <p>📦 Incluye <b>{total}</b> medicamentos registrados.</p>
            <p>
              <a href="{nombre_pdf}" target="_blank" class="pdf-btn">
                📥 Descargar reporte en PDF
              </a>
            </p>
            """

        # PROVEEDORES
        elif intencion == "proveedores":
            resp_prov = requests.get(f"{API_BASE_URL}/proveedores/all")
            resp_prov.raise_for_status()
            proveedores = resp_prov.json()

            if proveedores:
                filas = ""
                for p in proveedores[:10]:
                    filas += f"""
                    <tr>
                      <td>{p.get("id", "")}</td>
                      <td>{p.get("nombre", "Sin nombre")}</td>
                      <td>{p.get("contacto", "")}</td>
                    </tr>
                    """

                nombre_pdf = generar_reporte(
                    proveedores, "Reporte de proveedores", tipo="proveedores"
                )

                respuesta = f"""
                <p>🏭 <b>Reporte de Proveedores generado correctamente.</b></p>
                <p>Se encontraron <b>{len(proveedores)}</b> proveedores registrados.</p>

                <table class="tabla-datos">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Nombre</th>
                      <th>Contacto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas}
                  </tbody>
                </table>

                <p>
                  <a href="{nombre_pdf}" target="_blank" class="pdf-btn">
                    📥 Descargar reporte en PDF
                  </a>
                </p>
                """
            else:
                respuesta = "📦 No hay proveedores registrados actualmente."

        # USUARIOS (con UX mejorado cuando falla)
        elif intencion == "usuarios":
            try:
                resp_user = requests.get(f"{API_BASE_URL}/users/all")
                resp_user.raise_for_status()
                usuarios = resp_user.json()
            except Exception as e:
                detalle = str(e)
                respuesta = f"""
                <div class="bot-card error-card">

                  <p class="title">
                    👤 <b>No pude obtener la lista de usuarios.</b>
                  </p>

                  <p class="subtitle">
                    Parece que el módulo de <b>usuarios</b> en tu API presentó un inconveniente.
                  </p>

                  <div class="info-block">
                    🔧 <b>Revisa el endpoint:</b><br>
                    <code>/api/users/all</code><br>
                    (Entidad <code>Usuario</code> y su tabla en MySQL).
                  </div>

                  <p class="hint">
                    Mientras tanto, puedes seguir consultando
                    <b>medicamentos</b>, <b>proveedores</b> o generar
                    <b>reportes en PDF</b>.
                  </p>

                  <small class="tech-detail">
                    🔍 Detalles técnicos: {detalle}
                  </small>
                </div>
                """
            else:
                if usuarios:
                    filas = ""
                    for u in usuarios[:10]:
                        filas += f"""
                        <tr>
                          <td>{u.get("id", "")}</td>
                          <td>{u.get("nombre", u.get("name", "Sin nombre"))}</td>
                          <td>{u.get("email", "")}</td>
                          <td>{u.get("rol", "")}</td>
                        </tr>
                        """

                    nombre_pdf = generar_reporte(
                        usuarios, "Reporte de usuarios", tipo="usuarios"
                    )

                    respuesta = f"""
                    <p>👤 <b>Reporte de Usuarios generado correctamente.</b></p>
                    <p>Se encontraron <b>{len(usuarios)}</b> usuarios registrados.</p>

                    <table class="tabla-datos">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Nombre</th>
                          <th>Email</th>
                          <th>Rol</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filas}
                      </tbody>
                    </table>

                    <p>
                      <a href="{nombre_pdf}" target="_blank" class="pdf-btn">
                        📥 Descargar reporte en PDF
                      </a>
                    </p>
                    """
                else:
                    respuesta = "👤 No hay usuarios registrados actualmente."

        # BUSCAR MEDICAMENTO ESPECÍFICO
        else:  # buscar_medicamento
            nombre_busqueda = normalizar_texto(mensaje_usuario)
            encontrados = []

            for m in medicamentos:
                nombre_m = normalizar_texto(m.get("nombre", ""))
                if not nombre_m:
                    continue
                if nombre_busqueda in nombre_m:
                    encontrados.append(m)

            if encontrados:
                med = encontrados[0]
                nombre = med.get("nombre", "Medicamento desconocido")
                categoria = (
                    med.get("categoria", {}).get("nombre", "Sin categoría")
                    if isinstance(med.get("categoria"), dict)
                    else med.get("categoria", "Sin categoría")
                )
                proveedor = (
                    med.get("proveedor", {}).get("nombre", "Proveedor no registrado")
                    if isinstance(med.get("proveedor"), dict)
                    else med.get("proveedor", "Proveedor no registrado")
                )

                descripcion_ia = generar_descripcion_ia(nombre, categoria, proveedor)
                descripcion_ia_html = limpiar_markdown(descripcion_ia)

                respuesta = (
                    f"💊 <b>{nombre}</b><br>"
                    f"📂 Categoría: <i>{categoria}</i><br>"
                    f"🏭 Proveedor: <i>{proveedor}</i><br><br>"
                    f"🧾 <b>Descripción generada por IA:</b><br>{descripcion_ia_html}"
                )
            else:
                # No está en la base: card UX bonita, SIN el texto de "regístralo en el módulo..."
                descripcion_ia = generar_descripcion_ia(mensaje_usuario)
                descripcion_ia_html = limpiar_markdown(descripcion_ia)

                respuesta = f"""
                <div class="bot-card">
                  <p class="title">💊 <b>{mensaje_usuario.capitalize()}</b></p>

                  <p class="subtitle">
                    No encontré este medicamento en el <b>inventario registrado</b>,
                    pero te comparto una descripción general:
                  </p>

                  <div class="ia-block">
                    🧾 <b>Descripción generada por IA:</b><br>
                    {descripcion_ia_html}
                  </div>
                </div>
                """

    except Exception as e:
        detalle = str(e)
        respuesta = (
            "❌ <b>Ocurrió un problema mientras procesaba tu petición.</b><br>"
            "🔁 Intenta de nuevo en unos minutos.<br>"
            f"<small style='color:#888'>Detalle técnico: {detalle}</small>"
        )

    sesiones[session_id].append(
        {"rol": "bot", "mensaje": respuesta, "fecha": str(datetime.datetime.now())}
    )

    guardar_historial_json(session_id, sesiones[session_id])
    return {"respuesta": respuesta}


# =======================
# SCHEDULER: STARTUP / SHUTDOWN
# =======================
@app.on_event("startup")
def iniciar_scheduler():
    trigger = CronTrigger(hour=7, minute=30)  # ajusta la hora si quieres
    scheduler.add_job(
        generar_reportes_diarios,
        trigger,
        id="reportes_diarios",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
        print("🕒 Scheduler de reportes diarios iniciado.")


@app.on_event("shutdown")
def detener_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("🛑 Scheduler detenido.")
