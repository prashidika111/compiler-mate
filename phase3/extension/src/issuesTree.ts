import * as vscode from "vscode";

type IssueNode = IssueGroup | IssueLeaf | EmptyIssue;

class IssueGroup extends vscode.TreeItem {
  constructor(public readonly label: string, public readonly severity: vscode.DiagnosticSeverity) {
    super(label, vscode.TreeItemCollapsibleState.Expanded);
    this.contextValue = "compilermateIssueGroup";
    this.iconPath = new vscode.ThemeIcon(severity === vscode.DiagnosticSeverity.Error ? "error" : "warning");
  }
}

class EmptyIssue extends vscode.TreeItem {
  constructor() {
    super("No issues detected", vscode.TreeItemCollapsibleState.None);
    this.description = "Python diagnostics appear here";
    this.contextValue = "compilermateEmptyIssues";
  }
}

class IssueLeaf extends vscode.TreeItem {
  constructor(
    public readonly document: vscode.TextDocument,
    public readonly diagnostic: vscode.Diagnostic
  ) {
    const line = diagnostic.range.start.line + 1;
    const message = diagnostic.message.replace(/\s+/g, " ").trim();
    super(`${line}: ${message}`, vscode.TreeItemCollapsibleState.None);
    this.description = `${document.fileName.split(/[\\\\/]/).pop() || "Python"} · ${diagnostic.source || "Diagnostic"}`;
    this.tooltip = `${document.uri.fsPath}:${line}\n${message}`;
    this.accessibilityInformation = { label: `Line ${line}: ${message}`, role: "treeitem" };
    this.iconPath = new vscode.ThemeIcon(
      diagnostic.severity === vscode.DiagnosticSeverity.Error ? "error" :
      diagnostic.severity === vscode.DiagnosticSeverity.Warning ? "warning" : "info"
    );
    this.command = {
      command: "compilermate.investigateDiagnostic",
      title: "Investigate issue",
      arguments: [document.uri.toString(), diagnostic],
    };
    this.contextValue = "compilermateIssue";
  }
}

/** Native, keyboard-accessible overview of diagnostics for Python files. */
export class IssuesTreeProvider implements vscode.TreeDataProvider<IssueNode> {
  private readonly emitter = new vscode.EventEmitter<IssueNode | undefined | null | void>();
  readonly onDidChangeTreeData = this.emitter.event;

  constructor() {
    vscode.languages.onDidChangeDiagnostics(() => this.refresh());
    vscode.workspace.onDidOpenTextDocument((doc) => { if (doc.languageId === "python") this.refresh(); });
    vscode.workspace.onDidCloseTextDocument(() => this.refresh());
  }

  refresh(): void { this.emitter.fire(); }

  getTreeItem(element: IssueNode): vscode.TreeItem { return element; }

  getChildren(element?: IssueNode): Thenable<IssueNode[]> {
    if (element instanceof IssueGroup) {
      const wanted = element.severity;
      return Promise.resolve(this.allIssues().filter(({ diagnostic }) => diagnostic.severity === wanted)
        .map(({ document, diagnostic }) => new IssueLeaf(document, diagnostic)));
    }
    if (element) return Promise.resolve([]);
    const all = this.allIssues();
    const errors = all.filter(({ diagnostic }) => diagnostic.severity === vscode.DiagnosticSeverity.Error).length;
    const warnings = all.filter(({ diagnostic }) => diagnostic.severity === vscode.DiagnosticSeverity.Warning).length;
    const groups: IssueNode[] = [];
    if (errors) { const g = new IssueGroup(`Errors (${errors})`, vscode.DiagnosticSeverity.Error); groups.push(g); }
    if (warnings) { const g = new IssueGroup(`Warnings (${warnings})`, vscode.DiagnosticSeverity.Warning); groups.push(g); }
    const other = all.filter(({ diagnostic }) => diagnostic.severity !== vscode.DiagnosticSeverity.Error && diagnostic.severity !== vscode.DiagnosticSeverity.Warning);
    if (other.length) {
      // Informational diagnostics remain discoverable without inventing another severity group.
      groups.push(...other.map(({ document, diagnostic }) => new IssueLeaf(document, diagnostic)));
    }
    if (!groups.length) {
      return Promise.resolve([new EmptyIssue()]);
    }
    return Promise.resolve(groups);
  }

  private allIssues(): Array<{ document: vscode.TextDocument; diagnostic: vscode.Diagnostic }> {
    const result: Array<{ document: vscode.TextDocument; diagnostic: vscode.Diagnostic }> = [];
    for (const [uri, diagnostics] of vscode.languages.getDiagnostics()) {
      const document = vscode.workspace.textDocuments.find((doc) => doc.uri.toString() === uri.toString());
      if (!document || document.languageId !== "python") continue;
      for (const diagnostic of diagnostics) result.push({ document, diagnostic });
    }
    return result;
  }
}
