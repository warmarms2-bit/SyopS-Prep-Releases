# Instalación

Guía para instalar y usar **SyopS Prep** desde los binarios publicados.

## ⭐ Instalación recomendada — Portátil (sin Python, no instala nada)

La forma más fácil: bajá el archivo y ejecutalo. **No requiere Python ni
instalar nada** (el portable ya trae todo incluido).

### macOS

1. Descargá [`SyopS_Prep.dmg`](https://github.com/warmarms2-bit/SyopS-Prep-Releases/releases/latest/download/SyopS_Prep.dmg).
2. Abrí el `.dmg` y hacé doble clic en **"SyopS Prep.app"**.

> ⚠ **Primera vez:** como es una app sin firmar descargada de internet, macOS
> la bloquea y el doble clic "no hace nada". Hacé **clic derecho → Abrir →
> Abrir** una sola vez; después el doble clic funciona normal.

### Windows

1. Descargá [`syops-portable.exe`](https://github.com/warmarms2-bit/SyopS-Prep-Releases/releases/latest/download/syops-portable.exe).
2. Hacé doble clic y listo.

> ⚠ Si Windows Defender lo marca, agregá la carpeta de descarga a la whitelist
> (o hacé clic en "Más información → Ejecutar de todas formas").

## 🚀 Empezar a usarlo

El asistente arranca con un flujo guiado: **diagnóstico → categoría → selección
→ resumen → descarga**.

**1) Terminal** (la más directa) — ejecutá el binario.

**2) Navegador (interfaz web)** — el asistente también ofrece una vista en el
navegador con un panel de ayuda por cada paso.

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

- El **portátil** no instala nada: es un binario autónomo con todo incluido.
- Las descargas e instaladores quedan **en tu equipo** (`~/SYOPS`), en tus
  carpetas.
- Funciona en **Windows, macOS y Linux**.
