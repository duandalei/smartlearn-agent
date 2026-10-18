"""沙箱网络限制补丁：IPv6 socketpair 替代默认 IPv4 实现。

沙箱环境拦截 IPv4 回环连接（127.0.0.1），而 Windows asyncio
ProactorEventLoop 初始化时的 ``socket.socketpair()`` 内部走 IPv4
回环 connect，导致 TestClient（anyio blocking portal）创建事件
循环即报 ``WinError 10051``。

本补丁以 IPv6 回环（::1）模拟 socketpair，为 P2/P3 已验证的
沙箱绕行方案，仅在验证脚本内导入，业务代码不使用。

用法（验证脚本顶部）::

    import _sandbox_patch  # noqa: F401  （必须在 TestClient 使用前导入）
"""

from __future__ import annotations

import socket


def _ipv6_socketpair(
    family: int = socket.AF_INET6,
    type: int = socket.SOCK_STREAM,  # noqa: A002 —— 与标准库签名对齐
    proto: int = 0,
) -> tuple[socket.socket, socket.socket]:
    """以 IPv6 回环模拟 ``socket.socketpair``。"""
    listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        listener.bind(("::1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        client = socket.socket(socket.AF_INET6, type, proto)
        try:
            client.connect(("::1", port))
            server, _ = listener.accept()
            return server, client
        except BaseException:
            client.close()
            raise
    finally:
        listener.close()


def apply_patch() -> None:
    """以 IPv6 实现替换 ``socket.socketpair``（幂等）。"""
    if getattr(socket.socketpair, "_is_ipv6_patch", False):
        return
    _ipv6_socketpair._is_ipv6_patch = True  # type: ignore[attr-defined]
    socket.socketpair = _ipv6_socketpair  # type: ignore[assignment]


apply_patch()