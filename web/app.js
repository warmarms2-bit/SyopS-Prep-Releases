
const HELP = {
  inicio: ["Paso 1/7", "Este es un asistente de preparación e instalación remota. Presioná ▶ Empezar; el flujo te guía: diagnóstico → categoría → selección → resumen → descarga → final."],
  diagnostico: ["Paso 2/7", "El asistente detecta tu equipo (procesador, RAM, disco y SO) automáticamente. No hacés nada: esperá a que termine el escaneo y presioná Enter para continuar."],
  categoria: ["Paso 3/7", "Elegí una categoría escribiendo su número (1-7). Podés responder con un solo número o presionar Enter para aceptar el valor por defecto."],
  seleccion: ["Paso 4/7", "Elegí los programas por número (ej: 1,3,5 o 1-3). El límite depende de tu plan. 0 = salir de la categoría, q = cancelar el asistente."],
  adobe_method: ["Paso 4/7", "Elegí el método de Adobe por número (1-3). Algunos métodos requieren usar una cuenta de Adobe; se indican con una advertencia."],
  resumen: ["Paso 5/7", "Revisá el resumen de tu selección y la compatibilidad con tu equipo. Confirmá con s/n para continuar a la descarga."],
  descarga: ["Paso 6/7", "Se están descargando los archivos seleccionados. La barra de progreso muestra el avance de cada uno. Esperá a que terminen."],
  final: ["Paso 7/7", "¡Listo! Las descargas/instaladores quedaron en tu equipo. Si querés, podés solicitar asistencia remota (RustDesk). Gracias por usar SyopS."],
  adobe_fullpack: ["Paso 4/7", "Estás configurando el Adobe Full Pack. Seguí las indicaciones del asistente."],
};
/* SyopS Prep — UI web: el wizard se ve como una terminal en el navegador.
   Maneja el MISMO Wizard de terminal (input provider + stdout capturado). */
const PAGE_TITLES = {
  inicio: "Inicio",
  diagnostico: "Diagnóstico",
  categoria: "Categoría",
  seleccion: "Selección",
  resumen: "Resumen",
  descarga: "Descarga",
  final: "Final",
  adobe_method: "Método Adobe",
  adobe_fullpack: "Adobe Full Pack",
};

const outputEl = document.getElementById("output");
const inputEl = document.getElementById("input");
const inputbarEl = document.getElementById("inputbar");
const statusEl = document.getElementById("status");
const titleEl = document.getElementById("page-title");
const btnStart = document.getElementById("btn-start");
const btnSend = document.getElementById("btn-send");
const btnRestart = document.getElementById("btn-restart");
setHelp("inicio");
setHelp("inicio");

let lastRendered = "";
let lastPage = "inicio";

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* Reconstruye las líneas reales de la terminal aplicando los retornos de
   carro (\r) que usa la barra de progreso: cada \r reinicia la línea actual
   y gana el último valor, así el navegador ve la MISMISIMA salida que la
   terminal real. */
function toLines(text) {
  const lines = [];
  let cur = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === "\r") {
      if (text[i + 1] === "\n") { lines.push(cur); cur = ""; i += 2; continue; }
      cur = ""; i += 1; continue;
    }
    if (ch === "\n") { lines.push(cur); cur = ""; i += 1; continue; }
    cur += ch; i += 1;
  }
  if (cur !== "") lines.push(cur);
  return lines;
}

function renderOutput(text) {
  return toLines(text).map((line) => {
    const e = esc(line);
    if (e.startsWith("»")) return `<span class="prompt">${e}</span>`;
    if (e.includes("═")) return `<span class="accent">${e}</span>`;
    return e;
  }).join("\n");
}

function appendOutput(text) {
  text = text || "";
  // Idempotente: el server envía el buffer COMPLETO; si no cambió, no
  // re-renderizamos (evita parpadeo). Así el banner aparece UNA sola vez.
  if (text === lastRendered) return;
  lastRendered = text;
  outputEl.innerHTML = renderOutput(text);
  outputEl.scrollTop = outputEl.scrollHeight;
}

function setHelp(page) {
  const h = HELP[page];
  const stepEl = document.getElementById("help-step");
  const textEl = document.getElementById("help-text");
  if (h) {
    stepEl.textContent = h[0];
    textEl.textContent = h[1];
  } else {
    stepEl.textContent = PAGE_TITLES[page] || page;
    textEl.textContent = "";
  }
}

function setPage(page) {
  lastPage = page;
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.page === page));
  titleEl.textContent = PAGE_TITLES[page] || page;
  setHelp(page);
  updateRestart(page);
}

function setWaiting(waiting) {
  inputbarEl.hidden = !waiting;
  if (waiting) {
    statusEl.textContent = "Esperando tu respuesta…";
    statusEl.classList.add("spin");
    inputEl.focus();
  } else {
    statusEl.classList.remove("spin");
  }
}

function setWorking(working) {
  if (working) {
    statusEl.textContent = "Trabajando…";
    statusEl.classList.add("spin");
  } else if (!document.getElementById("inputbar").hidden) {
    statusEl.classList.remove("spin");
  }
}

async function start() {
  btnStart.style.display = "none";   // desaparece tras el click
  btnRestart.hidden = false;          // aparece Reiniciar
  lastRendered = "";                  // forzamos a re-renderizar la nueva salida
  document.getElementById("output").textContent = "";
  await fetch("/api/start", { method: "POST" });
}

async function restart() {
  lastRendered = "";                  // forzamos a re-renderizar la nueva salida
  document.getElementById("output").textContent =
    "Bienvenido. El wizard de SyopS corre en el navegador, con la misma lógica de la terminal.\nPresioná ▶ Empezar para arrancar el flujo.";
  setPage("inicio");
  setWaiting(false);
  setWorking(false);
  await fetch("/api/restart", { method: "POST" });
}

async function restartFromStart() {
  // Reiniciar y arrancar de una (desde el paso 1).
  await restart();
  await fetch("/api/start", { method: "POST" });
  statusEl.textContent = "Trabajando…";
}

// Visibilidad de Reiniciar: no durante la descarga (código activado + bajando).
function updateRestart(page) {
  const downloading = (page === "descarga");
  btnRestart.hidden = downloading;
}

async function sendInput() {
  const answer = inputEl.value;
  inputEl.value = "";
  await fetch("/api/input", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
}

async function poll() {
  try {
    // El server envía el buffer COMPLETO (sin `since`): render idempotente.
    const r = await fetch(`/api/state`);
    const s = await r.json();
    appendOutput(s.output || "");
    setPage(s.page || lastPage);
    setWaiting(!!s.waiting_input);
    setWorking(!!s.working);
    if (s.error) {
      statusEl.textContent = "Error: " + s.error;
    } else if (s.finished) {
      statusEl.textContent = "Terminado";
      btnStart.disabled = false;
      btnStart.textContent = "▶ Empezar de nuevo";
      btnStart.disabled = false;
    }
  } catch (e) {
    statusEl.textContent = "Sin conexión al servidor…";
  }
}

btnStart.addEventListener("click", start);
btnRestart.addEventListener("click", restartFromStart);
btnSend.addEventListener("click", sendInput);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendInput();
});

setInterval(poll, 700);
poll();
