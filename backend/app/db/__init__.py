"""db 层：数据库会话与初始化。

包含 engine、SessionLocal、FastAPI 依赖 ``get_db``；后续新增 init_db
（建表 + 种子数据）。db 层禁止写业务规则。
"""