/**
 * SyopS Prep - Google Apps Script backend
 *
 * 1. Ve a https://script.google.com
 * 2. Crea o abre el proyecto vinculado a tu hoja de cálculo (Importante: el
 *    proyecto debe estar VINCULADO a la hoja, no standalone, para que funcionen
 *    el menú SyopS y el autocompletado onEdit).
 * 3. Copia este archivo en el editor (Code.gs).
 * 4. Despliega como Web App (Implementar > Nueva implementación > Aplicación web).
 * 5. Copia la URL del deployment (termina en /exec) y pegala en syops_prep.py como SHEETS_URL,
 *    o setea la variable de entorno SYOPS_SHEETS_URL.
 * 6. Configurá el secret de activación: menú SyopS > "Configurar secret de
 *    activación" (se guarda en Script Properties, NUNCA en el código).
 *
 * Hojas:
 *   - Sesiones:  una fila por sesión. Solo se registra cuando el usuario llega
 *                al diálogo de activación en la app (el menú para poner el código).
 *   - Clientes:  datos del escaneo + código. Cuando escribes un ID en la columna A,
 *                se copian automáticamente los datos desde Sesiones (CPU, RAM, espacio, etc.).
 *                El botón SyopS genera el código y lo escribe en la columna "codigo".
 *   - Errores:   errores reportados por la app.
 *
 * Menú SyopS (en la hoja de cálculo):
 *   - Generar código 1 app  -> escribe el código en la columna "codigo" de la fila activa.
 *   - Generar código 3 apps -> igual pero para 3 apps.
 *   - Autocompletar por ID  -> útil para probar/forzar la copia desde Sesiones.
 *   - Configurar secret de activación -> guarda el secret en PropertiesService.
 */

const SHEET_NAME_SESSIONS = "Sesiones";
const SHEET_NAME_CLIENTS = "Clientes";
const SHEET_NAME_ERRORS = "Errores";

const ACTIVATION_STATUS_AVAILABLE = "disponible";
const ACTIVATION_STATUS_USED = "usado";
const ACTIVATION_STATUS_OTHER_HWID = "otro_equipo";
const ACTIVATION_STATUS_EXPIRED = "expirado";
const ACTIVATION_STATUS_INVALID_SIGNATURE = "firma_invalida";

// Vida útil de un código de activación desde su generación (en minutos).
const CODE_LIFETIME_MINUTES = 8;

// Carpeta de Drive donde se guardan las proformas PDF.
const DRIVE_FOLDER_ID = "1-M_jAUWb19lOpFhZsq2JaQRe73WCBdYZ";

// El secret de activación NO se hardcodea ni se commitea: se lee de
// Script Properties (PropertiesService). Para configurarlo usá el menú
// SyopS > "Configurar secret de activación" (o Project Settings > Script
// Properties > agregar la propiedad SYOPS_ACTIVATION_SECRET).
function getActivationSecret() {
  const secret = PropertiesService.getScriptProperties().getProperty("SYOPS_ACTIVATION_SECRET");
  if (!secret) {
    throw new Error(
      "SYOPS_ACTIVATION_SECRET no está configurado. Usá el menú SyopS > 'Configurar secret de activación'."
    );
  }
  return secret;
}

// Clave de vendedor: permite acciones de administración (leer el catálogo
// completo / actualizar un link). SOLO se guarda en Script Properties
// (propiedad SYOPS_SELLER_KEY), nunca hardcodeada.
function getSellerKey() {
  const key = PropertiesService.getScriptProperties().getProperty("SYOPS_SELLER_KEY");
  if (!key) {
    throw new Error(
      "SYOPS_SELLER_KEY no está configurado. Agregalo en Project Settings > Script Properties."
    );
  }
  return key;
}

function sellerKeyOk(candidate) {
  if (!candidate) return false;
  const expected = getSellerKey();
  return String(candidate) === expected;
}

// Rate-limit simple por identificador: máximo MAX_WRITES_POR_MINUTO
// escrituras por minuto (CacheService, TTL 60s). No bloquea jamás al
// cliente real (una sesión hace pocas escrituras), sí a un spammer.
function _spamOk(sessionId, clientId) {
  const key = (clientId && clientId !== "sin_cliente")
    ? clientId : (sessionId || "anon");
  const bucket = Math.floor(Date.now() / 60000);
  const cache = CacheService.getScriptCache();
  const ck = "rw:" + key + ":" + bucket;
  const count = Number(cache.get(ck) || 0) + 1;
  cache.put(ck, String(count), 60);
  return count <= 120;
}

// ═══ UTILIDADES DE HOJAS DE CÁLCULO ═══════════════════════════════════

function isCodeExpired(createdAtValue) {
  if (!createdAtValue) return true;
  let createdAt;
  try {
    createdAt = new Date(createdAtValue);
  } catch (e) {
    return true;
  }
  if (isNaN(createdAt.getTime())) return true;
  const now = new Date();
  const diffMs = now.getTime() - createdAt.getTime();
  return diffMs > CODE_LIFETIME_MINUTES * 60 * 1000;
}

function getOrCreateSheet(name, headers) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  ensureHeaders(sheet, headers);
  return sheet;
}

function ensureHeaders(sheet, headers) {
  // Siempre escribe los encabezados en la fila 1 y los formatea.
  const firstRow = sheet.getRange(1, 1, 1, headers.length);
  firstRow.setValues([headers]);
  formatHeaders(firstRow);
  sheet.setFrozenRows(1);
  autoResizeColumns(sheet, headers.length);
}

function formatHeaders(range) {
  range.setFontWeight("bold");
  range.setFontColor("#FFFFFF");
  range.setBackground("#2a2a2a");
  range.setHorizontalAlignment("center");
  range.setVerticalAlignment("middle");
  range.setBorder(true, true, true, true, true, true, "#444444", SpreadsheetApp.BorderStyle.SOLID);
}

function autoResizeColumns(sheet, numColumns) {
  const widths = {
    "id": 140,
    "session_id": 150,
    "fecha": 160,
    "client_id": 140,
    "hwid": 140,
    "so": 180,
    "cpu": 220,
    "ram": 80,
    "disco_total": 100,
    "disco_libre": 100,
    "version": 80,
    "apps": 220,
    "type": 120,
    "estado": 120,
    "codigo": 120,
    "error": 300,
    "ultima_sesion": 160,
  };
  for (let i = 1; i <= numColumns; i++) {
    const header = sheet.getRange(1, i).getValue();
    const width = widths[String(header)] || 140;
    sheet.setColumnWidth(i, width);
  }
}

function findRowBySession(sheet, sessionId, sessionCol = 1) {
  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (data[i][sessionCol - 1] === sessionId) {
      return i + 1;
    }
  }
  return -1;
}

function getOrCreateRowBySession(sheet, sessionId, headers) {
  const row = findRowBySession(sheet, sessionId);
  if (row > 0) return row;
  // Siempre escribir después de la fila 1 (encabezados)
  const nextRow = Math.max(sheet.getLastRow(), 1) + 1;
  const emptyRow = new Array(headers.length).fill("");
  sheet.getRange(nextRow, 1, 1, headers.length).setValues([emptyRow]);
  return nextRow;
}

function now() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
}

function jsonResponse(obj, statusCode = 200) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ═══ DATOS DE SESIONES Y CLIENTES ═════════════════════════════════════

function getSessionHeaders() {
  return [
    "session_id",
    "fecha",
    "client_id",
    "hwid",
    "so",
    "cpu",
    "ram",
    "disco_total",
    "disco_libre",
    "version",
    "apps",
    "estado",
  ];
}

function getClientHeaders() {
  return [
    "id",
    "hwid",
    "so",
    "cpu",
    "ram",
    "disco_total",
    "disco_libre",
    "version",
    "apps",
    "codigo",
    "type",
    "max_apps",
    "estado",
    "fecha",
    "created_at",
    "served",
  ];
}

function getErrorHeaders() {
  return ["fecha", "session_id", "client_id", "hwid", "error"];
}

function updateSessionRow(sheet, row, data, headers) {
  const setCol = (name, value) => {
    const idx = headers.indexOf(name);
    if (idx >= 0 && value !== undefined && value !== null && value !== "") {
      sheet.getRange(row, idx + 1).setValue(value);
    }
  };

  setCol("session_id", data.session_id);
  setCol("fecha", data.fecha);
  setCol("client_id", data.client_id);
  setCol("hwid", data.hwid);
  setCol("so", data.so);
  setCol("cpu", data.cpu);
  setCol("ram", data.ram);
  setCol("disco_total", data.disco_total);
  setCol("disco_libre", data.disco_libre);
  setCol("version", data.version);
  setCol("apps", data.apps);
  setCol("estado", data.estado);
}

function findLatestSessionByClient(clientId) {
  const sheet = getOrCreateSheet(SHEET_NAME_SESSIONS, getSessionHeaders());
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const clientIdx = headers.indexOf("client_id");
  let found = null;
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][clientIdx] || "").trim().toUpperCase() === String(clientId).trim().toUpperCase()) {
      const obj = {};
      for (let j = 0; j < headers.length; j++) {
        obj[headers[j]] = data[i][j];
      }
      found = obj;
    }
  }
  return found;
}

// ═══ AUTO-COMPLETADO DE CLIENTES ══════════════════════════════════════
// Cuando escribes un ID en la columna A de la hoja "Clientes", copia los
// datos del escaneo desde "Sesiones" automáticamente.

function onEdit(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = e.range.getSheet();
  if (sheet.getName().toLowerCase() !== SHEET_NAME_CLIENTS.toLowerCase()) return;
  const col = e.range.getColumn();
  if (col !== 1) return; // solo reaccionar a la columna "id"
  const row = e.range.getRow();
  if (row === 1) return;
  let id = e.value;
  if (id === undefined || id === null || String(id).trim() === "") {
    id = sheet.getRange(row, col).getValue();
  }
  id = String(id).trim();
  if (!id) return;

  try {
    const result = autoFillClient(sheet, row, id);
    if (result.ok) {
      ss.toast("Datos copiados desde la sesión de " + id, "SyopS");
    } else {
      ss.toast(result.message, "SyopS");
    }
  } catch (err) {
    ss.toast("Error al autocompletar: " + err, "SyopS");
  }
}

function autoFillClient(sheet, row, id) {
  const session = findLatestSessionByClient(id);
  if (!session) {
    return { ok: false, message: "No se encontró una sesión para el ID: " + id };
  }
  const clientHeaders = getClientHeaders();
  const setCol = (name, value) => {
    const idx = clientHeaders.indexOf(name);
    if (idx >= 0 && value !== undefined && value !== null) {
      sheet.getRange(row, idx + 1).setValue(value);
    }
  };
  setCol("so", session.so);
  setCol("hwid", session.hwid);
  setCol("cpu", session.cpu);
  setCol("ram", session.ram);
  setCol("disco_total", session.disco_total);
  setCol("disco_libre", session.disco_libre);
  setCol("version", session.version);
  setCol("apps", session.apps);
  setCol("fecha", session.fecha || now());
  return { ok: true, id: id };
}

function autoFillByMenu() {
  const ui = SpreadsheetApp.getUi();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  if (sheet.getName().toLowerCase() !== SHEET_NAME_CLIENTS.toLowerCase()) {
    ui.alert("Usa este comando en la hoja Clientes.");
    return;
  }
  const range = sheet.getActiveRange();
  if (!range) {
    ui.alert("Selecciona una celda en la columna id.");
    return;
  }
  const row = range.getRow();
  const id = String(range.getValue() || "").trim();
  if (row === 1 || !id) {
    ui.alert("Selecciona una fila que tenga el ID en la columna A.");
    return;
  }
  const result = autoFillClient(sheet, row, id);
  if (result.ok) {
    ui.alert("OK", "Datos copiados desde la sesión de " + id, ui.ButtonSet.OK);
  } else {
    ui.alert("Aviso", result.message, ui.ButtonSet.OK);
  }
}

// ═══ VERIFICACIÓN DE CÓDIGOS (contra la hoja Clientes) ════════════════

function findClientRowByCode(code) {
  const sheet = getOrCreateSheet(SHEET_NAME_CLIENTS, getClientHeaders());
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const codeIdx = headers.indexOf("codigo");
  if (codeIdx < 0) return -1;
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][codeIdx] || "").trim().toUpperCase() === String(code).trim().toUpperCase()) {
      return i + 1;
    }
  }
  return -1;
}

// ═══ VALIDACIÓN SÍNCRONA (atómicamente, contra reuso/abuso) ═══════════════
// Todos los mutadores de activación (use_code, get_link) corren bajo un lock
// de script: dos peticiones paralelas con el mismo código se serializan, y
// ninguna puede validar "disponible" si la otra ya consumió/limitó.

function withScriptLock(fn, timeoutMs) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(timeoutMs || 15000);
  } catch (e) {
    return jsonResponse({ status: "error", message: "Demasiadas peticiones, reintentá" }, 429);
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

// Si la hoja ya existía (creada antes de agregar columnas nuevas), agrega
// los headers faltantes al final, sin tocar los datos existentes.
function ensureColumns(sheet, headers) {
  const lastCol = sheet.getLastColumn();
  for (let i = 0; i < headers.length; i++) {
    if (i < lastCol) continue;
    sheet.getRange(1, i + 1).setValue(headers[i]);
  }
}

function checkCodeAction(data) {
  const code = data.code || "";
  const hwid = String(data.hwid || "").trim().toUpperCase();
  if (!code) {
    return jsonResponse({ status: "error", message: "Falta codigo" }, 400);
  }
  const sheet = getOrCreateSheet(SHEET_NAME_CLIENTS, getClientHeaders());
  const row = findClientRowByCode(code);
  if (row < 0) {
    return jsonResponse({ status: "ok", code_status: "not_found", available: false });
  }
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const values = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
  const getValue = (name) => {
    const idx = headers.indexOf(name);
    return idx >= 0 ? String(values[idx] || "").trim().toUpperCase() : "";
  };
  const savedHwid = getValue("hwid");
  const estado = getValue("estado");
  const typeValue = getValue("type") || "standard";
  const maxAppsRaw = values[headers.indexOf("max_apps")];
  const maxApps = parseInt(maxAppsRaw, 10);
  const createdAtValue = values[headers.indexOf("created_at")] || "";
  const cidRow = getValue("id");
  const reqCid = String(data.client_id || "").trim().toUpperCase();
  // Capa 1 (llave firme): el código pertenece al Cliente ID de la fila.
  if (reqCid && cidRow && cidRow !== reqCid) {
    return jsonResponse({ status: "ok", code_status: ACTIVATION_STATUS_OTHER_HWID, available: false, type: typeValue, max_apps: isNaN(maxApps) ? 0 : maxApps });
  }
  if (!codeSignatureValid(code, cidRow, savedHwid || hwid)) {
    return jsonResponse({ status: "ok", code_status: ACTIVATION_STATUS_INVALID_SIGNATURE, available: false, type: typeValue, max_apps: isNaN(maxApps) ? 0 : maxApps });
  }
  if (isCodeExpired(createdAtValue)) {
    return jsonResponse({ status: "ok", code_status: ACTIVATION_STATUS_EXPIRED, available: false, type: typeValue, max_apps: isNaN(maxApps) ? 0 : maxApps });
  }
  if (estado === ACTIVATION_STATUS_USED.toUpperCase()) {
    return jsonResponse({ status: "ok", code_status: ACTIVATION_STATUS_USED, available: false, type: typeValue, max_apps: isNaN(maxApps) ? 0 : maxApps });
  }
  // hwid = capa 2 (informativa): si rotó respecto del guardado, NO bloquea.
  // El binding firme es el Cliente ID; el hwid actual se re-registra al usar.
  return jsonResponse({ status: "ok", code_status: ACTIVATION_STATUS_AVAILABLE, available: true, type: typeValue, max_apps: isNaN(maxApps) ? 0 : maxApps });
}

function useCodeAction(data) {
  return withScriptLock(function () {
    const code = (data.code || "").trim().toUpperCase();
    const requestHwid = String(data.hwid || "").trim().toUpperCase();
    if (!code) {
      return jsonResponse({ status: "error", message: "Falta codigo" }, 400);
    }
    const row = findClientRowByCode(code);
    if (row < 0) {
      return jsonResponse({ status: "error", message: "Codigo no encontrado", code_status: "not_found" }, 404);
    }
    const sheet = getOrCreateSheet(SHEET_NAME_CLIENTS, getClientHeaders());
    ensureColumns(sheet, getClientHeaders());
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const values = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
    const createdAtValue = values[headers.indexOf("created_at")] || "";
    // Firma HMAC primero (capa 1): un código inventado se rechaza aunque
    // exista la fila.
    const hwidIdx = headers.indexOf("hwid");
    const savedHwid = hwidIdx >= 0 ? String(values[hwidIdx] || "").trim().toUpperCase() : "";
    const cidCell = hwidIdx >= 0 ? String(values[headers.indexOf("id")] || "").trim().toUpperCase() : "";
    const reqCid = String(data.client_id || "").trim().toUpperCase();
    if (reqCid && cidCell && cidCell !== reqCid) {
      return jsonResponse({ status: "error", message: "Codigo de otro equipo", code_status: ACTIVATION_STATUS_OTHER_HWID }, 403);
    }
    if (!codeSignatureValid(code, cidCell, savedHwid || requestHwid)) {
      return jsonResponse({ status: "error", message: "Codigo invalido", code_status: ACTIVATION_STATUS_INVALID_SIGNATURE }, 403);
    }
    if (isCodeExpired(createdAtValue)) {
      return jsonResponse({ status: "error", message: "Codigo expirado", code_status: ACTIVATION_STATUS_EXPIRED }, 410);
    }
    // hwid = capa 2 (informativa): re-registra el hwid actual. La llave firme
    // es el Cliente ID (id de la fila); el uso síncrono queda dentro del lock.
    if (requestHwid) {
      if (!savedHwid || savedHwid !== requestHwid) {
        sheet.getRange(row, hwidIdx + 1).setValue(requestHwid);
      }
    }
    const estadoIdx = headers.indexOf("estado");
    if (estadoIdx >= 0) {
      sheet.getRange(row, estadoIdx + 1).setValue(ACTIVATION_STATUS_USED);
    }
    return jsonResponse({ status: "ok", code_status: ACTIVATION_STATUS_USED });
  });
}

// ═══ SUBIDA DE PROFORMAS A DRIVE ═══════════════════════════════════════
// Recibe el PDF en base64 y lo guarda en la carpeta DRIVE_FOLDER_ID.

function uploadProformaAction(data) {
  const filename = data.filename || ("PROFORMA_" + now() + ".pdf");
  const content = data.content || "";
  const clientId = data.client_id || "";
  const hwid = data.hwid || "";
  if (!content) {
    return jsonResponse({ status: "error", message: "Falta contenido" }, 400);
  }
  if (!DRIVE_FOLDER_ID) {
    return jsonResponse({ status: "error", message: "Falta DRIVE_FOLDER_ID" }, 400);
  }
  try {
    const folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);
    const blob = Utilities.newBlob(
      Utilities.base64Decode(content),
      "application/pdf",
      filename
    );
    const file = folder.createFile(blob);

    return jsonResponse({
      status: "ok",
      file_id: file.getId(),
      url: file.getUrl(),
    });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() }, 500);
  }
}

// ═══ GENERACIÓN DE CÓDIGOS DESDE SHEETS ═════════════════════════════════

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("SyopS")
    .addItem("Generar código 1 app", "generateCode1App")
    .addItem("Generar código 3 apps", "generateCode3Apps")
    .addItem("Generar código Adobe Full Pack", "generateCodeAdobeFullPack")
    .addSeparator()
    .addItem("Autocompletar por ID", "autoFillByMenu")
    .addSeparator()
    .addItem("Configurar secret de activación", "setActivationSecretMenu")
    .addItem("Resetear hojas (borrar todo)", "resetAllSheetsMenu")
    .addToUi();
}

// ═══ CONFIGURACIÓN DEL SECRET (PropertiesService) ═══════════════════════════
// El secret NO se commitea en el código: se guarda en Script Properties
// (PropertiesService) y se lee en runtime con getActivationSecret(). El
// menú permite configurarlo sin tocar el editor de código.

function setActivationSecretMenu() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    "Configurar secret de activación",
    "Pega el secret (debe coincidir con SYOPS_ACTIVATION_SECRET de la app y "
      + "del generador local). Se guardará en Script Properties.",
    ui.ButtonSet.OK_CANCEL
  );
  if (response.getSelectedButton() !== ui.Button.OK) return;
  const secret = String(response.getResponseText() || "").trim();
  if (!secret) {
    ui.alert("El secret no puede estar vacío.", ui.ButtonSet.OK);
    return;
  }
  PropertiesService.getScriptProperties().setProperty("SYOPS_ACTIVATION_SECRET", secret);
  ui.alert("Secret configurado correctamente.", ui.ButtonSet.OK);
}

function deleteActivationSecretForRotation() {
  PropertiesService.getScriptProperties().deleteProperty("SYOPS_ACTIVATION_SECRET");
}

function resetAllSheetsMenu() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.alert(
    "Resetear hojas",
    "¿Borrar TODAS las hojas (Sesiones, Clientes, Errores) y recrearlas vacías?",
    ui.ButtonSet.YES_NO
  );
  if (result === ui.Button.YES) {
    resetAllSheets();
    ui.alert("Listo", "Hojas reseteadas. Vuelve a escanear para poblar los datos.", ui.ButtonSet.OK);
  }
}

function resetAllSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  [SHEET_NAME_SESSIONS, SHEET_NAME_CLIENTS, SHEET_NAME_ERRORS].forEach(name => {
    const existing = ss.getSheetByName(name);
    if (existing) ss.deleteSheet(existing);
  });
  getOrCreateSheet(SHEET_NAME_SESSIONS, getSessionHeaders());
  getOrCreateSheet(SHEET_NAME_CLIENTS, getClientHeaders());
  getOrCreateSheet(SHEET_NAME_ERRORS, getErrorHeaders());
}

function getIsoWeek(date) {
  // Ajustar al jueves de la semana actual (ISO 8601).
  const day = (date.getDay() + 6) % 7; // 0=lunes, 6=domingo
  const thursday = new Date(date.getFullYear(), date.getMonth(), date.getDate() - day + 3);
  // El año ISO viene dado por el jueves de la semana.
  const year = thursday.getFullYear();
  // Primer jueves del año ISO.
  const jan1 = new Date(year, 0, 1);
  const jan1Day = (jan1.getDay() + 6) % 7; // 0=lunes, 6=domingo
  const firstThursday = new Date(year, 0, 1 + ((3 - jan1Day) + 7) % 7);
  // Número de semana ISO.
  const diffDays = (thursday - firstThursday) / (24 * 60 * 60 * 1000);
  const week = Math.floor(diffDays / 7) + 1;
  return { year: year, week: week };
}

function randomBytes(count) {
  const bytes = [];
  for (let i = 0; i < count; i++) {
    bytes.push(Math.floor(Math.random() * 256));
  }
  return bytes;
}

function base32Encode(bytes) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (let i = 0; i < bytes.length; i++) {
    // Forzar byte sin signo (0-255) para evitar desface entre GAS y Python.
    bits += (bytes[i] & 0xFF).toString(2).padStart(8, "0");
  }
  let encoded = "";
  for (let i = 0; i < bits.length; i += 5) {
    const chunk = bits.substr(i, 5);
    if (!chunk) break;
    const padded = chunk.length < 5 ? chunk + "0".repeat(5 - chunk.length) : chunk;
    encoded += alphabet[parseInt(padded, 2)];
  }
  return encoded;
}

function generateActivationCodeGAS(clientId, hwid, maxApps) {
  const cid = String(clientId || "").trim().toUpperCase();
  const hid = String(hwid || "").trim().toUpperCase();
  if (!cid) throw new Error("client_id vacio");
  if (!hid) throw new Error("hwid vacio");
  // Full pack usa 99 para distinguirse de los códigos normales (1 o 3).
  maxApps = Math.max(1, Math.min(parseInt(maxApps) || 3, 99));

  const { year, week } = getIsoWeek(new Date());
  const period = year + "-W" + week;
  const validDays = 7;

  const nonce = base32Encode(randomBytes(3)).slice(0, 4);
  const payload = [nonce, cid, hid, maxApps, period, validDays].join(":");
  const hmac = Utilities.computeHmacSignature(
    Utilities.MacAlgorithm.HMAC_SHA_256,
    payload,
    getActivationSecret()
  );
  const codeHash = base32Encode(hmac).slice(0, 6);

  return nonce + codeHash;
}

// Verifica la FIRMA HMAC del código (capa 1 del "doble control"). Sin el
// secret este cálculo da always false: aunque alguien escriba una fila en
// "Clientes" con un código inventado, acá se rechaza. Replica el algoritmo
// del cliente (lookback 4 semanas, max_apps 1/3/99, validez 7/30/365).
const CODE_LOOKBACK_WEEKS = 4;
function codeSignatureValid(code, cid, hid) {
  try {
    code = String(code || "").trim().toUpperCase();
    cid = String(cid || "").trim().toUpperCase();
    hid = String(hid || "").trim().toUpperCase();
    if (code.length !== 10 || !cid || !hid) return false;
    const nonce = code.slice(0, 4);
    const codeHash = code.slice(4);
    const now = new Date();
    for (let i = 0; i <= CODE_LOOKBACK_WEEKS; i++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i * 7);
      const { year, week } = getIsoWeek(d);
      const period = year + "-W" + week;
      for (const maxApps of [1, 3, 99]) {
        for (const validDays of [7, 30, 365]) {
          const payload = [nonce, cid, hid, maxApps, period, validDays].join(":");
          const hmac = Utilities.computeHmacSignature(
            Utilities.MacAlgorithm.HMAC_SHA_256,
            payload,
            getActivationSecret()
          );
          const expected = base32Encode(hmac).slice(0, 6).toUpperCase();
          if (expected === codeHash) return true;
        }
      }
    }
    return false;
  } catch (e) {
    return false;
  }
}

function generateCodeForSelectedRow(maxApps, typeValue) {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();
  if (sheet.getName().toLowerCase() !== SHEET_NAME_CLIENTS.toLowerCase()) {
    ui.alert("Genera códigos solo desde la hoja Clientes.");
    return;
  }
  const range = sheet.getActiveRange();
  if (!range) {
    ui.alert("Selecciona una fila primero.");
    return;
  }

  const row = range.getRow();
  if (row === 1) {
    ui.alert("No selecciones la fila de encabezados.");
    return;
  }

  const lastCol = Math.max(sheet.getLastColumn(), 1);
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  const values = sheet.getRange(row, 1, 1, lastCol).getValues()[0];

  const getValue = (name) => {
    const idx = headers.indexOf(name);
    return idx >= 0 ? String(values[idx] || "").trim() : "";
  };

  const clientId = getValue("id") || getValue("client_id");
  const hwid = getValue("hwid");

  if (!clientId) {
    ui.alert("La fila debe tener un valor en la columna 'id'.");
    return;
  }
  if (!hwid) {
    ui.alert("La fila debe tener un valor en la columna 'hwid'. Escribe el HWID del cliente antes de generar el código.");
    return;
  }

  try {
    const code = generateActivationCodeGAS(clientId, hwid, maxApps);

    // Escribir el código en la columna 'codigo' (debe existir en Clientes)
    const codeIdx = headers.indexOf("codigo");
    if (codeIdx < 0) {
      ui.alert("La hoja no tiene la columna 'codigo'. Usa la hoja Clientes.");
      return;
    }
    sheet.getRange(row, codeIdx + 1).setValue(code);

    // Escribir el tipo en la columna 'type' (standard / adobe_full_pack)
    const typeIdx = headers.indexOf("type");
    if (typeIdx >= 0) {
      sheet.getRange(row, typeIdx + 1).setValue(typeValue || "standard");
    }

    // Escribir la cantidad de apps permitidas en la columna 'max_apps'
    const maxAppsIdx = headers.indexOf("max_apps");
    if (maxAppsIdx >= 0) {
      sheet.getRange(row, maxAppsIdx + 1).setValue(maxApps);
    }

    // Marcar el estado como "disponible" (nuevo código, nuevo uso).
    const estadoIdx = headers.indexOf("estado");
    if (estadoIdx >= 0) {
      sheet.getRange(row, estadoIdx + 1).setValue(ACTIVATION_STATUS_AVAILABLE);
    }

    // Limpiar el historial de apps servidas: si se regenera sobre una fila
    // ya usada, el código nuevo NO debe heredar el conteo viejo (si no, el
    // primer get_link ya superaría max_apps).
    const servedIdx = headers.indexOf("served");
    if (servedIdx >= 0) {
      sheet.getRange(row, servedIdx + 1).setValue("");
    }

    // Guardar timestamp de generación para expiración.
    const createdAtIdx = headers.indexOf("created_at");
    if (createdAtIdx >= 0) {
      sheet.getRange(row, createdAtIdx + 1).setValue(now());
    }

    ui.alert(
      "Código generado",
      "Código para " + maxApps + " app(s): " + code + "\n\nVálido por " + CODE_LIFETIME_MINUTES + " minutos. Copialo y envíaselo al cliente por WhatsApp.",
      ui.ButtonSet.OK
    );
  } catch (err) {
    ui.alert("Error: " + err.toString());
  }
}

function generateCode1App() {
  generateCodeForSelectedRow(1, "standard");
}

function generateCode3Apps() {
  generateCodeForSelectedRow(3, "standard");
}

function generateCodeAdobeFullPack() {
  generateCodeForSelectedRow(99, "adobe_full_pack");
}

// ═══ LINKS DE DESCARGA (Tier 1.5: catálogo en Sheets, sin URLs en el cliente) ═
// El wizard pide el link de una app con action=get_link; el script valida el
// código contra la hoja "Clientes" y devuelve la URL de la hoja "Links".
// Columnas de "Links": nombre | metodo | plataforma | url | resolver
//   - nombre:     nombre exacto de la app o tool (ej. "Blender", "Photoshop", "Sentinel")
//   - metodo:     método Adobe (ej. "aio_macked") o VACÍO para apps/tools normales
//   - plataforma: "mac" o "win"
//   - url:        la URL a descargar (se puede editar a mano en la hoja)
//   - resolver:   (opcional) qué resolver usará el cliente para esa URL:
//                 akirabox | swisstransfer | workupload | pixeldrain |
//                 seyarabata | appstorrent. Vacío = descarga directa.

const SHEET_NAME_LINKS = "Links";

function getLinkHeaders() {
  // "categoria" va SIEMPRE al final: ensureHeaders reescribe la fila 1 con
  // este array, y si se insertara un header en medio movería los datos de
  // las columnas existentes (corrupción de la hoja).
  return ["nombre", "metodo", "plataforma", "url", "resolver", "categoria"];
}

function findLinkEntry(name, method, platform) {
  const sheet = getOrCreateSheet(SHEET_NAME_LINKS, getLinkHeaders());
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const nameIdx = headers.indexOf("nombre");
  const methodIdx = headers.indexOf("metodo");
  const platIdx = headers.indexOf("plataforma");
  const urlIdx = headers.indexOf("url");
  const resIdx = headers.indexOf("resolver");
  const catIdx = headers.indexOf("categoria");
  const wantName = String(name || "").trim();
  const wantPlat = String(platform || "").trim().toLowerCase();
  const wantMethod = String(method || "").trim();
  for (let i = 1; i < data.length; i++) {
    const rowName = String(data[i][nameIdx] || "").trim();
    const rowMethod = String(data[i][methodIdx] || "").trim();
    const rowPlat = String(data[i][platIdx] || "").trim().toLowerCase();
    if (rowName === wantName &&
        rowPlat === wantPlat &&
        (rowMethod === "" || rowMethod === wantMethod)) {
      return {
        url: String(data[i][urlIdx] || "").trim(),
        resolver: resIdx >= 0 ? String(data[i][resIdx] || "").trim() : "",
        categoria: catIdx >= 0 ? String(data[i][catIdx] || "").trim() : "",
      };
    }
  }
  return null;
}

function getLinkAction(data) {
  return withScriptLock(function () {
    const code = String(data.code || "").trim().toUpperCase();
    const hwid = String(data.hwid || "").trim().toUpperCase();
    const name = String(data.name || data.app || "").trim();
    const method = String(data.method || "").trim();
    const platform = String(data.platform || "").trim();
    if (!code || !name) {
      return jsonResponse({ status: "error", message: "Faltan code o name" }, 400);
    }

    // Misma autoridad que check_code: validar el código contra "Clientes".
    const row = findClientRowByCode(code);
    if (row < 0) {
      return jsonResponse({ status: "error", message: "Codigo no encontrado" }, 404);
    }
    const sheet = getOrCreateSheet(SHEET_NAME_CLIENTS, getClientHeaders());
    ensureColumns(sheet, getClientHeaders());
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const values = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
    const getValue = (n) => {
      const i = headers.indexOf(n);
      return i >= 0 ? String(values[i] || "").trim().toUpperCase() : "";
    };
    const savedHwid = getValue("hwid");
    const estado = getValue("estado");
    const createdAtValue = values[headers.indexOf("created_at")] || "";
    // Firma HMAC primero (capa 1): rechaza códigos inventados aunque existan
    // en la hoja.
    if (!codeSignatureValid(code, getValue("id"), savedHwid || hwid)) {
      return jsonResponse({ status: "error", message: "Codigo invalido" }, 403);
    }
    if (isCodeExpired(createdAtValue)) {
      return jsonResponse({ status: "error", message: "Codigo expirado" }, 410);
    }
    if (estado === ACTIVATION_STATUS_USED.toUpperCase()) {
      return jsonResponse({ status: "error", message: "Codigo usado" }, 410);
    }

    // Capa 1 (llave firme): el código pertenece al Cliente ID de la fila.
    const cidLink = getValue("id");
    const reqCidLink = String(data.client_id || "").trim().toUpperCase();
    if (reqCidLink && cidLink && cidLink !== reqCidLink) {
      return jsonResponse({ status: "error", message: "Codigo de otro equipo" }, 403);
    }

    // hwid = capa 2 (informativa): si rotó, se re-registra en vez de bloquear.
    const hwidIdx = headers.indexOf("hwid");
    if (hwid) {
      if (!savedHwid || savedHwid !== hwid) {
        sheet.getRange(row, hwidIdx + 1).setValue(hwid);
      }
    }

    // Conteo server-side contra max_apps (síncrono: dentro del mismo lock).
    const kind = String(data.kind || "").trim().toLowerCase();
    // Las herramientas de instalación (kind="tool") NO consumen slots de apps.
    const isTool = kind === "tool";
    const maxAppsRaw = values[headers.indexOf("max_apps")];
    const maxApps = parseInt(maxAppsRaw, 10);
    let servedNames = [];
    const servedRaw = values[headers.indexOf("served")] || "";
    if (servedRaw !== "") {
      try { servedNames = JSON.parse(servedRaw); } catch (e) { servedNames = []; }
      if (!Array.isArray(servedNames)) servedNames = [];
    }
    const nameKey = name.toUpperCase();
    const alreadyServed = servedNames.indexOf(nameKey) >= 0;
    if (!isTool && !isNaN(maxApps) && maxApps >= 1 && !alreadyServed && servedNames.length >= maxApps) {
      return jsonResponse({ status: "error", message: "Limite de apps alcanzado" }, 423);
    }
    if (!alreadyServed && !isTool) {
      servedNames.push(nameKey);
      sheet.getRange(row, headers.indexOf("served") + 1).setValue(JSON.stringify(servedNames));
    }

    const entry = findLinkEntry(name, method, platform);
    if (!entry || !entry.url) {
      return jsonResponse({ status: "error", message: "Sin link para " + name }, 404);
    }
    const response = { status: "ok", url: entry.url, name: name };
    if (entry.resolver) {
      response.resolver = entry.resolver;
    }
    if (entry.categoria) {
      response.categoria = entry.categoria;
    }
    return jsonResponse(response);
  });
}

// `get_links_meta`: dev solo. Valida el código igual que `get_link` (capa
// HMAC + expiración + estado + cliente) pero NO expone URLs. Devuelve el
// catálogo mínimo para desarrollo/pruebas: nombre, método, plataforma,
// resolver (sin la columna url).
function getLinksMetaAction(data) {
  return withScriptLock(function () {
    const code = String(data.code || "").trim().toUpperCase();
    const hwid = String(data.hwid || "").trim().toUpperCase();
    if (!code) {
      return jsonResponse({ status: "error", message: "Falta code" }, 400);
    }
    const row = findClientRowByCode(code);
    if (row < 0) {
      return jsonResponse({ status: "error", message: "Codigo no encontrado" }, 404);
    }
    const sheet = getOrCreateSheet(SHEET_NAME_CLIENTS, getClientHeaders());
    ensureColumns(sheet, getClientHeaders());
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const values = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
    const getValue = (n) => {
      const i = headers.indexOf(n);
      return i >= 0 ? String(values[i] || "").trim().toUpperCase() : "";
    };
    const savedHwid = getValue("hwid");
    if (!codeSignatureValid(code, getValue("id"), savedHwid || hwid)) {
      return jsonResponse({ status: "error", message: "Codigo invalido" }, 403);
    }
    if (isCodeExpired(values[headers.indexOf("created_at")] || "")) {
      return jsonResponse({ status: "error", message: "Codigo expirado" }, 410);
    }
    if (getValue("estado") === ACTIVATION_STATUS_USED.toUpperCase()) {
      return jsonResponse({ status: "error", message: "Codigo usado" }, 410);
    }
    const cid = getValue("id");
    const reqCid = String(data.client_id || "").trim().toUpperCase();
    if (reqCid && cid && cid !== reqCid) {
      return jsonResponse({ status: "error", message: "Codigo de otro equipo" }, 403);
    }

    const linksSheet = getOrCreateSheet(SHEET_NAME_LINKS, getLinkHeaders());
    const ldata = linksSheet.getDataRange().getValues();
    const lheaders = ldata[0];
    const meta = [];
    for (let i = 1; i < ldata.length; i++) {
      const rowVals = ldata[i];
      const getL = (n) => {
        const j = lheaders.indexOf(n);
        return j >= 0 ? String(rowVals[j] || "").trim() : "";
      };
      if (!getL("url")) continue;
      meta.push({
        nombre: getL("nombre"),
        metodo: getL("metodo"),
        plataforma: getL("plataforma"),
        resolver: getL("resolver"),
        categoria: getL("categoria"),
      });
    }
    return jsonResponse({ status: "ok", links: meta });
  });
}

// `get_catalog_index`: índice público PRE-activación para armar el árbol de
// categorías del wizard. Devuelve SOLO nombre/categoria/plataforma — sin url
// ni resolver: los links reales se entregan únicamente por get_link (con el
// código validado). No requiere clave.
function getCatalogIndexAction(data) {
  const linksSheet = getOrCreateSheet(SHEET_NAME_LINKS, getLinkHeaders());
  const ldata = linksSheet.getDataRange().getValues();
  const lheaders = ldata[0];
  const nameIdx = lheaders.indexOf("nombre");
  const catIdx = lheaders.indexOf("categoria");
  const platIdx = lheaders.indexOf("plataforma");
  const urlIdx = lheaders.indexOf("url");
  const seen = {};
  const rows = [];
  for (let i = 1; i < ldata.length; i++) {
    const rowVals = ldata[i];
    const nombre = String(rowVals[nameIdx] || "").trim();
    const plataforma = String(rowVals[platIdx] || "").trim().toLowerCase();
    const url = String(rowVals[urlIdx] || "").trim();
    if (!nombre || !url) continue;
    const categoria = catIdx >= 0 ? String(rowVals[catIdx] || "").trim() : "";
    const key = nombre + "|" + plataforma;
    if (seen[key]) continue;
    seen[key] = true;
    rows.push({ nombre: nombre, plataforma: plataforma, categoria: categoria });
  }
  return jsonResponse({ status: "ok", items: rows });
}

// `get_links_seller`: catálogo completo SOLO con clave de vendedor.
// Reutiliza el mismo formato que la hoja Links (url incluida).
function getLinksSellerAction(data) {
  if (!sellerKeyOk(data.key)) {
    return jsonResponse({ status: "error", message: "Clave de vendedor inválida" }, 403);
  }
  const linksSheet = getOrCreateSheet(SHEET_NAME_LINKS, getLinkHeaders());
  const ldata = linksSheet.getDataRange().getValues();
  const lheaders = ldata[0];
  const rows = [];
  for (let i = 1; i < ldata.length; i++) {
    const rowVals = ldata[i];
    const row = {};
    for (let j = 0; j < lheaders.length; j++) {
      row[lheaders[j]] = String(rowVals[j] !== undefined ? rowVals[j] : "").trim();
    }
    if (!row.nombre && !row.url) continue;
    rows.push(row);
  }
  return jsonResponse({ status: "ok", links: rows });
}

// `update_link`: el vendedor actualiza url/resolver de una fila del catálogo
// (renovación). Busca por nombre + plataforma (+ método opcional) y setea las
// columnas url y resolver (y el nombre si viene).
function updateLinkAction(data) {
  return withScriptLock(function () {
    if (!sellerKeyOk(data.key)) {
      return jsonResponse({ status: "error", message: "Clave de vendedor inválida" }, 403);
    }
    const nombre = String(data.nombre || "").trim();
    const plataforma = String(data.plataforma || "").trim().toLowerCase();
    const metodo = String(data.method || data.metodo || "").trim();
    const url = String(data.url || "").trim();
    if (!nombre || !plataforma) {
      return jsonResponse({ status: "error", message: "Faltan nombre o plataforma" }, 400);
    }

    const sheet = getOrCreateSheet(SHEET_NAME_LINKS, getLinkHeaders());
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const data_ = sheet.getDataRange().getValues();
    const nameIdx = headers.indexOf("nombre");
    const platIdx = headers.indexOf("plataforma");
    const methodIdx = headers.indexOf("metodo");
    const urlIdx = headers.indexOf("url");
    const resIdx = headers.indexOf("resolver");
    let rowIdx = -1;
    for (let i = 1; i < data_.length; i++) {
      const rName = String(data_[i][nameIdx] || "").trim();
      const rPlat = String(data_[i][platIdx] || "").trim().toLowerCase();
      const rMethod = String(data_[i][methodIdx] || "").trim();
      if (rName === nombre && rPlat === plataforma &&
          (!metodo || rMethod === metodo)) {
        rowIdx = i;
        break;
      }
    }
    if (rowIdx < 0) {
      return jsonResponse({ status: "error", message: "Fila no encontrada: " + nombre + " / " + plataforma }, 404);
    }
    const updates = {};
    if (url) updates[urlIdx] = url;
    if (data.resolver) updates[resIdx] = data.resolver;
    const range = sheet.getRange(rowIdx + 1, 1, 1, sheet.getLastColumn());
    const values = range.getValues()[0].slice();
    for (const colIdx in updates) {
      if (updates.hasOwnProperty(colIdx)) {
        values[colIdx] = updates[colIdx];
      }
    }
    range.setValues([values]);
    return jsonResponse({ status: "ok", url: url || undefined });
  });
}

// ═══ DECODIFICACIÓN DE PETICIONES (POST O GET fallback) ═══════════════════

function getRequestData(e) {
  /**
   * Intenta obtener los datos de la petición.
   * - POST: cuerpo JSON en e.postData.contents.
   * - GET: parámetro `payload` con el JSON codificado.
   */
  if (e.postData && e.postData.contents) {
    try {
      return JSON.parse(e.postData.contents);
    } catch (err) {
      return null;
    }
  }
  const payload = e.parameter && (e.parameter.payload || e.parameter.json);
  if (payload) {
    try {
      return JSON.parse(payload);
    } catch (err) {
      return null;
    }
  }
  return null;
}

function handleDataAction(data, sessionsSheet, errorsSheet) {
  /**
   * Procesa las acciones de escritura: use_code, upload_proforma, session,
   * update, new_service y error. Usado tanto por doPost como por doGet.
   */
  const action = data.action || "";
  const sessionId = data.session_id || "sin_sesion";
  const clientId = data.client_id || "sin_cliente";
  const hwid = data.hwid || "";
  const sessionHeaders = getSessionHeaders();

  // ── Fase 5: validación anti-spam de escrituras ─────────────────
  // Los endpoints de escritura aceptan cualquier POST sin auth: cualquiera
  // podría ensuciar la hoja. Validamos identificadores de formato del cliente
  // (client_id/hwid = md5 hex[:12].upper()) y limitamos escrituras por minuto.
  const HEX_RE = /^[0-9A-Fa-f]{6,32}$/;
  const SESSION_RE = /^[A-Za-z0-9_\-:.]{1,64}$/;
  if (clientId === "sin_cliente" && sessionId === "sin_sesion") {
    return jsonResponse({ status: "error", message: "Faltan identificadores" }, 400);
  }
  if (clientId !== "sin_cliente" && !HEX_RE.test(clientId)) {
    return jsonResponse({ status: "error", message: "client_id inválido" }, 400);
  }
  if (hwid && !HEX_RE.test(hwid)) {
    return jsonResponse({ status: "error", message: "hwid inválido" }, 400);
  }
  if (!SESSION_RE.test(sessionId)) {
    return jsonResponse({ status: "error", message: "session_id inválido" }, 400);
  }
  if (!_spamOk(sessionId, clientId)) {
    return jsonResponse({ status: "error", message: "Demasiados intentos, esperá un minuto" }, 429);
  }

  if (action === "use_code") {
    return useCodeAction(data);
  }

  if (action === "get_link") {
    return getLinkAction(data);
  }

  // "update_link": el vendedor reemplaza url/resolver de una fila del
  // catálogo (renovación sin pegar CSV). Requiere la clave de vendedor.
  if (action === "update_link") {
    return updateLinkAction(data);
  }

  if (action === "upload_proforma") {
    return uploadProformaAction(data);
  }

  // "session": se registra SOLO cuando el usuario llega al diálogo de activación.
  if (action === "session") {
    const row = getOrCreateRowBySession(sessionsSheet, sessionId, sessionHeaders);
    updateSessionRow(sessionsSheet, row, data, sessionHeaders);
    return jsonResponse({ status: "ok" });
  }

  // "update" / "new_service": actualizan una sesión; si no existe (p. ej. la
  // selección confirmada antes de activar), la crean para no perder el dato.
  if (action === "update" || action === "new_service") {
    const row = getOrCreateRowBySession(sessionsSheet, sessionId, sessionHeaders);
    const extra = action === "new_service" ? { estado: "nuevo servicio" } : {};
    updateSessionRow(sessionsSheet, row, { ...data, ...extra }, sessionHeaders);
    return jsonResponse({ status: "ok" });
  }

  if (action === "error") {
    errorsSheet.appendRow([
      now(),
      sessionId,
      clientId,
      hwid,
      data.error || "",
    ]);
    return jsonResponse({ status: "ok" });
  }

  return null; // acción no reconocida como escritura
}

// ═══ ENDPOINTS PRINCIPALES ══════════════════════════════════════════════

function doPost(e) {
  const data = getRequestData(e);
  if (!data) {
    return jsonResponse({ status: "error", message: "JSON invalido o vacio" }, 400);
  }

  const sessionHeaders = getSessionHeaders();
  const sessionsSheet = getOrCreateSheet(SHEET_NAME_SESSIONS, sessionHeaders);
  const errorsSheet = getOrCreateSheet(SHEET_NAME_ERRORS, getErrorHeaders());

  try {
    const result = handleDataAction(data, sessionsSheet, errorsSheet);
    if (result) return result;
    return jsonResponse({ status: "error", message: "Accion desconocida: " + (data.action || "") }, 400);
  } catch (err) {
    errorsSheet.appendRow([now(), data.session_id || "sin_sesion", data.client_id || "sin_cliente", data.hwid || "", err.toString()]);
    return jsonResponse({ status: "error", message: err.toString() }, 500);
  }
}

function doGet(e) {
  const action = e.parameter.action || "";

  // Acciones de solo lectura (conservan compatibilidad hacia atrás).
  if (action === "check_code") {
    return checkCodeAction(e.parameter);
  }
  if (action === "get_link") {
    return getLinkAction(e.parameter);
  }
  // `get_links_meta`: SOLO para desarrollo. Igual de restringido que `get_link`
  // (código válido + firma HMAC + no expirado + no usado), y devuelve SOLO el
  // catálogo (nombre/método/plataforma/resolver) SIN la columna `url`: los
  // enlaces reales jamás se entregan en bloque.
  if (action === "get_links_meta") {
    return getLinksMetaAction(e.parameter);
  }

  // `get_catalog_index`: índice público PRE-activación para armar el árbol
  // de categorías del wizard. Devuelve SOLO nombre/categoria/plataforma
  // (sin url ni resolver: los links se entregan únicamente por get_link).
  if (action === "get_catalog_index") {
    return getCatalogIndexAction(e.parameter);
  }

  // `get_links_seller`: SOLO el vendedor (clave). Devuelve el catálogo
  // COMPLETO (incluye URLs) para el check de salud / renovación. La clave
  // vive en Script Properties (SYOPS_SELLER_KEY): sin ella, error 403.
  if (action === "get_links_seller") {
    return getLinksSellerAction(e.parameter);
  }

  // Fallback GET: si el despliegue del script no acepta POST, la app puede
  // enviar las acciones de escritura mediante el parámetro `payload`.
  const data = getRequestData(e);
  if (data) {
    const sessionHeaders = getSessionHeaders();
    const sessionsSheet = getOrCreateSheet(SHEET_NAME_SESSIONS, sessionHeaders);
    const errorsSheet = getOrCreateSheet(SHEET_NAME_ERRORS, getErrorHeaders());
    try {
      const result = handleDataAction(data, sessionsSheet, errorsSheet);
      if (result) return result;
    } catch (err) {
      errorsSheet.appendRow([now(), data.session_id || "sin_sesion", data.client_id || "sin_cliente", data.hwid || "", err.toString()]);
      return jsonResponse({ status: "error", message: err.toString() }, 500);
    }
  }

  return jsonResponse({ status: "error", message: "Accion GET desconocida" }, 400);
}
