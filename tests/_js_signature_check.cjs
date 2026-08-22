// Helper para tests: ejecuta `codeSignatureValid` REAL del google_apps_script.js
// en Node (con stubs mínimos), para verificar que la firma que produce Python
// coincide con la que valida el Apps Script desplegado.
//
// Uso:
//   node _js_signature_check.cjs <ruta-google_apps_script.js> <secret> <code> <cid> <hid>
// Imprime VALID o INVALID (exit 0 en ambos casos).
"use strict";

const fs = require("fs");
const crypto = require("crypto");

const jsPath = process.argv[2];
const secret = process.argv[3];
const code = process.argv[4];
const cid = process.argv[5];
const hid = process.argv[6];

const src = fs.readFileSync(jsPath, "utf8");

// Copia del cuerpo de una función del archivo, respetando llaves anidadas.
function grabFunction(name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error("no se encontró function " + name);
  const open = src.indexOf("{", start);
  let depth = 0;
  let i = open;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) {
        i++;
        break;
      }
    }
  }
  return src.slice(start, i);
}

globalThis.getActivationSecret = () => secret;
globalThis.Utilities = {
  MacAlgorithm: { HMAC_SHA_256: 1 },
  computeHmacSignature: (algo, payload, key) =>
    Array.from(crypto.createHmac("sha256", key).update(payload, "utf8").digest()),
};
function loadFunction(name, source) {
  const fn = (0, eval)("(" + source + ")");
  globalThis[name] = fn;
  return fn;
}
loadFunction("getIsoWeek", grabFunction("getIsoWeek"));
loadFunction("base32Encode", grabFunction("base32Encode"));
loadFunction("codeSignatureValid", grabFunction("codeSignatureValid").replace(/CODE_LOOKBACK_WEEKS/g, "4"));

console.log(codeSignatureValid(code, cid, hid) ? "VALID" : "INVALID");