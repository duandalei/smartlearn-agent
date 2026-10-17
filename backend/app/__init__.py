"""彭城智学（SmartLearn Agent）后端应用包。

本包为 FastAPI 应用的根包，内部按 api / schemas / models / services /
agent / rag / analytics / core / db 分层组织，分层调用方向为单向：
api → services → models / rag / analytics / agent。

注意：本模块仅暴露包元信息，禁止在此处 import 上层业务模块，避免循环依赖。
"""

__version__ = "0.1.0"