"""认证出入参模型（注册 / 登录 / Token 响应）。

密码安全约束：长度下限 6 位（演示账号 123456 恰好 6 位，可通过）；
密码只在此处短暂存在于内存，禁止落库明文、禁止写入日志。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.user import UserOut


class RegisterIn(BaseModel):
    """注册入参。

    密码与确认密码必须一致（``model_validator`` 校验失败时按
    Pydantic 校验错误处理，返回 1001 / 422）。
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=2, max_length=50, description="登录名")
    password: str = Field(min_length=6, max_length=128, description="密码，至少 6 位")
    confirm_password: str = Field(
        min_length=6, max_length=128, description="确认密码，须与密码一致"
    )

    @model_validator(mode="after")
    def _check_password_match(self) -> "RegisterIn":
        """校验两次输入的密码一致。"""
        if self.password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


class LoginIn(BaseModel):
    """登录入参。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=50, description="登录名")
    password: str = Field(min_length=1, max_length=128, description="密码")


class AuthResult(BaseModel):
    """登录 / 注册成功响应的 data 结构。

    注册成功后返回的 token 结构与登录**完全一致**，前端复用
    同一套存储逻辑（stores/user.ts 的 applyAuthState）。
    """

    access_token: str
    token_type: str = "bearer"
    user: UserOut