import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_TO = os.getenv("REPORTS_EMAIL_TO")  # destinatario

def enviar_correo_reportes(archivos: list):
    """
    Envía un correo con múltiples PDFs adjuntos.
    """
    try:
        # Encabezado del correo
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        msg["Subject"] = "📊 Reportes automáticos de PharmaControl"

        cuerpo = """
        <h3>📊 Reportes automáticos generados</h3>
        <p>Adjunto encontrarás los reportes del día.</p>
        <p>Saludos,<br>PharmaControl IA 🤖💊</p>
        """
        msg.attach(MIMEText(cuerpo, "html"))

        # Adjuntar cada archivo PDF
        for archivo in archivos:
            with open(archivo, "rb") as f:
                parte = MIMEBase("application", "octet-stream")
                parte.set_payload(f.read())
                encoders.encode_base64(parte)
                parte.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(archivo)}"',
                )
                msg.attach(parte)

        # Conectar al servidor SMTP de Gmail
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        print(f"📧 Correo enviado correctamente a {EMAIL_TO}")

    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")
