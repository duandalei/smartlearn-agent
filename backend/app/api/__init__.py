"""api 层：路由定义。

仅做「接收参数 + 鉴权 + 调用 service + 组装响应」，禁止写业务逻辑与 SQL。
依赖注入（get_db / get_current_user）统一放在 ``app/api/deps.py``。
"""