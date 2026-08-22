"""Interfaz de backend de verificación de activación.

Define el contrato que un backend debe cumplir para poder usarse con el
diálogo de activación (ui/dialogs_activation.py). El backend concreto de
SyopS implementa esta interfaz, pero cualquier otro backend (API propia,
etc.) puede hacerlo.

Con esto, la capa de activación deja de depender del backend concreto y se
puede reutilizar en otra app cambiando solo la implementación.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ActivationBackend(Protocol):
    """Backend que verifica códigos de activación contra un servidor."""

    # URL del endpoint (puede ser "" si no hay backend configurado).
    url: str

    def check_code_async(self, code: str, hwid: str = "", callback=None) -> None:
        """Consulta si un código es válido/disponible. Llama
        callback(resultado: dict | None) en el main thread vía signal."""
        ...

    def use_code_async(self, code: str, hwid: str = "", max_apps: int = 3,
                       callback=None) -> None:
        """Marca un código como usado. Llama callback(ok: bool)."""
        ...
