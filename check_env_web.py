"""
检查 Web 服务环境变量
"""
import os

print("=" * 60)
print("Web 服务环境变量检查")
print("=" * 60)

vars_to_check = [
    'SYSTEM_API_KEY',
    'SYSTEM_BASE_URL',
    'SYSTEM_MODEL',
    'SUPABASE_URL',
    'SUPABASE_SERVICE_ROLE_KEY',
    'USER_API_KEY',
    'USER_BASE_URL',
    'USER_MODEL'
]

all_ok = True
for var in vars_to_check:
    value = os.getenv(var, '')
    if value:
        # 只显示前10个字符
        display = value[:15] + '...' if len(value) > 15 else value
        print(f"✓ {var}: {display}")
    else:
        print(f"✗ {var}: NOT SET")
        all_ok = False

print()
if all_ok:
    print("✓ 所有环境变量已设置")
else:
    print("✗ 部分环境变量缺失！")
    print("\n请在 Zeabur 控制台检查环境变量设置。")
