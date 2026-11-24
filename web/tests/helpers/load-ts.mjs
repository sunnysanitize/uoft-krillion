import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
const modules = new Map();

// Use the project's existing TypeScript compiler to test the actual modules in Node.
export function loadTs(url) {
  const filename = url instanceof URL ? fileURLToPath(url) : url;
  if (modules.has(filename)) return modules.get(filename).exports;
  const module = { exports: {} };
  modules.set(filename, module);
  const { outputText } = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  const localRequire = (name) => name.startsWith(".") ? loadTs(resolve(dirname(filename), name + ".ts")) : require(name);
  runInThisContext(`(function(require, module, exports) {${outputText}\n})`, { filename })(localRequire, module, module.exports);
  return module.exports;
}
