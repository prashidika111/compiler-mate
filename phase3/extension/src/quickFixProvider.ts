import * as vscode from "vscode";

export class CompilerMateQuickFixProvider implements vscode.CodeActionProvider {
  public static readonly providedCodeActionKinds = [
    vscode.CodeActionKind.QuickFix,
  ];

  public provideCodeActions(
    document: vscode.TextDocument,
    _range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    _token: vscode.CancellationToken
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    // Filter diagnostics that overlap the current selection/range
    for (const diagnostic of context.diagnostics) {
      const shortMsg =
        diagnostic.message.length > 55
          ? diagnostic.message.substring(0, 52) + "..."
          : diagnostic.message;

      const action = new vscode.CodeAction(
        `🔍 CompilerMate: Investigate "${shortMsg}"`,
        vscode.CodeActionKind.QuickFix
      );

      // Extract safe JSON-serializable diagnostic payload
      const safeDiag = {
        message: diagnostic.message,
        range: {
          start: {
            line: diagnostic.range?.start?.line ?? 0,
            character: diagnostic.range?.start?.character ?? 0,
          },
          end: {
            line: diagnostic.range?.end?.line ?? 0,
            character: diagnostic.range?.end?.character ?? 0,
          },
        },
        code: typeof diagnostic.code === "object" ? (diagnostic.code as any).value : diagnostic.code,
        source: diagnostic.source || "Python",
        severity: typeof diagnostic.severity === "number" ? diagnostic.severity : 0,
      };

      action.command = {
        command: "compilermate.investigateDiagnostic",
        title: "Investigate Diagnostic with CompilerMate",
        arguments: [document.uri.toString(), safeDiag],
      };

      action.diagnostics = [diagnostic];
      // Investigation is optional; do not outrank the language server's actual fixes.
      action.isPreferred = false;

      actions.push(action);
    }

    return actions;
  }
}
