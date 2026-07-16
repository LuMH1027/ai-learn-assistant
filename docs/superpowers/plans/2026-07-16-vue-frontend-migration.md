# Vue Frontend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the native browser application with a tested Vue 3 + Vite + TypeScript + Pinia frontend while preserving the current UI, Python API, local data, and cross-platform startup experience.

**Architecture:** A `frontend/` Vite application owns UI components, Pinia stores, API access, and tests. Vite builds into `web/dist/`; the existing Python handler continues to serve `/api/*` and serves only the built frontend for non-API requests. Shell and batch scripts build before starting Python.

**Tech Stack:** Vue 3, TypeScript, Vite, Pinia, Vitest, Vue Test Utils, Python 3 standard-library HTTP server.

---

### Task 1: Preserve the native UI baseline

**Files:**
- Commit: `web/index.html`, `web/app.js`, `web/styles.css`, `tests/test_web_ui_contract.py`

- [ ] **Step 1: Run the existing regression suite**

Run: `python3 -m unittest discover -s tests -v`  
Expected: 25 tests pass.

- [ ] **Step 2: Commit the verified native UI baseline**

```bash
git add web/index.html web/app.js web/styles.css tests/test_web_ui_contract.py
git commit -m "feat: redesign course learning workspace"
```

### Task 2: Scaffold the Vue toolchain

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `.gitignore`

- [ ] **Step 1: Create the minimal package manifest**

Declare scripts `dev`, `build`, `typecheck`, and `test`; runtime dependencies `vue` and `pinia`; development dependencies `@vitejs/plugin-vue`, `vite`, `typescript`, `vue-tsc`, `vitest`, `jsdom`, and `@vue/test-utils`.

- [ ] **Step 2: Install dependencies and generate the lockfile**

Run: `npm install --prefix frontend`  
Expected: exit 0 and `frontend/package-lock.json` exists.

- [ ] **Step 3: Add Vite and TypeScript configuration**

Configure `build.outDir` as `../web/dist`, `emptyOutDir: true`, Vue plugin, jsdom tests, setup file, and development proxy `'/api' -> 'http://127.0.0.1:8000'`.

- [ ] **Step 4: Write and run a failing smoke test**

Mount `App.vue` and assert the heading `课程 Agent` is visible.

Run: `npm test --prefix frontend -- --run src/App.test.ts`  
Expected: FAIL because `App.vue` does not exist.

- [ ] **Step 5: Add the minimal app component and verify the toolchain**

Run: `npm test --prefix frontend -- --run src/App.test.ts && npm run typecheck --prefix frontend && npm run build --prefix frontend`  
Expected: the test and both commands pass; `web/dist/index.html` exists.

- [ ] **Step 6: Commit**

```bash
git add .gitignore frontend
git commit -m "build: scaffold Vue frontend"
```

### Task 3: Define API types and HTTP boundary

**Files:**
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/services/api.ts`
- Test: `frontend/src/services/api.test.ts`

- [ ] **Step 1: Write failing API tests**

Test that `requestJson()` returns typed JSON, throws `ApiError` with the backend message for non-2xx responses, and `postFiles()` sends `FormData` without manually setting `Content-Type`.

- [ ] **Step 2: Verify RED**

Run: `npm test --prefix frontend -- --run src/services/api.test.ts`  
Expected: FAIL because `api.ts` does not exist.

- [ ] **Step 3: Implement types and API functions**

Define `Course`, `FileNode`, `Message`, `Citation`, `TraceStep`, `Note`, and config/result response types. Implement `requestJson<T>(path, init)`, `getJson<T>()`, `postJson<T>()`, and `postFiles<T>()`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `npm test --prefix frontend -- --run src/services/api.test.ts`  
Expected: PASS.

```bash
git add frontend/src/types frontend/src/services
git commit -m "feat: add typed frontend API client"
```

### Task 4: Implement the percentage layout store

**Files:**
- Create: `frontend/src/stores/layout.ts`
- Test: `frontend/src/stores/layout.test.ts`

- [ ] **Step 1: Write failing layout tests**

Cover defaults `22/31`, left movement preserving preview share, right movement preserving sidebar share, center minimum `34`, preview bounds `20..44`, boundary reset, persisted state, and mobile-first preview closed without saved state.

- [ ] **Step 2: Verify RED**

Run: `npm test --prefix frontend -- --run src/stores/layout.test.ts`  
Expected: FAIL because the store is missing.

- [ ] **Step 3: Implement `useLayoutStore`**

Expose `sidebarShare`, `previewShare`, `previewOpen`, computed `centerShare`, `moveLeftBoundary`, `moveRightBoundary`, `resetLeftBoundary`, `resetRightBoundary`, `setPreviewOpen`, `hydrate`, and `persist`. Use storage key `local-course-agent-layout-v1`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `npm test --prefix frontend -- --run src/stores/layout.test.ts`  
Expected: PASS.

```bash
git add frontend/src/stores/layout.ts frontend/src/stores/layout.test.ts
git commit -m "feat: add resizable layout store"
```

### Task 5: Implement course, chat, and preview stores

**Files:**
- Create: `frontend/src/stores/course.ts`
- Create: `frontend/src/stores/chat.ts`
- Create: `frontend/src/stores/preview.ts`
- Test: `frontend/src/stores/course.test.ts`
- Test: `frontend/src/stores/chat.test.ts`
- Test: `frontend/src/stores/preview.test.ts`

- [ ] **Step 1: Write failing store tests**

Test course loading/selection and context version increments; chat ignores stale course responses, clears attachments on course change, and prevents duplicate writes; preview restores after close, clears on course change, and retains citation page/quote.

- [ ] **Step 2: Verify RED**

Run: `npm test --prefix frontend -- --run src/stores`  
Expected: FAIL because stores are missing.

- [ ] **Step 3: Implement stores with injected API functions**

Use course ID plus context version before applying asynchronous results. Keep independent busy flags for indexing, chat, summary, and quiz. Store preview file URL as `/api/files/preview?id=<encoded id>`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `npm test --prefix frontend -- --run src/stores`  
Expected: PASS.

```bash
git add frontend/src/stores
git commit -m "feat: add course learning state stores"
```

### Task 6: Build the Vue workspace components

**Files:**
- Create: `frontend/src/components/ResizableWorkspace.vue`
- Create: `frontend/src/components/CourseSidebar.vue`
- Create: `frontend/src/components/FileTree.vue`
- Create: `frontend/src/components/ChatWorkspace.vue`
- Create: `frontend/src/components/FilePreview.vue`
- Create: `frontend/src/components/NotesDrawer.vue`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/components/workspace.test.ts`

- [ ] **Step 1: Write failing component tests**

Mount `App.vue` with Pinia and assert the semantic three-region shell, accessible separators, preview tabs, file inputs, busy button disabling, preview close/reopen, citation source rendering, and inert closed drawers.

- [ ] **Step 2: Verify RED**

Run: `npm test --prefix frontend -- --run src/components/workspace.test.ts`  
Expected: FAIL because components do not exist.

- [ ] **Step 3: Implement the components**

Move markup and behavior from the verified native UI into focused Vue components. Use template event bindings, refs for file inputs, pointer capture for separators, keyboard arrows, double-click reset, Escape handling, and store actions for all API operations.

- [ ] **Step 4: Verify GREEN and commit**

Run: `npm test --prefix frontend -- --run src/components/workspace.test.ts`  
Expected: PASS.

```bash
git add frontend/src/App.vue frontend/src/components
git commit -m "feat: build Vue course workspace"
```

### Task 7: Migrate the approved visual system

**Files:**
- Create: `frontend/src/styles.css`
- Modify: `frontend/src/main.ts`
- Test: `frontend/src/components/style-contract.test.ts`

- [ ] **Step 1: Write the failing style contract test**

Assert the stylesheet declares `--sidebar-share: 22%`, `--preview-share: 31%`, `100dvh`, responsive breakpoints, compact sidebar selectors, reduced motion, and no gradients.

- [ ] **Step 2: Verify RED**

Run: `npm test --prefix frontend -- --run src/components/style-contract.test.ts`  
Expected: FAIL because the stylesheet is missing.

- [ ] **Step 3: Port and component-scope the current CSS**

Preserve fog-gray sidebar, restrained green accent, amber evidence states, percentage grid, mobile 44px targets, overlay inert behavior, and no decorative gradients.

- [ ] **Step 4: Verify GREEN and commit**

Run: `npm test --prefix frontend -- --run src/components/style-contract.test.ts`  
Expected: PASS.

```bash
git add frontend/src/styles.css frontend/src/main.ts frontend/src/components/style-contract.test.ts
git commit -m "style: migrate course workspace visual system"
```

### Task 8: Serve the Vite build from Python

**Files:**
- Modify: `local_course_agent/server.py`
- Create: `tests/test_static_frontend.py`
- Delete after verification: `web/index.html`, `web/app.js`, `web/styles.css`
- Delete: `tests/test_web_ui_contract.py`

- [ ] **Step 1: Write failing Python tests**

Assert `STATIC_DIR == PROJECT_ROOT / "web" / "dist"`, root resolves to `dist/index.html`, normalized assets remain under `dist`, and missing build output returns an actionable message.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_static_frontend -v`  
Expected: FAIL because static files still point to `web/`.

- [ ] **Step 3: Implement static build serving**

Point `STATIC_DIR` to `web/dist`, keep `/api/*` routing unchanged, constrain resolved paths to the static root, and return a clear build instruction when `index.html` is missing.

- [ ] **Step 4: Verify GREEN, remove legacy frontend, and commit**

Run: `python3 -m unittest discover -s tests -v`  
Expected: all Python tests pass.

```bash
git add local_course_agent/server.py tests web
git commit -m "refactor: serve compiled Vue frontend"
```

### Task 9: Add cross-platform startup and documentation

**Files:**
- Create: `start.sh`
- Modify: `start.bat`
- Modify: `README.md`
- Modify: `.gitignore`
- Test: `tests/test_startup_contract.py`

- [ ] **Step 1: Write failing startup contract tests**

Assert both scripts install only when `node_modules` is absent, run the frontend build, then launch Python; assert README lists Node.js, both scripts, development commands, and production build behavior.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_startup_contract -v`  
Expected: FAIL because `start.sh` and updated documentation are missing.

- [ ] **Step 3: Implement scripts and documentation**

Use `set -e` in `start.sh` and `errorlevel` checks in `start.bat`. Do not silently continue after npm install/build failure. Document `npm run dev --prefix frontend`, Python API startup, and the one-command scripts.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python3 -m unittest tests.test_startup_contract -v`  
Expected: PASS.

```bash
git add start.sh start.bat README.md .gitignore tests/test_startup_contract.py
git commit -m "docs: add Vue startup workflows"
```

### Task 10: Full verification and review

**Files:**
- Modify only if verification reveals a tested defect.

- [ ] **Step 1: Run frontend verification**

Run: `npm run typecheck --prefix frontend && npm test --prefix frontend -- --run && npm run build --prefix frontend`  
Expected: all commands pass without warnings or TypeScript errors.

- [ ] **Step 2: Run backend verification**

Run: `python3 -m unittest discover -s tests -v`  
Expected: all tests pass.

- [ ] **Step 3: Run repository checks**

Run: `git diff --check && git status --short`  
Expected: no whitespace errors; only intentional changes, ideally a clean tree after commits.

- [ ] **Step 4: Perform browser verification when policy permits**

Check desktop and mobile screenshots, nonblank rendering, overflow, separator dragging, preview restore, file opening, citation page, and drawer focus. If localhost access is blocked, record this as an explicit residual verification gap.

- [ ] **Step 5: Request code review and resolve all Critical/Important findings**

Run the full frontend and Python verification again after fixes, then use the finishing-development-branch workflow.
