import hashlib, secrets
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.models.staff import StaffUser, StaffAuditLog
from app.core.config import settings

engine = create_engine(settings.database_url, future=True)
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
db = SessionLocal()

username = 'admin'
if not db.query(StaffUser).filter(StaffUser.username == username).first():
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', b'Admin@123', salt.encode('utf-8'), 256000)
    hashed = f'{salt}:{dk.hex()}'
    owner = StaffUser(
        username=username,
        full_name='Administrator',
        email='admin@adsbusinessos.com',
        password_hash=hashed,
        role='OWNER',
        is_active=True
    )
    db.add(owner)
    db.commit()
    print('Default OWNER created: admin')
else:
    print('OWNER already exists: admin')

db.close()