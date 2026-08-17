"""app_flow — esqueleto del flujo de SyopS Prep.

Lógica de decisión del asistente, agnóstica de presentación. El wizard de
terminal y la UI son dos vistas sobre este esqueleto.
"""

from app_flow.flujo import (
    Etapa, FlujoEstado, FlujoMotor, Efectos,
    platform_apps, metodos_compatibles, preseleccionar_metodo,
    cobertura_metodo, versiones_metodo, clarify_mentions,
    bypass_pixeldrain_sirve, necesita_serializar,
)

__all__ = [
    "Etapa", "FlujoEstado", "FlujoMotor", "Efectos",
    "platform_apps", "metodos_compatibles", "preseleccionar_metodo",
    "cobertura_metodo", "versiones_metodo", "clarify_mentions",
    "bypass_pixeldrain_sirve", "necesita_serializar",
]
