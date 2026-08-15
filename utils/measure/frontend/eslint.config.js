import js from '@eslint/js';
import babelParser from '@babel/eslint-parser';
import lit from 'eslint-plugin-lit';
import wc from 'eslint-plugin-wc';
import globals from 'globals';

// The parser is Babel rather than typescript-eslint: typescript-eslint hard-refuses
// to load against the TypeScript 7 compiler this project uses. Type-aware rules are
// therefore unavailable here; `tsc --noEmit` remains the type checker.
export default [
  {
    ignores: ['dist/**', 'test-results/**'],
  },
  js.configs.recommended,
  lit.configs['flat/recommended'],
  wc.configs['flat/recommended'],
  {
    files: ['**/*.ts'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
      parser: babelParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          presets: ['@babel/preset-typescript'],
          plugins: [['@babel/plugin-proposal-decorators', { version: 'legacy' }]],
        },
      },
    },
    rules: {
      // Babel strips types before ESLint sees the AST, so both rules misfire on
      // type-only imports and declared globals. tsc covers them (noUnusedLocals,
      // noUnusedParameters) with full type information.
      'no-unused-vars': 'off',
      'no-undef': 'off',

      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'prefer-const': 'error',
      'no-var': 'error',
      'object-shorthand': 'error',

      'lit/lifecycle-super': 'error',
      'lit/no-classfield-shadowing': 'error',
      'lit/no-invalid-escape-sequences': 'error',
      'lit/no-legacy-imports': 'error',
      'lit/no-native-attributes': 'error',
      'lit/no-this-assign-in-render': 'error',
      'lit/no-useless-template-literals': 'error',
      'lit/prefer-nothing': 'error',
      'lit/prefer-static-styles': 'error',
      'lit/value-after-constraints': 'error',

      // wc/guard-super-call is deliberately off: it exists for elements extending
      // HTMLElement directly, and every component here extends LitElement, which
      // does implement connectedCallback/disconnectedCallback.
      'wc/no-constructor-params': 'error',
      'wc/no-typos': 'error',
      'wc/require-listener-teardown': 'error',
    },
  },
  {
    files: ['**/*.test.ts', 'src/components/test-fixtures.ts'],
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      'no-console': 'off',
    },
  },
];
