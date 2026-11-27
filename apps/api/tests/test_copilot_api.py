"""Kiểm thử REST API Copilot cho Web CRM (/api/v1/copilot/chat & status)."""

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.models.staff import StaffUser, hash_password
from app.services.ai.providers.mock import MockLLMProvider


def test_copilot_api_status():
    client = TestClient(app)
    res = client.get("/api/v1/copilot/status")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "staff_tools_count" in data
    assert data["staff_tools_count"] >= 5
    assert "get_system_overview" in data["staff_tools"]


def test_copilot_api_chat_auth_required():
    client = TestClient(app)
    # Chưa đăng nhập -> 401
    res = client.post("/api/v1/copilot/chat", json={"message": "Xin chào"})
    assert res.status_code == 401


def test_copilot_api_chat_authenticated(db, monkeypatch):
    from app.services.ai import orchestrator as orch_module

    # Sử dụng MockLLMProvider cho test
    monkeypatch.setattr(orch_module, "get_llm_provider", lambda *args, **kwargs: MockLLMProvider())

    # Tạo nhân viên hợp lệ
    staff = StaffUser(
        username="copilot_user",
        full_name="Staff Copilot Tester",
        password_hash=hash_password("Password123!"),
        role="STAFF_OPS",
        is_active=True,
    )
    db.add(staff)
    db.commit()

    token = create_access_token(staff.id)

    from app.db import get_db

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/copilot/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Cho tôi báo cáo tổng quan hôm nay"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert "get_system_overview" in data["tools_used"]
    finally:
        app.dependency_overrides.pop(get_db, None)
