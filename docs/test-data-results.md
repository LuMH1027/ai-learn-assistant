# 测试数据测试结果

> 状态：2026-07-23 的局部测试快照，仅覆盖下述扫描、解析和上传边界；当前全系统验证见 [`acceptance-report.md`](acceptance-report.md)。

测试日期：2026-07-23  
测试目录：仓库内 `test_materials/`
测试对象：本地课程 RAG Agent 测试资料集

## 总结

本次测试覆盖课程目录扫描、文件过滤、边界命名识别、文本解析、异常资料解析容错、上传同名冲突和上传文件名清洗。

结果：通过 17 项，失败 0 项。

补充说明：损坏 PDF 测试用例在解析阶段输出了 `invalid pdf header` 和 `EOF marker not found`，这是测试数据刻意构造的异常输入。程序没有崩溃，并返回了可处理的解析结果，因此判定通过。

## 执行命令

```bash
python3 -m unittest tests.test_course_scanner tests.test_config_and_uploads -v
```

结果：16 个相关单元测试全部通过。

```bash
python3 -c 'from pathlib import Path; from local_course_agent.scanner import CourseScanner; import json; courses=CourseScanner(Path("test_materials")).scan(); print(json.dumps([{k:c[k] for k in ("name","file_count")} for c in courses], ensure_ascii=False, indent=2))'
```

扫描结果：

| 课程 | 文件数 |
| --- | ---: |
| `00-空课程` | 0 |
| `01-正常课程-数据结构` | 5 |
| `02-正常课程-操作系统` | 5 |
| `03-边界命名与编码` | 6 |
| `04-异常资料与忽略规则` | 3 |
| `05-上传冲突模拟` | 2 |

## 测试用例明细

| 编号 | 用例 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| TC-001 | 扫描 `test_materials` 一级课程目录 | 识别 6 门课程 | 实际识别 6 门课程 | 通过 |
| TC-002 | 扫描 `00-空课程` | 课程存在，受支持文件数为 0 | `file_count=0` | 通过 |
| TC-003 | 忽略 `04-异常资料与忽略规则/unsupported-video.mp4` | 不出现在文件树 | 未扫描到该文件 | 通过 |
| TC-004 | 忽略 `04-异常资料与忽略规则/no-extension` | 不出现在文件树 | 未扫描到该文件 | 通过 |
| TC-005 | 忽略 `04-异常资料与忽略规则/.隐藏但支持.md` | 隐藏文件不出现在文件树 | 未扫描到该文件 | 通过 |
| TC-006 | 忽略 `00-空课程/.hidden.md` | 隐藏文件不出现在文件树 | 未扫描到该文件 | 通过 |
| TC-007 | 扫描大写扩展名 Markdown `中英混合_Mixed-Case.MD` | 作为 Markdown 支持文件出现 | 已扫描到该文件 | 通过 |
| TC-008 | 扫描大写扩展名 PDF `复杂度速查.PDF` | 作为 PDF 支持文件出现 | 已扫描到该文件 | 通过 |
| TC-009 | 扫描含空格文件名 `含 空 格 的 文件.md` | 正常进入文件树 | 已扫描到该文件 | 通过 |
| TC-010 | 扫描含括号文件名 `括号-版本(v1.0).txt` | 正常进入文件树 | 已扫描到该文件 | 通过 |
| TC-011 | 解析 `第01章-栈和队列.md` | 能提取“后进先出”等正文内容 | 返回 1 页，393 字符 | 通过 |
| TC-012 | 解析 `死锁四条件.txt` | 能提取“循环等待条件”等正文内容 | 返回 1 页，150 字符 | 通过 |
| TC-013 | 解析 `空白Markdown.md` | 不崩溃，文本为空白 | 返回 1 页，5 字符，去空白后为空 | 通过 |
| TC-014 | 解析损坏 PDF `损坏的PDF.pdf` | 不导致服务崩溃 | 返回 1 页降级结果 | 通过 |
| TC-015 | 解析伪 DOCX `伪装DOCX.docx` | 不导致服务崩溃，并给出解析失败降级信息 | 返回 1 页降级结果 | 通过 |
| TC-016 | 上传同名冲突候选路径 | 已存在 `chapter.md` 和 `chapter-2.md` 时生成 `chapter-3.md` | 候选文件名为 `chapter-3.md` | 通过 |
| TC-017 | 上传文件名清洗 | `../evil.pdf` 转为 `evil.pdf`，`C:\tmp\note.md` 转为 `note.md` | 实际输出符合预期 | 通过 |

## 风险与后续建议

本次验证未启动完整前后端服务，也未调用真实 LLM、Embedding、Rerank、MinerU 或 Web Search，因此未覆盖模型质量、联网搜索质量和前端视觉交互。若要做完整验收，建议将 `data/config.json` 的 `root_folder` 指向 `test_materials`，启动服务后补充浏览器端手工验证和 RAG 问答验证。
