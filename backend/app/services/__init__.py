"""业务逻辑层（services）。

P2 仅提供只读查询助手 ``readonly``；各资源的业务 service 随
P3+ 写接口阶段按需建立。
"""

from __future__ import annotations

from app.services.readonly import get_by_id_or_404, paginate

__all__ = ["get_by_id_or_404", "paginate"]