const fs = require("fs");
const path = require("path");

const src = path.resolve(__dirname, "..", "..", "engine", "compilermate_engine");
const dest = path.resolve(__dirname, "..", "engine", "compilermate_engine");

if (fs.existsSync(src)) {
  fs.mkdirSync(dest, { recursive: true });
  fs.cpSync(src, dest, { recursive: true, force: true });
  console.log(`[bundle-engine] Bundled Python engine from ${src} into ${dest}`);
} else {
  console.warn(`[bundle-engine] Source engine directory not found at ${src}`);
}
