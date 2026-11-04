// Regenerate the schema to a temp file and diff against the committed one.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "types-drift-"));
const tmp = join(dir, "schema.d.ts");
try {
  execFileSync("npx", ["openapi-typescript", "../openapi.json", "-o", tmp], { stdio: "ignore" });
  const fresh = readFileSync(tmp, "utf8");
  const committed = readFileSync("src/generated/schema.d.ts", "utf8");
  if (fresh !== committed) {
    console.error("src/generated/schema.d.ts is out of date. Run: npm run gen:types");
    process.exit(1);
  }
  console.log("types drift: clean");
} finally {
  rmSync(dir, { recursive: true, force: true });
}
