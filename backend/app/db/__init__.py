"""db 层：数据库会话与初始化。

包含 engine、SessionLocal、FastAPI 依赖 ``get_db``；``init_db`` 只负责
建表与本地用户初始化，不写任何演示种子。db 层禁止写业务规则。
"""