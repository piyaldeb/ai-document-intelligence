"""Small, deterministic test documents built on the fly (reportlab / Pillow / openpyxl / xlwt)."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import openpyxl
import pymupdf
import xlwt
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

INVOICE = {
    "number": "INV-20417",
    "date": "14/03/2025",
    "supplier": "Acme Industrial Supplies Ltd",
    "customer": "Riverside Home Care",
    "items": [("Consulting services", "10", "150.00", "1,500.00"), ("Software license", "2", "425.50", "851.00")],
    "subtotal": "2,351.00",
    "tax": "470.20",
    "total": "2,821.20",
    "currency": "GBP",
}


def invoice_pdf(path: Path, inv: dict | None = None, *, pages: int = 1, encrypt: str | None = None) -> Path:
    inv = inv or INVOICE
    c = canvas.Canvas(str(path), pagesize=A4, encrypt=encrypt)
    w, h = A4
    for p in range(pages):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, h - 60, inv["supplier"])
        c.setFont("Helvetica-Bold", 20)
        c.drawRightString(w - 40, h - 60, "INVOICE")
        c.setFont("Helvetica", 10)
        if inv.get("number"):
            c.drawString(w - 200, h - 90, "Invoice No:")
            c.drawRightString(w - 40, h - 90, inv["number"])
        c.drawString(w - 200, h - 104, "Date:")
        c.drawRightString(w - 40, h - 104, inv["date"])
        if inv.get("customer"):
            c.drawString(40, h - 150, "Bill To:")
            c.drawString(40, h - 164, inv["customer"])
        y = h - 210
        c.setFont("Helvetica-Bold", 10)
        for label, x, right in (("Description", 40, False), ("Qty", 340, True), ("Unit Price", 440, True),
                                ("Amount", w - 40, True)):
            (c.drawRightString if right else c.drawString)(x, y, label)
        c.setFont("Helvetica", 10)
        y -= 18
        for desc, qty, unit, amount in inv["items"]:
            c.drawString(40, y, desc)
            c.drawRightString(340, y, qty)
            c.drawRightString(440, y, unit)
            c.drawRightString(w - 40, y, amount)
            y -= 16
        y -= 10
        if p == pages - 1:
            sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(inv["currency"], "")
            if inv.get("subtotal"):
                c.drawString(w - 220, y, "Subtotal")
                c.drawRightString(w - 40, y, f"{sym}{inv['subtotal']}")
                y -= 16
            if inv.get("tax"):
                c.drawString(w - 220, y, "VAT (20%)")
                c.drawRightString(w - 40, y, f"{sym}{inv['tax']}")
                y -= 16
            c.setFont("Helvetica-Bold", 11)
            c.drawString(w - 220, y, f"Total ({inv['currency']})")
            c.drawRightString(w - 40, y, f"{sym}{inv['total']}")
        c.setFont("Helvetica", 8)
        c.drawRightString(w - 40, 40, f"Page {p + 1} of {pages}")
        c.showPage()
    c.save()
    return path


def pdf_page_image(pdf: Path, dpi: int = 200) -> Image.Image:
    doc = pymupdf.open(pdf)
    pix = doc[0].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


class Samples:
    def __init__(self, root: Path):
        self.root = root

    def digital_pdf(self, name="invoice.pdf", **kw) -> Path:
        return invoice_pdf(self.root / name, **kw)

    def scanned_pdf(self, name="scanned.pdf", inv: dict | None = None) -> Path:
        img = pdf_page_image(invoice_pdf(self.root / "_src.pdf", inv), 200).convert("L").rotate(
            1.5, expand=True, fillcolor=255)
        out = self.root / name
        img.save(out, "PDF", resolution=200)
        return out

    def image(self, name="invoice.png", *, degrade: str | None = None, inv: dict | None = None) -> Path:
        img = pdf_page_image(invoice_pdf(self.root / "_src.pdf", inv), 200).convert("L")
        if degrade == "noisy":
            import numpy as np

            arr = np.asarray(img).astype("int16") + np.random.default_rng(1).normal(0, 15, img.size[::-1]).astype("int16")
            img = Image.fromarray(arr.clip(0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.6))
            img = img.rotate(-2.5, expand=True, fillcolor=255)
        elif degrade == "rotated90":
            img = img.rotate(90, expand=True, fillcolor=255)
        elif degrade == "lowres":
            img = img.resize((img.width // 2, img.height // 2))
        out = self.root / name
        fmt = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "tif": "TIFF", "tiff": "TIFF"}[name.rsplit(".", 1)[1]]
        img.save(out, fmt)
        return out

    def multipage_tiff(self, name="pages.tiff") -> Path:
        a = pdf_page_image(invoice_pdf(self.root / "_a.pdf"), 150)
        b = pdf_page_image(invoice_pdf(self.root / "_b.pdf", {**INVOICE, "number": "INV-20418"}), 150)
        out = self.root / name
        a.save(out, "TIFF", save_all=True, append_images=[b])
        return out

    def register_xlsx(self, name="register.xlsx") -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Q1"
        ws.append(["Accounts Payable Register"])
        ws.append([])
        ws.append(["Invoice No", "Invoice Date", "Supplier", "Customer", "Net Amount", "VAT", "Total", "Currency"])
        ws.append(["A-1001", datetime(2025, 2, 3), "Northwind Traders Inc", "Lakeside PLC", 100.0, 20.0, 120.0, "USD"])
        ws.append(["A-1002", datetime(2025, 2, 4), "Bluewave Logistics LLC", "Lakeside PLC", 200.0, 40.0, 245.0, "USD"])
        ws2 = wb.create_sheet("Q2")
        ws2.append(["Bill No", "Date", "Vendor Name", "Client", "Subtotal", "Tax Amount", "Grand Total", "CCY"])
        ws2.append(["B-77", datetime(2025, 5, 9), "Orion Software Systems", "Nova Pharma", 50.5, 0, 50.5, "EUR"])
        wb.create_sheet("Empty")
        wb.create_sheet("Notes").append(["Reviewed by the finance team"])  # must not become an invoice
        out = self.root / name
        wb.save(out)
        return out

    def lines_xlsx(self, name="lines.xlsx") -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Invoice #", "Date", "Supplier", "Description", "Qty", "Unit Price", "Line Total", "Invoice Total"])
        ws.append(["L-1", datetime(2025, 1, 2), "Acme Ltd", "Bolts", 10, 2.5, 25.0, 40.0])
        ws.append(["L-1", datetime(2025, 1, 2), "Acme Ltd", "Nuts", 5, 3.0, 15.0, None])
        ws.append(["L-2", datetime(2025, 1, 3), "Acme Ltd", "Washers", 4, 1.0, 4.0, 4.0])
        out = self.root / name
        wb.save(out)
        return out

    def xls(self, name="legacy.xls") -> Path:
        book = xlwt.Workbook()
        sh = book.add_sheet("Register")
        for c, h in enumerate(["Inv No", "Bill Date", "Vendor", "Invoice Total", "Currency"]):
            sh.write(0, c, h)
        sh.write(1, 0, "X-9")
        sh.write(1, 1, datetime(2025, 7, 1), xlwt.easyxf(num_format_str="DD/MM/YYYY"))
        sh.write(1, 2, "Kestrel Data Labs")
        sh.write(1, 3, 990.0)
        sh.write(1, 4, "GBP")
        out = self.root / name
        book.save(str(out))
        return out

    def eu_csv(self, name="eu.csv") -> Path:
        text = (
            "Rechnungsnummer / Invoice No;Datum / Date;Lieferant / Supplier;Netto / Subtotal;MwSt / VAT;Gesamt / Total;Währung / Currency\n"
            "R-1;14.03.2025;Müller Bürobedarf GmbH;1.000,00;190,00;1.190,00;EUR\n"
            "R-2;15.03.2025;Société Générale SA;20,50;3,90;24,40;EUR\n"
            "broken;row;with;far;too;many;columns;here;x\n"
        )
        out = self.root / name
        out.write_bytes(text.encode("latin-1"))
        return out

    def form_xlsx(self, name="form.xlsx") -> Path:
        """An invoice laid out as a form inside a sheet (not a table)."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Greenfield Office Solutions"
        ws["D1"] = "INVOICE"
        ws["C3"] = "Invoice No:"
        ws["D3"] = "GF-3321"
        ws["C4"] = "Date:"
        ws["D4"] = "2025-06-30"
        ws["A6"] = "Bill To:"
        ws["A7"] = "Metro Health Clinic"
        ws["A9"], ws["B9"], ws["C9"], ws["D9"] = "Description", "Qty", "Unit Price", "Amount"
        ws["A10"], ws["B10"], ws["C10"], ws["D10"] = "Toner cartridge", 3, 40, 120
        ws["C12"], ws["D12"] = "Subtotal", 120
        ws["C13"], ws["D13"] = "Tax", 12
        ws["C14"], ws["D14"] = "Total USD", 132
        out = self.root / name
        wb.save(out)
        return out

    def corrupted(self, kind: str) -> Path:
        if kind == "pdf_truncated":
            data = invoice_pdf(self.root / "_t.pdf").read_bytes()
            p = self.root / "truncated.pdf"
            p.write_bytes(data[: len(data) // 3])
        elif kind == "pdf_garbage":
            p = self.root / "garbage.pdf"
            p.write_bytes(b"this is definitely not a pdf" * 50)
        elif kind == "xlsx_garbage":
            p = self.root / "garbage.xlsx"
            p.write_bytes(b"PK\x03\x04" + b"\x00\x13garbage" * 200)
        elif kind == "png_garbage":
            p = self.root / "garbage.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        elif kind == "jpg_truncated":
            buf = io.BytesIO()
            pdf_page_image(invoice_pdf(self.root / "_j.pdf"), 150).save(buf, "JPEG", quality=80)
            p = self.root / "truncated.jpg"
            p.write_bytes(buf.getvalue()[: int(len(buf.getvalue()) * 0.75)])
        elif kind == "pdf_encrypted":
            p = invoice_pdf(self.root / "encrypted.pdf", encrypt="secret")
        else:
            raise ValueError(kind)
        return p
