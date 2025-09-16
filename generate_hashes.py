from werkzeug.security import generate_password_hash
print(f"admin_hash = '{generate_password_hash('admin')}'")
print(f"seller1_hash = '{generate_password_hash('seller1')}'")
