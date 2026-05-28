"""
verify_users.py
Check if users exist and verify password hashes.
If hashes are corrupted, recreate users with proper bcrypt hashing.
"""

from app import create_app, db
from app.models import AuthUser
import bcrypt

app = create_app()

with app.app_context():
    # Check if users exist
    users = AuthUser.query.all()
    print(f"Total users in auth_users table: {len(users)}")
    
    corrupted = False
    for user in users:
        print(f"\nUser: {user.email}")
        print(f"  Role: {user.role}")
        print(f"  Status: {user.status}")
        print(f"  Password hash: {user.password_hash[:50]}...")
        
        # Try to verify password
        try:
            result = user.check_password('admin123')
            print(f"  Password 'admin123' matches: {result}")
            if not result:
                corrupted = True
        except Exception as e:
            print(f"  Error checking password: {e}")
            corrupted = True
    
    # If users are corrupted or don't exist, recreate them
    if len(users) == 0 or corrupted:
        print("\n\n" + "="*60)
        if corrupted:
            print("CORRUPTED HASHES DETECTED - Recreating users...")
        else:
            print("No users found! Creating test users...")
        print("="*60)
        
        # Delete existing users if corrupted
        if corrupted:
            AuthUser.query.delete()
            db.session.commit()
            print("Deleted corrupted users.")
        
        users_data = [
            {
                'email': 'admin@company.com',
                'password': 'admin123',
                'full_name': 'Admin User',
                'role': 'admin'
            },
            {
                'email': 'agent@company.com',
                'password': 'agent123',
                'full_name': 'Jane Agent',
                'role': 'agent'
            },
            {
                'email': 'supervisor@company.com',
                'password': 'supervisor123',
                'full_name': 'Bob Supervisor',
                'role': 'supervisor'
            }
        ]
        
        for user_data in users_data:
            user = AuthUser(
                email=user_data['email'],
                full_name=user_data['full_name'],
                role=user_data['role'],
                status='active'
            )
            user.set_password(user_data['password'])
            db.session.add(user)
            print(f"Created user: {user_data['email']} with password: {user_data['password']}")
        
        db.session.commit()
        print("\n✓ Test users created successfully!")
        
        # Verify the new users
        print("\n" + "="*60)
        print("VERIFICATION - Testing new users:")
        print("="*60)
        new_users = AuthUser.query.all()
        for user in new_users:
            print(f"\nUser: {user.email}")
            print(f"  Role: {user.role}")
            print(f"  Password hash: {user.password_hash[:50]}...")
            try:
                result = user.check_password(user.email.split('@')[0] + '123')
                print(f"  Password verification: {'✓ PASS' if result else '✗ FAIL'}")
            except Exception as e:
                print(f"  Password verification: ✗ ERROR - {e}")
    else:
        print("\n✓ All users have valid password hashes!")

