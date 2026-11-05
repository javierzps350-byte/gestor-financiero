import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.database import connection as db_connection
from src.services.finance_service import create_client, search_movements, list_client_charges
from src.agent.controller import FinancialAgent


class FinancialAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "agent.sqlite3"
        self.db_patch = patch.object(db_connection, "DB_PATH", self.database_path)
        self.db_patch.start()
        db_connection.initialize_database()
        self.agent = FinancialAgent()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_income_is_only_saved_after_explicit_confirmation(self):
        client_id = create_client("Carlos", 1000, "2026-11-01")
        response = self.agent.handle(
            "Carlos me pagó 25 dólares por mensualidad mediante transferencia, voucher 2581"
        )
        self.assertIn("revisión antes de guardar", response)
        self.assertIn("$25,00", response)
        self.assertEqual(search_movements(query="Carlos"), [])

        confirmation = self.agent.confirm()
        self.assertIn("guardada correctamente", confirmation)
        rows = search_movements(query="Carlos")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount_cents"], 2500)
        self.assertEqual(rows[0]["voucher_number"], "2581")
        charges = list_client_charges(client_id, "2026-11-30")
        self.assertEqual([row["remaining_cents"] for row in charges], [0, 0, 500])


    def test_voucher_extraction_handles_natural_phrase(self):
        create_client("Carlos", 1000, "2026-11-01")
        response = self.agent.handle(
            "Carlos me pagó 25 dólares por mensualidad mediante transferencia, el voucher es el 002581"
        )
        self.assertIn("Voucher: 002581", response)
        self.assertIn("Importe: $25,00", response)

    def test_agent_collects_missing_reason_before_confirmation(self):
        create_client("Ana", 1000, "2026-01-01")
        first = self.agent.handle("Ana me pagó 10 dólares mediante transferencia")
        self.assertIn("motivo", first.lower())
        second = self.agent.handle("mensualidad")
        self.assertIn("revisión antes de guardar", second)
        self.assertIsNotNone(self.agent.pending)
        self.assertTrue(self.agent.pending["payload"]["apply_to_monthly"])
        result = self.agent.confirm()
        self.assertIn("guardada correctamente", result)
        self.assertEqual(len(search_movements(query="Ana")), 1)

    def test_expense_action_is_not_applied_to_monthly_charges(self):
        response = self.agent.handle(
            "Pagué 18 dólares a Empresa Eléctrica por electricidad mediante efectivo"
        )
        self.assertIn("revisión antes de guardar", response)
        result = self.agent.confirm()
        self.assertIn("guardada correctamente", result)
        rows = search_movements(query="Empresa Eléctrica", direction="expense")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount_cents"], 1800)

    def test_create_client_is_staged_before_saving(self):
        response = self.agent.handle(
            "Crea un cliente Ana López con mensualidad de 23 dólares desde 2026-01-31"
        )
        self.assertIn("CLIENTE — revisión", response)
        self.assertEqual(len(search_movements()), 0)
        result = self.agent.confirm()
        self.assertIn("Cliente creado correctamente", result)
        from src.services.finance_service import list_clients
        clients = list_clients(active_only=True)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["name"], "Ana López")
        self.assertEqual(clients[0]["current_rate_cents"], 2300)

    def test_cancel_discards_pending_action(self):
        self.agent.handle("Recibí 15 dólares de Juan por servicio mediante efectivo")
        result = self.agent.cancel()
        self.assertIn("cancelada", result.lower())
        self.assertEqual(search_movements(), [])


    def test_voice_style_yes_confirms_ready_operation(self):
        response = self.agent.handle(
            "Pagué 18 dólares a Empresa Eléctrica por electricidad mediante efectivo"
        )
        self.assertIn("revisión antes de guardar", response)
        confirmed = self.agent.handle("sí")
        self.assertIn("guardada correctamente", confirmed)
        self.assertEqual(len(search_movements(direction="expense")), 1)

    def test_attachment_requires_file_selection_and_confirmation(self):
        from unittest.mock import patch
        from src.services.finance_service import create_movement

        movement_id = create_movement(
            direction="income", counterparty="Carlos", reason="Mensualidad",
            amount_cents=2500, payment_date="2026-11-01",
            payment_method="Transferencia", voucher_number="2581",
        )
        fake_files = [
            {"name": "transferencia_1.pdf", "path": "/tmp/one.pdf", "modified": "2026-11-01 10:00", "size": 100},
            {"name": "transferencia_2.pdf", "path": "/tmp/two.pdf", "modified": "2026-11-01 10:01", "size": 200},
        ]
        with patch("src.agent.controller.find_recent_downloads", return_value=fake_files), \
             patch("src.agent.controller.attach_evidence_from_download", return_value=77) as attach:
            choice_prompt = self.agent.handle("Adjunta la descarga reciente al voucher 2581")
            self.assertIn("varios archivos", choice_prompt)
            preview = self.agent.handle("2")
            self.assertIn("transferencia_2.pdf", preview)
            self.assertIn(f"#{movement_id}", preview)
            self.assertFalse(attach.called)
            result = self.agent.confirm()
            self.assertIn("adjuntado correctamente", result)
            attach.assert_called_once_with(movement_id, "/tmp/two.pdf")

    def test_attachment_can_target_latest_expense(self):
        from unittest.mock import patch
        from src.services.finance_service import create_movement

        movement_id = create_movement(
            direction="expense", counterparty="Proveedor", reason="Materiales",
            amount_cents=1800, payment_date="2026-11-01",
            payment_method="Transferencia", voucher_number="G-001",
        )
        fake_file = [{"name": "comprobante.pdf", "path": "/tmp/comprobante.pdf", "modified": "2026-11-01 10:00", "size": 100}]
        with patch("src.agent.controller.find_recent_downloads", return_value=fake_file), \
             patch("src.agent.controller.attach_evidence_from_download", return_value=88) as attach:
            preview = self.agent.handle("Adjunta la descarga reciente al último gasto que hice")
            self.assertIn("ADJUNTAR EVIDENCIA", preview)
            self.assertIn(f"#{movement_id}", preview)
            result = self.agent.confirm()
            self.assertIn("adjuntado correctamente", result)
            attach.assert_called_once_with(movement_id, "/tmp/comprobante.pdf")


    def test_agent_prepares_and_confirms_future_rate_change(self):
        from src.services.finance_service import list_clients
        create_client("Carlos", 1000, "2026-11-01")
        response = self.agent.handle("Cambia la mensualidad de Carlos a 30 dólares")
        self.assertIn("CAMBIO DE TARIFA", response)
        result = self.agent.confirm()
        self.assertIn("Tarifa actualizada", result)
        client = list_clients(active_only=True)[0]
        self.assertEqual(client["current_rate_cents"], 3000)

    def test_navigation_commands_return_page_target(self):
        response = self.agent.handle("Abre la sección de clientes")
        self.assertIn("clientes", response.lower())
        self.assertEqual(self.agent.navigation_target, "clients")

    def test_cancel_works_while_agent_is_waiting_for_a_required_field(self):
        self.agent.handle("Registra un pago recibido")
        result = self.agent.handle("cancelar")
        self.assertIn("cancelada", result.lower())
        self.assertIsNone(self.agent.pending)


    def test_monthly_payment_phrase_without_por_is_understood(self):
        create_client("Laura", 1000, "2026-11-01")
        response = self.agent.handle("Laura me pagó 10 dólares de mensualidad por transferencia")
        self.assertIn("revisión antes de guardar", response)
        self.assertIn("Motivo: Mensualidad", response)
        result = self.agent.confirm()
        self.assertIn("guardada correctamente", result)


    def test_agent_lists_clients_with_overdue_charges(self):
        create_client("Deudor", 1000, "2025-01-01")
        response = self.agent.handle("¿Quién me debe dinero?")
        self.assertIn("Deudor", response)
        self.assertIn("Vencido", response)

    def test_query_month_balance(self):
        answer = self.agent.handle("¿Cuál es el balance del mes?")
        self.assertIn("ingresos", answer.lower())
        self.assertIn("gastos", answer.lower())


    def test_named_month_range_understands_income_query(self):
        from src.services.finance_service import create_movement
        create_movement(
            direction="income", counterparty="Carlos", reason="Mensualidad",
            amount_cents=2500, payment_date="2026-11-02",
            payment_method="Transferencia", voucher_number="N-01",
        )
        answer = self.agent.handle("¿Cuánto he recibido en noviembre de 2026?")
        self.assertIn("$25,00", answer)
        self.assertIn("noviembre de 2026", answer)

    def test_category_query_filters_expenses_in_named_month(self):
        from src.services.finance_service import create_movement
        create_movement(
            direction="expense", counterparty="Supermercado", reason="Compra de alimentos",
            amount_cents=3750, payment_date="2026-11-03",
            payment_method="Tarjeta", category="Comida",
        )
        create_movement(
            direction="expense", counterparty="Taxi", reason="Traslado",
            amount_cents=1200, payment_date="2026-11-03",
            payment_method="Efectivo", category="Transporte",
        )
        answer = self.agent.handle("¿Cuánto gasté en comida durante noviembre de 2026?")
        self.assertIn("$37,50", answer)
        self.assertIn("Comida", answer)

    def test_client_history_query_uses_registered_client(self):
        from src.services.finance_service import create_movement
        client_id = create_client("María Fernanda", 2500, "2026-01-01")
        create_movement(
            direction="income", counterparty="María Fernanda", reason="Mensualidad",
            amount_cents=2500, payment_date="2026-11-02",
            payment_method="Transferencia", client_id=client_id,
        )
        answer = self.agent.handle("Muéstrame los pagos de María Fernanda en noviembre de 2026")
        self.assertIn("María Fernanda", answer)
        self.assertIn("$25,00", answer)

    def test_previous_month_period_is_resolved(self):
        from calendar import monthrange
        from src.agent.controller import _extract_period_range
        today = date.today()
        expected_year = today.year if today.month > 1 else today.year - 1
        expected_month = today.month - 1 if today.month > 1 else 12
        actual = _extract_period_range("¿Qué gastos tuve el mes pasado?")
        self.assertEqual(actual[0], date(expected_year, expected_month, 1).isoformat())
        self.assertEqual(actual[1], date(expected_year, expected_month, monthrange(expected_year, expected_month)[1]).isoformat())

    def test_year_period_is_resolved(self):
        from src.agent.controller import _extract_period_range
        self.assertEqual(
            _extract_period_range("Consulta los movimientos de todo el año 2025"),
            ("2025-01-01", "2025-12-31"),
        )

    def test_question_about_amount_paid_is_not_treated_as_new_expense(self):
        from src.agent.controller import FinancialAgent
        self.assertTrue(FinancialAgent._is_query_request("cuanto he pagado este mes"))
        self.assertFalse(FinancialAgent._is_query_request("pague 18 dolares a la empresa electrica"))


if __name__ == "__main__":
    unittest.main()
