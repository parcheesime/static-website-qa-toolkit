import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "**/node_modules/**", "**/.git/**", "**/reports/**", "**/dist/**",
      "**/build/**", "**/_site/**", "**/coverage/**", "**/vendor/**",
      "**/generated/**", "**/*.min.js",
    ],
  },
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        dataLayer: "writable",
        gtag: "readonly",
      },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-constant-condition": ["error", { checkLoops: false }],
      "no-undef": "error",
      "no-unreachable": "error",
      "no-dupe-keys": "error",
      "no-dupe-args": "error",
      "valid-typeof": "error",
      "no-func-assign": "error",
      "no-import-assign": "error",
    },
  },
];
