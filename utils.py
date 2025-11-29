from __future__ import annotations

import datetime
import os
from typing import List, Dict, Any

from fpdf import FPDF

__all__ = ["PDFReport", "generar_reporte", "transformar_medicamento"]


class PDFReport(FPDF):
    def __init__(
        self,
        tipo: str = "medicamentos",
        logo_path: str | None = None,
    ) -> None:
        orientation = "L" if tipo.lower() == "medicamentos" else "P"
        super().__init__(orientation=orientation, unit="mm", format="A4")
        self.tipo = tipo.lower().strip()
        self.logo_path = logo_path if logo_path and os.path.isfile(logo_path) else None
        self.set_auto_page_break(auto=True, margin=12)

        font_dir = os.path.dirname(__file__)
        reg = os.path.join(font_dir, "DejaVuSans.ttf")
        bold = os.path.join(font_dir, "DejaVuSans-Bold.ttf")
        if os.path.isfile(reg) and os.path.isfile(bold):
            try:
                self.add_font("DejaVu", "", reg, uni=True)
                self.add_font("DejaVu", "B", bold, uni=True)
                self.fname = "DejaVu"
                self.use_emoji = True
            except Exception:
                self.fname = "Arial"
                self.use_emoji = False
        else:
            self.fname = "Arial"
            self.use_emoji = False

        self.theme: Dict[str, Dict[str, tuple[int, int, int]]] = {
            "medicamentos": dict(primary=(153, 0, 0), header=(255, 235, 235), a=(255, 250, 250), b=(245, 240, 240), alert=(255, 220, 220)),
            "proveedores": dict(primary=(0, 76, 153), header=(230, 242, 255), a=(245, 250, 255), b=(235, 245, 255), alert=(255, 230, 230)),
            "usuarios": dict(primary=(0, 102, 51), header=(225, 255, 235), a=(240, 255, 240), b=(230, 250, 230), alert=(255, 230, 230)),
        }[self.tipo if self.tipo in {"proveedores", "usuarios"} else "medicamentos"]

    def header(self):
        self.set_fill_color(*self.theme["header"])
        self.rect(0, 0, self.w, 30, "F")

        if self.logo_path:
            logo_width = 18
            x_pos = self.w - logo_width - 12  # 12 mm de margen derecho
            self.image(self.logo_path, x_pos, 5, w=logo_width)
            self.set_xy(12, 12)  # texto alineado a la izquierda como siempre
        else:
            self.set_xy(12, 12)

        
        emoji = {"medicamentos": "💊 ", "proveedores": "📦 ", "usuarios": "👤 "}.get(self.tipo, "") if self.use_emoji else ""
        title = f"{emoji}PharmaControl - Reporte de {self.tipo.capitalize()}"
        self.set_font(self.fname, "B", 18)
        self.set_text_color(*self.theme["primary"])
        self.cell(0, 8, title, ln=True, align="L")

        self.set_font(self.fname, "", 10)
        self.set_text_color(60)
        pref = "📅 " if self.use_emoji else "Fecha: "
        self.cell(0, 6, f"{pref}{datetime.datetime.now():%d/%m/%Y %H:%M}", ln=True, align="L")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.fname, "I", 8)
        self.set_text_color(100)
        label = "📄 Página" if self.use_emoji else "Página"
        self.cell(0, 10, f"{label} {self.page_no()}/{{nb}}", 0, 0, "C")

    def chapter_title(self, title: str):
        self.set_font(self.fname, "B", 13)
        self.set_text_color(*self.theme["primary"])
        self.cell(0, 9, title, ln=True)
        self.ln(2)

    def chapter_body(self, data: List[Dict[str, Any]]):
        if self.tipo == "proveedores":
            self._table(data, ["nombre", "direccion"], [90, 90], ["Nombre", "Dirección"])
        elif self.tipo == "usuarios":
            self._table(data, ["nombre", "email", "direccion"], [60, 70, 60], ["Nombre", "Email", "Dirección"])
        else:
            self._table_meds(data)

    def _table(self, data: List[Dict[str, Any]], keys: List[str], widths: List[int], headers: List[str]):
        self.set_font(self.fname, "B", 9)
        self.set_fill_color(*self.theme["header"])
        self.set_text_color(*self.theme["primary"])
        for w, h in zip(widths, headers):
            self.cell(w, 7, h, 1, 0, "C", True)
        self.ln()

        self.set_font(self.fname, "", 9)
        alternate = False
        for item in data:
            self.set_fill_color(*(self.theme["b"] if alternate else self.theme["a"]))
            for w, k in zip(widths, keys):
                val = item.get(k, "N/A")
                if isinstance(val, dict):
                    val = val.get("nombre", "N/A")
                self.cell(w, 6, str(val)[:60], 1, 0, "L", True)
            self.ln()
            alternate = not alternate

    def _table_meds(self, data: List[Dict[str, Any]]):
        headers = ["Nombre", "Categoría", "Dosis", "Proveedor", "Vencimiento", "Lote", "Cantidad"]
        widths = [70, 35, 25, 50, 25, 25, 20]  # Ajustado
        self.set_font(self.fname, "B", 8.5)
        self.set_fill_color(*self.theme["header"])
        self.set_text_color(*self.theme["primary"])
        for w, h in zip(widths, headers):
            self.cell(w, 6, h, 1, 0, "C", True)
        self.ln()

        self.set_font(self.fname, "", 8)
        alt = False
        for med in data:
            nombre = str(med.get("nombre", "N/A"))[:70]
            categoria = (
                med.get("categoria", {}).get("nombre", "N/A")
                if isinstance(med.get("categoria"), dict)
                else str(med.get("categoria", "N/A"))
            )
            dosis = str(med.get("dosis", "N/A"))
            proveedor = (
                med.get("proveedor", {}).get("nombre", "N/A")
                if isinstance(med.get("proveedor"), dict)
                else str(med.get("proveedor", "N/A"))
            )
            vencimiento = str(med.get("vencimiento", med.get("caducidad", "N/A")))
            lote = str(med.get("lote", "N/A"))
            stock = int(med.get("cantidad", med.get("existencias", 0) or 0))
            estado = str(med.get("estado", "")).lower()

            low = stock <= 0 or estado in {"bajo", "agotado"}
            self.set_fill_color(*(self.theme["alert"] if low else self.theme["b"] if alt else self.theme["a"]))

            row = [nombre, categoria, dosis, proveedor, vencimiento, lote, str(stock)]
            for w, txt in zip(widths, row):
                self.cell(w, 6, txt[:50], 1, 0, "C", True)
            self.ln()
            alt = not alt



def generar_reporte(
    data: List[Dict[str, Any]],
    titulo: str = "Reporte de Medicamentos",
    tipo: str = "medicamentos",
    salida_dir: str = "static/reportes",
    logo_path: str = "static/img/logo.jpg" if os.path.isfile("static/img/logo.jpg") else None

) -> str:
    os.makedirs(salida_dir, exist_ok=True)
    pdf = PDFReport(tipo, logo_path)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.chapter_title(titulo)
    pdf.chapter_body(data)

    fname = f"reporte_{titulo.replace(' ', '_').lower()}_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf"
    full_path = os.path.join(salida_dir, fname)
    pdf.output(full_path)
    return full_path


def transformar_medicamento(m: dict) -> dict:
    return {
        "nombre": m.get("nombre", "N/A"),
        "categoria": m.get("categoria", {}).get("nombre", "N/A"),
        "dosis": m.get("dosis", "N/A"),
        "proveedor": m.get("proveedor", {}).get("nombre", "N/A"),
        "vencimiento": m.get("caducidad", "N/A"),
        "lote": m.get("lote", "N/A"),
        "cantidad": m.get("stock", 0),
        "existencias": m.get("existencias", 0),
        "estado": m.get("estado", "N/A"),
        "descripcion": m.get("descripcion", "N/A"),
    }
