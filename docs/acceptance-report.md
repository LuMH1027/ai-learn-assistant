# 当前版本验收报告

## 基线

- 日期：2026-07-23（Asia/Shanghai）
- Commit：待提交，本报告按当前工作区复查。
- 浏览器数据：隔离目录 `/tmp/course-docs-data`，资料根目录为仓库 `test_materials`，外部 AI/MCP/MinerU 全部关闭。

## 自动化结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量单测 | `uv run python -m unittest discover -s tests` | 281 项通过，0 失败 |
| 前端组件/Store 测试 | `npm test --prefix frontend -- --run` | 9 个文件、109 项通过，0 失败 |
| TypeScript 类型检查 | `npm run build --prefix frontend` 的前置 typecheck | 通过 |
| 生产构建 | `npm run build --prefix frontend` | 通过，生成 `web/dist` |
| RAG demo baseline | `.venv/bin/python scripts/rag_eval.py --demo-baseline --index-dir /tmp/course-rag-docs-index --output /tmp/course-rag-docs-report.md` | quality gate 通过 |

前端测试输出包含 Node 对 `localStorage` 测试环境的 ExperimentalWarning，不影响测试结果。

当前工作区已通过后端、前端和生产构建检查。外部模型、真实 Web Search MCP、MinerU 和跨平台脚本仍属于未覆盖项，见下文。

## RAG 指标

- Retrieval cases：6/6 通过。
- Citation hit rate：100%。
- First citation hit rate：50%。
- Retrieval quality：5 个 `sufficient`，1 个 `partial`。
- Answer term、citation support、forbidden term gates：100%。
- ChatFlow structure：3/3 通过。
- Summary pipeline：4/4 通过。
- `quality_gate_passed = True`。

该 baseline 使用本地 sample、禁用真实 LLM，并用 deterministic stub 验证 map-reduce；它不代表外部模型的实际回答质量。

## 浏览器验收

隔离实例运行在 `http://127.0.0.1:8019`，完成以下操作：

1. 加载 6 门测试课程，空课程和边界命名课程正常显示。
2. 选择“02-正常课程-操作系统”，创建第二个对话并显示多对话列表。
3. 从设置菜单构建知识库，后台完成后恢复 Idle。
4. 打开 `README.md`，搜索 `FIFO`，结果显示 `1/1` 并正确高亮。
5. 选择“启发提示”，完成两轮问答；流式阶段显示 Running、当前思考、stop 按钮和增量回答，完成后展示课程引用。
6. 打开课程笔记，保存“死锁复习”示例并在已保存列表中显示。
7. 保存 5 张 1440×900 PNG，目视确认无旧学习计划/课程概览 UI、无重叠和敏感信息。

内置浏览器不支持页面原生 `window.prompt()`，因此双击重命名对话的手工步骤未在该浏览器完成，并产生一条仅与测试环境有关的 console error。重命名的 Store/API/组件路径由自动化测试覆盖；在 Chrome、Edge 或 Safari 的最终演示中仍应手工点验一次。

## 未覆盖项

- 未调用真实 OpenAI-compatible LLM、embedding 或 rerank provider。
- 未调用真实 Web Search MCP 或 MinerU API/CLI。
- 未验证大文件、长 PDF、扫描文档质量和外部 provider 额度/限流。
- 未验证 Windows 批处理脚本的真实机器运行，只由启动契约测试检查内容。
- 当前前端不展示 Dashboard/mastery，学习计划公开 UI/API 已移除，因此没有相应浏览器验收。

## 截图

- [`screenshots/01-首页总览.png`](screenshots/01-首页总览.png)
- [`screenshots/02-课程展开与文件树.png`](screenshots/02-课程展开与文件树.png)
- [`screenshots/03-文本资料预览.png`](screenshots/03-文本资料预览.png)
- [`screenshots/04-课程Agent问答记录.png`](screenshots/04-课程Agent问答记录.png)
- [`screenshots/05-课程笔记抽屉.png`](screenshots/05-课程笔记抽屉.png)
