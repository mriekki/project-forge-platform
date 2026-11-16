'use strict';

const vscode = require('vscode');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { execFile } = require('child_process');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);
const WORK_ITEMS_RELATIVE = path.join('docs', 'work-items');
const ID_FROM_NAME = /^([A-Za-z][A-Za-z0-9]*-\d+)(?:-|$)/;
const ID_FROM_BRANCH = /(?:^|\/)([A-Za-z][A-Za-z0-9]*-\d+)(?:-|\/|$)/i;
const MARKER = /<!--\s*project-forge-work-item:\s*([A-Za-z][A-Za-z0-9]*-\d+)\s*-->/gi;
const REFRESH_INTERVAL_MS = 120000;
const REVIEW_TOOL_NAME = 'projectForge_openReviewArtifact';

function normalizeId(value) {
  return value ? value.toUpperCase() : undefined;
}

function workItemIdFromFolderName(name) {
  const match = ID_FROM_NAME.exec(name);
  return match ? normalizeId(match[1]) : undefined;
}

function workItemIdFromBranch(name) {
  const match = ID_FROM_BRANCH.exec(name || '');
  return match ? normalizeId(match[1]) : undefined;
}

function workItemIdsFromPr(pr) {
  const ids = new Set();
  const body = typeof pr.body === 'string' ? pr.body : '';
  MARKER.lastIndex = 0;
  for (let match = MARKER.exec(body); match; match = MARKER.exec(body)) {
    ids.add(normalizeId(match[1]));
  }
  const branchId = workItemIdFromBranch(pr.headRefName);
  if (branchId) {
    ids.add(branchId);
  }
  return ids;
}

async function run(command, args, cwd) {
  try {
    const result = await execFileAsync(command, args, {
      cwd,
      encoding: 'utf8',
      timeout: 6000,
      windowsHide: true,
      maxBuffer: 1024 * 1024,
    });
    return (result.stdout || '').trim();
  } catch {
    return undefined;
  }
}

async function readJsonCommand(command, args, cwd) {
  const output = await run(command, args, cwd);
  if (!output) {
    return undefined;
  }
  try {
    return JSON.parse(output);
  } catch {
    return undefined;
  }
}

async function defaultBranch(root) {
  const repo = await readJsonCommand('gh', ['repo', 'view', '--json', 'defaultBranchRef'], root);
  const fromGh = repo && repo.defaultBranchRef && repo.defaultBranchRef.name;
  if (fromGh) {
    return fromGh;
  }
  const remoteHead = await run('git', ['symbolic-ref', '--short', 'refs/remotes/origin/HEAD'], root);
  if (remoteHead && remoteHead.includes('/')) {
    return remoteHead.slice(remoteHead.lastIndexOf('/') + 1);
  }
  return 'main';
}

async function listWorkItemFolders(root) {
  const directory = path.join(root, WORK_ITEMS_RELATIVE);
  try {
    const entries = await fsp.readdir(directory, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => ({
        id: workItemIdFromFolderName(entry.name),
        uri: vscode.Uri.file(path.join(directory, entry.name)),
      }))
      .filter((entry) => entry.id);
  } catch {
    return [];
  }
}

async function githubPrEvidence(root) {
  const [openPrs, mergedPrs, base] = await Promise.all([
    readJsonCommand('gh', ['pr', 'list', '--state', 'open', '--limit', '100', '--json', 'number,body,headRefName,baseRefName,url'], root),
    readJsonCommand('gh', ['pr', 'list', '--state', 'merged', '--limit', '200', '--json', 'number,body,headRefName,baseRefName,mergedAt,url'], root),
    defaultBranch(root),
  ]);
  return {
    openPrs: Array.isArray(openPrs) ? openPrs : [],
    mergedPrs: Array.isArray(mergedPrs) ? mergedPrs : [],
    defaultBranch: base,
  };
}

async function computeRootStatus(root) {
  const folders = await listWorkItemFolders(root);
  if (!folders.length) {
    return { folders, statusById: new Map() };
  }

  const statusById = new Map();
  const evidence = await githubPrEvidence(root);

  for (const pr of evidence.mergedPrs) {
    if (pr.baseRefName !== evidence.defaultBranch) {
      continue;
    }
    for (const id of workItemIdsFromPr(pr)) {
      statusById.set(id, {
        state: 'complete',
        detail: `merged PR #${pr.number}`,
      });
    }
  }

  for (const pr of evidence.openPrs) {
    for (const id of workItemIdsFromPr(pr)) {
      statusById.set(id, {
        state: 'in-progress',
        detail: `open PR #${pr.number}`,
      });
    }
  }

  const branch = await run('git', ['branch', '--show-current'], root);
  const currentId = workItemIdFromBranch(branch);
  if (currentId) {
    statusById.set(currentId, {
      state: 'in-progress',
      detail: `current branch ${branch}`,
    });
  }

  return { folders, statusById };
}

function canonicalExistingPath(value) {
  try {
    return fs.realpathSync.native
      ? fs.realpathSync.native(value)
      : fs.realpathSync(value);
  } catch {
    return path.resolve(value);
  }
}

function isPathInside(root, candidate) {
  const canonicalRoot = canonicalExistingPath(root);
  const canonicalCandidate = canonicalExistingPath(candidate);
  const relative = path.relative(canonicalRoot, canonicalCandidate);
  return relative === '' || (
    relative !== '..' &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

function reviewTargetPath(target) {
  if (typeof target === 'string') {
    return target.trim();
  }
  if (target && typeof target.fsPath === 'string') {
    return target.fsPath;
  }
  if (target && typeof target.path === 'string') {
    return target.path.trim();
  }
  return '';
}

function isRegularFile(candidate) {
  try {
    return fs.statSync(candidate).isFile();
  } catch {
    return false;
  }
}

async function resolveReviewUri(target) {
  let requested = reviewTargetPath(target);
  if (!requested) {
    requested = (await vscode.window.showInputBox({
      prompt: 'Workspace-relative Project Forge review artifact path',
      placeHolder: 'docs/work-items/.../requirements.md',
      ignoreFocusOut: true,
    })) || '';
  }
  requested = requested.trim();
  if (!requested) {
    return undefined;
  }

  const folders = vscode.workspace.workspaceFolders || [];
  if (!folders.length) {
    throw new Error('No VS Code workspace is open.');
  }

  if (path.isAbsolute(requested)) {
    const candidate = canonicalExistingPath(requested);
    const owner = folders.find((folder) => isPathInside(folder.uri.fsPath, candidate));
    if (!owner) {
      throw new Error('Review artifact must be inside the open workspace.');
    }
    if (!isRegularFile(candidate)) {
      throw new Error(`Review artifact was not found: ${requested}`);
    }
    return vscode.Uri.file(candidate);
  }

  const matches = [];
  for (const folder of folders) {
    const candidate = canonicalExistingPath(path.resolve(folder.uri.fsPath, requested));
    if (!isPathInside(folder.uri.fsPath, candidate) || !isRegularFile(candidate)) {
      continue;
    }
    matches.push({ folder, uri: vscode.Uri.file(candidate) });
  }

  if (matches.length === 1) {
    return matches[0].uri;
  }
  if (!matches.length) {
    throw new Error(`Review artifact was not found in the open workspace: ${requested}`);
  }

  throw new Error(`Review artifact path is ambiguous across workspace folders: ${requested}`);
}

function requestedReviewMode(uri) {
  const extension = path.extname(uri.fsPath).toLowerCase();
  return extension === '.md' || extension === '.markdown'
    ? 'markdown-preview'
    : 'editor-preview';
}

async function presentReviewArtifact(target, options = {}) {
  const notify = options.notify !== false;
  let uri;
  try {
    uri = await resolveReviewUri(target);
    if (!uri) {
      return {
        status: 'cancelled',
        uri: null,
        requestedMode: null,
        openedMode: null,
        message: 'No review artifact was selected.',
      };
    }

    const requestedMode = requestedReviewMode(uri);
    if (requestedMode === 'markdown-preview') {
      try {
        await vscode.commands.executeCommand('markdown.showPreview', uri);
        return {
          status: 'opened',
          uri: uri.toString(),
          requestedMode,
          openedMode: 'rendered-markdown',
          message: 'Rendered Markdown preview opened.',
        };
      } catch {
        // Fall back to the normal editor preview surface when Markdown preview is unavailable.
      }
    }

    await vscode.commands.executeCommand('vscode.open', uri, {
      preview: true,
      preserveFocus: false,
    });
    return {
      status: 'opened',
      uri: uri.toString(),
      requestedMode,
      openedMode: 'editor-preview',
      message: requestedMode === 'markdown-preview'
        ? 'Rendered Markdown preview was unavailable; editor preview opened instead.'
        : 'Editor preview opened.',
    };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    if (notify) {
      await vscode.window.showWarningMessage(`Project Forge review artifact: ${message}`);
    }
    return {
      status: 'failed',
      uri: uri ? uri.toString() : null,
      requestedMode: uri ? requestedReviewMode(uri) : null,
      openedMode: null,
      message,
    };
  }
}

async function openReviewArtifact(target) {
  return presentReviewArtifact(target, { notify: true });
}

class OpenReviewArtifactTool {
  async invoke(options) {
    const result = await presentReviewArtifact(options && options.input, { notify: false });
    return new vscode.LanguageModelToolResult([
      new vscode.LanguageModelTextPart(JSON.stringify(result)),
    ]);
  }
}

class WorkItemDecorationProvider {
  constructor() {
    this._onDidChangeFileDecorations = new vscode.EventEmitter();
    this.onDidChangeFileDecorations = this._onDidChangeFileDecorations.event;
    this.byPath = new Map();
    this.uris = [];
  }

  provideFileDecoration(uri) {
    const entry = this.byPath.get(path.normalize(uri.fsPath));
    if (!entry) {
      return undefined;
    }
    if (entry.state === 'complete') {
      return {
        badge: '✓',
        color: new vscode.ThemeColor('gitDecoration.addedResourceForeground'),
        tooltip: `Project Forge: COMPLETE — ${entry.detail}`,
        propagate: false,
      };
    }
    if (entry.state === 'in-progress') {
      return {
        badge: '●',
        color: new vscode.ThemeColor('gitDecoration.modifiedResourceForeground'),
        tooltip: `Project Forge: IN PROGRESS — ${entry.detail}`,
        propagate: false,
      };
    }
    return undefined;
  }

  async refresh() {
    const next = new Map();
    const nextUris = [];
    const roots = (vscode.workspace.workspaceFolders || []).map((folder) => folder.uri.fsPath);

    for (const root of roots) {
      if (!fs.existsSync(path.join(root, WORK_ITEMS_RELATIVE))) {
        continue;
      }
      const result = await computeRootStatus(root);
      for (const folder of result.folders) {
        nextUris.push(folder.uri);
        const status = result.statusById.get(folder.id);
        if (status) {
          next.set(path.normalize(folder.uri.fsPath), status);
        }
      }
    }

    const changed = [...this.uris, ...nextUris];
    this.byPath = next;
    this.uris = nextUris;
    if (changed.length) {
      this._onDidChangeFileDecorations.fire(changed);
    }
  }

  dispose() {
    this._onDidChangeFileDecorations.dispose();
  }
}

function activate(context) {
  const provider = new WorkItemDecorationProvider();
  context.subscriptions.push(provider);
  context.subscriptions.push(vscode.window.registerFileDecorationProvider(provider));

  let refreshing = false;
  const refresh = async () => {
    if (refreshing) {
      return;
    }
    refreshing = true;
    try {
      await provider.refresh();
    } finally {
      refreshing = false;
    }
  };

  context.subscriptions.push(
    vscode.commands.registerCommand('projectForge.refreshWorkItemStatus', refresh),
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('projectForge.openReviewArtifact', openReviewArtifact),
  );

  if (
    vscode.lm &&
    typeof vscode.lm.registerTool === 'function' &&
    typeof vscode.LanguageModelToolResult === 'function' &&
    typeof vscode.LanguageModelTextPart === 'function'
  ) {
    context.subscriptions.push(
      vscode.lm.registerTool(REVIEW_TOOL_NAME, new OpenReviewArtifactTool()),
    );
  }

  context.subscriptions.push(
    vscode.window.onDidChangeWindowState((event) => {
      if (event.focused) {
        void refresh();
      }
    }),
  );

  for (const folder of vscode.workspace.workspaceFolders || []) {
    const head = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(folder, '.git/HEAD'),
    );
    const refs = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(folder, '.git/refs/heads/**'),
    );
    const workItems = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(folder, 'docs/work-items/*'),
    );
    for (const watcher of [head, refs, workItems]) {
      watcher.onDidChange(() => void refresh());
      watcher.onDidCreate(() => void refresh());
      watcher.onDidDelete(() => void refresh());
      context.subscriptions.push(watcher);
    }
  }

  const timer = setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
  void refresh();
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
  openReviewArtifact,
  presentReviewArtifact,
  resolveReviewUri,
};