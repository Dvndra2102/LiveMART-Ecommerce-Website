
import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'livemart.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.test.utils import setup_test_environment

User = get_user_model()

def verify_change_password():
    setup_test_environment()
    email = "change_pw_test@example.com"
    old_password = "old_password_123"
    new_password = "StrongPassword123!"
    
    # Create user
    if User.objects.filter(email=email).exists():
        User.objects.get(email=email).delete()
    
    user = User.objects.create_user(email=email, password=old_password, full_name="Change PW User", role="CUSTOMER")
    print(f"User created: {email} with password: {old_password}")

    client = Client()
    
    # Login first
    client.login(email=email, password=old_password)
    
    change_url = reverse('account_change_password')
    
    # 1. Test Wrong Current Password
    print("\n--- Testing Wrong Current Password ---")
    response = client.post(change_url, {
        'oldpassword': 'wrong_current_password',
        'newpassword1': new_password,
        'newpassword2': new_password,
    })
    if response.status_code == 200:
        # Check for form error
        print("PASS: Wrong current password rejected (form error displayed).")
    else:
        print(f"FAIL: Wrong current password returned status {response.status_code}")

    # 2. Test Mismatched New Passwords
    print("\n--- Testing Mismatched New Passwords ---")
    response = client.post(change_url, {
        'oldpassword': old_password,
        'newpassword1': new_password,
        'newpassword2': 'mismatch_password',
    })
    if response.status_code == 200:
        print("PASS: Mismatched passwords rejected (form error displayed).")
    else:
        print(f"FAIL: Mismatched passwords returned status {response.status_code}")

    # 3. Test Successful Password Change
    print("\n--- Testing Successful Password Change ---")
    response = client.post(change_url, {
        'oldpassword': old_password,
        'newpassword1': new_password,
        'newpassword2': new_password,
    })
    
    if response.status_code == 302:
        print("PASS: Password change request redirected (success).")
    else:
        print(f"FAIL: Password change request returned status {response.status_code}")
        # Inspect context
        try:
            if response.context:
                # Usually the first context has the form
                ctx = response.context[0] if isinstance(response.context, list) else response.context
                if 'form' in ctx:
                    form = ctx['form']
                    print(f"Form is bound: {form.is_bound}")
                    print(f"Form data: {form.data}")
                    print(f"Form errors: {form.errors}")
                    print(f"Form non_field_errors: {form.non_field_errors()}")
                else:
                    print("Form not found in context.")
        except Exception as e:
            print(f"Could not extract context info: {e}")
        
        # Always print snippet if 200
        print(f"Response content snippet: {response.content.decode('utf-8')[:1000]}")
        with open("debug_response.html", "wb") as f:
            f.write(response.content)
        print("Wrote full response to debug_response.html")

    # Check DB password directly
    user.refresh_from_db()
    print(f"DB Check: check_password(old) = {user.check_password(old_password)}")
    print(f"DB Check: check_password(new) = {user.check_password(new_password)}")

    # 4. Verify Persistence (Login with NEW password)
    print("\n--- Verifying Persistence ---")
    # Use a FRESH client to ensure no session persistence
    client = Client()
    
    # Try Old Password
    print("Attempting login with OLD password...")
    login_url = '/accounts/login/'
    response = client.post(login_url, {
        'login': email,
        'password': old_password,
    })
    if response.status_code == 200:
        print("PASS: Login with OLD password failed (as expected).")
    else:
        print(f"FAIL: Login with OLD password returned status {response.status_code} (Should fail)")

    client.logout() # Logout before next attempt

    # Try New Password
    print("Attempting login with NEW password...")
    response = client.post(login_url, {
        'login': email,
        'password': new_password,
    })
    if response.status_code == 302:
        print("PASS: Login with NEW password succeeded.")
    else:
        print(f"FAIL: Login with NEW password returned status {response.status_code}")
        print(f"Response content snippet: {response.content.decode('utf-8')[:500]}")

if __name__ == "__main__":
    verify_change_password()
