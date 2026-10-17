import * as vscode from "vscode";
import { EngineBridge } from "./engineBridge";
import { CompilerMateQuickFixProvider } from "./quickFixProvider";
import { InvestigationViewProvider } from "./resultsPanel";
import { IssuesTreeProvider } from "./issuesTree";
import { InvestigationStore } from "./investigationStore";
import { VerificationEngine } from "./verificationEngine";
import {
  CandidateFix,
  DiagnosticInput,
  InvestigationRequest,
  ChatMessage,
  InteractionRequest,
  InteractionResponse,
  InvestigationResult,
  InvestigationRecord,
  VerificationReport,
} from "./types";

let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel("CompilerMate");
  console.log("[CompilerMate] Extension activating...");
  outputChannel.appendLine("[CompilerMate] Extension activating...");

  const engineBridge = new EngineBridge(outputChannel);
  const investigationStore = new InvestigationStore(context);
  const verificationEngine = new VerificationEngine(engineBridge, outputChannel);

  let lastInvestigatedDoc: vscode.TextDocument | undefined;
  let lastInvestigatedDiag: DiagnosticInput | undefined;
  let lastInvestigatedResult: InvestigationResult | undefined;
  let activeRecord: InvestigationRecord | undefined;

  // Helper to apply fixes safely via WorkspaceEdit with user consent
  const handleApplyFix = async (
    fix: CandidateFix,
    docUri: vscode.Uri,
    expectedVersion?: number
  ): Promise<boolean> => {
    const doc = await vscode.workspace.openTextDocument(docUri);

    // Stale check
    if (expectedVersion !== undefined && doc.version !== expectedVersion) {
      vscode.window.showWarningMessage(
        "CompilerMate: Document was modified after investigation. Please re-investigate before applying."
      );
      return false;
    }

    // Explicit developer consent before mutating code
    const confirm = await vscode.window.showInformationMessage(
      `Apply proposed correction "${fix.title}" to ${doc.fileName.split(/[/\\]/).pop()}?`,
      { modal: true },
      "Apply Fix",
      "Cancel"
    );
    if (confirm !== "Apply Fix") {
      outputChannel.appendLine(`[CompilerMate] Fix application cancelled by user.`);
      return false;
    }

    const edit = new vscode.WorkspaceEdit();
    for (const e of fix.edits) {
      const vsRange = new vscode.Range(
        new vscode.Position(e.range.start.line, e.range.start.character),
        new vscode.Position(e.range.end.line, e.range.end.character)
      );
      edit.replace(docUri, vsRange, e.new_text);
    }

    const applied = await vscode.workspace.applyEdit(edit);
    if (applied) {
      vscode.window.showInformationMessage(`CompilerMate: Applied fix "${fix.title}".`);
      console.log(`[CompilerMate] Applied fix ${fix.id} on ${docUri.fsPath}`);
      outputChannel.appendLine(`[CompilerMate] Applied fix ${fix.id} on ${docUri.fsPath}`);

      const updatedDoc = await vscode.workspace.openTextDocument(docUri);

      // Record applied fix in active persistent investigation record
      if (activeRecord) {
        activeRecord.status = "APPLIED";
        activeRecord.decision_status = "APPLIED";
        activeRecord.selected_fix_id = fix.id;
        activeRecord.applied_diff = fix.diff || null;
        activeRecord.document_version = updatedDoc.version;
        await investigationStore.saveRecord(activeRecord);
      }

      viewProvider.showAppliedFix(fix.title, updatedDoc.version);
    } else {
      vscode.window.showErrorMessage(`CompilerMate: Failed to apply fix "${fix.title}".`);
      console.error(`[CompilerMate] Failed to apply fix ${fix.id} on ${docUri.fsPath}`);
    }
    return applied;
  };

  // Helper to re-investigate on active diagnostic
  const handleReinvestigate = async (docUri: vscode.Uri): Promise<void> => {
    const doc = await vscode.workspace.openTextDocument(docUri);
    // Allow brief interval for language tooling / linter to publish new diagnostics
    await new Promise((r) => setTimeout(r, 150));
    const diags = vscode.languages.getDiagnostics(docUri);
    if (diags.length > 0) {
      await investigateDiagnostic(doc, diags[0]);
    } else {
      viewProvider.showResolvedState("No active diagnostics found in document. All issues resolved.");
      vscode.window.showInformationMessage("CompilerMate: All diagnostics resolved! No issues found.");
    }
  };

  // Helper to independently verify a candidate fix
  const handleVerifyFix = async (
    fix: CandidateFix,
    docUri: vscode.Uri
  ): Promise<VerificationReport | undefined> => {
    try {
      const doc = await vscode.workspace.openTextDocument(docUri);
      const diag = lastInvestigatedDiag || (activeRecord ? activeRecord.diagnostic : undefined);
      if (!diag) {
        vscode.window.showWarningMessage("CompilerMate: No active diagnostic context to verify.");
        return undefined;
      }

      outputChannel.appendLine(`[CompilerMate] Verifying candidate fix "${fix.title}" (${fix.id})...`);
      const report = await verificationEngine.verifyFix(context, doc, fix, diag);

      fix.verification = {
        status: report.status,
        checks: report.checks,
        limitation: report.limitation,
        unresolved_risks: report.unresolved_risks,
      };

      if (lastInvestigatedResult) {
        lastInvestigatedResult.verification_report = report;
        lastInvestigatedResult.unresolved_risks = report.unresolved_risks;
      }

      if (activeRecord) {
        activeRecord.verification_report = report;
        activeRecord.unresolved_risks = report.unresolved_risks;
        activeRecord.status =
          report.status === "PASSED" ? "VERIFIED" :
          report.status === "PARTIALLY_VERIFIED" ? "PARTIALLY_VERIFIED" :
          report.status === "FAILED" ? "FAILED" : "OPEN";
        const fixIdx = activeRecord.candidate_fixes.findIndex((f) => f.id === fix.id);
        if (fixIdx >= 0) {
          activeRecord.candidate_fixes[fixIdx] = fix;
        }
        await investigationStore.saveRecord(activeRecord);
      }

      vscode.window.showInformationMessage(
        `CompilerMate: Verification ${report.status} (${report.checks.filter((c) => c.passed).length}/${report.checks.length} checks passed).`
      );
      return report;
    } catch (err) {
      outputChannel.appendLine(`[CompilerMate] Verification error: ${err}`);
      vscode.window.showErrorMessage(`CompilerMate: Verification error: ${err}`);
      return undefined;
    }
  };

  // Helper to run automated test runner verification
  const handleRunTests = async (
    fix: CandidateFix,
    docUri: vscode.Uri
  ): Promise<VerificationReport | undefined> => {
    try {
      const doc = await vscode.workspace.openTextDocument(docUri);
      const diag = lastInvestigatedDiag || (activeRecord ? activeRecord.diagnostic : undefined);
      if (!diag) {
        vscode.window.showWarningMessage("CompilerMate: No active diagnostic context to test.");
        return undefined;
      }

      const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
      const defaultCommand = process.platform === "win32" ? "python -m unittest discover -v" : "python3 -m unittest discover -v";

      // Obtain explicit user approval before executing external command
      const testCommand = await vscode.window.showInputBox({
        title: "CompilerMate: Run Automated Tests",
        prompt: "Confirm or enter test command to execute in workspace",
        value: defaultCommand,
        ignoreFocusOut: true,
      });

      if (!testCommand || !testCommand.trim()) {
        outputChannel.appendLine("[CompilerMate] Test execution cancelled by user.");
        return undefined;
      }

      outputChannel.appendLine(`[CompilerMate] Running tests: "${testCommand.trim()}" in ${workspaceDir}`);
      const report = await verificationEngine.verifyFix(context, doc, fix, diag, {
        runTests: true,
        testCommand: testCommand.trim(),
        cwd: workspaceDir,
      });

      fix.verification = {
        status: report.status,
        checks: report.checks,
        limitation: report.limitation,
        unresolved_risks: report.unresolved_risks,
      };

      if (lastInvestigatedResult) {
        lastInvestigatedResult.verification_report = report;
        lastInvestigatedResult.unresolved_risks = report.unresolved_risks;
      }

      if (activeRecord) {
        activeRecord.verification_report = report;
        activeRecord.unresolved_risks = report.unresolved_risks;
        activeRecord.status =
          report.status === "PASSED" ? "VERIFIED" :
          report.status === "PARTIALLY_VERIFIED" ? "PARTIALLY_VERIFIED" :
          report.status === "FAILED" ? "FAILED" : "OPEN";
        const fixIdx = activeRecord.candidate_fixes.findIndex((f) => f.id === fix.id);
        if (fixIdx >= 0) {
          activeRecord.candidate_fixes[fixIdx] = fix;
        }
        await investigationStore.saveRecord(activeRecord);
      }

      if (report.status === "PASSED") {
        vscode.window.showInformationMessage("CompilerMate: All checks passed including automated tests!");
      } else if (report.status === "FAILED") {
        vscode.window.showWarningMessage("CompilerMate: Automated test verification failed.");
      }

      return report;
    } catch (err) {
      outputChannel.appendLine(`[CompilerMate] Run tests error: ${err}`);
      vscode.window.showErrorMessage(`CompilerMate: Run tests error: ${err}`);
      return undefined;
    }
  };

  // Helper to browse and reopen past persistent investigations
  const handleShowHistory = async (): Promise<void> => {
    const records = await investigationStore.listRecords();
    if (records.length === 0) {
      vscode.window.showInformationMessage("CompilerMate: No saved investigation records found.");
      return;
    }

    const items: Array<vscode.QuickPickItem & { recordId: string }> = records.map((r) => {
      const dateStr = new Date(r.updated_at).toLocaleString();
      const statusIcon =
        r.status === "APPLIED" ? "✅" :
        r.status === "VERIFIED" ? "✓" :
        r.status === "PARTIALLY_VERIFIED" ? "⚡" :
        r.status === "FAILED" ? "✗" : "○";
      return {
        label: `${statusIcon} [${r.category}] ${r.problem_description}`,
        description: `${r.document_name} · ${r.status}`,
        detail: `ID: ${r.id} · Verification: ${r.verification_status || "NOT_CHECKED"} · Updated: ${dateStr}`,
        recordId: r.id,
      };
    });

    const selected = await vscode.window.showQuickPick(items, {
      placeHolder: "Select a previous investigation record to reopen",
      matchOnDescription: true,
      matchOnDetail: true,
    });

    if (selected) {
      await handleReopenRecord(selected.recordId);
    }
  };

  const handleReopenRecord = async (recordId: string): Promise<void> => {
    const record = await investigationStore.getRecord(recordId);
    if (!record) {
      vscode.window.showErrorMessage(`CompilerMate: Record "${recordId}" could not be found.`);
      return;
    }

    lastInvestigatedDoc = undefined;
    lastInvestigatedDiag = record.diagnostic;
    lastInvestigatedResult = {
      status: "success",
      category: record.category,
      diagnostic: record.diagnostic,
      explanation: record.explanation || undefined,
      evidence: record.evidence,
      candidate_fixes: record.candidate_fixes,
      metadata: record.metadata,
      record_id: record.id,
      verification_report: record.verification_report || undefined,
      unresolved_risks: record.unresolved_risks,
    };
    activeRecord = record;

    try {
      const docUri = vscode.Uri.parse(record.document_uri);
      const doc = await vscode.workspace.openTextDocument(docUri);
      lastInvestigatedDoc = doc;
      await vscode.window.showTextDocument(doc, { preview: true, preserveFocus: true });
    } catch (e) {
      outputChannel.appendLine(`[CompilerMate] Note: Could not open document ${record.document_uri}: ${e}`);
    }

    await viewProvider.showRecord(record);
    vscode.window.showInformationMessage(`CompilerMate: Reopened investigation record "${record.id}".`);
  };

  // Helper to handle two-way chat interaction
  const handleSendMessage = async (
    userMessage: string,
    history: ChatMessage[]
  ): Promise<InteractionResponse> => {
    if (!lastInvestigatedDoc || !lastInvestigatedDiag || !lastInvestigatedResult) {
      return {
        status: "error",
        message: "No active diagnostic investigation context available. Please select and investigate a diagnostic first.",
        error_message: "No active diagnostic context.",
      };
    }

    const req: InteractionRequest = {
      command: "interact",
      document: {
        uri: lastInvestigatedDoc.uri.toString(),
        text: lastInvestigatedDoc.getText(),
        language_id: lastInvestigatedDoc.languageId || "python",
      },
      diagnostic: lastInvestigatedDiag,
      investigation_result: lastInvestigatedResult,
      user_message: userMessage,
      history: history,
      active_record: activeRecord,
    };

    outputChannel.appendLine(`[CompilerMate] Sending chat interaction: "${userMessage}"`);
    const resp = await engineBridge.interact(context, req);

    // Record conversation in active record and persist
    if (activeRecord) {
      const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      activeRecord.history.push({ role: "user", content: userMessage, timestamp: timeStr });
      if (resp.status === "success" && resp.message) {
        activeRecord.history.push({ role: "assistant", content: resp.message, timestamp: timeStr });
      }
      if (resp.action === "select_fix" && resp.selected_fix_id) {
        activeRecord.selected_fix_id = resp.selected_fix_id;
      }
      await investigationStore.saveRecord(activeRecord);
    }

    // Trigger action workflows if requested
    if (resp.action === "show_history") {
      setTimeout(() => { handleShowHistory(); }, 50);
    } else if (resp.action === "run_tests" && lastInvestigatedResult && lastInvestigatedDoc) {
      const fix = lastInvestigatedResult.candidate_fixes[0];
      if (fix) {
        setTimeout(() => { handleRunTests(fix, lastInvestigatedDoc!.uri); }, 50);
      }
    } else if (resp.action === "reopen_record" && resp.target_record_id) {
      setTimeout(() => { handleReopenRecord(resp.target_record_id!); }, 50);
    }

    return resp;
  };

  // Native issue overview: selecting an issue opens the focused detail view.
  const issuesProvider = new IssuesTreeProvider();
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("compilermate.issuesView", issuesProvider),
    vscode.commands.registerCommand("compilermate.refreshIssues", () => issuesProvider.refresh())
  );

  // Register sidebar detail provider with full verification & history callbacks
  const viewProvider = new InvestigationViewProvider(
    context.extensionUri,
    handleApplyFix,
    handleReinvestigate,
    handleSendMessage,
    handleVerifyFix,
    handleRunTests,
    handleShowHistory,
    handleReopenRecord
  );

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      InvestigationViewProvider.viewType,
      viewProvider,
      {
        webviewOptions: {
          retainContextWhenHidden: true,
        },
      }
    )
  );

  // Core investigation logic
  const investigateDiagnostic = async (
    document: vscode.TextDocument,
    diagnostic: any
  ) => {
    try {
      console.log(`[CompilerMate] Starting investigation of "${diagnostic.message}"`);
      await viewProvider.showLoading(diagnostic.message);

      // Safe extraction of range
      const startLine = diagnostic.range?.start?.line ?? 0;
      const startChar = diagnostic.range?.start?.character ?? 0;
      const endLine = diagnostic.range?.end?.line ?? startLine;
      const endChar = diagnostic.range?.end?.character ?? startChar;

      const diagInput: DiagnosticInput = {
        message: String(diagnostic.message || "Unknown diagnostic"),
        range: {
          start: { line: startLine, character: startChar },
          end: { line: endLine, character: endChar },
        },
        code: typeof diagnostic.code === "object" ? diagnostic.code.value : diagnostic.code,
        source: diagnostic.source || "Python",
        severity: typeof diagnostic.severity === "number" ? diagnostic.severity + 1 : 1,
      };

      const request: InvestigationRequest = {
        command: "investigate",
        document: {
          uri: document.uri.toString(),
          text: document.getText(), // In-memory text buffer including unsaved changes
          language_id: document.languageId || "python",
        },
        diagnostic: diagInput,
      };

      console.log("[CompilerMate] Dispatching payload to Python engine via EngineBridge...");
      lastInvestigatedDoc = document;
      lastInvestigatedDiag = diagInput;
      const result = await engineBridge.investigate(context, request);
      lastInvestigatedResult = result;

      // Create and persist investigation record
      const record = investigationStore.createRecord(result, document, [diagInput]);
      await investigationStore.saveRecord(record);
      activeRecord = record;
      result.record_id = record.id;

      console.log(`[CompilerMate] Received engine result: status=${result.status}, category=${result.category}, candidate_fixes=${result.candidate_fixes?.length || 0}, record=${record.id}`);
      await viewProvider.updateResult(result, document);
    } catch (err) {
      console.error("[CompilerMate] Investigation error:", err);
      outputChannel.appendLine(`[CompilerMate] Investigation error: ${err}`);
      await viewProvider.updateResult(
        {
          status: "error",
          category: "BRIDGE_EXCEPTION",
          diagnostic: {
            message: diagnostic?.message || "Unknown error",
            range: diagnostic?.range || { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } },
            severity: 1,
          },
          evidence: [],
          candidate_fixes: [],
          metadata: {},
          error_message: String(err),
        },
        document
      );
    }
  };

  // Register command: compilermate.investigateDiagnostic
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "compilermate.investigateDiagnostic",
      async (docArg?: any, diagArg?: any) => {
        console.log("[CompilerMate] Command 'compilermate.investigateDiagnostic' triggered.");
        outputChannel.appendLine("[CompilerMate] Command 'compilermate.investigateDiagnostic' triggered.");

        try {
          let document: vscode.TextDocument | undefined;

          // 1. Resolve TextDocument robustly
          if (typeof docArg === "string") {
            const uri = vscode.Uri.parse(docArg);
            document = await vscode.workspace.openTextDocument(uri);
          } else if (docArg instanceof vscode.Uri) {
            document = await vscode.workspace.openTextDocument(docArg);
          } else if (docArg && typeof docArg.getText === "function") {
            document = docArg;
          } else if (docArg && docArg.uri) {
            document = await vscode.workspace.openTextDocument(docArg.uri);
          } else {
            const editor = vscode.window.activeTextEditor;
            if (editor && editor.document.languageId === "python") {
              document = editor.document;
            }
          }

          if (document && document.languageId !== "python") {
            vscode.window.showWarningMessage("CompilerMate investigation is available for Python files. Open a .py file and select a diagnostic.");
            return;
          }

          if (!document) {
            const msg = "CompilerMate: Please open a Python file to investigate diagnostics.";
            console.warn(`[CompilerMate] ${msg}`);
            outputChannel.appendLine(`[CompilerMate] ${msg}`);
            vscode.window.showWarningMessage(msg);
            return;
          }

          // 2. Resolve Diagnostic
          let diagnostic = diagArg;
          if (!diagnostic || !diagnostic.range) {
            const editor = vscode.window.activeTextEditor;
            const pos = editor?.selection.active;
            const diags = vscode.languages.getDiagnostics(document.uri);
            const match = pos ? diags.find((d) => d.range.contains(pos)) : undefined;
            if (!match) {
              const msg = "CompilerMate: No diagnostic found at cursor in current file.";
              console.log(`[CompilerMate] ${msg}`);
              outputChannel.appendLine(`[CompilerMate] ${msg}`);
              vscode.window.showInformationMessage(msg);
              return;
            }
            diagnostic = match;
          }

          console.log(`[CompilerMate] Investigating diagnostic: "${diagnostic.message}" on ${document.uri.fsPath}`);
          await investigateDiagnostic(document, diagnostic);
        } catch (commandErr) {
          console.error("[CompilerMate] Fatal error in investigateDiagnostic command:", commandErr);
          outputChannel.appendLine(`[CompilerMate] Fatal command error: ${commandErr}`);
          vscode.window.showErrorMessage(`CompilerMate Error: ${commandErr}`);
        }
      }
    )
  );

  // Register command: compilermate.reinvestigate
  context.subscriptions.push(
    vscode.commands.registerCommand("compilermate.reinvestigate", async () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        await handleReinvestigate(editor.document.uri);
      }
    }),
    vscode.commands.registerCommand("compilermate.showHistory", async () => {
      await handleShowHistory();
    })
  );

  // Register Quick Fix provider for Python
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      { language: "python", scheme: "file" },
      new CompilerMateQuickFixProvider(),
      {
        providedCodeActionKinds: CompilerMateQuickFixProvider.providedCodeActionKinds,
      }
    )
  );

  // Detect document changes to flag stale results
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      viewProvider.checkStale(e.document);
    })
  );

  console.log("[CompilerMate] Extension activated successfully.");
  outputChannel.appendLine("[CompilerMate] Extension activated successfully.");
}

export function deactivate() {
  if (outputChannel) {
    outputChannel.appendLine("[CompilerMate] Extension deactivating.");
    outputChannel.dispose();
  }
}
