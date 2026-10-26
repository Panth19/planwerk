// Called by test_js_import.py: node js_import_runner.js <file.csv>...
// Prints one import report per file, produced by the browser importer.
const fs = require("fs");
const path = require("path");
const I = require(path.join(__dirname, "..", "web", "importer.js"));

const out = {};
for (const f of process.argv.slice(2)) {
  try {
    out[path.basename(f)] = I.readRows(I.parseCsv(fs.readFileSync(f, "utf8")));
  } catch (e) {
    out[path.basename(f)] = { error: e.message };
  }
}
process.stdout.write(JSON.stringify(out));
