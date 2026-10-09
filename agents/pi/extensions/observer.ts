// Passive observer for synthetic workshop sessions, not an OS audit or sandbox.
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, sep } from "node:path";
import type { ExtensionAPI, ExtensionContext, Theme } from "@earendil-works/pi-coding-agent";
import { Text, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";

const CARD = "workshop-observer";
const MAX_RECORD_BYTES = 4 * 1024 * 1024;
const MAX_PREVIEW_CHARS = 4096;
// Keep compact history for the complete recording segment; display pagination
// must not evict earlier turns or requests. Raw bodies remain only in the log.

interface Card {
  sequence: number;
  summary: string;
  logFile: string;
}

interface LoopScope {
  runId: number | null;
  turnIndex: number | null;
}

interface ToolStart extends LoopScope {
  requestId: number | null;
  toolNumber: number;
  at: number;
}

interface LoopRow extends LoopScope {
  sequence: number;
  type: string;
  summary: string;
  error: boolean;
  outcome?: "completed" | "aborted" | "error" | "unknown";
  toolNumber?: number | null;
  toolName?: "bash" | "read" | "edit" | "write" | "other";
  preview?: string;
  isError?: boolean;
}

interface LoopGroup extends LoopScope {
  key: string;
  rows: LoopRow[];
  runRows: LoopRow[];
}

interface LoopSnapshot {
  observerId: string;
  logFile: string;
  capturedAt: string;
  recording: boolean;
  activeTurnKey: string | null;
  groups: LoopGroup[];
  samples: ContextSample[];
}

function snapshotLoop(rows: LoopRow[], samples: ContextSample[], observerId: string, recording: boolean, logFile: string): LoopSnapshot {
  const groups = new Map<string, LoopGroup>();
  const runs = new Map<number, LoopRow[]>();
  let activeTurnKey: string | null = null;
  for (const original of rows) {
    // Liveness is evidence from the latest successful boundary, not inferred
    // independently for every unfinished historical turn.
    if (["agent_start", "agent_end", "agent_settled", "turn_end", "session_shutdown"].includes(original.type)) {
      activeTurnKey = null;
    } else if (original.type === "turn_start") {
      activeTurnKey = original.runId !== null && original.turnIndex !== null
        ? `${original.runId}:${original.turnIndex}` : null;
    }
    const row = { ...original }; // No live arrays/objects enter a display snapshot.
    if (row.runId !== null && ["agent_start", "agent_end", "agent_settled"].includes(row.type)) {
      const run = runs.get(row.runId) ?? [];
      run.push(row);
      runs.set(row.runId, run);
      continue;
    }
    const key = row.runId === null ? "unassociated" : `${row.runId}:${row.turnIndex}`;
    const group = groups.get(key) ?? {
      key, runId: row.runId, turnIndex: row.runId === null ? null : row.turnIndex, rows: [], runRows: [],
    };
    group.rows.push(row);
    groups.set(key, group);
  }
  const groupedRuns = new Set([...groups.values()].map(group => group.runId));
  for (const [runId, runRows] of runs) {
    if (!groupedRuns.has(runId)) {
      groups.set(`${runId}:null`, { key: `${runId}:null`, runId, turnIndex: null, rows: [], runRows });
    }
  }
  for (const group of groups.values()) {
    if (group.runId !== null) group.runRows = runs.get(group.runId) ?? [];
  }
  const firstSequence = (group: LoopGroup) => group.rows[0]?.sequence ?? group.runRows[0]?.sequence ?? 0;
  return {
    observerId, logFile, capturedAt: new Date().toISOString(), recording, activeTurnKey,
    groups: [...groups.values()].sort((a, b) => firstSequence(a) - firstSequence(b)),
    samples: samples.map(sample => ({ ...sample, composition: { ...sample.composition }, skills: { ...sample.skills } })),
  };
}

function groupLabel(group: LoopGroup): string {
  if (group.runId === null) return "Unassociated events";
  if (group.turnIndex === null) return `Run ${group.runId} · Outside turns`;
  return scopeLabel(group);
}

function turnOutcome(group: LoopGroup, snapshot: LoopSnapshot): string {
  if (group.turnIndex === null) return "no turn association";
  const end = group.rows.findLast(row => row.type === "turn_end");
  if (end) return end.outcome ?? "unknown";
  return snapshot.recording && snapshot.activeTurnKey === group.key
    ? "active · end not observed" : "unknown · end not observed";
}

function escapeControls(text: string): string {
  // Render terminal introducers and Unicode formatting controls literally.
  return text.replace(/[\u0000-\u001f\u007f-\u009f\p{Cf}\u2028\u2029]/gu,
    char => `\\u${char.codePointAt(0)!.toString(16).padStart(4, "0")}`);
}

// Best-effort recognition, not a shell parser or a confidentiality guarantee.
// Redact before escaping so quoted/header values remain recognizable. Never
// retain tool output, edit text, file contents or arbitrary extra arguments.
function toolPreview(value: unknown): string | undefined {
  if (typeof value !== "string") return;
  const secret = "(?:[\\w-]*(?:token|password|passwd|secret)|(?:[\\w-]*[_-])?api[_-]?key|authorization|credential)";
  const argument = `(?:"(?:\\\\.|[^"\\\\])*"|'[^']*'|[^\\s;&|]+)`;
  // Bound processing too: hostile/very long input must not make credential
  // recognition scan an entire multi-megabyte raw record on every tool start.
  const inputTruncated = value.length > MAX_PREVIEW_CHARS;
  let preview = value.slice(0, MAX_PREVIEW_CHARS)
    .replace(/\b(?:https?|ssh):\/\/[^\s/]+@/gi, match => match.slice(0, match.indexOf("://") + 3) + "[redacted]@")
    .replace(/\b(Authorization\s*:\s*)[^\r\n"']+/gi, "$1[redacted]")
    .replace(/\b(X-Api-Key\s*:\s*)[^\r\n"']+/gi, "$1[redacted]")
    .replace(new RegExp(`(\\b${secret}\\s*=\\s*)${argument}`, "gi"), "$1[redacted]")
    .replace(new RegExp(`(--${secret}(?:=|\\s+))${argument}`, "gi"), "$1[redacted]")
    .replace(new RegExp(`([?&]${secret}=)[^\\s&#"']+`, "gi"), "$1[redacted]")
    .replace(new RegExp(`((?:-u|--user)(?:=|\\s+))${argument}`, "gi"), "$1[redacted]");
  preview = escapeControls(preview);
  return inputTruncated || preview.length > MAX_PREVIEW_CHARS
    ? preview.slice(0, MAX_PREVIEW_CHARS) + " … [preview truncated]" : preview;
}

/** One interaction owns a stable snapshot; only recording health is live. */
class LoopPopup {
  private snapshot: LoopSnapshot;
  private selected = 0;
  private page: 1 | 2 | 3 = 1;
  private requestId: number | null = null;
  private offset = 0;
  private pageHeight = 1;
  private narrow = false;
  private showTurns = false;

  private capture: () => LoopSnapshot;
  private health: (observerId: string) => { text: string; warning: boolean };
  private theme: Theme;
  private height: () => number;
  private redraw: () => void;
  private done: () => void;

  constructor(
    capture: () => LoopSnapshot,
    health: (observerId: string) => { text: string; warning: boolean },
    theme: Theme,
    height: () => number,
    redraw: () => void,
    done: () => void,
  ) {
    this.capture = capture;
    this.health = health;
    this.theme = theme;
    this.height = height;
    this.redraw = redraw;
    this.done = done;
    this.snapshot = capture();
    this.selectLatest();
  }

  private selectLatest() {
    const lastTurn = this.snapshot.groups.findLastIndex(group => group.runId !== null && group.turnIndex !== null);
    this.selected = lastTurn >= 0 ? lastTurn : Math.max(0, this.snapshot.groups.length - 1);
  }

  handleInput(data: string) {
    if (matchesKey(data, "escape")) { this.done(); return; }
    if (matchesKey(data, "r") || matchesKey(data, "shift+r")) {
      const old = this.snapshot;
      const key = old.groups[this.selected]?.key;
      const oldRequest = this.currentRequest()?.requestId;
      this.snapshot = this.capture();
      const preserved = old.observerId === this.snapshot.observerId
        ? this.snapshot.groups.findIndex(group => group.key === key) : -1;
      if (preserved >= 0) { this.selected = preserved; this.requestId = oldRequest ?? null; }
      else { this.selectLatest(); this.requestId = null; }
      this.offset = 0;
    } else if (matchesKey(data, "pageUp")) this.offset = Math.max(0, this.offset - this.pageHeight);
    else if (matchesKey(data, "pageDown")) this.offset += this.pageHeight;
    else if (matchesKey(data, "tab") && this.narrow) this.showTurns = !this.showTurns;
    else if (matchesKey(data, "return") && this.narrow) this.showTurns = false;
    else if (this.page === 3 && (matchesKey(data, "[") || matchesKey(data, "]"))) {
      const requests = this.requests();
      const current = requests.findIndex(sample => sample.requestId === this.currentRequest()?.requestId);
      const next = Math.max(0, Math.min(requests.length - 1, current + (matchesKey(data, "[") ? -1 : 1)));
      this.requestId = requests[next]?.requestId ?? null;
      this.offset = 0;
    }
    else if (matchesKey(data, "1") || matchesKey(data, "2") || matchesKey(data, "3")) {
      this.page = matchesKey(data, "1") ? 1 : matchesKey(data, "2") ? 2 : 3;
      this.showTurns = false;
      this.offset = 0;
    }
    else {
      const previous = this.selected;
      if (matchesKey(data, "up")) this.selected--;
      else if (matchesKey(data, "down")) this.selected++;
      else if (matchesKey(data, "home")) this.selected = 0;
      else if (matchesKey(data, "end")) this.selectLatest();
      else return;
      this.selected = Math.max(0, Math.min(this.selected, this.snapshot.groups.length - 1));
      if (previous !== this.selected) { this.offset = 0; this.requestId = null; }
    }
    this.redraw();
  }

  private fg(name: Parameters<Theme["fg"]>[0], text: string): string {
    // Use subtle secondary text throughout the popup, including shared category labels.
    return this.theme.fg(name === "muted" ? "dim" : name, text);
  }

  private details(): string[] {
    const color = this.fg.bind(this);
    const group = this.snapshot.groups[this.selected];
    if (this.page === 3) return this.contextDetails();
    if (!group) return [color("muted", "No recorded loop events in this segment."), "",
      "Submit a task after closing this popup. Recording begins at session start."];
    if (this.page === 2) return this.toolDetails(group);
    const outcome = turnOutcome(group, this.snapshot);
    const completedWithErrors = outcome === "completed" && group.rows.some(row => row.error);
    const outcomeColor = completedWithErrors ? "warning" : outcome === "completed" ? "success" : outcome === "error" ? "error" :
      outcome === "aborted" ? "warning" : outcome.startsWith("active") ? "accent" : "muted";
    const lines = [color("accent", groupLabel(group)),
      color(outcomeColor, `Outcome: ${outcome}${completedWithErrors ? " · errors observed" : ""}`), ""];
    const eventLine = (row: LoopRow) => color(row.error ? "error" : row.outcome === "aborted" ? "warning" : row.outcome === "completed" ? "success" : "muted",
      `  ${popupSummary(row)}`);
    if (group.runId === null || group.turnIndex === null) {
      lines.push(color("accent", "EVENTS WITHOUT A KNOWN TURN"), ...group.rows.map(eventLine));
      lines.push("Turn unknown");
    } else {
      lines.push(color("accent", "OBSERVED CYCLE"));
      for (const [title, types] of [
        ["1  Request preparation", ["request_prepared"]],
        ["2  Model response", ["http_response", "assistant_finished"]],
        ["3  Tool activity", ["tool_requested", "tool_result", "tool_finished"]],
        ["4  Turn ending", ["turn_end"]],
      ] as const) {
        lines.push("", color("accent", title));
        const events = group.rows.filter(row => (types as readonly string[]).includes(row.type));
        if (!events.length) lines.push(color("muted", "  Not observed"));
        else if (types[0] === "tool_requested") {
          const count = (type: string) => events.filter(row => row.type === type).length;
          lines.push(`  ${count("tool_requested")} requests · ${count("tool_result")} results · ${count("tool_finished")} finishes observed`);
          if (events.some(row => row.error)) lines.push(color("error", "  At least one tool reported an error"));
        } else lines.push(...events.map(eventLine));
      }
    }
    lines.push("", color("accent", "RUN STATUS"));
    if (!group.runRows.length) lines.push(color("muted", "No run boundaries observed."));
    for (const [label, type] of [["Agent start", "agent_start"], ["Agent end", "agent_end"], ["Agent idle", "agent_settled"]]) {
      const events = group.runRows.filter(row => row.type === type);
      if (events.length) lines.push(...events.map(eventLine));
      else lines.push(color("muted", `${label}: Not observed`));
    }
    return lines;
  }

  private toolDetails(group: LoopGroup): string[] {
    const fg = this.fg.bind(this);
    const lines = [fg("muted", groupLabel(group)), fg("muted", "Tool inputs only."), ""];
    const calls = new Map<string, LoopRow[]>();
    for (const row of group.rows) {
      if (!row.toolName) continue;
      // Local numbers come only from saved starts. Each unassociated phase
      // stays separate: an absent start is not a license to invent a call.
      const key = row.toolNumber == null ? `event:${row.sequence}` : `tool:${row.toolNumber}`;
      const phases = calls.get(key) ?? [];
      phases.push(row);
      calls.set(key, phases);
    }
    if (!calls.size) lines.push(fg("muted", "No tool phases observed for this selection."));
    for (const [title, names] of [
      ["COMMANDS — BASH", ["bash"]],
      ["FILE-TOOL ACTIVITY", ["read", "edit", "write"]],
      ["OTHER TOOLS", ["other"]],
    ] as const) {
      const section = [...calls.values()].filter(rows => (names as readonly string[]).includes(rows[0].toolName!));
      if (!section.length) continue;
      lines.push(fg("accent", title));
      for (const rows of section) {
        const start = rows.find(row => row.type === "tool_requested");
        const first = start ?? rows[0];
        const name = first.toolName!;
        const labelColor = name === "read" ? "mdLink" : name === "edit" ? "warning" :
          name === "write" ? "syntaxKeyword" : "accent";
        lines.push("", fg("muted", `Tool ${first.toolNumber ?? "?"} · `) + fg(labelColor, name.toUpperCase()));
        if (name !== "other") lines.push(`${name === "bash" ? "Command" : "Path"}: ${start?.preview ??
          (start ? "Argument unavailable (missing or non-string)" : "Not observed")}`);
        for (const [label, type] of [["Tool requested", "tool_requested"], ["Result received", "tool_result"], ["Tool finished", "tool_finished"]]) {
          const phases = rows.filter(row => row.type === type);
          if (!phases.length) lines.push(fg("muted", `${label}: Not observed`));
          for (const row of phases) {
            const state = type === "tool_requested" ? "Yes" :
              row.isError === true ? "Error reported" : row.isError === false ? "No error reported" : "Outcome unknown";
            lines.push(fg(row.isError === true ? "error" : "muted", `${label}: ${state}`));
          }
        }
        const finish = rows.findLast(row => row.type === "tool_finished");
        const pending = this.snapshot.recording && !!start && this.snapshot.activeTurnKey === group.key;
        const outcome = rows.some(row => row.isError === true) ? "Error reported" :
          !finish ? (pending ? "Pending — finish not observed" : "Incomplete — finish not observed") :
          finish.isError === false ? "No error reported" : "Unknown — finish has no error flag";
        lines.push(fg(outcome === "Error reported" ? "error" : outcome === "No error reported" ? "success" : "muted",
          `Tool outcome: ${outcome}`), "");
      }
    }
    return lines;
  }

  private requests(): ContextSample[] {
    const sequences = new Set(this.snapshot.groups[this.selected]?.rows
      .filter(row => row.type === "request_prepared").map(row => row.sequence));
    return this.snapshot.samples.filter(sample => sequences.has(sample.sequence));
  }

  private currentRequest(): ContextSample | undefined {
    const requests = this.requests();
    return requests.find(sample => sample.requestId === this.requestId) ?? requests.at(-1);
  }

  private contextDetails(): string[] {
    const fg = this.fg.bind(this);
    const group = this.snapshot.groups[this.selected];
    const requests = this.requests();
    const sample = this.currentRequest();
    const lines = [fg("muted", group ? groupLabel(group) : "CONTEXT"),
      fg("muted", "Context · prepared JSON bytes"), ""];
    if (!sample) {
      lines.push(fg("muted", this.snapshot.samples.length
        ? "No prepared request recorded for this selection — size unknown, not zero."
        : "No recorded prepared requests in this segment — size unknown, not zero."));
    } else {
      lines.push(fg("muted", `Request ${sample.requestId} · ${requests.indexOf(sample) + 1}/${requests.length} in this ${group?.turnIndex == null ? "group" : "turn"}`),
        `Context size: ${sample.bytes} bytes · ${(sample.bytes / 1000).toFixed(2)} KB`,
        `Change since previous request: ${deltaLabel(sample.delta)}`,
        fg("muted", `Messages: ${sample.messages} · Tool results: ${sample.toolResults}`), "");
      // Cumulative rounding keeps the combined bar exactly 30 cells long.
      let total = 0;
      let cells = 0;
      const bar = CONTEXT_CATEGORIES.map(category => {
        total += sample.composition[category.key];
        const end = sample.bytes > 0 ? Math.round(30 * total / sample.bytes) : 0;
        const segment = fg(category.color, "█".repeat(end - cells));
        cells = end;
        return segment;
      }).join("");
      lines.push(bar);
      for (const category of CONTEXT_CATEGORIES) {
        lines.push(fg(category.color, `${category.label}: ${sample.composition[category.key]} bytes`));
      }
      lines.push("", fg("muted", "SKILL MARKERS"));
      const skills = sample.skills;
      if (!Object.values(skills).some(count => count > 0)) lines.push(fg("muted", "None identified"));
      if (skills.catalog) lines.push(fg("muted", `Skill lists: ${skills.catalog} messages`));
      if (skills.read) lines.push(fg("muted", `SKILL.md read results: ${skills.read} messages`));
      if (skills.expansion) lines.push(fg("muted", `Skill instructions: ${skills.expansion} messages`));
    }
    lines.push("", fg("accent", "CONTEXT OVER TIME"));
    for (const request of this.snapshot.samples) {
      const selected = request.requestId === sample?.requestId;
      lines.push(fg(selected ? "accent" : "muted",
        `${selected ? "▸ " : "  "}Request ${request.requestId}: ${(request.bytes / 1000).toFixed(2)} KB · ${scopeLabel(request)}`));
    }
    return lines;
  }

  render(width: number): string[] {
    const limit = Math.max(1, Math.floor(this.height()));
    const health = this.health(this.snapshot.observerId);
    const fg = this.fg.bind(this);
    this.narrow = width < 84;
    const resizeHint = () => {
      this.pageHeight = 1;
      return [fg("accent", `Observer · ${this.page === 1 ? "Cycle" : this.page === 2 ? "Tool details" : "Context"}`), fg(health.warning ? "error" : "muted", health.text),
        "Enlarge terminal · Esc close"].slice(0, limit).map(line => truncateToWidth(line, width));
    };
    if (width < 28 || limit < 12) return resizeHint();
    const inner = width - 4;
    const border = (left: string, right: string) => fg("border", left + "─".repeat(width - 2) + right);
    const row = (text: string) => fg("border", "│ ") + truncateToWidth(text, inner, "…", true) + fg("border", " │");
    const header = [border("╭", "╮"), row(fg("accent", this.narrow ? "Observer · Not paused" : "OBSERVER · Agent lifecycle")),
      row(fg(health.warning ? "error" : "success", health.text)),
      row(fg("muted", this.narrow ? `Snapshot ${this.snapshot.capturedAt.slice(11, 19)} UTC` :
        `Snapshot captured at ${this.snapshot.capturedAt.slice(11, 19)} UTC · ${this.snapshot.groups.length} history entries`)),
      row(fg(this.page === 1 ? "accent" : "muted", this.page === 1 ? "[1 Cycle]" : "1 Cycle") + " · " +
        fg(this.page === 2 ? "accent" : "muted", this.page === 2 ? "[2 Tool details]" : "2 Tool details") +
        " · " + fg(this.page === 3 ? "accent" : "muted", this.page === 3 ? "[3 Context]" : "3 Context")), border("├", "┤")];
    const controls = [
      this.narrow ? "↑↓ Turn · Tab List/Details · PgUp/PgDn" : "↑↓ Turn · Home/End First/Latest · PgUp/PgDn Details",
      ...(this.narrow ? [`${this.page === 3 ? "[/] Request · " : ""}Home/End · Enter Details`] : []),
      this.narrow ? "1/2/3 Page · R · Esc Close" :
        `${this.page === 3 ? "[/] Request · " : ""}1/2/3 Page · R Refresh · Esc Close · Agent not paused`,
    ];
    const footer = [border("├", "┤"),
      row(fg("muted", `Log: ${escapeControls(this.snapshot.logFile || "unavailable")}`)),
      ...new Text(controls.join("\n"), 0, 0).render(inner).map(line => row(fg("muted", line))), border("╰", "╯")];
    if (limit < header.length + footer.length + 1) return resizeHint();
    this.pageHeight = limit - header.length - footer.length;
    const sidebarWidth = this.narrow ? inner : 27;
    const detailWidth = this.narrow ? inner : inner - sidebarWidth - 3;
    const turnRows = this.snapshot.groups.map((group, index) => {
      const label = group.runId !== null && group.turnIndex !== null
        ? `R${group.runId} T${group.turnIndex + 1} · ${turnOutcome(group, this.snapshot).split(" · ")[0]}` : groupLabel(group);
      return fg(index === this.selected ? "accent" : "muted", `${index === this.selected ? "▸" : " "} ${label}`);
    });
    if (!turnRows.length) turnRows.push(fg("muted", "No turns recorded"));
    const listStart = Math.max(0, this.selected - Math.floor(Math.max(1, this.pageHeight - 1) / 2));
    const list = [fg("accent", "TURN HISTORY"), ...turnRows.slice(listStart, listStart + this.pageHeight - 1)];
    const details = new Text(this.details().join("\n"), 0, 0).render(detailWidth);
    this.offset = Math.max(0, Math.min(this.offset, details.length - this.pageHeight));
    const visibleDetails = details.slice(this.offset, this.offset + this.pageHeight);
    const body = Array.from({ length: this.pageHeight }, (_, index) => {
      if (this.narrow) return row((this.showTurns ? list : visibleDetails)[index] ?? "");
      return row(truncateToWidth(list[index] ?? "", sidebarWidth, "…", true) + fg("border", " │ ") + (visibleDetails[index] ?? ""));
    });
    return [...header, ...body, ...footer].slice(0, limit);
  }

  invalidate() { /* No cached themed strings or terminal-width layout. */ }
}

function scopeLabel(scope: LoopScope) {
  return `Run ${scope.runId ?? "?"} · Turn ${scope.turnIndex === null ? "?" : scope.turnIndex + 1}`;
}

/** Short popup labels; detailed raw/non-TUI summaries stay unchanged. */
function popupSummary(row: LoopRow): string {
  switch (row.type) {
    case "agent_start": return "Agent started";
    case "agent_end": return "Agent ended";
    case "agent_settled": return "Agent idle";
    case "request_prepared": return row.summary.replace(" (delivery not established)", "");
    case "http_response": return row.summary.replace("HTTP response hook:", "Response status:");
    case "assistant_finished": return row.summary.replace("Assistant finished:", "Response finished:")
      .replace("toolUse", "tool requested").replace("stop", "complete").replace("length", "length limit");
    case "tool_requested": return row.summary.replace(" (execution not established)", "");
    case "tool_finished": return row.summary.replace("error (may include abort/rejection)", "error reported");
    default: return row.summary;
  }
}

// Only known labels and observer-generated numbers enter lifecycle summaries.
// Tool-page input previews have their own bounded redaction/escaping above.
function loopSummary(type: string, data: Record<string, unknown>): string | undefined {
  const tool = `Tool ${data.toolNumber ?? "?"} ${["read", "bash", "edit", "write"].includes(data.toolName as string) ? data.toolName : "other"}`;
  switch (type) {
    case "agent_start": return "Agent loop started";
    case "agent_end": return "Agent ended; settlement may follow";
    case "agent_settled": return "Agent settled";
    case "turn_start": return "Turn started";
    case "turn_end": return `Turn ended: ${["completed", "aborted", "error"].includes(data.outcome as string) ? data.outcome : "unknown"}`;
    case "request_prepared": return `Request ${data.requestId} prepared (delivery not established)`;
    case "http_response": return `HTTP response hook: ${typeof data.status === "number" ? data.status : "unknown"}`;
    case "assistant_finished": return `Assistant finished: ${["stop", "length", "toolUse", "error", "aborted"].includes(data.stopReason as string) ? data.stopReason : "unknown"}`;
    case "tool_requested": return `${tool} requested (execution not established)`;
    case "tool_result": return `${tool} result received${data.isError === true ? " (error)" : ""}`;
    case "tool_finished": return `${tool} finished: ${data.isError === true ? "error (may include abort/rejection)" : data.isError === false ? "no error reported" : "unknown"}`;
    case "session_shutdown": return `Session shutdown; unfinished tool starts: ${Array.isArray(data.unfinishedToolCallIds) ? data.unfinishedToolCallIds.length : "unknown"}`;
  }
}

interface ContextSample extends LoopScope {
  requestId: number;
  sequence: number;
  bytes: number;
  delta: number | null;
  messages: number;
  toolResults: number;
  composition: Record<ContextCategory, number>;
  skills: { catalog: number; read: number; expansion: number };
}

const CONTEXT_CATEGORIES = [
  { key: "system", label: "System/developer", color: "syntaxKeyword" },
  { key: "definitions", label: "Tool definitions", color: "mdLink" },
  { key: "user", label: "User messages", color: "success" },
  { key: "assistant", label: "Assistant history", color: "accent" },
  { key: "results", label: "Tool results", color: "warning" },
  { key: "other", label: "Other/framing", color: "muted" },
] as const;
type ContextCategory = typeof CONTEXT_CATEGORIES[number]["key"];

function byteBar(bytes: number, maximum: number): string {
  return "█".repeat(maximum > 0 ? Math.round(20 * bytes / maximum) : 0);
}

function deltaLabel(delta: number | null): string {
  return delta === null ? "n/a" : `${delta >= 0 ? "+" : ""}${delta} bytes`;
}

/** Measurements use only the plain JSON snapshot, never serialize live data twice. */
function measureContext(payload: { messages: unknown[]; tools?: unknown }) {
  const bytes = Buffer.byteLength(JSON.stringify(payload));
  const composition: Record<ContextCategory, number> = { system: 0, definitions: 0, user: 0, assistant: 0, results: 0, other: 0 };
  const skills = { catalog: 0, read: 0, expansion: 0 };
  const calls = new Map<string, boolean | null>();
  let toolResults = 0;
  for (const value of payload.messages) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    const message = value as Record<string, unknown>;
    const role = message.role;
    const category = role === "system" || role === "developer" ? "system" :
      role === "user" ? "user" : role === "assistant" ? "assistant" : role === "tool" ? "results" : undefined;
    if (category) composition[category] += Buffer.byteLength(JSON.stringify(message));
    const text = typeof message.content === "string" ? message.content : Array.isArray(message.content)
      ? message.content.filter(block => block?.type === "text" && typeof block.text === "string").map(block => block.text).join("\n") : "";
    if (category === "system") {
      // Inspect one bounded-by-tags block with linear searches. A global lazy
      // regex would rescan the tail for every unmatched opening tag.
      const tag = "<available_skills>";
      const begin = text.indexOf(tag);
      const end = begin < 0 ? -1 : text.indexOf("</available_skills>", begin + tag.length);
      if (end >= 0) {
        const catalog = text.slice(begin + tag.length, end);
        if (catalog.includes("<skill>") && /<location>[^<]*SKILL\.md<\/location>/.test(catalog)) skills.catalog++;
      }
    }
    if (role === "user" && /^<skill name="[^"]+" location="[^"]+SKILL\.md">\n[\s\S]*\n<\/skill>(?:\n\n[\s\S]*)?$/.test(text)) skills.expansion++;
    if (role === "assistant" && Array.isArray(message.tool_calls)) {
      for (const call of message.tool_calls) {
        if (typeof call?.id !== "string") continue;
        let skillRead = false;
        if (call.function?.name === "read" && typeof call.function.arguments === "string") {
          try {
            const path = JSON.parse(call.function.arguments)?.path;
            skillRead = typeof path === "string" && /(?:^|\/)SKILL\.md$/.test(path);
          } catch { /* Malformed arguments cannot identify a skill read. */ }
        }
        // Duplicate IDs are ambiguous, even when their arguments are identical.
        calls.set(call.id, calls.has(call.id) ? null : skillRead);
      }
    }
    if (role === "tool") {
      toolResults++;
      if (typeof message.tool_call_id === "string" && calls.get(message.tool_call_id) === true) skills.read++;
    }
  }
  // Conservatively classify only wholly recognizable function-definition
  // arrays; unknown/mixed arrays stay in Other rather than imply schema bytes.
  if (Array.isArray(payload.tools) && payload.tools.every(tool => {
    const schema = tool?.function?.parameters;
    return tool?.type === "function" && typeof tool.function?.name === "string" && tool.function.name.length > 0 &&
      (schema === undefined || (schema !== null && typeof schema === "object" && !Array.isArray(schema)));
  })) composition.definitions = Buffer.byteLength(JSON.stringify(payload.tools));
  composition.other = bytes - Object.values(composition).reduce((sum, count) => sum + count, 0);
  return { bytes, composition, skills, messages: payload.messages.length, toolResults };
}

function contextSummary(samples: ContextSample[]): string[] {
  if (!samples.length) return ["No recorded prepared requests in this segment — size unknown, not zero."];
  const maximum = samples.reduce((largest, sample) => Math.max(largest, sample.bytes), 0);
  const lines = [`Showing all ${samples.length} recorded requests in this segment. Bars relative to segment maximum (rounded).`];
  for (const sample of samples) lines.push(
    `Request ${sample.requestId} #${sample.sequence} ${byteBar(sample.bytes, maximum)} ${(sample.bytes / 1000).toFixed(2)} KB ` +
    `(${sample.bytes} bytes); delta ${deltaLabel(sample.delta)}; messages ${sample.messages}; tool results ${sample.toolResults}; ${scopeLabel(sample)}`);
  lines.push(`Cumulative prepared JSON, displayed requests ${samples[0].requestId}–${samples.at(-1)!.requestId}: ${samples.reduce((sum, sample) => sum + sample.bytes, 0)} bytes`,
    "UTF-8 JSON; 1 KB = 1,000 bytes (rounded). Deltas compare the previous recorded request.",
    "Totals repeat earlier context; not unique information, not tokens, delivery or cost.");
  return lines;
}

export default function (pi: ExtensionAPI) {
  let fd: number | undefined;
  let logFile = "";
  let observerId = "";
  let sequence = 0;
  let requestId = 0;
  let problem: string | undefined;
  let runCounter = 0;
  let runId: number | null = null;
  let endedRunId: number | null = null;
  let turnIndex: number | null = null;
  let activeRequestId: number | null = null;
  let toolCounter = 0;
  const starts = new Map<string, ToolStart>();
  const results = new Set<string>();
  const contextSamples: ContextSample[] = [];
  const loopRows: LoopRow[] = [];
  let popup: { redraw: () => void; close: () => void } | undefined;

  function toolScope(toolCallId: string) {
    const start = starts.get(toolCallId);
    return {
      runId: start?.runId ?? null, turnIndex: start?.turnIndex ?? null,
      requestId: start?.requestId ?? null, toolNumber: start?.toolNumber ?? null,
    };
  }

  pi.registerFlag("workshop-log-dir", {
    type: "string",
    description: "Override ~/pi-log with an existing private directory outside the workspace",
  });
  pi.registerEntryRenderer<Card>(CARD, (entry, { expanded }) => {
    const card = entry.data;
    if (!card) return;
    return new Text(
      `[Workshop observation — not model context] #${Number.isSafeInteger(card.sequence) && card.sequence >= 0 ? card.sequence : "?"} ` +
        escapeControls(typeof card.summary === "string" ? card.summary : "Summary unavailable") +
        (expanded ? `\nRaw record: ${escapeControls(typeof card.logFile === "string" ? card.logFile : "Path unavailable")}` : ""),
      0, 0,
    );
  });

  function stopRecording(ctx: ExtensionContext, reason: string) {
    if (fd !== undefined) {
      try { fs.closeSync(fd); } catch { /* The recording failure is reported below. */ }
      fd = undefined;
    }
    problem = reason;
    const message = `Workshop observer incomplete: ${reason}`;
    ctx.ui.setStatus(CARD, message);
    popup?.redraw();
    if (ctx.hasUI) ctx.ui.notify(message, "error");
    else console.error(message);
  }

  function record(ctx: ExtensionContext, type: string, data: Record<string, unknown> = {}) {
    if (fd === undefined) return;
    try {
      const item = {
        schema: 1, observerId, sessionId: ctx.sessionManager.getSessionId(),
        sequence: ++sequence, timestamp: new Date().toISOString(), type,
        runId, turnIndex, requestId: activeRequestId, ...data,
      };
      // Serialize immediately without mutating the live event or provider payload.
      const line = JSON.stringify(item) + "\n";
      if (Buffer.byteLength(line) > MAX_RECORD_BYTES) {
        stopRecording(ctx, "event exceeds 4 MiB; raw record omitted, recording stopped");
        return;
      }
      const captured = JSON.parse(line);
      let sample: ContextSample | undefined;
      if (type === "request_prepared") {
        // Measure the recorded snapshot, without serializing live data again.
        const payload = captured.payload;
        const metrics = measureContext(payload);
        const previous = contextSamples.at(-1);
        sample = {
          requestId, sequence, runId: captured.runId, turnIndex: captured.turnIndex,
          ...metrics, delta: previous ? metrics.bytes - previous.bytes : null,
        };
      }
      if (fs.writeSync(fd, line) !== Buffer.byteLength(line)) throw new Error("Short log write");
      if (sample) contextSamples.push(sample);
      const loop = loopSummary(type, captured);
      if (loop !== undefined) {
        loopRows.push({
          sequence, type, runId: captured.runId, turnIndex: captured.turnIndex, summary: loop,
          error: captured.isError === true || captured.outcome === "error" || captured.stopReason === "error" ||
            (type === "http_response" && typeof captured.status === "number" && captured.status >= 400),
          ...(type === "turn_end" ? { outcome: ["completed", "aborted", "error"].includes(captured.outcome) ? captured.outcome : "unknown" } : {}),
          ...(["tool_requested", "tool_result", "tool_finished"].includes(type) ? {
            toolNumber: captured.toolNumber,
            toolName: ["bash", "read", "edit", "write"].includes(captured.toolName) ? captured.toolName : "other",
            ...(typeof captured.isError === "boolean" ? { isError: captured.isError } : {}),
            ...(type === "tool_requested" ? {
              preview: toolPreview(captured.toolName === "bash" ? captured.args?.command :
                ["read", "edit", "write"].includes(captured.toolName) ? captured.args?.path : undefined),
            } : {}),
          } : {}),
        });
      }
      // Advertise readiness only after a successful write. Recording must not
      // inject automatic cards (or tool-input previews) into the conversation.
      ctx.ui.setStatus(CARD, `Observer: recording · ${sequence} events · /observer`);
    } catch {
      // Do not echo an exception which could contain request/credential material.
      stopRecording(ctx, "cannot serialize or write an event; recording stopped");
    }
  }

  pi.on("session_start", (_event, ctx) => {
    popup?.close();
    contextSamples.length = 0;
    loopRows.length = 0;
    runCounter = 0;
    runId = null;
    endedRunId = null;
    turnIndex = null;
    activeRequestId = null;
    toolCounter = 0;
    logFile = "";
    observerId = "";
    try {
      if (fd !== undefined) fs.closeSync(fd);
      fd = undefined;
      problem = undefined;
      sequence = 0;
      requestId = 0;
      starts.clear();
      results.clear();
      const configured = pi.getFlag("workshop-log-dir");
      const location = configured === undefined ? join(homedir(), "pi-log") : configured;
      if (typeof location !== "string" || !isAbsolute(location)) {
        throw new Error("Expected an absolute log directory");
      }
      const directory = fs.realpathSync(location);
      const info = fs.statSync(directory);
      const fromWorkspace = relative(fs.realpathSync(ctx.cwd), directory);
      if (!info.isDirectory() || !process.getuid || info.uid !== process.getuid() ||
          (info.mode & 0o077) !== 0 ||
          !(fromWorkspace === ".." || fromWorkspace.startsWith(`..${sep}`) || isAbsolute(fromWorkspace))) {
        throw new Error("Log directory is not private and outside the workspace");
      }
      observerId = randomUUID();
      logFile = join(directory, `${observerId}.jsonl`);
      fd = fs.openSync(logFile, "wx", 0o600);
      record(ctx, "session_start", {
        provider: ctx.model?.provider ?? null, model: ctx.model?.id ?? null,
        activeTools: pi.getActiveTools(),
        coverage: "Pi lifecycle and prepared ollama/openai-completions bodies; not endpoint policy, OS access or delivery proof",
      });
    } catch {
      stopRecording(ctx, "create ~/pi-log (0700) outside the workspace or supply --workshop-log-dir with an owned private directory");
    }
  });

  pi.on("agent_start", (_event, ctx) => {
    if (fd === undefined) return;
    runId = ++runCounter;
    endedRunId = null;
    turnIndex = null;
    activeRequestId = null;
    record(ctx, "agent_start");
  });
  pi.on("turn_start", (event, ctx) => {
    if (fd === undefined) return;
    turnIndex = Number.isSafeInteger(event.turnIndex) && event.turnIndex >= 0 ? event.turnIndex : null;
    activeRequestId = null;
    record(ctx, "turn_start");
  });
  pi.on("turn_end", (event, ctx) => {
    if (fd === undefined) return;
    const matched = turnIndex !== null && turnIndex === event.turnIndex;
    record(ctx, "turn_end", {
      runId: matched ? runId : null,
      turnIndex: Number.isSafeInteger(event.turnIndex) && event.turnIndex >= 0 ? event.turnIndex : null,
      requestId: matched ? activeRequestId : null, outcome: event.outcome,
    });
    if (matched) { turnIndex = null; activeRequestId = null; }
  });
  pi.on("agent_end", (_event, ctx) => {
    if (fd === undefined) return;
    turnIndex = null;
    activeRequestId = null;
    record(ctx, "agent_end");
    endedRunId = runId;
    runId = null;
  });
  pi.on("agent_settled", (_event, ctx) => {
    if (fd === undefined) return;
    turnIndex = null;
    activeRequestId = null;
    record(ctx, "agent_settled", { runId: runId ?? endedRunId });
    runId = null;
    endedRunId = null;
  });

  pi.on("before_provider_request", (event, ctx) => {
    if (fd === undefined) return;
    const payload = event.payload;
    // Reuse the preparation observer's Ollama chat-completions body contract.
    // This is passive recording, not endpoint authorization or a request blocker.
    // Do not subscribe to before_provider_headers or record response headers.
    if (ctx.model?.provider !== "ollama" || ctx.model?.api !== "openai-completions" ||
        !payload || typeof payload !== "object" ||
        !Array.isArray((payload as { messages?: unknown }).messages) ||
        Object.keys(payload).some(key => ["headers", "authorization", "apikey", "api_key", "httpoptions"].includes(key.toLowerCase()))) {
      stopRecording(ctx, "unexpected request shape/provider; no raw body recorded");
      return;
    }
    activeRequestId = ++requestId;
    record(ctx, "request_prepared", { delivery: "not established", payload });
  });

  pi.on("after_provider_response", (event, ctx) => {
    // HTTP success is not stream completion; headers can carry authentication.
    record(ctx, "http_response", { status: event.status });
  });

  pi.on("message_end", (event, ctx) => {
    if (event.message.role === "assistant") {
      record(ctx, "assistant_finished", {
        stopReason: event.message.stopReason,
      });
    }
  });

  pi.on("tool_execution_start", (event, ctx) => {
    if (fd === undefined) return;
    if (starts.has(event.toolCallId)) {
      stopRecording(ctx, "duplicate active tool-call ID; association ambiguous, recording stopped");
      return;
    }
    const scope = { runId, turnIndex, requestId: activeRequestId, toolNumber: ++toolCounter };
    starts.set(event.toolCallId, { ...scope, at: performance.now() });
    results.delete(event.toolCallId);
    // This event precedes validation/blocking. It does not prove execution.
    record(ctx, "tool_requested", {
      ...scope, toolCallId: event.toolCallId, toolName: event.toolName, args: event.args,
    });
  });

  pi.on("tool_result", (event, ctx) => {
    if (fd === undefined) return;
    results.add(event.toolCallId);
    record(ctx, "tool_result", {
      ...toolScope(event.toolCallId), toolCallId: event.toolCallId, toolName: event.toolName, input: event.input,
      content: event.content, details: event.details, isError: event.isError,
    });
  });

  pi.on("tool_execution_end", (event, ctx) => {
    if (fd === undefined) return;
    const start = starts.get(event.toolCallId);
    record(ctx, "tool_finished", {
      ...toolScope(event.toolCallId), toolCallId: event.toolCallId, toolName: event.toolName, isError: event.isError,
      observedDurationMs: start === undefined ? null : Math.round(performance.now() - start.at),
      resultHookObserved: results.has(event.toolCallId),
      // Preserve early rejection/abort results when there was no tool_result hook.
      ...(results.has(event.toolCallId) ? {} : { result: event.result }),
    });
    starts.delete(event.toolCallId);
    results.delete(event.toolCallId);
  });

  pi.on("session_shutdown", (_event, ctx) => {
    popup?.close();
    record(ctx, "session_shutdown", { unfinishedToolCallIds: [...starts.keys()] });
    if (fd !== undefined) {
      try {
        fs.closeSync(fd);
        fd = undefined;
        ctx.ui.setStatus(CARD, "Observer: stopped · recording closed");
      } catch { stopRecording(ctx, "cannot close the observation log"); }
    }
  });

  pi.registerCommand("observer", {
    description: "Open the Cycle/Tool details/Context popup without contacting a model",
    handler: async (args, ctx) => {
      if (args.trim()) {
        const usage = "Usage: /observer. Views are local; no model request.";
        if (ctx.hasUI) ctx.ui.notify(usage, "error");
        else console.error(usage);
        return;
      }
      if (ctx.mode === "tui") {
        if (popup) { ctx.ui.notify("Observer popup is already open.", "info"); return; }
        let interaction: { redraw: () => void; close: () => void } | undefined;
        try {
          await ctx.ui.custom<void>((tui, theme, _keybindings, done) => {
            interaction = { redraw: () => tui.requestRender(), close: () => done() };
            popup = interaction;
            return new LoopPopup(
              () => snapshotLoop(loopRows, contextSamples, observerId, fd !== undefined, logFile),
              snapshotId => {
                if (snapshotId !== observerId) return { text: "Recording segment changed · R refresh", warning: true };
                if (fd === undefined) return { text: `Recording incomplete: ${problem ?? "not recording"}`, warning: true };
                return { text: "Recording active · Display is a snapshot", warning: false };
              },
              theme, () => Math.floor(tui.terminal.rows * 0.9),
              interaction.redraw, interaction.close,
            );
          }, { overlay: true, overlayOptions: { width: "95%", maxHeight: "90%", margin: 1 } });
        } finally {
          if (popup === interaction) popup = undefined;
        }
        return;
      }
      const status = fd === undefined
        ? `Workshop observer incomplete: ${problem ?? "not recording"}`
        : `Workshop observer active: ${escapeControls(logFile)}`;
      const lines = [status, `Loop summary — segment ${observerId || "none"}`,
        `Showing all ${loopRows.length} recorded loop events in this segment.`];
      let group = "";
      for (const row of loopRows) {
        const label = scopeLabel(row);
        if (label !== group) { lines.push(label); group = label; }
        lines.push(`  #${row.sequence} ${row.summary}`);
      }
      if (!loopRows.length) lines.push("No recorded loop events in this segment.");
      lines.push(fd === undefined ? "Tool completion coverage unknown (not recording)." : `Tool starts awaiting finish: ${starts.size}`,
        "? = association unknown or outside a turn. Turns are not private reasoning.",
        "Tool numbers are local aliases; use #sequence in the raw log for provider tool-call IDs.",
        "Chronological recorded events, not OS access, execution/success or delivery proof; missing boundaries were not observed.");
      lines.push("", "CONTEXT — complete recording segment", ...contextSummary(contextSamples));
      const summary = lines.join("\n");
      // RPC supports notifications, not terminal components. Headless keeps
      // the same metadata-only summary; neither path appends a chat entry.
      if (ctx.hasUI) ctx.ui.notify(summary, "info");
      else console.error(summary);
    },
  });
}
