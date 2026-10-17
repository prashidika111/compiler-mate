// Setup mock for 'vscode' module so integration tests can execute in pure Node.js environments
const Module = require("module");
const originalRequire = Module.prototype.require;
(global as any).__COMPILERMATE_MOCK_CONFIG__ = {};
Module.prototype.require = function (id: string) {
  if (id === "vscode") {
    return {
      workspace: {
        getConfiguration: (section?: string) => ({
          get: (key: string, defVal: any) => {
            const store = (global as any).__COMPILERMATE_MOCK_CONFIG__ || {};
            const fullKey = section ? `${section}.${key}` : key;
            if (store[fullKey] !== undefined) return store[fullKey];
            if (store[key] !== undefined) return store[key];
            return defVal;
          },
        }),
        workspaceFolders: [
          { uri: { fsPath: require("path").resolve(__dirname, "..", "..", "..", "..") } }
        ],
      },
      extensions: {
        getExtension: () => undefined,
      },
      window: {
        createOutputChannel: (_name: string) => ({
          append: () => {},
          appendLine: () => {},
          clear: () => {},
          show: () => {},
          hide: () => {},
          dispose: () => {},
          replace: () => {},
        }),
        createWebviewPanel: (_id: string, _title: string, _col: any, _options?: any) => {
          let htmlContent = "";
          return {
            webview: {
              options: {},
              set html(val: string) { htmlContent = val; },
              get html() { return htmlContent; },
              onDidReceiveMessage: () => {},
            },
            onDidDispose: () => {},
            reveal: () => {},
            dispose: () => {},
          };
        },
      },
      commands: {
        executeCommand: async (_cmd: string, ..._args: any[]) => undefined,
      },
      ViewColumn: {
        Beside: -2,
        Active: -1,
        One: 1,
        Two: 2,
      },
      Uri: {
        parse: (s: string) => ({
          toString: () => s,
          fsPath: s.replace(/^file:\/\/\/?/, ""),
        }),
        file: (s: string) => ({
          toString: () => `file:///${s.replace(/\\/g, "/")}`,
          fsPath: s,
        }),
      },
      CodeAction: class {
        title: string;
        kind?: any;
        command?: any;
        diagnostics?: any[];
        isPreferred?: boolean;
        constructor(title: string, kind?: any) {
          this.title = title;
          this.kind = kind;
        }
      },
      CodeActionKind: {
        QuickFix: { value: "quickfix" },
      },
      languages: {
        getDiagnostics: (_uri?: any) => [],
      },
    };
  }
  return originalRequire.apply(this, arguments);
};

import { runBridgeTests } from "./bridge.test";

async function main() {
  console.log("==================================================");
  console.log("      CompilerMate VS Code Extension Test Suite    ");
  console.log("==================================================");

  let totalFailures = 0;
  totalFailures += await runBridgeTests();

  console.log("--------------------------------------------------");
  if (totalFailures === 0) {
    console.log("ALL EXTENSION INTEGRATION TESTS PASSED!");
    process.exit(0);
  } else {
    console.error(`TEST SUITE FAILED with ${totalFailures} failure(s).`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Test runner encountered fatal error:", err);
  process.exit(1);
});
