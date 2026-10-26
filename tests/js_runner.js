// Called by test_js_parity.py: node js_runner.js <case.json> <scenarios.json>
// Prints {name: {result, fit}} computed by the browser engine.
const fs = require("fs");
const path = require("path");
const P = require(path.join(__dirname, "..", "web", "engine.js"));

const kase = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const scenarios = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = {};
for (const [name, changes] of Object.entries(scenarios)) {
  const scheme = Object.assign({}, kase.scheme, changes);
  out[name] = {
    result: P.calculate(kase.employees, scheme),
    fit: P.fitBudget(kase.employees, scheme, 6000000),
  };
}
process.stdout.write(JSON.stringify(out));
