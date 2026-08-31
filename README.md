# SyopS Prep

Asistente de **preparación e instalación de software** de forma remota y guiada.
Instala en tu equipo con un flujo simple: diagnóstico → categoría → selección
→ resumen → descarga.

Este repositorio es el canal de **distribución de binarios** de SyopS Prep:
contiene los instaladores listos para usar, la guía de instalación y los
procedimientos de build. **No contiene código fuente** (ese vive en un
repositorio privado de desarrollo).

## ⭐ Instalación

La forma más fácil: bajá el binario de tu plataforma desde la
[**pestaña Releases**](https://github.com/warmarms2-bit/SyopS-Prep-Releases/releases)
y ejecutalo. **No requiere Python ni instalar nada** (el binario ya trae todo
incluido).

- **macOS:** descargá `SyopS_Prep.dmg`, abrí el `.dmg` y hacé doble clic en
  **"SyopS Prep.app"**.
  *⚠ Primera vez: como es una app sin firmar descargada de internet, macOS la
  bloquea y el doble clic "no hace nada". Hacé **clic derecho → Abrir →
  Abrir** una vez; después el doble clic funciona normal.*

- **Windows:** descargá `syops-portable.exe` y hacé doble clic.
  *⚠ Si Windows Defender lo marca, agregá la carpeta de descarga a la
  whitelist (o "Más información → Ejecutar de todas formas").*

Para más detalle (uso, desinstalación y solución de problemas), ver
[**docs/INSTALACION.md**](docs/INSTALACION.md).

## 🚀 Empezar a usarlo

El asistente arranca con un flujo guiado: **diagnóstico → categoría → selección
→ resumen → descarga**.

**1) Terminal** — ejecutá el binario descargado.

**2) Navegador (interfaz web)** — el asistente también ofrece una vista en el
navegador con un panel de ayuda por cada paso.

## 📦 Binarios

Los instaladores publicados en cada [**Release**](https://github.com/warmarms2-bit/SyopS-Prep-Releases/releases):

| Plataforma | Archivo | Tipo |
|---|---|---|
| macOS | `SyopS_Prep.dmg` | Instalador (.app) |
| Windows | `syops-portable.exe` | Portable (.exe) |

## 🧹 Desinstalación segura

El desinstalador **elimina SyopS** (la app y sus comandos) pero **conserva tus
archivos descargados e instalados** (`~/SYOPS`) — no se borra nada de lo que ya
tenés en tu equipo. Te pide confirmación (s/n) antes de borrar nada. Cerrá y
reabrí la terminal al terminar.

**Windows**
```powershell
& "$env:USERPROFILE\syops\eliminar-syops.cmd"
```

**macOS / Linux**
```bash
eliminar-syops
```

## 📝 Notas

- **Binario** = no instala nada: es un ejecutable autónomo con todo incluido.
- Las descargas e instaladores quedan **en tu equipo** (`~/SYOPS`), en tus
  carpetas.
- Funciona en **Windows, macOS y Linux**.
- Los binarios se generan en el entorno de desarrollo y se publican acá; la
  versión nueva llega como una Release nueva.
