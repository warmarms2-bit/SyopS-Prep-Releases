# SyopS Prep

Asistente de **preparación e instalación de software** de forma remota y guiada.
Instala en tu equipo con un flujo simple: diagnóstico → categoría → selección
→ resumen → descarga.

## ⭐ Instalación

La forma más fácil: bajá el binario de tu plataforma y ejecutalo. **No requiere
Python ni instalar nada** (el binario ya trae todo incluido).

- **macOS:** [`dist/portable/SyopS_Prep.dmg`](dist/portable/SyopS_Prep.dmg)
  → abrí el `.dmg` y hacé doble clic en **"SyopS Prep.app"**.
  *⚠ Primera vez: como es app sin firmar descargada de internet, macOS la
  bloquea y el doble clic "no hace nada". Hacé **clic derecho → Abrir →
  Abrir** una vez; después el doble clic funciona.*

- **Windows:** [`dist/portable/syops-portable.exe`](dist/portable/syops-portable.exe)
  → doble clic y listo. *(Si todavía no existe, lo genera el workflow
  **Build portable Windows** en Actions.)*

Para más detalle (uso, desinstalación y solución de problemas), ver
[**docs/INSTALACION.md**](docs/INSTALACION.md).

## 🚀 Empezar a usarlo

El asistente arranca con un flujo guiado: **diagnóstico → categoría → selección
→ resumen → descarga**.

**1) Terminal** — ejecutá el binario descargado.

**2) Navegador (interfaz web)** — el asistente también ofrece una vista en el
navegador con un panel de ayuda por cada paso.

## 🧹 Desinstalación segura

El desinstalador **elimina SyopS** (la app y sus comandos) pero **conserva tus
archivos descargados e instalados** (`~/SYOPS`) — no se borra nada de lo que ya
tenés en tu equipo.

**Windows**
```powershell
& "$env:USERPROFILE\syops\eliminar-syops.cmd"
```

**macOS / Linux**
```bash
eliminar-syops
```

Te pide confirmación (s/n) antes de borrar nada. Cerrá y reabrí la terminal al
terminar.

## 📝 Notas

- El **portátil** no instala nada: es un binario autónomo con todo incluido.
- Las descargas e instaladores quedan **en tu equipo** (`~/SYOPS`), en tus
  carpetas.
- Funciona en **Windows, macOS y Linux**.
