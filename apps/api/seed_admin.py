import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, inspect
from app.models import Base, StaffUser
from app.core.security import hash_password
from app.db import SessionLocal

engine = create_engine('sqlite:///adsos.db')
inspector = inspect(engine)

# Check if admin already exists
existing = SessionLocal()
try:
    admin_existing = existing.query(StaffUser).filter(StaffUser.username == 'admin').first()
    if admin_existing:
        print('Admin user already exists, skipping seed.')
    else:
        admin = StaffUser(
            username='admin',
            full_name='System Administrator',
            email='admin@adsos.local',
            password_hash=hash_password('Admin@123'),
            role='OWNER',
            is_active=True,
        )
        existing.add(admin)
        existing.commit()
        print('Default OWNER admin user seeded successfully.')
except Exception as e:
    existing.rollback()
    print(f'Error seeding admin: {e}')
finally:
    existing.close()