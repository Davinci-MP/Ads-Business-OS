from sqlalchemy import create_engine, inspect
from app.models import Base, StaffUser, StaffAuditLog

engine = create_engine('sqlite:///adsos.db')
inspector = inspect(engine)

# Check staff_users table
print('=== staff_users columns ===')
if inspector.has_table('staff_users'):
    cols = inspector.get_columns('staff_users')
    for c in cols:
        print(f'  {c["name"]}: {c["type"]}')
else:
    print('  TABLE NOT FOUND')

# Check staff_audit_logs table
print('=== staff_audit_logs columns ===')
if inspector.has_table('staff_audit_logs'):
    cols = inspector.get_columns('staff_audit_logs')
    for c in cols:
        print(f'  {c["name"]}: {c["type"]}')
else:
    print('  TABLE NOT FOUND')

# Try to create tables if needed
print('\n=== Creating tables if needed ===')
Base.metadata.create_all(bind=engine, checkfirst=True)
print('Tables created successfully (checkfirst=True)')

# Verify after create
inspector = inspect(engine)
print('\n=== After create_all ===')
print('staff_users' in inspector.get_table_names())
print('staff_audit_logs' in inspector.get_table_names())

# Now seed the default OWNER admin
from app.core.security import hash_password
from app.db import SessionLocal

def seed_default_owner():
    db = SessionLocal()
    try:
        # Check if admin already exists
        existing = db.query(StaffUser).filter(StaffUser.username == 'admin').first()
        if existing:
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
            db.add(admin)
            db.commit()
            print('Default OWNER admin user seeded successfully.')
    except Exception as e:
        db.rollback()
        print(f'Error seeding admin: {e}')
    finally:
        db.close()

seed_default_owner()