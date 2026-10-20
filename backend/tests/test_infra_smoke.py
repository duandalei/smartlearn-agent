"""测试基础设施冒烟（组 5.1 验收：可收集运行 + 隔离生效）。"""


def test_isolated_db_and_users(app_client, user_a, user_b):
    """临时库 + 双用户注册 + 鉴权列表请求全链路冒烟。"""
    resp = app_client.get("/api/v1/knowledge/items", headers=user_a["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 0
    assert app_client.get("/api/v1/knowledge/items").status_code == 401


def test_db_is_not_production_file():
    """断言 engine 绑定的是临时库而非 data/smartlearn.db。"""
    from app.db.session import engine

    assert "smartlearn.db" not in str(engine.url), str(engine.url)
    assert "kb_pytest_" in str(engine.url), str(engine.url)


def test_chroma_dir_isolated():
    """断言 Chroma 目录可被 monkeypatch 到 tmp_path 并真实读写。"""
    import app.rag.vectorstore as vs

    vs.get_vector_store()
    col = vs._collection("personal", 12345, "offline")
    col.upsert(
        ids=["x1"], embeddings=[[0.1, 0.2]], documents=["t"], metadatas=[{"item_id": 1}]
    )
    assert col.count() == 1