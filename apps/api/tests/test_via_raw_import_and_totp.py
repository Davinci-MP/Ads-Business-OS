from __future__ import annotations

import base64
import time
from typing import Generator
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db import get_db
from app.main import app
from app.models.staff import StaffUser, hash_password
from app.models.via import ViaAccount, ViaProfile
from app.services.via_auto_login import (
    generate_totp_code,
    parse_bulk_raw_vias,
    parse_via_raw_line,
)


def test_totp_rfc6238_generation():
    """Kiểm tra tạo mã 2FA TOTP 6 chữ số theo chuẩn RFC 6238."""
    # Test secret RFC standard
    secret = "JBSWY3DPEHPK3PXP"  # Base32 for "Hello!\xde\xad\xbe\xef"
    code, rem = generate_totp_code(secret)
    assert len(code) == 6
    assert code.isdigit()
    assert 0 <= rem <= 30

    # Test with spaces in secret
    code_spaced, rem_spaced = generate_totp_code("JBSW Y3DP EHPK 3PXP")
    assert code == code_spaced

    # Empty secret
    empty_code, empty_rem = generate_totp_code("")
    assert empty_code == ""
    assert empty_rem == 0


def test_parse_via_raw_lines_various_formats():
    """Kiểm tra phân tích chuỗi VIA với 3, 5, 7 và 9 trường phân tách bằng pipe."""
    # 3 fields: uid|pass|2fa
    line_3 = "100088111222|MyPass123|JBSWY3DPEHPK3PXP"
    p3 = parse_via_raw_line(line_3)
    assert p3 is not None
    assert p3["uid"] == "100088111222"
    assert p3["fb_password"] == "MyPass123"
    assert p3["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert p3["email"] == ""
    assert len(p3["totp_code"]) == 6

    # 5 fields: uid|pass|2fa|mail|passmail
    line_5 = "100088333444|PassFive|JBSWY3DPEHPK3PXP|user@hotmail.com|MailPass123"
    p5 = parse_via_raw_line(line_5)
    assert p5 is not None
    assert p5["uid"] == "100088333444"
    assert p5["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert p5["email"] == "user@hotmail.com"
    assert p5["email_password"] == "MailPass123"
    assert p5["backup_email"] == ""

    # 7 fields: uid|pass|2fa|mail|passmail|mailbackup|passmailbackup
    line_7 = "100088555666|PassSeven|JBSW Y3DP EHPK 3PXP|main@gmail.com|MainPass|backup@outlook.com|BackupPass"
    p7 = parse_via_raw_line(line_7)
    assert p7 is not None
    assert p7["uid"] == "100088555666"
    assert p7["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert p7["email"] == "main@gmail.com"
    assert p7["email_password"] == "MainPass"
    assert p7["backup_email"] == "backup@outlook.com"
    assert p7["backup_email_password"] == "BackupPass"

    # 9 fields (extra cookie + EAAG token)
    line_9 = "100088777888|PassNine|JBSWY3DPEHPK3PXP|work@domain.com|WorkPass|bk@domain.com|BkPass|c_user=100088777888; xs=abc123xyz|EAAG1234567890abcdef"
    p9 = parse_via_raw_line(line_9)
    assert p9 is not None
    assert p9["uid"] == "100088777888"
    assert "c_user=100088777888" in p9["cookie"]
    assert p9["eaag_token"].startswith("EAAG")

    # Bulk text parsing
    bulk = f"{line_3}\n{line_5}\n{line_7}\n{line_9}"
    parsed_bulk = parse_bulk_raw_vias(bulk)
    assert len(parsed_bulk) == 4


def test_import_raw_vias_and_sync_rbac(db: Session):
    """Kiểm tra persistence và che giấu dữ liệu nhạy cảm theo vai trò RBAC."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # Seed Owner and Staff
    owner = StaffUser(
        username="test_owner_import",
        full_name="Boss",
        password_hash=hash_password("OwnerSecret123"),
        role="OWNER",
        is_active=True,
    )
    staff = StaffUser(
        username="test_staff_import",
        full_name="Support Staff",
        password_hash=hash_password("StaffSecret123"),
        role="STAFF_SUPPORT",
        is_active=True,
    )
    db.add_all([owner, staff])
    db.commit()

    owner_token = create_access_token(owner.id)
    staff_token = create_access_token(staff.id)

    raw_text = "100099887766|SecretPassFB|JBSWY3DPEHPK3PXP|client@hotmail.com|HotmailPass|rec@gmail.com|RecPass"

    # 1. Staff Import (no live auto_login_and_scan to avoid network call in unit test)
    resp_staff = client.post(
        "/api/v1/ads-check/import-raw-vias-and-sync",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={"raw_vias_text": raw_text, "auto_login_and_scan": False},
    )
    assert resp_staff.status_code == 200
    data_staff = resp_staff.json()
    assert data_staff["success"] is True
    assert data_staff["imported_count"] == 1
    res0_staff = data_staff["results"][0]

    # Verify sensitive fields are masked for STAFF
    assert res0_staff["has_2fa"] is True
    assert res0_staff["has_mail"] is True
    assert "fb_password" not in res0_staff or res0_staff.get("fb_password") == ""
    assert "two_fa_secret" not in res0_staff or res0_staff.get("two_fa_secret") == ""
    assert "email_password" not in res0_staff or res0_staff.get("email_password") == ""
    assert "backup_email_password" not in res0_staff or res0_staff.get("backup_email_password") == ""

    # Verify model alias ViaAccount works
    via_db = db.query(ViaAccount).filter(ViaAccount.uid == "100099887766").first()
    assert via_db is not None
    assert via_db.fb_uid == "100099887766"

    # 2. Owner Import/Query sees full sensitive fields
    resp_owner = client.post(
        "/api/v1/ads-check/import-raw-vias-and-sync",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"raw_vias_text": raw_text, "auto_login_and_scan": False},
    )
    assert resp_owner.status_code == 200
    res0_owner = resp_owner.json()["results"][0]
    assert res0_owner["fb_password"] == "SecretPassFB"
    assert res0_owner["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert res0_owner["email_password"] == "HotmailPass"
    assert res0_owner["backup_email_password"] == "RecPass"

    app.dependency_overrides.clear()
