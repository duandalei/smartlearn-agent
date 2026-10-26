"""RAG 子系统：文档解析 → 切分 → 向量化 → 向量存储/检索。

模块构成（design.md 2.1.2 模块职责表）：
- ``loader``：按扩展名路由解析器（pypdf / python-docx /
  python-pptx / 纯文本行级读取），含空文本检测红线；
- ``splitter``：中文友好切分（标题/段落优先 + 500 字符滑窗 +
  80 重叠），保留标题路径；
- ``embedding``：在线批量向量化（batch=16 + 重试）与本地兜底
  （带符号哈希 TF，纯标准库、确定性）；
- ``vectorstore``：Chroma 四 collection 封装（归属 × 向量空间）。

与 PROJECT_CONTEXT §3 目录契约的命名映射（取舍依据：契约卷首
「本文件未覆盖的细节，以提示词为准」——P8 提示词指定
loader/embedding/vectorstore 命名，design.md 2.1.2 与 2.9 决策 #1
同口径）：

================  =====================
契约 §3 命名       实际模块名
================  =====================
rag/parser.py     rag/loader.py
rag/embedder.py   rag/embedding.py
rag/store.py      rag/vectorstore.py
rag/splitter.py   rag/splitter.py（一致）
================  =====================

分层约束（契约 §4）：本包不 import api / services（单向依赖
services → rag），不与业务事务耦合。

唯一显式豁免：``embedding`` 为复用唯一在线客户端而 import
``app.services.llm``（design.md 2.1.2 架构图 rag_embed --> svc_llm，
依据 spec 4.5 规则 1 的客户端锁定条款）。
"""