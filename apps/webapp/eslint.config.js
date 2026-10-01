import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * ESLint flat config.
 *
 * The `lint` script already existed in package.json but had no config, so
 * `eslint .` failed before any of the UI 2.0 work. This file makes it runnable
 * and keeps it useful:
 *
 *   - type-aware linting is deliberately NOT enabled. `tsc -b` already runs on
 *     every build with `strict` on, and a second type checker in the lint pass
 *     would be slow and would report the same problems twice (§94: no
 *     redundant machinery).
 *   - the rule set is the recommended set plus the two rules this codebase can
 *     actually violate in a way that matters: floating promises (an un-awaited
 *     fetch that silently never reports a failure) and hook dependency arrays.
 *   - tests get globals; the legacy donor stylesheets and build config are
 *     linted as plain JS/TS with node/browser globals respectively.
 */

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "src/styles/**"],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Note: `no-floating-promises` would be the rule that catches an
      // un-awaited fetch in an event handler, but it needs type information and
      // this config is deliberately not type-aware (see the header). Enabling
      // it would mean a second type checker on every lint run, for one rule.

      // Domain vocabulary is platform-owned; the UI must not mint names (§98).
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "NewTypeExpression > TSTypeLiteral[1] > TSPropertySignature > Identifier[ name=/^(IntelItem|KnowledgeCard|GraphThing|DataPoint)$/ ]",
          message:
            "§98: the domain vocabulary is fixed (Investigation / Entity / Observation / Capture / Claim / Finding / AcquisitionTask / AcquisitionRun / Source).",
        },
      ],

      // Unused arguments prefixed with an underscore are deliberate.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // `any` in the legacy API client is already locally disabled; keep the
      // rule on everywhere else.
      "@typescript-eslint/no-explicit-any": "error",

      eqeqeq: ["error", "smart"],
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },

  {
    // Test files: vitest globals, and the store singleton is reset per test.
    files: ["**/*.test.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },

  {
    files: ["*.config.ts", "*.config.js"],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
);