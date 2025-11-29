from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def generar_pedido(nombre_archivo: str, pedido: dict):
    c = canvas.Canvas(nombre_archivo, pagesize=A4)
    width, height = A4

    # Encabezado
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, 800, "Pedido de Medicamentos con Bajo Stock")

    # Datos generales
    c.setFont("Helvetica", 12)
    c.drawString(50, 770, f"Número de pedido: {pedido['numero']}")
    c.drawString(50, 750, f"Responsable: {pedido['responsable']}")
    c.drawString(50, 730, f"Fecha: {pedido['fecha']}")

    # Tabla
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 700, "Medicamento")
    c.drawString(220, 700, "Stock Actual")
    c.drawString(340, 700, "Stock Mínimo")
    c.drawString(470, 700, "Proveedor")

    y = 680
    c.setFont("Helvetica", 12)
    for med in pedido["items"]:
        c.drawString(50, y, med["nombre"])
        c.drawString(220, y, str(med["stock_actual"]))
        c.drawString(340, y, str(med["stock_minimo"]))
        c.drawString(470, y, med["proveedor"])
        y -= 20

    c.save()
    return nombre_archivo
