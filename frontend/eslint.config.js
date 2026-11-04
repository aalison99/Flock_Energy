import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * Layer map (src/):
 *   app -> routes, features (index only), shared, lib
 *   routes -> features (index only), shared
 *   features/<name> -> itself, other features' index only, shared, generated, lib/api-error;
 *                      lib/api-client only from api.ts (the single HTTP caller)
 *   shared -> shared, generated;  lib -> generated
 */
export const boundariesSettings = {
  // Lets the plugin resolve extensionless TypeScript imports.
  "import/resolver": { node: { extensions: [".ts", ".tsx", ".js"] } },
  "boundaries/elements": [
    { type: "app", pattern: "src/app/**", partialMatch: false },
    { type: "routes", pattern: "src/routes/**", partialMatch: false },
    { type: "feature", pattern: "src/features/*/**", partialMatch: false, capture: ["name"] },
    { type: "shared", pattern: "src/shared/**", partialMatch: false },
    { type: "lib", pattern: "src/lib/**", partialMatch: false },
    { type: "generated", pattern: "src/generated/**", partialMatch: false },
  ],
  "boundaries/files": [
    { pattern: "src/features/*/index.ts", category: "public" },
    { pattern: "src/features/*/api.ts", category: "api" },
    { pattern: "src/lib/api-client.ts", category: "http-client" },
  ],
  "boundaries/ignore": ["src/test/**", "src/main.tsx", "**/*.test.ts", "**/*.test.tsx", "src/vite-env.d.ts"],
};

export const boundariesRules = {
  "boundaries/dependencies": [
    "error",
    {
      default: "disallow",
      policies: [
        { from: { element: { type: "app" } }, allow: { to: { element: { types: ["app", "routes", "shared", "lib"] } } } },
        { from: { element: { type: "app" } }, allow: { to: { element: { type: "feature" }, file: { categories: "public" } } } },
        { from: { element: { type: "routes" } }, allow: { to: { element: { types: ["routes", "shared"] } } } },
        { from: { element: { type: "routes" } }, allow: { to: { element: { type: "feature" }, file: { categories: "public" } } } },
        {
          from: { element: { type: "feature" } },
          allow: { to: { element: { type: "feature", captured: { name: "{{ from.element.captured.name }}" } } } },
        },
        { from: { element: { type: "feature" } }, allow: { to: { element: { types: ["shared", "generated"] } } } },
        { from: { element: { type: "feature" } }, allow: { to: { element: { type: "feature" }, file: { categories: "public" } } } },
        { from: { element: { type: "feature" } }, allow: { to: { element: { type: "lib" } } } },
        { from: { element: { type: "feature" } }, disallow: { to: { file: { categories: "http-client" } } } },
        { from: { element: { type: "feature" }, file: { categories: "api" } }, allow: { to: { file: { categories: "http-client" } } } },
        { from: { element: { type: "shared" } }, allow: { to: { element: { types: ["shared", "generated"] } } } },
        { from: { element: { type: "lib" } }, allow: { to: { element: { types: ["lib", "generated"] } } } },
      ],
    },
  ],
};

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/generated", "src/test/fixtures"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks, boundaries },
    settings: boundariesSettings,
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      ...boundariesRules,
    },
  },
  { files: ["scripts/**/*.mjs", "*.config.{js,ts}"], languageOptions: { globals: { ...globals.node } } },
);
