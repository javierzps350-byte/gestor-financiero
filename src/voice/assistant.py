"""Compatibilidad para versiones anteriores del asistente por texto.

La lógica de conversación reside ahora en src.agent.controller.
"""
from src.agent.controller import FinancialAgent


def handle_text_command(command: str) -> str:
    # Instancia corta para mantener la firma histórica. La interfaz principal
    # utiliza FinancialAgent directamente y conserva el estado de confirmación.
    return FinancialAgent().handle(command)
