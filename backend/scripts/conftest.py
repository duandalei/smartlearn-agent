"""scripts/ 目录 pytest 收集守卫（P13 修复）。

本目录下的 ``test_tools.py`` 是独立验收脚本（docstring 声明
``cd backend && .venv/Scripts/python scripts/test_tools.py`` 运行），
并非 pytest 测试：其模块顶层会把 ``DATABASE_URL`` 改写为
``tmp_verify/p10_tools.db`` 并 import ``app.db.session``。一旦被 pytest
全量收集时 import，engine 即在 import 期固化为非测试库，导致
``tests/conftest.py`` 的临时库隔离失效（全量运行时所有测试真实落在
p10_tools.db 上，tests/test_infra_smoke.py::test_db_is_not_production_file
失败的根因）。

此处声明 ``collect_ignore``，使 pytest 收集阶段不 import 该文件（收集
决策发生在 import 之前，顶层副作用不发生）；脚本独立运行方式不受影响。
"""

collect_ignore = ["test_tools.py"]