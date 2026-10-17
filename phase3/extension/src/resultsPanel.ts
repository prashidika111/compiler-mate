import * as vscode from "vscode";
import { CandidateFix, InvestigationResult, ChatMessage, InteractionResponse, InvestigationRecord } from "./types";

export class InvestigationViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "compilermate.investigationView";

  private _view?: vscode.WebviewView;
  private _panel?: vscode.WebviewPanel;
  private _lastResult?: InvestigationResult;
  private _lastDocumentUri?: vscode.Uri;
  private _lastDocumentVersion?: number;
  private _isLoading: boolean = false;
  private _loadingMessage?: string;
  private _chatHistory: ChatMessage[] = [];
  private _selectedFixId?: string;
  private _isChatLoading: boolean = false;
  private _isStale: boolean = false;

  constructor(
    private readonly _extensionUri: vscode.Uri,
    private readonly _onApplyFix: (fix: CandidateFix, docUri: vscode.Uri, expectedVersion?: number) => Promise<boolean>,
    private readonly _onReinvestigate: (docUri: vscode.Uri) => Promise<void>,
    private readonly _onSendMessage?: (userMessage: string, history: ChatMessage[]) => Promise<InteractionResponse>,
    private readonly _onVerifyFix?: (fix: CandidateFix, docUri: vscode.Uri) => Promise<any>,
    private readonly _onRunTests?: (fix: CandidateFix, docUri: vscode.Uri) => Promise<any>,
    private readonly _onShowHistory?: () => Promise<void>,
    private readonly _onReopenRecord?: (recordId: string) => Promise<void>
  ) {}

  private async _handleMessage(message: any): Promise<void> {
    console.log("[CompilerMate] Webview message received:", message.command);
    if (message.command === "applyFix") {
      if (this._lastResult && this._lastDocumentUri) {
        const fix = this._lastResult.candidate_fixes.find((f) => f.id === message.fixId);
        if (fix) {
          await this._onApplyFix(fix, this._lastDocumentUri, this._lastDocumentVersion);
        }
      }
    } else if (message.command === "verifyFix") {
      if (this._onVerifyFix && this._lastResult && this._lastDocumentUri) {
        const fix = this._lastResult.candidate_fixes.find((f) => f.id === message.fixId) || this._lastResult.candidate_fixes[0];
        if (fix) {
          const report = await this._onVerifyFix(fix, this._lastDocumentUri);
          if (report) {
            fix.verification = {
              status: report.status,
              checks: report.checks,
              limitation: report.limitation,
            };
            this._lastResult.verification_report = report;
            this.render();
          }
        }
      }
    } else if (message.command === "runTests") {
      if (this._onRunTests && this._lastResult && this._lastDocumentUri) {
        const fix = this._lastResult.candidate_fixes.find((f) => f.id === message.fixId) || this._lastResult.candidate_fixes[0];
        if (fix) {
          const report = await this._onRunTests(fix, this._lastDocumentUri);
          if (report) {
            fix.verification = {
              status: report.status,
              checks: report.checks,
              limitation: report.limitation,
            };
            this._lastResult.verification_report = report;
            this.render();
          }
        }
      }
    } else if (message.command === "showHistory") {
      if (this._onShowHistory) {
        await this._onShowHistory();
      }
    } else if (message.command === "reopenRecord") {
      if (this._onReopenRecord && message.recordId) {
        await this._onReopenRecord(message.recordId);
      }
    } else if (message.command === "selectFix") {
      this._selectedFixId = message.fixId;
      this.render();
    } else if (message.command === "chatMessage") {
      const text = (message.text || "").trim();
      if (!text) {
        return;
      }
      this._chatHistory.push({
        role: "user",
        content: text,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      });
      this._isChatLoading = true;
      this.render();

      if (this._onSendMessage) {
        try {
          const priorHistory = this._chatHistory.slice(0, -1);
          const resp = await this._onSendMessage(text, priorHistory);
          this._chatHistory.push({
            role: "assistant",
            content: resp.message,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          });
          if (resp.action === "select_fix" && resp.selected_fix_id) {
            this._selectedFixId = resp.selected_fix_id;
          }
          this._isChatLoading = false;
          this.render();

          if (resp.action === "reinvestigate" && this._lastDocumentUri) {
            await this._onReinvestigate(this._lastDocumentUri);
          }
        } catch (err) {
          this._chatHistory.push({
            role: "assistant",
            content: `Interaction error: ${err}`,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          });
          this._isChatLoading = false;
          this.render();
        }
      } else {
        this._isChatLoading = false;
        this.render();
      }
    } else if (message.command === "reinvestigate") {
      if (this._lastDocumentUri) {
        await this._onReinvestigate(this._lastDocumentUri);
      }
    }
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    console.log("[CompilerMate] resolveWebviewView called by VS Code.");
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };

    webviewView.webview.onDidReceiveMessage(this._handleMessage.bind(this));

    if (this._isLoading && this._loadingMessage) {
      this._view.webview.html = this._getHtmlForLoading(this._loadingMessage);
    } else if (this._lastResult) {
      this.render();
    } else {
      this.showEmptyState();
    }
  }

  /**
   * Ensures the results webview is visible to the user.
   * First attempts to focus the sidebar view container. If not resolved,
   * falls back to creating an editor WebviewPanel in ViewColumn.Beside.
   */
  public async reveal(): Promise<vscode.Webview | undefined> {
    if (this._view) {
      this._view.show?.(true);
      return this._view.webview;
    }

    try {
      console.log("[CompilerMate] Executing compilermate.investigationView.focus...");
      await vscode.commands.executeCommand("compilermate.investigationView.focus");
    } catch (err) {
      console.warn("[CompilerMate] Could not execute compilermate.investigationView.focus:", err);
    }

    // Wait briefly (up to 400ms) for VS Code to invoke resolveWebviewView
    for (let i = 0; i < 8 && !this._view; i++) {
      await new Promise((r) => setTimeout(r, 50));
    }

    const currentView = this._view as vscode.WebviewView | undefined;
    if (currentView) {
      currentView.show?.(true);
      return currentView.webview;
    }

    // Fallback: create or reveal editor WebviewPanel beside active editor
    console.log("[CompilerMate] Sidebar view not resolved; opening WebviewPanel beside active editor.");
    const targetColumn = (vscode.ViewColumn && vscode.ViewColumn.Beside !== undefined)
      ? vscode.ViewColumn.Beside
      : (vscode.ViewColumn ? vscode.ViewColumn.One : -2);

    if (vscode.window && typeof vscode.window.createWebviewPanel === "function") {
      if (!this._panel) {
        this._panel = vscode.window.createWebviewPanel(
          "compilermate.investigationPanel",
          "Python Issue Investigation",
          targetColumn,
          {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
            retainContextWhenHidden: true,
          }
        );
        this._panel.onDidDispose(() => {
          this._panel = undefined;
        });
        this._panel.webview.onDidReceiveMessage(this._handleMessage.bind(this));
      }
      this._panel.reveal(targetColumn, true);
      return this._panel.webview;
    }
    return undefined;
  }

  public async showLoading(diagMessage: string): Promise<void> {
    this._isLoading = true;
    this._loadingMessage = diagMessage;
    const webview = await this.reveal();
    const html = this._getHtmlForLoading(diagMessage);
    if (this._view) {
      this._view.webview.html = html;
    }
    if (this._panel) {
      this._panel.webview.html = html;
    }
    if (webview && !this._view && !this._panel) {
      webview.html = html;
    }
  }

  public async updateResult(
    result: InvestigationResult,
    document: vscode.TextDocument
  ): Promise<void> {
    this._isLoading = false;
    this._lastResult = result;
    this._isStale = false;
    this._lastDocumentUri = document.uri;
    this._lastDocumentVersion = document.version;
    this._chatHistory = [];
    this._selectedFixId = result.candidate_fixes && result.candidate_fixes.length > 0 ? result.candidate_fixes[0].id : undefined;
    this._isChatLoading = false;

    await this.reveal();
    this.render();
  }

  public checkStale(document: vscode.TextDocument): void {
    if (
      this._lastDocumentUri &&
      this._lastDocumentUri.toString() === document.uri.toString() &&
      this._lastDocumentVersion !== undefined &&
      this._lastDocumentVersion !== document.version
    ) {
      if (this._lastResult && !this._isStale) {
        this._isStale = true;
        this.render();
      }
    }
  }

  public render(): void {
    if (!this._lastResult) {
      return;
    }
    const html = this._getHtmlForResult(this._lastResult, this._isStale);
    if (this._view) {
      this._view.webview.html = html;
    }
    if (this._panel) {
      this._panel.webview.html = html;
    }
  }

  public showEmptyState(): void {
    const html = this._getHtmlForEmpty();
    if (this._view) {
      this._view.webview.html = html;
    }
    if (this._panel) {
      this._panel.webview.html = html;
    }
  }

  public showAppliedFix(fixTitle: string, updatedVersion: number): void {
    this._isLoading = false;
    this._lastDocumentVersion = updatedVersion;
    const html = this._getHtmlForAppliedFix(fixTitle);
    if (this._view) {
      this._view.webview.html = html;
    }
    if (this._panel) {
      this._panel.webview.html = html;
    }
  }

  public showResolvedState(message: string): void {
    this._isLoading = false;
    this._lastResult = undefined;
    const html = this._getHtmlForResolved(message);
    if (this._view) {
      this._view.webview.html = html;
    }
    if (this._panel) {
      this._panel.webview.html = html;
    }
  }

  public async showRecord(record: InvestigationRecord): Promise<void> {
    this._isLoading = false;
    this._isStale = false;
    this._lastDocumentUri = vscode.Uri.parse(record.document_uri);
    this._lastDocumentVersion = record.document_version ?? undefined;
    this._chatHistory = record.history ? [...record.history] : [];
    this._selectedFixId = record.selected_fix_id || (record.candidate_fixes && record.candidate_fixes.length > 0 ? record.candidate_fixes[0].id : undefined);
    this._lastResult = {
      status: "success",
      category: record.category,
      diagnostic: record.diagnostic,
      explanation: record.explanation || undefined,
      evidence: record.evidence || [],
      candidate_fixes: record.candidate_fixes || [],
      metadata: record.metadata || {},
      record_id: record.id,
      verification_report: record.verification_report || undefined,
      unresolved_risks: record.unresolved_risks || [],
    };
    await this.reveal();
    this.render();
  }

  private _escapeHtml(text: string): string {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  private _formatMessageContent(text: string): string {
    let escaped = this._escapeHtml(text);
    // Replace backtick inline code
    escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Replace bold text
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // Replace newlines with <br/>
    escaped = escaped.replace(/\n/g, "<br/>");
    return escaped;
  }

  private _getHtmlForEmpty(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
      :root {
        color-scheme: light dark;
        --cm-bg: var(--vscode-sideBar-background, var(--vscode-editor-background));
        --cm-fg: var(--vscode-foreground);
        --cm-muted: var(--vscode-descriptionForeground);
        --cm-border: var(--vscode-panel-border, var(--vscode-widget-border));
        --cm-accent: var(--vscode-button-background);
        --cm-accent-fg: var(--vscode-button-foreground);
        --cm-warning: var(--vscode-editorWarning-foreground, #b58100);
      }
      body { color: var(--cm-fg); background: var(--cm-bg); }
      .stale-banner { color: var(--vscode-editorWarning-foreground, #f0c674) !important; border-color: var(--vscode-editorWarning-foreground, #b58100) !important; }
      button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 2px; }
      button { min-height: 28px; }
      input, textarea { color: var(--vscode-input-foreground); background: var(--vscode-input-background); border-color: var(--vscode-input-border, var(--cm-border)); }
      .muted, .subtitle, .meta { color: var(--cm-muted); }
      @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; } }

    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 16px; line-height: 1.5; font-size: var(--vscode-font-size); }
    .card { background: var(--vscode-sideBar-background); border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 14px; margin-bottom: 12px; }
    h3 { margin-top: 0; color: var(--vscode-editorInfo-foreground); font-size: 1.05em; }
    p { margin: 6px 0; color: var(--vscode-descriptionForeground); font-size: 0.9em; }
    .step { display: flex; align-items: flex-start; margin: 8px 0; font-size: 0.9em; }
    .num { background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; margin-right: 8px; font-weight: bold; flex-shrink: 0; font-size: 11px; }
  </style>
</head>
<body>
  <div class="card">
    <h3>Python issue investigation</h3>
    <p>Understand the issue, explore options, and decide what to change.</p>
  </div>
  <div class="card">
    <p><strong>To investigate an issue:</strong></p>
    <div class="step"><div class="num">1</div><span>Open a Python (.py) file in the editor.</span></div>
    <div class="step"><div class="num">2</div><span>Place your cursor on any diagnostic error or warning line.</span></div>
    <div class="step"><div class="num">3</div><span>Click the Quick Fix lightbulb (or press <kbd>Ctrl+.</kbd>) and select <em>"Investigate issue"</em>.</span></div>
  </div>
</body>
</html>`;
  }

  private _getHtmlForAppliedFix(fixTitle: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 16px; line-height: 1.5; font-size: var(--vscode-font-size); }
    .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-left: 4px solid #388a34; border-radius: 6px; padding: 14px; margin-bottom: 12px; }
    h3 { margin-top: 0; color: #388a34; font-size: 1.05em; display: flex; align-items: center; gap: 8px; }
    p { margin: 8px 0; color: var(--vscode-foreground); font-size: 0.9em; }
    .muted { color: var(--vscode-descriptionForeground); font-size: 0.85em; }
    .btn { cursor: pointer; padding: 6px 14px; border-radius: 4px; border: none; font-size: 0.9em; font-weight: 500; background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); margin-top: 8px; }
    .btn:hover { background: var(--vscode-button-secondaryHoverBackground, #3a3d41); }
  </style>
</head>
<body>
  <div class="card">
    <h3>✓ Correction Applied Successfully</h3>
    <p><strong>Applied Fix:</strong> ${this._escapeHtml(fixTitle)}</p>
    <p class="muted">The source buffer has been updated. Visual Studio Code will re-check the file for any remaining diagnostics.</p>
    <button class="btn" onclick="reinvestigate()">🔄 Re-investigate Document</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function reinvestigate() {
      vscode.postMessage({ command: 'reinvestigate' });
    }
  </script>
</body>
</html>`;
  }

  private _getHtmlForResolved(message: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 16px; line-height: 1.5; font-size: var(--vscode-font-size); }
    .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-left: 4px solid #388a34; border-radius: 6px; padding: 14px; margin-bottom: 12px; }
    h3 { margin-top: 0; color: #388a34; font-size: 1.05em; display: flex; align-items: center; gap: 8px; }
    p { margin: 8px 0; color: var(--vscode-foreground); font-size: 0.9em; }
    .muted { color: var(--vscode-descriptionForeground); font-size: 0.85em; }
    .btn { cursor: pointer; padding: 6px 14px; border-radius: 4px; border: none; font-size: 0.9em; font-weight: 500; background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); margin-top: 8px; }
    .btn:hover { background: var(--vscode-button-secondaryHoverBackground, #3a3d41); }
  </style>
</head>
<body>
  <div class="card">
    <h3>✓ All Diagnostics Resolved</h3>
    <p>${this._escapeHtml(message)}</p>
    <p class="muted">No syntax errors or diagnostics detected in the active file.</p>
    <button class="btn" onclick="reinvestigate()">🔄 Check Again</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function reinvestigate() {
      vscode.postMessage({ command: 'reinvestigate' });
    }
  </script>
</body>
</html>`;
  }

  private _getHtmlForLoading(message: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 20px; text-align: center; }
    .spinner { display: inline-block; width: 32px; height: 32px; border: 3px solid rgba(255,255,255,.3); border-radius: 50%; border-top-color: var(--vscode-progressBar-background); animation: spin 1s ease-in-out infinite; margin-bottom: 12px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    h4 { margin: 8px 0; font-size: 1em; }
    p { color: var(--vscode-descriptionForeground); font-size: 0.85em; }
  </style>
</head>
<body>
  <div class="spinner"></div>
  <h4>Investigating diagnostic...</h4>
  <p>${this._escapeHtml(message)}</p>
</body>
</html>`;
  }

  private _getHtmlForResult(result: InvestigationResult, isStale: boolean): string {
    const diag = result.diagnostic;
    const expl = result.explanation;
    const fixes = result.candidate_fixes || [];
    const evidence = result.evidence || [];

    const sevLabel = diag.severity === 1 ? "Error" : diag.severity === 2 ? "Warning" : "Info";
    const sevClass = diag.severity === 1 ? "badge-error" : "badge-warning";
    const sourceLabel = diag.source || "Python";
    const line1 = diag.range.start.line + 1;
    const col1 = diag.range.start.character + 1;

    let staleBanner = "";
    if (isStale) {
      staleBanner = `
      <div class="stale-banner">
        ⚠️ <strong>Document modified since investigation</strong>
        <p>The source buffer has changed. Click below to refresh the investigation.</p>
        <button class="btn btn-secondary" onclick="reinvestigate()">🔄 Re-investigate Document</button>
      </div>`;
    }

    let recordMetaBar = "";
    if (result.record_id) {
      recordMetaBar = `
      <div class="record-meta-bar">
        <span>Investigation Record: <code>${this._escapeHtml(result.record_id)}</code></span>
        <button class="pill-btn" onclick="showHistory()">📁 Past Investigations</button>
      </div>`;
    }

    let causeSymptomSection = "";
    if (expl?.cause_vs_symptom) {
      causeSymptomSection = `
      <div class="cause-card">
        <div class="card-title">🔍 Cause and symptom context</div>
        <p>${this._escapeHtml(expl.cause_vs_symptom)}</p>
      </div>`;
    }

    let evidenceHtml = "";
    if (evidence.length > 0) {
      evidenceHtml = `
      <div class="section">
        <div class="section-header">Source Code Evidence</div>
        ${evidence
          .map((ev) => {
            const kind = (ev.kind || "OBSERVED").toUpperCase();
            const kindClass =
              kind === "OBSERVED"
                ? "badge-observed"
                : kind === "INFERRED"
                ? "badge-inferred"
                : "badge-unverified";
            return `
          <div class="evidence-item">
            <div class="evidence-meta">
              <span class="badge ${kindClass}">[${kind}]</span>
              <span class="evidence-tag">Line ${ev.line}, Col ${ev.column}</span>
              <strong>${this._escapeHtml(ev.title)}</strong>
            </div>
            <pre class="snippet"><code>${this._escapeHtml(ev.snippet)}</code></pre>
            <div class="annotation">${this._escapeHtml(ev.annotation)}</div>
          </div>
        `;
          })
          .join("")}
      </div>`;
    }

    let risksHtml = "";
    const allRisks = result.unresolved_risks || [];
    if (allRisks.length > 0) {
      risksHtml = `
      <div class="section">
        <div class="risks-box">
          <div class="risks-title">⚠️ Unresolved Risks & Verification Limitations:</div>
          <ul>
            ${allRisks.map((r) => `<li>${this._escapeHtml(r)}</li>`).join("")}
          </ul>
        </div>
      </div>`;
    }

    let fixesHtml = "";
    if (fixes.length > 0) {
      fixesHtml = `
      <div class="section">
        <div class="section-header">Proposed fixes & verification</div>
        ${fixes
          .map((fix) => {
            const verif = fix.verification || { status: "NOT_CHECKED", checks: [] };
            const status = verif.status || "NOT_CHECKED";
            const verifBadgeClass =
              status === "PASSED" || status === "VERIFIED"
                ? "badge-verified"
                : status === "PARTIALLY_VERIFIED"
                ? "badge-partially-verified"
                : status === "FAILED"
                ? "badge-failed"
                : status === "UNABLE_TO_VERIFY"
                ? "badge-inconclusive"
                : "badge-not-checked";
            const displayStatus = status === "PARTIALLY_VERIFIED" ? "PARTIALLY VERIFIED" : status;

            const checksHtml = (verif.checks || [])
              .map(
                (c) => `
                <div class="check-item ${c.passed ? "check-pass" : "check-fail"}">
                  ${c.passed ? "✓" : "✗"} <strong>${this._escapeHtml(c.name)}:</strong> ${this._escapeHtml(c.message)}
                </div>
              `
              )
              .join("");

            let diffHtml = "";
            if (fix.diff && fix.diff.trim()) {
              const diffLines = fix.diff
                .split("\n")
                .map((line) => {
                  let lineClass = "diff-ctx";
                  if (line.startsWith("+") && !line.startsWith("+++")) {
                    lineClass = "diff-add";
                  } else if (line.startsWith("-") && !line.startsWith("---")) {
                    lineClass = "diff-del";
                  } else if (line.startsWith("@@")) {
                    lineClass = "diff-info";
                  }
                  return `<div class="${lineClass}">${this._escapeHtml(line)}</div>`;
                })
                .join("");

              diffHtml = `
              <div class="diff-box">
                <div class="diff-header">Proposed Source Diff:</div>
                <div class="diff-content">${diffLines}</div>
              </div>`;
            }

            const isSelected = fix.id === this._selectedFixId;
            const fixCardClass = isSelected ? "fix-card fix-selected" : "fix-card";
            const selectedBadge = isSelected ? `<span class="badge badge-selected">Selected</span>` : "";

            return `
            <div class="${fixCardClass}">
              <div class="fix-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <strong>${this._escapeHtml(fix.title)}</strong>
                  ${selectedBadge}
                </div>
                <span class="badge ${verifBadgeClass}">${displayStatus}</span>
              </div>
              <p class="fix-desc">${this._escapeHtml(fix.description)}</p>

              ${diffHtml}

              <div class="checks-box">
                <div class="checks-title">Verification Outcome:</div>
                ${checksHtml}
                <div class="limitation-note">${this._escapeHtml(verif.limitation || "Static check validates syntax only.")}</div>
              </div>

              <div class="fix-actions">
                ${fixes.length > 1 ? `<button class="btn btn-secondary" onclick="selectFix('${fix.id}')">${isSelected ? "✓ Selected" : "Select fix"}</button>` : ""}
                <button class="btn btn-secondary" onclick="verifyFix('${fix.id}')" title="Run deterministic compiler & diagnostic verification">⚡ Verify</button>
                <button class="btn btn-secondary" onclick="runTests('${fix.id}')" title="Run automated test runner">🧪 Run Tests</button>
                <button class="btn btn-primary" ${isStale ? "disabled" : ""} onclick="applyFix('${fix.id}')">
                  Apply fix
                </button>
              </div>
            </div>
          `;
          })
          .join("")}
      </div>`;
    } else if (result.status === "unsupported") {
      fixesHtml = `
      <div class="section">
        <div class="unsupported-box">
          <strong>Deterministic Correction Unavailable</strong>
          <p>The source context was inspected, but this diagnostic cannot be corrected deterministically without risking semantic changes. Inspect the diagnostic details above.</p>
        </div>
      </div>`;
    }

    let chatThreadHtml = "";
    if (this._chatHistory.length === 0) {
      chatThreadHtml = `
      <div class="chat-placeholder">
        Type a short keyword to steer the discussion, or ask a question in your own words. Try: why · hint · explain · trace · fix · alternatives · compare · impact · example · simplify · verify.
      </div>`;
    } else {
      chatThreadHtml = this._chatHistory
        .map((msg) => {
          const roleClass = msg.role === "user" ? "chat-msg-user" : "chat-msg-assistant";
          const roleLabel = msg.role === "user" ? "You" : "Assistant";
          const formatted = this._formatMessageContent(msg.content);
          const time = msg.timestamp ? `<div class="chat-msg-time">${this._escapeHtml(msg.timestamp)}</div>` : "";
          return `
          <div class="chat-msg ${roleClass}">
            <div style="font-size: 0.78em; opacity: 0.8; margin-bottom: 2px; font-weight: 600;">${roleLabel}</div>
            <div>${formatted}</div>
            ${time}
          </div>`;
        })
        .join("");
    }

    let loadingIndicatorHtml = "";
    if (this._isChatLoading) {
      loadingIndicatorHtml = `
      <div class="chat-loading">
        <span class="chat-loading-dots">⏳</span> Working through your question...
      </div>`;
    }

    const dialogueHtml = `
    <div class="section conversation-section">
      <div class="section-header">💬 Talk through this issue</div>
      <p class="conversation-intro">Use a keyword as a command, then follow the thread wherever you need. Full questions are optional.</p>

      <div class="keyword-guide" aria-label="Keyword examples">
        <span>Try a keyword:</span>
        <button class="pill-btn" onclick="askQuestion('investigate')">investigate</button>
        <button class="pill-btn" onclick="askQuestion('why')">why</button>
        <button class="pill-btn" onclick="askQuestion('cause')">cause</button>
        <button class="pill-btn" onclick="askQuestion('evidence')">evidence</button>
        <button class="pill-btn" onclick="askQuestion('trace')">trace</button>
        <button class="pill-btn" onclick="askQuestion('diff')">diff</button>
        <button class="pill-btn" onclick="askQuestion('verify')">verify</button>
        <button class="pill-btn" onclick="askQuestion('tests')">tests</button>
        <button class="pill-btn" onclick="askQuestion('alternatives')" ${!result.candidate_fixes || result.candidate_fixes.length < 2 ? 'disabled title="Available when multiple candidate fixes exist."' : ''}>alternatives</button>
        <button class="pill-btn" onclick="askQuestion('compare')" ${!result.candidate_fixes || result.candidate_fixes.length < 2 ? 'disabled title="Available when multiple candidate fixes exist."' : ''}>compare</button>
        <button class="pill-btn" onclick="askQuestion('impact')">impact</button>
        <button class="pill-btn" onclick="askQuestion('risks')">risks</button>
        <button class="pill-btn" onclick="askQuestion('history')">history</button>
        <button class="pill-btn" onclick="askQuestion('next')">next</button>
      </div>

      <div class="chat-thread" id="chatThread" role="log" aria-live="polite" aria-label="Issue conversation">
        ${chatThreadHtml}
        ${loadingIndicatorHtml}
      </div>

      <div class="chat-input-bar">
        <label class="sr-only" for="chatInput">Ask a follow-up question about this issue</label><input type="text" id="chatInput" aria-label="Ask a follow-up question about this issue" placeholder="Type a keyword (why, hint, fix…) or ask your own question" onkeydown="handleChatKey(event)" ${isStale || this._isChatLoading ? "disabled" : ""} />
        <button class="btn btn-primary" onclick="sendChatInput()" ${isStale || this._isChatLoading ? "disabled" : ""}>Send</button>
      </div>
    </div>`;

    let errorBanner = "";
    if (result.status === "error") {
      errorBanner = `
      <div class="error-banner">
        <strong>⚠️ Engine Error (${this._escapeHtml(result.category)})</strong>
        <p>${this._escapeHtml(result.error_message || "An unexpected error occurred during investigation.")}</p>
      </div>`;
    }

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    :root {
      color-scheme: light dark;
      --cm-bg: var(--vscode-sideBar-background, var(--vscode-editor-background));
      --cm-fg: var(--vscode-foreground);
      --cm-muted: var(--vscode-descriptionForeground);
      --cm-border: var(--vscode-panel-border, var(--vscode-widget-border));
    }
    body { color: var(--cm-fg); background: var(--cm-bg); }
    button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 2px; }
    input, textarea { color: var(--vscode-input-foreground); background: var(--vscode-input-background); border-color: var(--vscode-input-border, var(--cm-border)); }
    .stale-banner { color: var(--vscode-editorWarning-foreground, #f0c674); border-color: var(--vscode-editorWarning-foreground, #b58100); }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; scroll-behavior: auto !important; } }

    body {
      font-family: var(--vscode-font-family);
      color: var(--vscode-foreground);
      padding: 12px;
      line-height: 1.45;
      font-size: var(--vscode-font-size);
      margin: 0;
    }
    .badge {
      display: inline-block;
      padding: 2px 7px;
      font-size: 11px;
      font-weight: bold;
      border-radius: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .badge-error { background: #e51400; color: white; }
    .badge-warning { background: #d18e00; color: white; }
    .badge-verified { background: #388a34; color: white; }
    .badge-partially-verified { background: #b87a00; color: white; }
    .badge-failed { background: #a82020; color: white; }
    .badge-inconclusive { background: #6e7681; color: white; }
    .badge-not-checked { background: #6e7681; color: white; }
    .badge-observed { background: #2ea043; color: white; }
    .badge-inferred { background: #d29922; color: #1e1e1e; font-weight: bold; }
    .badge-unverified { background: #8957e5; color: white; }

    .header-card {
      background: var(--vscode-editor-background);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .meta-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .source-tag {
      background: var(--vscode-badge-background);
      color: var(--vscode-badge-foreground);
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .loc-tag {
      color: var(--vscode-descriptionForeground);
      font-size: 12px;
    }
    .diag-msg {
      font-size: 1.05em;
      font-weight: 600;
      color: var(--vscode-editorError-foreground);
      word-break: break-word;
    }

    .cause-card {
      background: rgba(0, 122, 204, 0.12);
      border-left: 4px solid var(--vscode-textLink-foreground);
      border-radius: 4px;
      padding: 10px 12px;
      margin-bottom: 12px;
    }
    .cause-card .card-title {
      font-weight: bold;
      margin-bottom: 4px;
      color: var(--vscode-textLink-foreground);
      font-size: 0.95em;
    }
    .cause-card p {
      margin: 0;
      font-size: 0.9em;
    }

    .section {
      margin-bottom: 14px;
    }
    .section-header {
      font-weight: bold;
      font-size: 0.9em;
      text-transform: uppercase;
      color: var(--vscode-descriptionForeground);
      letter-spacing: 0.5px;
      margin-bottom: 6px;
      border-bottom: 1px solid var(--vscode-panel-border);
      padding-bottom: 4px;
    }

    .evidence-item {
      background: var(--vscode-editor-background);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
      padding: 8px 10px;
      margin-bottom: 8px;
    }
    .evidence-meta {
      font-size: 0.85em;
      margin-bottom: 4px;
    }
    .evidence-tag {
      color: var(--vscode-editorInfo-foreground);
      font-weight: bold;
      margin-right: 6px;
    }
    pre.snippet {
      background: var(--vscode-textCodeBlock-background);
      border: 1px solid rgba(128,128,128,0.2);
      padding: 6px 8px;
      border-radius: 4px;
      margin: 4px 0;
      font-family: var(--vscode-editor-font-family);
      font-size: 0.9em;
      overflow-x: auto;
    }
    .annotation {
      font-size: 0.85em;
      color: var(--vscode-descriptionForeground);
      margin-top: 4px;
    }

    .fix-card {
      background: var(--vscode-editor-background);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 10px;
    }
    .fix-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }
    .fix-desc {
      font-size: 0.9em;
      margin: 4px 0 8px 0;
      color: var(--vscode-descriptionForeground);
    }
    .checks-box {
      background: rgba(0,0,0,0.15);
      border-radius: 4px;
      padding: 8px;
      margin: 8px 0;
      font-size: 0.85em;
    }
    .checks-title {
      font-weight: bold;
      margin-bottom: 4px;
    }
    .check-item {
      margin: 3px 0;
    }
    .check-pass { color: #89d185; }
    .check-fail { color: #f48771; }
    .limitation-note {
      font-style: italic;
      color: var(--vscode-descriptionForeground);
      font-size: 0.8em;
      margin-top: 6px;
      border-top: 1px dotted rgba(128,128,128,0.3);
      padding-top: 4px;
    }

    .diff-box {
      background: var(--vscode-textCodeBlock-background);
      border: 1px solid rgba(128,128,128,0.25);
      border-radius: 4px;
      margin: 8px 0;
      overflow-x: auto;
      font-family: var(--vscode-editor-font-family);
      font-size: 0.85em;
    }
    .diff-header {
      background: rgba(0,0,0,0.18);
      padding: 4px 8px;
      font-weight: 600;
      font-size: 0.82em;
      color: var(--vscode-descriptionForeground);
      border-bottom: 1px solid rgba(128,128,128,0.2);
    }
    .diff-content {
      padding: 6px 8px;
      white-space: pre;
      line-height: 1.35;
    }
    .diff-add {
      color: #89d185;
      background: rgba(76, 175, 80, 0.12);
    }
    .diff-del {
      color: #f48771;
      background: rgba(244, 67, 54, 0.12);
    }
    .diff-info {
      color: #4ec9b0;
    }
    .diff-ctx {
      color: var(--vscode-editor-foreground);
    }

    .btn {
      cursor: pointer;
      padding: 6px 14px;
      border-radius: 4px;
      border: none;
      font-size: 0.9em;
      font-weight: 500;
    }
    .btn-primary {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
    }
    .btn-primary:hover {
      background: var(--vscode-button-hoverBackground);
    }
    .btn-secondary {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
      margin-top: 6px;
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .stale-banner {
      background: rgba(209, 142, 0, 0.18);
      border: 1px solid #d18e00;
      border-radius: 4px;
      padding: 10px;
      margin-bottom: 12px;
      font-size: 0.88em;
    }
    .error-banner {
      background: rgba(229, 20, 0, 0.18);
      border: 1px solid #e51400;
      border-radius: 4px;
      padding: 10px;
      margin-bottom: 12px;
    }
    .unsupported-box {
      background: rgba(128,128,128,0.1);
      border: 1px dashed var(--vscode-panel-border);
      border-radius: 4px;
      padding: 12px;
      font-size: 0.9em;
      color: var(--vscode-descriptionForeground);
    }

    .fix-selected {
      border: 2px solid var(--vscode-focusBorder) !important;
      background: rgba(0, 122, 204, 0.08) !important;
    }
    .badge-selected {
      background: var(--vscode-focusBorder);
      color: white;
    }
    .record-meta-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      padding: 6px 10px;
      background: rgba(0,0,0,0.12);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
      font-size: 0.85em;
    }
    .record-meta-bar code {
      color: var(--vscode-textLink-foreground);
      font-weight: 600;
    }
    .risks-box {
      background: rgba(209, 142, 0, 0.12);
      border-left: 3px solid #d18e00;
      padding: 8px 12px;
      margin: 8px 0;
      border-radius: 4px;
      font-size: 0.85em;
    }
    .risks-title {
      font-weight: bold;
      margin-bottom: 4px;
      color: #d18e00;
    }
    .risks-box ul {
      margin: 0;
      padding-left: 18px;
    }
    .risks-box li {
      margin: 2px 0;
    }

    .pills-container {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }
    .pill-btn {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 14px;
      padding: 4px 10px;
      font-size: 0.82em;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .pill-btn:hover {
      background: var(--vscode-button-secondaryHoverBackground);
    }
    .conversation-intro {
      margin: 4px 0 12px;
      color: var(--vscode-descriptionForeground);
      line-height: 1.5;
      max-width: 78ch;
    }
    .pill-btn:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
    .pill-btn:focus-visible,
    .chat-input-bar button:focus-visible,
    .chat-input-bar input:focus-visible {
      outline: 2px solid var(--vscode-focusBorder);
      outline-offset: 2px;
    }
    .chat-thread {
      max-height: 320px;
      overflow-y: auto;
      border: 1px solid var(--vscode-panel-border);
      border-radius: 6px;
      padding: 10px;
      background: rgba(0, 0, 0, 0.15);
      margin-bottom: 8px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .chat-msg {
      max-width: 90%;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 0.88em;
      line-height: 1.4;
      word-break: break-word;
    }
    .chat-msg-user {
      align-self: flex-end;
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border-bottom-right-radius: 2px;
    }
    .chat-msg-assistant {
      align-self: flex-start;
      background: var(--vscode-sideBar-background);
      color: var(--vscode-foreground);
      border: 1px solid var(--vscode-panel-border);
      border-bottom-left-radius: 2px;
    }
    .chat-msg-time {
      font-size: 0.75em;
      opacity: 0.7;
      margin-top: 4px;
      text-align: right;
    }
    .chat-placeholder {
      color: var(--vscode-descriptionForeground);
      font-size: 0.85em;
      text-align: center;
      padding: 16px 8px;
      font-style: italic;
    }
    .chat-loading {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.85em;
      color: var(--vscode-descriptionForeground);
      padding: 6px 10px;
    }
    .chat-loading-dots {
      display: inline-block;
      animation: pulse 1.2s infinite;
    }
    .chat-input-bar {
      display: flex;
      gap: 6px;
    }
    .chat-input-bar input {
      flex: 1;
      padding: 6px 10px;
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border: 1px solid var(--vscode-input-border);
      border-radius: 4px;
      font-size: 0.88em;
      outline: none;
    }
    .chat-input-bar input:focus {
      border-color: var(--vscode-focusBorder);
    }
  </style>
</head>
<body>
  ${recordMetaBar}
  ${errorBanner}
  ${staleBanner}

  <div class="header-card">
    <div class="meta-bar">
      <span class="badge ${sevClass}">${sevLabel}</span>
      <span class="source-tag">${this._escapeHtml(result.category)}</span>
      <span class="source-tag">${this._escapeHtml(sourceLabel)}</span>
      <span class="loc-tag">Line ${line1}, Column ${col1}</span>
    </div>
    <div class="diag-msg">${this._escapeHtml(diag.message)}</div>
  </div>

  ${causeSymptomSection}

  <div class="section">
    <div class="section-header">Explanation</div>
    <p style="margin: 4px 0 6px 0; font-weight: 500;">${this._escapeHtml(expl?.summary || "")}</p>
    <p style="margin: 0; font-size: 0.9em; color: var(--vscode-descriptionForeground);">${this._escapeHtml(expl?.details || "")}</p>
    ${
      expl?.next_steps
        ? `<p style="margin: 6px 0 0 0; font-size: 0.85em; font-style: italic;"><strong>Recommended Action:</strong> ${this._escapeHtml(expl.next_steps)}</p>`
        : ""
    }
  </div>

  ${evidenceHtml}
  ${fixesHtml}
  ${risksHtml}
  ${dialogueHtml}

  <script>
    const vscode = acquireVsCodeApi();
    function applyFix(fixId) {
      vscode.postMessage({ command: 'applyFix', fixId: fixId });
    }
    function selectFix(fixId) {
      vscode.postMessage({ command: 'selectFix', fixId: fixId });
    }
    function verifyFix(fixId) {
      vscode.postMessage({ command: 'verifyFix', fixId: fixId });
    }
    function runTests(fixId) {
      vscode.postMessage({ command: 'runTests', fixId: fixId });
    }
    function showHistory() {
      vscode.postMessage({ command: 'showHistory' });
    }
    function reopenRecord(recordId) {
      vscode.postMessage({ command: 'reopenRecord', recordId: recordId });
    }
    function reinvestigate() {
      vscode.postMessage({ command: 'reinvestigate' });
    }
    function sendChatInput() {
      const inp = document.getElementById('chatInput');
      if (inp && inp.value && inp.value.trim()) {
        const text = inp.value.trim();
        inp.value = '';
        vscode.postMessage({ command: 'chatMessage', text: text });
      }
    }
    function askQuestion(text) {
      vscode.postMessage({ command: 'chatMessage', text: text });
    }
    function handleChatKey(event) {
      if (event.key === 'Enter') {
        sendChatInput();
      }
    }
    setTimeout(() => {
      const thread = document.getElementById('chatThread');
      if (thread) {
        thread.scrollTop = thread.scrollHeight;
      }
    }, 50);
  </script>
</body>
</html>`;
  }
}
