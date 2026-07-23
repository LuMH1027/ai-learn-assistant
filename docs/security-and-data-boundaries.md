# 安全与数据边界

本项目面向单机本地使用，不提供账号体系、远程多用户隔离或公网部署安全保证。浏览器、Python 服务和课程资料应运行在用户可控的设备上。

## 本地保存

- 课程资料保留在用户配置的 `root_folder`。
- 对话、记忆、笔记和掌握度保存在 `data/course_memory/`。
- 课程文本索引和向量索引保存在 `data/indexes/`。
- 聊天临时附件保存在 `data/chat_uploads/`。
- 真实配置保存在 `data/config.json`，该文件被 Git 忽略。

## 发送到外部服务的数据

| 服务 | 触发条件 | 可能发送的数据 |
| --- | --- | --- |
| OpenAI-compatible LLM | 已配置模型且聊天/摘要需要生成 | 用户问题、当前对话的最近历史、选中的课程证据；图片问答还会发送附件图片 |
| Embedding provider | 已配置 `ai.embedding_model` | 建库时的课程文本片段和查询文本 |
| Rerank provider | 已完整配置 rerank | 查询与候选课程片段 |
| Web Search MCP | `web_search.enabled=true` 且 ReAct 选择联网 | 搜索查询；不发送课程片段或附件正文 |
| MinerU | 启用 API/CLI 解析且处理对应文件 | 待解析文档；具体传输方式由 MinerU 配置决定 |

外部服务的保留策略、训练策略、额度和可用性不由本项目控制。含个人信息、考试材料或受限资料时，应先确认所选服务的政策，或关闭相应外部能力。

## 密钥和配置

- 仓库只提交 `data/config.example.json`；不要提交 `data/config.json`。
- `api_key` 和 token 可以写成环境变量引用，例如 `$SILICONFLOW_API_KEY`。
- 前端配置接口不会返回密钥。
- 截图、日志、测试报告和问题反馈中不得展示密钥、真实个人目录或私有课程内容。

## 上传、预览与恢复

- 上传文件名会清理路径片段并限制落盘位置，服务端仍会校验目录边界。
- Markdown 预览先解析再用 DOMPurify 清理，不直接执行课程文件中的 HTML 脚本。
- 备份只包含 `config.example.json`、`course_memory/**` 和 `indexes/**`；排除真实配置、SQLite、上传和缓存。
- 恢复会拒绝绝对路径、反斜杠、`..` 和白名单外成员，防止 zip slip。

## 部署边界

默认监听 `127.0.0.1`。如果把服务改为监听所有网卡，必须自行增加鉴权、TLS、请求大小限制、访问日志和网络防火墙；当前实现不应直接暴露到公网。
