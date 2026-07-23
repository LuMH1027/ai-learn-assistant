# 文档地图

本文是仓库文档入口。技术事实以当前代码和根目录文档为准；`docs/夏季实训提交材料/` 是面向提交的报告快照；`docs/superpowers/` 保存历史设计与实施记录。

## 使用与架构

- [`../README.md`](../README.md)：安装、启动、配置、主要能力和数据位置。
- [`使用说明.md`](使用说明.md)：当前界面的完整操作手册。
- [`系统设计.md`](系统设计.md)：架构、数据模型、流程和 API。
- [`module-structure.md`](module-structure.md)：后端包边界与结构约束。
- [`conversations-and-storage.md`](conversations-and-storage.md)：多对话 API、文件布局和旧数据迁移。
- [`security-and-data-boundaries.md`](security-and-data-boundaries.md)：密钥、本地数据和外部服务的数据边界。

## RAG 与学习能力

- [`study-modes-and-react.md`](study-modes-and-react.md)：答疑、启发提示、复习三种模式与 ReAct 编排。
- [`rag-retrieval-strategy.md`](rag-retrieval-strategy.md)：检索、联网和证据边界。
- [`vector-retrieval.md`](vector-retrieval.md)：embedding、持久向量索引和融合。
- [`conversation-context.md`](conversation-context.md)：当前对话内的追问改写。
- [`citation-check.md`](citation-check.md)：生成后引用支撑检查。
- [`summary-pipeline.md`](summary-pipeline.md)：课程摘要 pipeline。
- [`course-dashboard.md`](course-dashboard.md)、[`mastery-model.md`](mastery-model.md)：仍可调用的后端聚合与掌握度 API；当前前端不展示对应操作区。

## 解析、运维与质量

- [`parser-quality.md`](parser-quality.md)：解析质量评估。
- [`telemetry.md`](telemetry.md)：请求级和任务级诊断数据。
- [`backup-and-migration.md`](backup-and-migration.md)：备份恢复范围和安全约束。
- [`rag-eval.md`](rag-eval.md)、[`rag-eval-baseline.md`](rag-eval-baseline.md)：RAG 回归评测。
- [`test-data-design.md`](test-data-design.md)、[`test-data-results.md`](test-data-results.md)：测试资料设计和 2026-07-23 局部测试快照。
- [`acceptance-report.md`](acceptance-report.md)：当前版本的完整验证结果；由实际命令结果更新。

## 报告材料

- [`报告撰写指南.md`](报告撰写指南.md)、[`程序模块与代码摘录.md`](程序模块与代码摘录.md)、[`验收清单.md`](验收清单.md)、[`开发问题与解决记录.md`](开发问题与解决记录.md)、[`个人体会.md`](个人体会.md)。
- [`夏季实训提交材料/README.md`](夏季实训提交材料/README.md)：实训报告、演示脚本、清单和截图入口。

## 历史文档

`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 记录 2026-07-15 至 2026-07-16 的设计与迁移过程。它们不是当前操作手册，正文保留历史原貌，顶部状态说明会标明 `Superseded` 或 `Implemented`。

## 维护规则

1. 代码行为变化时先更新根目录权威文档，再同步实训交付快照。
2. 测试结果必须写明日期、commit、命令和未覆盖项，不能把局部测试写成全系统通过。
3. 当前产品能力不得引用未暴露的遗留模块；历史日志可以保留曾实现过的原型，但要说明最终状态。
4. 截图统一存放在 `docs/screenshots/`，使用演示资料且不得出现密钥、个人路径或隐私内容。
