import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from src.services.report_service import build_movement_report, export_report


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "id": 17, "direction": "income", "status": "active",
                "payment_date": "2026-11-03", "registered_at": "2026-11-03 09:30:00",
                "counterparty": "Cliente Álvarez", "reason": "Mensualidad noviembre",
                "category": "Ingresos", "amount_cents": 2500,
                "payment_method": "Transferencia", "voucher_number": "TRX-00017",
                "notes": "Pago recibido", "client_id": 2, "client_name": "Cliente Álvarez",
                "evidence_count": 1,
            },
            {
                "id": 18, "direction": "expense", "status": "active",
                "payment_date": "2026-11-04", "registered_at": "2026-11-04 12:00:00",
                "counterparty": "Supermercado", "reason": "Compra de alimentos",
                "category": "Comida", "amount_cents": 875,
                "payment_method": "Tarjeta", "voucher_number": "",
                "notes": "", "client_id": None, "client_name": "",
                "evidence_count": 0,
            },
            {
                "id": 19, "direction": "expense", "status": "void",
                "payment_date": "2026-11-05", "registered_at": "2026-11-05 12:00:00",
                "counterparty": "Proveedor", "reason": "Registro anulado",
                "category": "Otros", "amount_cents": 1000,
                "payment_method": "Efectivo", "voucher_number": "V-19",
                "notes": "Anulado con motivo", "client_id": None, "client_name": "",
                "evidence_count": 0,
            },
        ]
        self.report = build_movement_report(
            self.rows,
            {"desde": "2026-11-01", "hasta": "2026-11-30", "cliente": "Todos"},
            "Ingresos y gastos de noviembre",
        )

    def test_summary_excludes_void_movements_from_financial_totals(self):
        summary = self.report["summary"]
        self.assertEqual(summary["records"], 3)
        self.assertEqual(summary["active_records"], 2)
        self.assertEqual(summary["void_records"], 1)
        self.assertEqual(summary["income_cents"], 2500)
        self.assertEqual(summary["expenses_cents"], 875)
        self.assertEqual(summary["net_cents"], 1625)

    def test_exports_pdf_xlsx_xml_txt_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = {
                ".pdf": root / "noviembre.pdf",
                ".xlsx": root / "noviembre.xlsx",
                ".xml": root / "noviembre.xml",
                ".txt": root / "noviembre.txt",
                ".csv": root / "noviembre.csv",
            }
            for suffix, path in outputs.items():
                with self.subTest(format=suffix):
                    count = export_report(path, self.report)
                    self.assertEqual(count, 3)
                    self.assertGreater(path.stat().st_size, 100)
            pdf_bytes = outputs[".pdf"].read_bytes()
            self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
            self.assertIn(b"%%EOF", pdf_bytes)
            with zipfile.ZipFile(outputs[".xlsx"]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
                sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                self.assertTrue(sheet.tag.endswith("worksheet"))
                sheet_text = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                self.assertIn("Cliente Álvarez", sheet_text)
                self.assertIn("Pago recibido", sheet_text)
                page_setup = sheet.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}pageSetup")
                self.assertEqual(page_setup.attrib["orientation"], "landscape")
                self.assertEqual(page_setup.attrib["fitToWidth"], "1")
                self.assertEqual(page_setup.attrib["paperSize"], "8")
            xml_root = ET.parse(outputs[".xml"]).getroot()
            self.assertEqual(xml_root.attrib["kind"], "movements")
            self.assertEqual(len(xml_root.find("records")), 3)
            xml_text = outputs[".xml"].read_text(encoding="utf-8")
            self.assertIn("Cliente Álvarez", xml_text)
            self.assertIn("Pago recibido", xml_text)
            txt = outputs[".txt"].read_text(encoding="utf-8")
            self.assertIn("Ingresos y gastos de noviembre", txt)
            self.assertIn("Cliente Álvarez", txt)
            self.assertIn("Pago recibido", txt)
            csv_text = outputs[".csv"].read_text(encoding="utf-8-sig")
            self.assertIn("Categoría", csv_text)
            self.assertIn("Cliente asociado", csv_text)
            self.assertIn("Evidencias", csv_text)
            self.assertIn("Comida", csv_text)
            self.assertIn("Pago recibido", csv_text)
            self.assertIn("Observaciones", csv_text)

    def test_pdf_is_readable_by_pdf_parser_when_available(self):
        import shutil
        import subprocess
        if not shutil.which("pdfinfo") or not shutil.which("pdftotext"):
            self.skipTest("pdfinfo/pdftotext no están instalados")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.pdf"
            export_report(path, self.report)
            info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True)
            self.assertIn("Pages:", info.stdout)
            text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout
            self.assertIn("Ingresos y gastos de noviembre", text)
            self.assertIn("Cliente", text)


if __name__ == "__main__":
    unittest.main()
