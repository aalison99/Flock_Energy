import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- plain JS ESLint config, no type declarations
import { boundariesRules, boundariesSettings } from "../../eslint.config.js";
import boundaries from "eslint-plugin-boundaries";
import tseslint from "typescript-eslint";

const eslint = new ESLint({
  cwd: process.cwd(),
  overrideConfigFile: true,
  overrideConfig: [
    {
      files: ["**/*.ts", "**/*.tsx"],
      languageOptions: { parser: tseslint.parser },
      plugins: { boundaries },
      settings: boundariesSettings,
      rules: boundariesRules,
    },
  ],
});

async function lint(filePath: string, code: string) {
  const [result] = await eslint.lintText(code, { filePath });
  return result?.messages ?? [];
}

describe("import boundaries (planted violations must fail lint)", () => {
  it("rejects a route deep-importing a feature internal", async () => {
    const msgs = await lint("src/routes/Planted.tsx", `import { MeterTable } from "../features/meters/MeterTable";\nexport const x = MeterTable;\n`);
    expect(msgs.some((m) => m.ruleId === "boundaries/dependencies")).toBe(true);
  });

  it("rejects one feature deep-importing another", async () => {
    const msgs = await lint("src/features/readings/Planted.tsx", `import { useMeter } from "../meters/hooks";\nexport const x = useMeter;\n`);
    expect(msgs.some((m) => m.ruleId === "boundaries/dependencies")).toBe(true);
  });

  it("rejects a component importing the api client directly", async () => {
    const msgs = await lint("src/features/meters/Planted.tsx", `import { client } from "../../lib/api-client";\nexport const x = client;\n`);
    expect(msgs.some((m) => m.ruleId === "boundaries/dependencies")).toBe(true);
  });

  it("rejects a route importing lib directly", async () => {
    const msgs = await lint("src/routes/Planted2.tsx", `import { client } from "../lib/api-client";\nexport const x = client;\n`);
    expect(msgs.some((m) => m.ruleId === "boundaries/dependencies")).toBe(true);
  });

  it("allows the legal imports", async () => {
    expect(await lint("src/routes/Ok.tsx", `import { MetersExplorer } from "../features/meters";\nexport const x = MetersExplorer;\n`)).toEqual([]);
    expect(await lint("src/features/meters/api.ts", `import { client } from "../../lib/api-client";\nexport const x = client;\n`)).toEqual([]);
    expect(await lint("src/features/meters/Ok.tsx", `import { useMeters } from "./hooks";\nexport const x = useMeters;\n`)).toEqual([]);
  });
});
