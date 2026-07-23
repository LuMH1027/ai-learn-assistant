# 测试数据设计

测试数据目录：`test_materials/`

使用方式：

```json
{
  "root_folder": "/Users/bytedance/course/test_materials"
}
```

## 覆盖矩阵

| 课程目录 | 用例类型 | 重点验证 |
| --- | --- | --- |
| `00-空课程` | 异常/边界 | 一级空课程仍可被识别；隐藏文件和不支持扩展名不会进入文件树。 |
| `01-正常课程-数据结构` | 正常 | Markdown、TXT、多级目录、大写扩展名 PDF、明确知识点检索。 |
| `02-正常课程-操作系统` | 正常/歧义 | 跨文件问答、重复术语 FIFO、死锁四条件、拖入资料目录。 |
| `03-边界命名与编码` | 边界 | 中文、空格、括号、大写扩展名、超长文件名、同名不同路径。 |
| `04-异常资料与忽略规则` | 异常 | 损坏 PDF、伪 DOCX、空白 Markdown、unsupported/no-extension/hidden 忽略规则。 |
| `05-上传冲突模拟` | 边界 | `unique_path` 同名递增，已有 `chapter.md` 和 `chapter-2.md`。 |

## 手工验收点

1. 课程列表应显示 6 个一级课程目录。
2. `unsupported-video.mp4`、`no-extension`、`.隐藏但支持.md` 和 `.hidden.md` 不应出现在文件树中。
3. `中英混合_Mixed-Case.MD` 应作为 Markdown 文件出现。
4. `复杂度速查.PDF` 应因大写扩展名被识别为 PDF。
5. 损坏 PDF 和伪 DOCX 的解析失败不应中断服务。
6. 查询“死锁四个必要条件”应优先引用 `死锁四条件.txt`。
7. 查询“FIFO 和 LRU 区别”应优先引用 `页面置换.md`，而不是数据结构课程中的 FIFO 队列说明。
8. 查询“红黑树在哪里出现”应能定位 `第02章-树与查找.markdown`。
9. 上传一个名为 `chapter.md` 的文件到 `05-上传冲突模拟` 时，预期保存为 `拖入资料/chapter-3.md`。

