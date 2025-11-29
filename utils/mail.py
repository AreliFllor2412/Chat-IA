import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

def enviar_correo_notificacion():
    remitente = os.getenv("SMTP_USER")
    destinatario = "arelidjfgmail@gmail.com"
    password = os.getenv("SMTP_PASS")

    asunto = "Notificación de Medicamentos Agotados"
    cuerpo = "⚠️ No hay medicamentos en existencia actualmente en el sistema."

    mensaje = MIMEMultipart()
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.attach(MIMEText(cuerpo, "plain"))

    try:
        servidor = smtplib.SMTP("smtp.gmail.com", 587)
        servidor.starttls()
        servidor.login(remitente, password)
        servidor.sendmail(remitente, destinatario, mensaje.as_string())
        servidor.quit()
        print("Correo enviado correctamente")
    except Exception as e:
        print("Error al enviar correo:", e)
