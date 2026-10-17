import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  InvestigationRecord,
  InvestigationIndexEntry,
  InvestigationResult,
  DiagnosticInput,
} from "./types";

export class InvestigationStore {
  private static readonly INDEX_KEY = "compilermate.investigations.index";
  private static readonly MAX_EXCERPT_BYTES = 4096;

  constructor(private readonly context: vscode.ExtensionContext) {}

  /**
   * Resolves the local persistent directory for investigation records.
   * Prefers workspace folder (.compilermate/investigations) for project co-location.
   */
  public getStorageDirectory(): string {
    if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
      return path.join(
        vscode.workspace.workspaceFolders[0].uri.fsPath,
        ".compilermate",
        "investigations"
      );
    }
    if (this.context.globalStorageUri) {
      return path.join(this.context.globalStorageUri.fsPath, "investigations");
    }
    return path.join(process.cwd(), ".compilermate", "investigations");
  }

  /**
   * Ensures the persistent storage directory exists.
   */
  public ensureStorageDirectory(): string {
    const dir = this.getStorageDirectory();
    try {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
    } catch (e) {
      console.warn(`[InvestigationStore] Warning: Could not create directory ${dir}: ${e}`);
    }
    return dir;
  }

  /**
   * Constructs an InvestigationRecord from an InvestigationResult and document context.
   */
  public createRecord(
    result: InvestigationResult,
    document: vscode.TextDocument,
    initialDiagnostics?: DiagnosticInput[]
  ): InvestigationRecord {
    const now = new Date().toISOString();
    const id = result.record_id || `inv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const line0 = result.diagnostic?.range?.start?.line ?? 0;
    const lines = document.getText().split(/\r?\n/);
    const startLine = Math.max(0, line0 - 3);
    const endLine = Math.min(lines.length, line0 + 4);
    let excerpt = lines.slice(startLine, endLine).join("\n");
    if (excerpt.length > InvestigationStore.MAX_EXCERPT_BYTES) {
      excerpt = excerpt.slice(0, InvestigationStore.MAX_EXCERPT_BYTES) + "\n... [truncated for storage size limit]";
    }

    const verificationStatus =
      result.verification_report?.status ||
      (result.candidate_fixes && result.candidate_fixes.length > 0
        ? result.candidate_fixes[0].verification?.status
        : "NOT_CHECKED");

    // Compute source sha256 hash if not in metadata
    let sourceHash = String(result.metadata?.source_sha256 || "");
    if (!sourceHash) {
      try {
        const crypto = require("crypto");
        sourceHash = crypto.createHash("sha256").update(document.getText(), "utf-8").digest("hex");
      } catch {}
    }

    const record: InvestigationRecord = {
      id: id,
      created_at: now,
      updated_at: now,
      status:
        verificationStatus === "PASSED"
          ? "VERIFIED"
          : verificationStatus === "FAILED"
          ? "FAILED"
          : verificationStatus === "PARTIALLY_VERIFIED"
          ? "PARTIALLY_VERIFIED"
          : "OPEN",
      document_uri: document.uri.toString(),
      document_version: document.version,
      source_hash: sourceHash,
      source_excerpt: excerpt,
      diagnostic: result.diagnostic,
      problem_description: `[${result.category}] ${result.diagnostic.message} (Line ${line0 + 1})`,
      category: result.category,
      explanation: result.explanation || null,
      evidence: result.evidence || [],
      candidate_fixes: result.candidate_fixes || [],
      selected_fix_id: result.candidate_fixes && result.candidate_fixes.length > 0 ? result.candidate_fixes[0].id : null,
      verification_report: result.verification_report || null,
      decision_status: "PENDING",
      applied_diff: null,
      unresolved_risks: result.unresolved_risks || [],
      history: [],
      metadata: {
        ...result.metadata,
        initial_diagnostics: initialDiagnostics || (result.diagnostic ? [result.diagnostic] : []),
      },
    };

    return record;
  }

  /**
   * Persists an investigation record to disk and updates the index.
   */
  public async saveRecord(record: InvestigationRecord): Promise<void> {
    const dir = this.ensureStorageDirectory();
    record.updated_at = new Date().toISOString();

    // Enforce size limits on stored excerpt
    if (record.source_excerpt && record.source_excerpt.length > InvestigationStore.MAX_EXCERPT_BYTES) {
      record.source_excerpt = record.source_excerpt.slice(0, InvestigationStore.MAX_EXCERPT_BYTES) + "\n... [truncated]";
    }

    const filePath = path.join(dir, `${record.id}.json`);
    const payload = JSON.stringify(record, null, 2);
    try {
      fs.writeFileSync(filePath, payload, "utf-8");
    } catch (err) {
      console.error(`[InvestigationStore] Error saving record to ${filePath}:`, err);
    }

    // Fallback cache in workspaceState
    try {
      await this.context.workspaceState.update(`compilermate.record.${record.id}`, record);
    } catch (e) {
      console.warn(`[InvestigationStore] Error caching in workspaceState:`, e);
    }

    // Update in-memory / workspace index
    await this._updateIndex(record);
  }

  /**
   * Retrieves an investigation record by its unique ID.
   */
  public async getRecord(id: string): Promise<InvestigationRecord | undefined> {
    const dir = this.getStorageDirectory();
    const filePath = path.join(dir, `${id}.json`);
    if (fs.existsSync(filePath)) {
      try {
        const raw = fs.readFileSync(filePath, "utf-8");
        return JSON.parse(raw) as InvestigationRecord;
      } catch (err) {
        console.error(`[InvestigationStore] Error reading record ${id}:`, err);
      }
    }

    // Check global storage directory fallback
    if (this.context.globalStorageUri) {
      const globalPath = path.join(this.context.globalStorageUri.fsPath, "investigations", `${id}.json`);
      if (fs.existsSync(globalPath)) {
        try {
          const raw = fs.readFileSync(globalPath, "utf-8");
          return JSON.parse(raw) as InvestigationRecord;
        } catch (err) {
          console.error(`[InvestigationStore] Error reading global record ${id}:`, err);
        }
      }
    }

    // Check workspaceState fallback cache
    const cached = this.context.workspaceState.get<InvestigationRecord>(`compilermate.record.${id}`);
    if (cached) {
      return cached;
    }

    return undefined;
  }

  /**
   * Lists all saved investigation entries sorted by updated_at descending.
   */
  public async listRecords(): Promise<InvestigationIndexEntry[]> {
    const entriesMap = new Map<string, InvestigationIndexEntry>();

    const scanDirectory = (dir: string) => {
      if (fs.existsSync(dir)) {
        try {
          const files = fs.readdirSync(dir);
          for (const file of files) {
            if (file.endsWith(".json") && file !== "index.json") {
              try {
                const fullPath = path.join(dir, file);
                const content = fs.readFileSync(fullPath, "utf-8");
                const rec = JSON.parse(content) as InvestigationRecord;
                entriesMap.set(rec.id, this._recordToEntry(rec));
              } catch {}
            }
          }
        } catch (e) {
          console.warn(`[InvestigationStore] Error scanning directory ${dir}:`, e);
        }
      }
    };

    scanDirectory(this.getStorageDirectory());
    if (this.context.globalStorageUri) {
      scanDirectory(path.join(this.context.globalStorageUri.fsPath, "investigations"));
    }

    // Merge in index entries from workspaceState if any
    const indexed = this._getIndex();
    for (const item of indexed) {
      if (!entriesMap.has(item.id)) {
        entriesMap.set(item.id, item);
      }
    }

    const entries = Array.from(entriesMap.values());
    // Sort descending by updated_at
    entries.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    return entries;
  }

  /**
   * Deletes an investigation record from disk and index.
   */
  public async deleteRecord(id: string): Promise<boolean> {
    const dir = this.getStorageDirectory();
    const filePath = path.join(dir, `${id}.json`);
    let removed = false;
    if (fs.existsSync(filePath)) {
      try {
        fs.unlinkSync(filePath);
        removed = true;
      } catch (e) {
        console.error(`[InvestigationStore] Failed to delete file ${filePath}:`, e);
      }
    }

    if (this.context.globalStorageUri) {
      const globalPath = path.join(this.context.globalStorageUri.fsPath, "investigations", `${id}.json`);
      if (fs.existsSync(globalPath)) {
        try {
          fs.unlinkSync(globalPath);
          removed = true;
        } catch {}
      }
    }

    try {
      await this.context.workspaceState.update(`compilermate.record.${id}`, undefined);
    } catch {}

    const index = this._getIndex().filter((e) => e.id !== id);
    await this._setIndex(index);
    return removed;
  }

  /**
   * Finds records relevant to a given document URI.
   */
  public async findForDocument(documentUri: string): Promise<InvestigationRecord[]> {
    const all = await this.listRecords();
    const matches: InvestigationRecord[] = [];
    for (const entry of all) {
      if (entry.document_uri === documentUri) {
        const rec = await this.getRecord(entry.id);
        if (rec) {
          matches.push(rec);
        }
      }
    }
    return matches;
  }

  private _recordToEntry(rec: InvestigationRecord): InvestigationIndexEntry {
    const docName = rec.document_uri.split(/[/\\]/).pop() || "source.py";
    return {
      id: rec.id,
      created_at: rec.created_at,
      updated_at: rec.updated_at,
      status: rec.status,
      document_uri: rec.document_uri,
      document_name: docName,
      category: rec.category,
      problem_description: rec.problem_description,
      decision_status: rec.decision_status,
      has_diff: !!rec.applied_diff || !!(rec.candidate_fixes && rec.candidate_fixes.some((f) => !!f.diff)),
      verification_status: rec.verification_report?.status || (rec.candidate_fixes[0]?.verification?.status),
    };
  }

  private _getIndex(): InvestigationIndexEntry[] {
    return this.context.workspaceState.get<InvestigationIndexEntry[]>(InvestigationStore.INDEX_KEY, []);
  }

  private async _setIndex(index: InvestigationIndexEntry[]): Promise<void> {
    await this.context.workspaceState.update(InvestigationStore.INDEX_KEY, index);
  }

  private async _updateIndex(record: InvestigationRecord): Promise<void> {
    const index = this._getIndex().filter((e) => e.id !== record.id);
    index.unshift(this._recordToEntry(record));
    await this._setIndex(index);
  }
}
