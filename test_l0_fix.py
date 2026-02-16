"""
测试L0 Buffer修复 - 验证纯文本用户输入是否被正确记录
"""
import os
import asyncio
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 测试前清理
print("=" * 60)
print("L0 Buffer Bug修复测试")
print("=" * 60)

# 连接Supabase
from supabase import create_client

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# 获取测试前的记录数
def get_l0_stats():
    result = supabase.table("mem_l0_buffer") \
        .select("role, content, created_at") \
        .gte("created_at", (datetime.utcnow() - timedelta(minutes=5)).isoformat()) \
        .execute()

    if result.data:
        user_count = len([r for r in result.data if r['role'] == 'user'])
        ai_count = len([r for r in result.data if r['role'] == 'ai'])
        return user_count, ai_count, result.data
    return 0, 0, []

# 测试前统计
print("\n1. 测试前L0 Buffer状态（最近5分钟）:")
before_user, before_ai, before_data = get_l0_stats()
print(f"   User记录: {before_user}")
print(f"   AI记录: {before_ai}")

# 直接调用 _save_to_l0_buffer 方法测试
print("\n2. 模拟发送纯文本消息（无附件）...")

# 导入Graph
from graph import MemOSGraph

async def test_l0_save():
    graph = MemOSGraph()

    # 直接测试 _save_to_l0_buffer 方法
    test_message = f"[测试消息] 这是一条纯文本测试消息，时间戳: {datetime.utcnow().isoformat()}"

    graph._save_to_l0_buffer(
        role="user",
        content=test_message,
        attachments=[],  # 无附件
        perception=""
    )

    print(f"   已发送测试消息: {test_message[:50]}...")
    return test_message

# 运行测试
test_msg = asyncio.run(test_l0_save())

# 等待一下确保数据写入
import time
time.sleep(1)

# 测试后统计
print("\n3. 测试后L0 Buffer状态（最近5分钟）:")
after_user, after_ai, after_data = get_l0_stats()
print(f"   User记录: {after_user} (增加: {after_user - before_user})")
print(f"   AI记录: {after_ai} (增加: {after_ai - before_ai})")

# 验证结果
print("\n4. 验证结果:")
if after_user > before_user:
    # 查找刚才插入的记录
    new_records = [r for r in after_data if r not in before_data]
    if not new_records:
        # 通过内容查找
        new_records = [r for r in after_data if test_msg[:20] in r.get('content', '')]

    if new_records:
        print("   [OK] PASS: 纯文本用户消息已正确保存到L0 Buffer")
        print(f"   - Role: {new_records[0]['role']}")
        print(f"   - Content: {new_records[0]['content'][:60]}...")
    else:
        print("   ? 记录已保存但无法精确定位（可能是时间戳匹配问题）")
        # 显示最新的user记录
        user_records = [r for r in after_data if r['role'] == 'user']
        if user_records:
            latest = sorted(user_records, key=lambda x: x['created_at'], reverse=True)[0]
            print(f"   最新的user记录: {latest['content'][:60]}...")
else:
    print("   [FAIL] 纯文本用户消息未被保存到L0 Buffer！")
    print("   Bug可能仍然存在，请检查代码。")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
