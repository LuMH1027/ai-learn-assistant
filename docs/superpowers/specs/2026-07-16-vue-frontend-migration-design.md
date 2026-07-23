# Vue 前端迁移设计规格

> Status: Implemented. Vue/Vite/TypeScript/Pinia 已成为当前前端；后续界面和聊天能力继续演化，因此本文保留为迁移设计记录，不作为当前用户手册。

日期：2026-07-16  
状态：用户已确认架构、状态边界与测试方向

## 1. 目标与边界

将当前原生 HTML、CSS、JavaScript 前端迁移为 Vue 3 工程，为课程、聊天、文件预览、引用、笔记和可调整布局建立清晰的组件及状态边界。

迁移必须保持：

- 已确认的 Codex 风格浅色三栏界面与响应式行为。
- 百分比栏宽、相邻栏交换、紧凑模式和预览开关恢复。
- 课程隔离、聊天附件、课程文件上传、摘要、练习、笔记和引用预览。
- 当前 Python HTTP API 的路径、请求格式与响应结构。
- 本地优先、无需独立数据库或外部前端托管的运行方式。

本规格取代 `2026-07-15-course-agent-ui-redesign-design.md` 中“不得引入 Vue 或构建工具”的实现限制，但不取代其视觉、交互和可访问性要求。

非目标：

- 不引入前端路由、登录、权限或云端部署。
- 不修改 RAG、LLM、MinerU、课程扫描和文件存储逻辑。
- 不在迁移期间重新设计已确认的用户界面。
- 不并行维护原生 JavaScript 与 Vue 两套业务实现。

## 2. 技术方案

采用：

- Vue 3 Composition API
- Vite
- TypeScript
- Pinia
- Vitest 与 Vue Test Utils

前端工程位于 `frontend/`，生产构建输出到 `web/dist/`。Python 服务继续处理 `/api/*`，并在生产模式下托管 `web/dist/`。开发模式由 Vite 提供页面和热更新，并将 `/api` 代理到 Python 服务。

不使用 CDN 版本 Vue，也不在组件中直接散布 `fetch` 或跨组件可变全局状态。

## 3. 工程结构

```text
frontend/
  index.html
  package.json
  tsconfig.json
  vite.config.ts
  src/
    App.vue
    main.ts
    styles.css
    components/
      AppShell.vue
      CourseSidebar.vue
      FileTree.vue
      ChatWorkspace.vue
      MessageList.vue
      ChatComposer.vue
      FilePreview.vue
      NotesDrawer.vue
      ResizableWorkspace.vue
    services/
      api.ts
    stores/
      course.ts
      chat.ts
      preview.ts
      layout.ts
    types/
      api.ts
    test/
      setup.ts
web/
  dist/
start.sh
start.bat
```

组件可以在实施时按职责合并小型展示组件，但 Store、API 服务和领域类型必须保持独立。

## 4. 组件职责

### 4.1 AppShell 与 ResizableWorkspace

- 组装左栏、中栏、右栏及笔记抽屉。
- 管理桌面网格、移动抽屉和预览覆盖层。
- 将指针位移换算为容器百分比。
- 左边界只改变左栏和中栏；右边界只改变中栏和右栏。
- 支持方向键调整、双击复位、紧凑下限测量和 ARIA 数值范围。

### 4.2 CourseSidebar 与 FileTree

- 展示课程列表、当前课程资料树和服务状态。
- 处理资料根目录、课程选择、课程资料上传和知识库构建入口。
- 文件夹可折叠，文件点击交给 Preview Store 打开。
- 移动端打开预览后关闭课程抽屉，避免覆盖层冲突。

### 4.3 ChatWorkspace

- 展示当前课程标题、工具栏、消息列表和输入框。
- 管理问答模式、临时附件、发送、摘要和练习操作。
- 忙碌期间禁用会产生重复写入的操作。
- 切换课程立即清空上一课程的消息、附件与加载状态。

### 4.4 FilePreview

- 提供当前文件、引用来源和文件信息三个标签。
- 支持 PDF、文本和图片预览。
- 引用包含原文、文件名和页码；可返回文件并定位页码。
- 关闭时保留文件、标签和栏宽；重新打开恢复。
- PDF 内嵌失败时提供保留页码的新窗口链接。

### 4.5 NotesDrawer

- 加载、创建和展示当前课程笔记。
- 关闭时使用 `inert` 移出焦点顺序，支持 Escape 关闭和焦点返回。
- 课程切换时立即清空旧笔记，再显示新课程加载状态。

## 5. 状态设计

### 5.1 Course Store

保存课程列表、当前课程、配置和索引状态。课程切换产生单调递增的上下文版本，供其他 Store 判断异步响应是否仍属于当前课程。

### 5.2 Chat Store

保存消息、问答模式、临时附件和各操作忙碌状态。加载消息时捕获课程 ID 和上下文版本；响应返回后仅在二者仍匹配时写入状态。

### 5.3 Preview Store

保存当前文件、当前引用、选中标签、打开状态和预览错误。课程切换会清空内容；单纯关闭预览不会清空内容。

### 5.4 Layout Store

保存左栏比例、右栏比例和预览开关。默认比例为 `22% / 45.8% / 31%`，分隔条各约 `0.6%`。持久化键继续使用 `local-course-agent-layout-v1`，兼容已有用户设置。

移动端首次且没有持久化状态时默认关闭预览。打开预览时，背后的对话区进入 `inert` 状态。

## 6. 数据与错误流

`services/api.ts` 是唯一 HTTP 边界：

- JSON 请求统一设置请求头、解析错误并返回类型化结果。
- 文件上传使用 `FormData`，不得手动设置 multipart Content-Type。
- 非 2xx 响应转换为带用户可读信息的 `ApiError`。
- Store 决定错误展示位置；成功 Toast 只用于非阻断通知。

课程切换采用“立即清空 + 版本校验”策略，防止慢响应把上一课程的消息、笔记或预览写入新课程。

## 7. 构建与启动

提供两套跨平台入口：

- `start.sh`：macOS/Linux。
- `start.bat`：Windows。

默认启动流程：

1. 检查 Python、Node.js 和 npm。
2. 在缺少 `frontend/node_modules` 时执行依赖安装。
3. 构建 Vue 前端到 `web/dist/`。
4. 启动 `python3 run.py` 或 Windows 对应 Python 命令。

开发命令保留为 npm scripts：一个命令并行启动 Python API 与 Vite。Vite 代理 `/api`，避免开发环境跨域配置。

Python 静态服务规则：

- `/api/*` 继续进入现有 Handler。
- 其他路径从 `web/dist/` 读取。
- 缺少构建产物时返回明确错误，提示运行启动脚本，不回退到旧原生前端。

## 8. 测试与验收

### 8.1 前端自动化

- API 服务：JSON、FormData 和错误转换。
- Layout Store：相邻栏不变量、上下限、复位、持久化和移动默认状态。
- Course/Chat Store：快速切课竞态、附件清空和忙碌互锁。
- Preview Store：关闭恢复、课程切换清空、引用页码。
- 组件：预览标签、抽屉焦点、文件选择与禁用状态。

所有新增前端行为遵循测试先行：测试先因模块缺失或行为缺失而失败，再实现最小代码使其通过。

### 8.2 后端回归

- 保持现有 Python 测试全部通过。
- 增加静态目录指向 `web/dist/` 的测试。
- 验证缺少构建产物时的错误响应。

### 8.3 构建与视觉验收

- `npm run typecheck`、`npm test` 和 `npm run build` 均通过。
- 桌面与移动视口无横向溢出、内容遮挡或不可达输入框。
- 真实验证拖动、双击复位、预览开关、快速切课、引用页码和文件选择。
- 浏览器策略若阻止本地页面访问，必须明确记录未完成的视觉验证，不得用静态检查冒充。

## 9. 迁移顺序与回滚

迁移按 API/类型、Store、组件、静态托管、启动脚本顺序进行。原生 `web/index.html`、`web/app.js` 和 `web/styles.css` 在 Vue 功能与构建验证通过后删除，避免双实现漂移。

迁移提交保持在独立分支。回滚时可恢复迁移前提交，不影响 Python API 和本地课程数据。
