# Course Agent UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current decorative three-panel page with a Codex-inspired, light learning workspace whose percentage-based columns resize locally, whose preview can close, and whose existing course, chat, preview, upload, note, summary, and quiz workflows remain usable.

**Architecture:** Keep the existing static `index.html` + `styles.css` + `app.js` frontend and all current Python APIs. Rebuild the DOM into a semantic left navigation, central conversation, and right preview; keep layout state in browser storage as percentages; let each separator exchange space only between its adjacent panels. Add Python contract tests for the static UI surface and perform browser interaction checks for behaviors that require a real DOM.

**Tech Stack:** HTML5, CSS custom properties/grid/container queries, browser-native JavaScript, Python `unittest`, Codex in-app browser.

---

## File Map

- Modify: `web/index.html` - semantic three-column shell and all persistent controls.
- Modify: `web/styles.css` - Codex-inspired tokens, percentage grid, compact mode, preview states, responsive layouts.
- Modify: `web/app.js` - resize controller, persistence, preview tabs, file pickers, accessible file tree and focus behavior.
- Create: `tests/test_web_ui_contract.py` - static markup, styling, and JavaScript contract checks.
- Reference: `docs/superpowers/specs/2026-07-15-course-agent-ui-redesign-design.md` - approved behavior and visual constraints.

### Task 1: Lock the UI Contract and Rebuild the Semantic Shell

**Files:**
- Create: `tests/test_web_ui_contract.py`
- Modify: `web/index.html`

- [ ] **Step 1: Write the failing UI contract tests**

Create `tests/test_web_ui_contract.py` with this complete test module:

```python
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
STYLES = ROOT / "web" / "styles.css"
APP_JS = ROOT / "web" / "app.js"


class ElementCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class WebUiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.css = STYLES.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")
        parser = ElementCollector()
        parser.feed(cls.html)
        cls.elements = parser.elements
        cls.by_id = {
            attrs["id"]: (tag, attrs)
            for tag, attrs in cls.elements
            if attrs.get("id")
        }

    def test_semantic_three_column_shell_exists(self):
        required = {
            "appWorkspace",
            "courseSidebar",
            "leftResizer",
            "agentPanel",
            "rightResizer",
            "previewPanel",
            "previewToggle",
            "preview",
        }
        self.assertTrue(required.issubset(self.by_id))
        self.assertEqual(self.by_id["courseSidebar"][0], "aside")
        self.assertEqual(self.by_id["agentPanel"][0], "main")
        self.assertEqual(self.by_id["previewPanel"][0], "aside")

    def test_resizers_are_keyboard_accessible_separators(self):
        for element_id in ("leftResizer", "rightResizer"):
            _, attrs = self.by_id[element_id]
            self.assertEqual(attrs.get("role"), "separator")
            self.assertEqual(attrs.get("aria-orientation"), "vertical")
            self.assertEqual(attrs.get("tabindex"), "0")
            self.assertTrue(attrs.get("aria-label"))

    def test_preview_and_upload_controls_exist(self):
        for element_id in (
            "previewToggle",
            "previewTabFile",
            "previewTabSources",
            "previewTabInfo",
            "courseFilePicker",
            "chatFilePicker",
        ):
            self.assertIn(element_id, self.by_id)
        self.assertEqual(self.by_id["previewToggle"][0], "button")
        self.assertEqual(self.by_id["courseFilePicker"][1].get("type"), "file")
        self.assertEqual(self.by_id["chatFilePicker"][1].get("type"), "file")

    def test_percentage_layout_contract_is_declared(self):
        self.assertIn("--sidebar-share: 22%", self.css)
        self.assertIn("--preview-share: 31%", self.css)
        self.assertIn("100dvh", self.css)
        self.assertIn("grid-template-columns", self.css)

    def test_layout_controller_contract_is_declared(self):
        for name in (
            "setupResizableLayout",
            "moveLeftBoundary",
            "moveRightBoundary",
            "setPreviewOpen",
            "renderLayout",
            "local-course-agent-layout-v1",
        ):
            self.assertIn(name, self.js)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_web_ui_contract -v
```

Expected: failures for missing `courseSidebar`, `leftResizer`, `rightResizer`, preview tabs, file pickers, percentage CSS variables, and layout controller names.

- [ ] **Step 3: Replace the page shell while preserving API-bound IDs**

Rebuild `web/index.html` with this hierarchy. Preserve every ID referenced by the existing JavaScript, and use this exact structural core:

```html
<body>
  <a class="skip-link" href="#agentPanel">跳到课程对话</a>
  <div id="appWorkspace" class="workspace-shell">
    <aside id="courseSidebar" class="course-sidebar" aria-label="课程与资料">
      <header class="sidebar-brand">
        <span class="brand-mark" aria-hidden="true">LC</span>
        <span class="brand-copy"><b>本地课程助手</b><small>COURSE WORKSPACE</small></span>
      </header>

      <section class="sidebar-section course-section">
        <div class="section-label">课程</div>
        <div id="courseList" class="course-list empty">请先设置资料根目录</div>
      </section>

      <section class="sidebar-section file-section">
        <div class="section-label">资料</div>
        <div id="activeFileTree" class="active-file-tree"></div>
      </section>

      <footer class="sidebar-footer">
        <div class="service-status" aria-label="服务状态">
          <span id="aiStatus">AI：读取中</span>
          <span id="mineruStatus">MinerU：读取中</span>
        </div>
        <label for="rootFolder">资料根目录</label>
        <input id="rootFolder" placeholder="例如 D:\StudyMaterials" />
        <div class="sidebar-actions">
          <button id="saveRoot">设置目录</button>
          <button id="refreshCourses" class="secondary-button">刷新</button>
        </div>
        <input id="courseFilePicker" class="sr-only" type="file" multiple />
        <button id="courseFilePickerButton" class="secondary-button" disabled>添加课程资料</button>
        <div id="courseDropZone" class="drop-zone">也可拖入文件</div>
      </footer>
    </aside>

    <div id="leftResizer" class="column-resizer" role="separator"
      aria-label="调整课程栏与对话区" aria-orientation="vertical" tabindex="0"></div>

    <main id="agentPanel" class="agent-panel">
      <header class="agent-header">
        <div><h1 id="agentTitle">课程 Agent</h1><small id="courseMeta">选择一门课程开始学习</small></div>
        <div class="agent-header-actions">
          <span class="run-state"><i class="dot"></i><span id="runStateText">Idle</span></span>
          <button id="indexCourse" class="secondary-button" disabled>构建知识库</button>
          <button id="previewToggle" class="secondary-button" aria-expanded="true">隐藏预览</button>
        </div>
      </header>

      <nav class="study-toolbar" aria-label="学习工具">
        <button class="study-tab active" data-view="chat">对话</button>
        <button id="generateSummary" class="study-tab" disabled>摘要</button>
        <button id="generateQuiz" class="study-tab" disabled>练习题</button>
        <button id="notesToggle" class="study-tab" disabled>笔记</button>
        <label for="chatMode" class="sr-only">问答模式</label>
        <select id="chatMode" aria-label="问答模式">
          <option value="answer">资料答疑</option>
          <option value="socratic">启发模式</option>
          <option value="homework">作业提示</option>
          <option value="review">复习模式</option>
        </select>
      </nav>

      <div id="messages" class="messages" aria-live="polite"></div>
      <div class="composer-wrap">
        <div id="chatDropHint" class="chat-drop-hint">可拖入附件临时提问</div>
        <div class="composer">
          <input id="chatFilePicker" class="sr-only" type="file" multiple />
          <button id="chatFilePickerButton" class="attachment-button secondary-button" disabled aria-label="添加聊天附件">添加附件</button>
          <label for="question" class="sr-only">课程问题</label>
          <textarea id="question" placeholder="继续围绕当前课程资料提问…"></textarea>
          <button id="sendQuestion" disabled>发送</button>
        </div>
      </div>
    </main>

    <div id="rightResizer" class="column-resizer" role="separator"
      aria-label="调整对话区与资料预览" aria-orientation="vertical" tabindex="0"></div>

    <aside id="previewPanel" class="preview-panel" aria-label="资料预览">
      <header class="preview-header">
        <div><h2 id="previewTitle">资料预览</h2><small id="previewHint">选择文件或回答引用</small></div>
      </header>
      <div class="preview-tabs" role="tablist" aria-label="预览内容">
        <button id="previewTabFile" role="tab" aria-selected="true">当前文件</button>
        <button id="previewTabSources" role="tab" aria-selected="false">引用片段</button>
        <button id="previewTabInfo" role="tab" aria-selected="false">文件信息</button>
      </div>
      <div id="preview" class="preview-content">选择课程资料后在此预览。</div>
      <div id="previewSources" class="preview-content" hidden></div>
      <div id="previewInfo" class="preview-content" hidden></div>
    </aside>
  </div>

  <aside id="notesDrawer" class="notes-drawer" aria-hidden="true" aria-label="课程笔记">
    <div class="notes-head">
      <div><div class="notes-title">课程笔记</div><small>保存到当前课程</small></div>
      <button id="notesClose" class="secondary-button" aria-label="关闭课程笔记">关闭</button>
    </div>
    <label for="noteTitle">笔记标题</label>
    <input id="noteTitle" placeholder="例如：页表易错点" />
    <label for="noteContent">笔记内容</label>
    <textarea id="noteContent" placeholder="记录重点、错题或 AI 回答"></textarea>
    <button id="saveNote" disabled>保存笔记</button>
    <div id="notesList" class="notes-list"></div>
  </aside>
  <div id="toast" class="toast" role="status" aria-live="polite"></div>
  <script src="/app.js"></script>
</body>
```

Retain the existing `notesDrawer`, note fields, `saveNote`, `notesList`, and `toast` markup below the workspace.

- [ ] **Step 4: Run the contract tests and confirm only CSS/JS contract checks remain failing**

Run:

```bash
python3 -m unittest tests.test_web_ui_contract -v
```

Expected: semantic shell, separator, preview control, and file picker tests pass; CSS variable and JavaScript controller tests still fail.

- [ ] **Step 5: Commit the semantic shell**

```bash
git add web/index.html tests/test_web_ui_contract.py
git commit -m "test: define redesigned course workspace contract"
```

### Task 2: Build the Codex-Inspired Visual System and Responsive Grid

**Files:**
- Modify: `web/styles.css`
- Test: `tests/test_web_ui_contract.py`

- [ ] **Step 1: Add the approved design tokens and percentage grid**

Replace the old decorative background and three-card layout with these core rules, then style the existing controls consistently around them:

```css
:root {
  color-scheme: light;
  --sidebar-share: 22%;
  --preview-share: 31%;
  --left-handle-share: 0.6%;
  --right-handle-share: 0.6%;
  --center-share: 45.8%;
  --sidebar-bg: #e8ecef;
  --surface: #ffffff;
  --canvas: #f7f7f5;
  --surface-subtle: #fbfbfa;
  --border: #d4d9dd;
  --border-soft: #e1e3e3;
  --text: #20211f;
  --muted: #6d747a;
  --accent: #2f7d67;
  --accent-soft: #e4f1ed;
  --evidence: #b99a4b;
  --evidence-soft: #f7f2e5;
  --danger: #b42318;
  --focus: rgba(47, 125, 103, 0.32);
}

html, body { margin: 0; min-height: 100%; }
body {
  min-height: 100dvh;
  overflow: hidden;
  background: var(--canvas);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}

.workspace-shell {
  width: 100%;
  height: 100dvh;
  display: grid;
  grid-template-columns:
    var(--sidebar-share)
    var(--left-handle-share)
    minmax(0, var(--center-share))
    var(--right-handle-share)
    var(--preview-share);
  overflow: hidden;
  background: var(--canvas);
}

.course-sidebar { min-width: 0; background: var(--sidebar-bg); overflow: hidden; }
.agent-panel { min-width: 0; display: grid; grid-template-rows: auto auto 1fr auto; background: var(--surface-subtle); }
.preview-panel { min-width: 0; display: grid; grid-template-rows: auto auto 1fr; background: var(--surface); overflow: hidden; }

.column-resizer {
  position: relative;
  z-index: 5;
  background: var(--border-soft);
  cursor: col-resize;
  touch-action: none;
}
.column-resizer::before { content: ""; position: absolute; inset: 0 -0.35rem; }
.column-resizer:hover,
.column-resizer.dragging,
.column-resizer:focus-visible { background: var(--accent); outline: 0; }

.workspace-shell.sidebar-compact .brand-copy,
.workspace-shell.sidebar-compact .section-label,
.workspace-shell.sidebar-compact .course-label,
.workspace-shell.sidebar-compact .file-label,
.workspace-shell.sidebar-compact .sidebar-footer label,
.workspace-shell.sidebar-compact .sidebar-footer input,
.workspace-shell.sidebar-compact .service-status { display: none; }

.workspace-shell.preview-closed {
  --preview-share: 0%;
  --right-handle-share: 0%;
}
.workspace-shell.preview-closed .preview-panel,
.workspace-shell.preview-closed #rightResizer { opacity: 0; pointer-events: none; }
```

Use `0.25rem`/`0.5rem` spacing increments, radii no larger than `0.5rem`, visible focus rings, at least `2.75rem` primary targets, and no gradients.

- [ ] **Step 2: Add compact, overlay, and reduced-motion rules**

Add container-aware fallbacks without converting saved column shares to pixels:

```css
@media (max-width: 60rem) {
  .workspace-shell {
    --preview-share: 0% !important;
    --right-handle-share: 0% !important;
    --center-share: calc(100% - var(--sidebar-share) - var(--left-handle-share)) !important;
  }
  .preview-panel {
    position: fixed;
    inset: 3.5rem 0 0 auto;
    width: min(82%, 25rem);
    height: calc(100dvh - 3.5rem);
    z-index: 30;
    box-shadow: -1rem 0 2.5rem rgba(32, 33, 31, 0.14);
    transform: translateX(100%);
  }
  .workspace-shell.preview-overlay-open .preview-panel { transform: translateX(0); }
}

@media (max-width: 42rem) {
  .workspace-shell {
    --sidebar-share: 0% !important;
    --left-handle-share: 0% !important;
    --center-share: 100% !important;
  }
  .course-sidebar { position: fixed; inset: 0 auto 0 0; width: min(86%, 20rem); z-index: 40; transform: translateX(-100%); }
  .workspace-shell.sidebar-open .course-sidebar { transform: translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
```

- [ ] **Step 3: Run the CSS contract and all existing tests**

```bash
python3 -m unittest tests.test_web_ui_contract -v
python3 -m unittest discover -s tests -v
```

Expected: the percentage layout CSS test passes; only the JavaScript controller contract remains failing. Existing 19 tests remain passing.

- [ ] **Step 4: Commit the visual system**

```bash
git add web/styles.css tests/test_web_ui_contract.py
git commit -m "feat: add responsive light workspace styling"
```

### Task 3: Implement the Percentage Resize Controller and Preview Toggle

**Files:**
- Modify: `web/app.js`
- Test: `tests/test_web_ui_contract.py`

- [ ] **Step 1: Add the percentage state model**

Add this controller near the top of `web/app.js`, after the global UI state:

```javascript
const LAYOUT_STORAGE_KEY = "local-course-agent-layout-v1";
const HANDLE_SHARE = 0.6;
const COMPACT_THRESHOLD = 14;
const MIN_CENTER_SHARE = 34;
const MIN_PREVIEW_SHARE = 20;
const MAX_PREVIEW_SHARE = 44;
const MAX_SIDEBAR_SHARE = 32;

let layoutState = {
  sidebarShare: 22,
  previewShare: 31,
  previewOpen: true,
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function readLayoutState() {
  try {
    const stored = JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY) || "null");
    if (!stored) return;
    layoutState.sidebarShare = Number(stored.sidebarShare) || 22;
    layoutState.previewShare = Number(stored.previewShare) || 31;
    layoutState.previewOpen = stored.previewOpen !== false;
  } catch (error) {
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
  }
}

function saveLayoutState() {
  localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layoutState));
}

function measureCompactSidebarShare() {
  const workspace = $("appWorkspace");
  const sidebar = $("courseSidebar");
  const wasCompact = workspace.classList.contains("sidebar-compact");
  workspace.classList.add("sidebar-compact");
  const candidates = [
    sidebar.querySelector(".brand-mark"),
    ...sidebar.querySelectorAll(".course-icon, .file-icon"),
    sidebar.querySelector("#courseFilePickerButton"),
  ].filter(Boolean);
  const largest = Math.max(...candidates.map((node) => node.getBoundingClientRect().width));
  workspace.classList.toggle("sidebar-compact", wasCompact);
  return clamp((largest / workspace.clientWidth) * 100 + 1.5, 5.5, 9);
}

function centerShare() {
  return 100
    - layoutState.sidebarShare
    - HANDLE_SHARE
    - (layoutState.previewOpen ? layoutState.previewShare + HANDLE_SHARE : 0);
}

function renderLayout() {
  const workspace = $("appWorkspace");
  const compactMinimum = measureCompactSidebarShare();
  layoutState.sidebarShare = Math.max(layoutState.sidebarShare, compactMinimum);
  workspace.style.setProperty("--sidebar-share", `${layoutState.sidebarShare}%`);
  workspace.style.setProperty("--preview-share", layoutState.previewOpen ? `${layoutState.previewShare}%` : "0%");
  workspace.style.setProperty("--left-handle-share", `${HANDLE_SHARE}%`);
  workspace.style.setProperty("--right-handle-share", layoutState.previewOpen ? `${HANDLE_SHARE}%` : "0%");
  workspace.style.setProperty("--center-share", `${centerShare()}%`);
  workspace.classList.toggle("sidebar-compact", layoutState.sidebarShare < COMPACT_THRESHOLD);
  workspace.classList.toggle("preview-closed", !layoutState.previewOpen);
  workspace.classList.toggle(
    "preview-overlay-open",
    layoutState.previewOpen && window.matchMedia("(max-width: 60rem)").matches,
  );
  $("previewToggle").textContent = layoutState.previewOpen ? "隐藏预览" : "显示预览";
  $("previewToggle").setAttribute("aria-expanded", String(layoutState.previewOpen));
}

function moveLeftBoundary(deltaShare) {
  const compactMinimum = measureCompactSidebarShare();
  const next = clamp(layoutState.sidebarShare + deltaShare, compactMinimum, MAX_SIDEBAR_SHARE);
  const nextCenter = centerShare() - (next - layoutState.sidebarShare);
  if (nextCenter < MIN_CENTER_SHARE) return;
  layoutState.sidebarShare = next;
  renderLayout();
}

function moveRightBoundary(deltaShare) {
  if (!layoutState.previewOpen) return;
  const next = clamp(layoutState.previewShare - deltaShare, MIN_PREVIEW_SHARE, MAX_PREVIEW_SHARE);
  const nextCenter = centerShare() - (next - layoutState.previewShare);
  if (nextCenter < MIN_CENTER_SHARE) return;
  layoutState.previewShare = next;
  renderLayout();
}

function setPreviewOpen(open) {
  layoutState.previewOpen = Boolean(open);
  renderLayout();
  saveLayoutState();
}
```

- [ ] **Step 2: Bind pointer, keyboard, reset, resize, and persistence behavior**

Add these functions and call `setupResizableLayout()` during startup:

```javascript
function bindResizer(element, mover, reset) {
  element.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    element.setPointerCapture(event.pointerId);
    element.classList.add("dragging");
    let previousX = event.clientX;

    const onMove = (moveEvent) => {
      const deltaShare = ((moveEvent.clientX - previousX) / $("appWorkspace").clientWidth) * 100;
      previousX = moveEvent.clientX;
      mover(deltaShare);
    };
    const onUp = () => {
      element.classList.remove("dragging");
      element.removeEventListener("pointermove", onMove);
      element.removeEventListener("pointerup", onUp);
      saveLayoutState();
    };
    element.addEventListener("pointermove", onMove);
    element.addEventListener("pointerup", onUp);
  });

  element.addEventListener("keydown", (event) => {
    if (!new Set(["ArrowLeft", "ArrowRight"]).has(event.key)) return;
    event.preventDefault();
    mover(event.key === "ArrowRight" ? 0.75 : -0.75);
    saveLayoutState();
  });

  element.addEventListener("dblclick", () => {
    reset();
    renderLayout();
    saveLayoutState();
  });
}

function setupResizableLayout() {
  readLayoutState();
  bindResizer($("leftResizer"), moveLeftBoundary, () => { layoutState.sidebarShare = 22; });
  bindResizer($("rightResizer"), moveRightBoundary, () => { layoutState.previewShare = 31; });
  $("previewToggle").onclick = () => setPreviewOpen(!layoutState.previewOpen);
  window.addEventListener("resize", renderLayout);
  renderLayout();
}
```

Append `setupResizableLayout()` after the existing startup chain succeeds:

```javascript
loadConfig()
  .then(loadCourses)
  .then(() => {
    setupDragAndDrop();
    setupResizableLayout();
    setupFilePickers();
    setupPreviewTabs();
  })
  .catch((err) => {
    $("courseList").textContent = err.message;
  });
```

- [ ] **Step 3: Run the contract test and full Python suite**

```bash
python3 -m unittest tests.test_web_ui_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all contract tests and all existing tests pass.

- [ ] **Step 4: Commit the layout controller**

```bash
git add web/app.js tests/test_web_ui_contract.py
git commit -m "feat: add percentage-based resizable workspace"
```

### Task 4: Wire the File Tree, Preview Tabs, Citations, and File Pickers

**Files:**
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Test: `tests/test_web_ui_contract.py`

- [ ] **Step 1: Make the file tree semantic and collapsible**

Replace `renderNodes` with a version that uses `details`, `summary`, and real buttons:

```javascript
function renderNodes(nodes) {
  const fragment = document.createDocumentFragment();
  for (const node of nodes) {
    if (node.type === "folder") {
      const folder = document.createElement("details");
      folder.className = "tree-folder";
      folder.open = true;
      const summary = document.createElement("summary");
      summary.innerHTML = `<span class="file-icon folder-icon" aria-hidden="true"></span><span class="file-label">${escapeHtml(node.name)}</span>`;
      folder.appendChild(summary);
      const children = document.createElement("div");
      children.className = "tree-children";
      children.appendChild(renderNodes(node.children || []));
      folder.appendChild(children);
      fragment.appendChild(folder);
      continue;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "tree-file" + (activeFile?.id === node.id ? " active" : "");
    button.setAttribute("aria-label", `预览文件 ${node.name}`);
    button.innerHTML = `<span class="file-icon" aria-hidden="true"></span><span class="file-label">${escapeHtml(node.name)}</span>`;
    button.onclick = () => previewFile(node);
    fragment.appendChild(button);
  }
  return fragment;
}
```

Update `renderCourses` so the selected course's children render into `activeFileTree`, while `courseList` contains only course buttons. Preserve `selectCourse(course)` behavior.

- [ ] **Step 2: Implement preview tabs and source state**

Add this state and behavior:

```javascript
let activePreviewTab = "file";
let latestCitations = [];

function setPreviewTab(tabName) {
  activePreviewTab = tabName;
  const map = {
    file: ["previewTabFile", "preview"],
    sources: ["previewTabSources", "previewSources"],
    info: ["previewTabInfo", "previewInfo"],
  };
  for (const [name, [buttonId, panelId]] of Object.entries(map)) {
    const selected = name === tabName;
    $(buttonId).setAttribute("aria-selected", String(selected));
    $(panelId).hidden = !selected;
  }
}

function renderPreviewSources(citations) {
  latestCitations = citations || [];
  const host = $("previewSources");
  host.innerHTML = "";
  if (!latestCitations.length) {
    host.textContent = "当前回答没有引用来源。";
    return;
  }
  for (const citation of latestCitations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preview-source-item";
    button.textContent = `${citation.file_name}${citation.page ? ` · 第 ${citation.page} 页` : ""} · 片段 ${citation.chunk_index}`;
    button.onclick = () => previewByFileId(citation.file_id, citation.page || null);
    host.appendChild(button);
  }
}

function renderPreviewInfo(file) {
  $("previewInfo").innerHTML = file
    ? `<dl><dt>名称</dt><dd>${escapeHtml(file.name)}</dd><dt>类型</dt><dd>${escapeHtml(file.extension || "未知")}</dd><dt>大小</dt><dd>${formatBytes(file.size || 0)}</dd></dl>`
    : "尚未选择文件。";
}

function setupPreviewTabs() {
  $("previewTabFile").onclick = () => setPreviewTab("file");
  $("previewTabSources").onclick = () => setPreviewTab("sources");
  $("previewTabInfo").onclick = () => setPreviewTab("info");
  setPreviewTab("file");
}

function formatBytes(value) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
```

Replace `previewFile` and `previewByFileId` with these complete versions so citations can target PDF pages:

```javascript
async function previewFile(file, page = null) {
  activeFile = file;
  setPreviewOpen(true);
  setPreviewTab("file");
  renderPreviewInfo(file);
  renderCourses();
  $("previewTitle").textContent = file.name;
  const url = `/api/files/preview?id=${encodeURIComponent(file.id)}`;

  if (file.extension === ".pdf") {
    const pageUrl = `${url}${page ? `#page=${page}` : ""}`;
    $("preview").innerHTML = `
      <div class="pdf-preview-wrap">
        <iframe class="pdf-preview" src="${pageUrl}" title="${escapeHtml(file.name)}"></iframe>
        <a class="preview-fallback" href="${pageUrl}" target="_blank" rel="noopener">在新窗口打开 PDF</a>
      </div>`;
    return;
  }

  if ([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].includes(file.extension)) {
    $("preview").innerHTML = `<div class="image-preview-wrap"><img class="image-preview" src="${url}" alt="${escapeHtml(file.name)}" /></div>`;
    return;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error("资料预览加载失败");
  const text = await response.text();
  $("preview").innerHTML = `<pre class="text-preview">${escapeHtml(text)}</pre>`;
}

function previewByFileId(fileId, page = null) {
  const file = findFile(courses, fileId);
  if (file) previewFile(file, page);
}
```

In `appendMessage`, replace citation spans with real buttons and update the preview source list for assistant messages:

```javascript
if (role === "assistant" && citations.length) renderPreviewSources(citations);
for (const citation of citations) {
  const link = document.createElement("button");
  link.type = "button";
  link.className = "citation";
  link.textContent = `来源：${citation.file_name}${citation.page ? ` 第 ${citation.page} 页` : ""}，片段 ${citation.chunk_index}`;
  link.onclick = () => {
    setPreviewOpen(true);
    previewByFileId(citation.file_id, citation.page || null);
  };
  node.appendChild(link);
}
```

- [ ] **Step 3: Wire click-based file selection alongside drag and drop**

Add:

```javascript
function setupFilePickers() {
  $("courseFilePickerButton").onclick = () => $("courseFilePicker").click();
  $("courseFilePicker").onchange = (event) => {
    uploadCourseFiles([...event.target.files])
      .catch((error) => showToast(error.message))
      .finally(() => { event.target.value = ""; });
  };

  $("chatFilePickerButton").onclick = () => $("chatFilePicker").click();
  $("chatFilePicker").onchange = (event) => {
    pendingChatFiles = [...event.target.files];
    $("chatDropHint").textContent = `已附加 ${pendingChatFiles.length} 个文件，发送后临时读取。`;
    event.target.value = "";
  };
}
```

Enable both picker buttons in `selectCourse` and disable them when no course is selected.

- [ ] **Step 4: Add focus-safe notes drawer behavior**

Extend `setNotesDrawer`:

```javascript
let notesReturnFocus = null;

function setNotesDrawer(open) {
  const drawer = $("notesDrawer");
  drawer.classList.toggle("open", open);
  drawer.setAttribute("aria-hidden", open ? "false" : "true");
  if (open) {
    notesReturnFocus = document.activeElement;
    $("noteTitle").focus();
  } else if (notesReturnFocus instanceof HTMLElement) {
    notesReturnFocus.focus();
  }
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("notesDrawer").classList.contains("open")) {
    setNotesDrawer(false);
  }
});
```

- [ ] **Step 5: Run the full test suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all 19 existing tests plus all new UI contract tests pass.

- [ ] **Step 6: Commit the interactive workflow wiring**

```bash
git add web/app.js web/styles.css tests/test_web_ui_contract.py
git commit -m "feat: wire accessible course workspace interactions"
```

### Task 5: Browser Verification and Final Polish

**Files:**
- Modify if verification finds defects: `web/index.html`, `web/styles.css`, `web/app.js`
- Test: `tests/test_web_ui_contract.py`

- [ ] **Step 1: Start the local app and confirm a clean initial load**

Run:

```bash
python3 run.py
```

Open `http://127.0.0.1:8000`. Expected: no console errors; course sidebar, conversation, and preview fit the viewport with no horizontal scroll.

- [ ] **Step 2: Verify the percentage invariants in a desktop viewport**

At a desktop viewport, read `--sidebar-share`, `--center-share`, and `--preview-share` from `#appWorkspace`. Drag `#leftResizer` by a visible horizontal distance, read the three values again, and assert that sidebar and center changed while preview stayed identical. Then drag `#rightResizer`, read the values again, and assert that center and preview changed while sidebar stayed identical. Sum the three panel shares and the two visible handle shares and assert the result is `100%` within browser rounding tolerance.

- [ ] **Step 3: Verify compact mode and preview restore**

Drag the left boundary below `14%`. Expected: text labels hide, icons remain, and dragging can continue to the measured compact minimum. Close preview, verify preview and right separator collapse to `0%`, then reopen and verify the previous preview share and content return.

- [ ] **Step 4: Verify file and citation workflows**

Select a course, click a text/PDF/image file, ask a question, and click a citation. Expected: file clicks open the right preview; citation clicks open the source list and then the matching file; preview title and file info update; no popup is required except the explicit PDF fallback action.

- [ ] **Step 5: Verify narrow and mobile layouts**

Check at representative widths around `90rem`, `64rem`, `48rem`, and `23.5rem`, plus mobile landscape. Expected: no horizontal scrolling, preview becomes a closable overlay when necessary, and the course sidebar becomes a drawer on the narrowest layout.

- [ ] **Step 6: Verify accessibility and motion**

Use Tab/Shift+Tab through courses, files, toolbar, resizers, preview tabs, composer, and notes. Use arrow keys on both separators and Escape on the notes drawer. Enable reduced motion and verify preview transitions are effectively disabled.

- [ ] **Step 7: Run final automated verification**

```bash
python3 -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: all tests pass; no whitespace errors; only intended frontend and test files are modified.

- [ ] **Step 8: Commit any verification fixes**

If browser verification required changes:

```bash
git add web/index.html web/styles.css web/app.js tests/test_web_ui_contract.py
git commit -m "fix: polish responsive course workspace"
```

If no fixes were required, do not create an empty commit.
