# SyopS Prep

Asistente de preparación de equipos para macOS y Windows: configura el
sistema, revisa hardware y genera una cola de instalación/descarga de
aplicaciones según lo que tenga el equipo.

## Requisitos

- Python 3.10 o superior (macOS/Linux/Windows)
- Conexión a internet (algunas funciones requieren un servidor de links)

## Instalar y ejecutar

Opción A — instalador (crea su propio entorno virtual):

```bash
curl -fsSL https://<host>/syops-prep/install.sh | bash
python3 syops_wizard.py
```

Windows:

```powershell
irm https://<host>/syops-prep/install.ps1 | iex
python syops_wizard.py
```

Opción B — directo:

```bash
python3 syops_wizard.py
```

Dependencias opcionales (torrent, etc.) se instalan con `--full` en el
instalador.

## Funciones

- Revisión de hardware y sistema (CPU, RAM, disco, macOS/Windows)
- Selección guiada de aplicaciones según categorías
- Cola de descarga/instalación con varios métodos (http, torrent, …)
- Modo vista previa sin descargar
- Soporte remoto (RustDesk)

## Configuración

`SYOPS_LINK_SERVER` — URL base del servidor de links de descarga. Si no está
definida, algunas funciones se ejecutan en modo local (lista indicativa sin
descargas).

El idioma de la interfaz se controla con `SYOPS_LANG=es|en` (por defecto `es`).

## Notas

Este repositorio es la variante del cliente. No incluye lógica de
licenciamiento ni infraestructura del proveedor del servicio.