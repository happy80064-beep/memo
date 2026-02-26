# -*- coding: utf-8 -*-
"""
检查atomic_facts状态分布
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print('=' * 80)
print('Atomic Facts 状态统计')
print('=' * 80)
print()

# 按状态统计
result = supabase.table('mem_l3_atomic_facts') \
    .select('status', count='exact') \
    .execute()

# 需要按status分组查询
statuses = ['active', 'superseded', 'deleted', 'pending']

for status in statuses:
    count_result = supabase.table('mem_l3_atomic_facts') \
        .select('id', count='exact') \
        .eq('status', status) \
        .execute()
    print(f"{status}: {count_result.count}")

print()
print('=' * 80)
print('最近2天创建的 Facts')
print('=' * 80)
print()

from datetime import datetime, timedelta
two_days_ago = (datetime.utcnow() - timedelta(days=2)).isoformat()

recent_facts = supabase.table('mem_l3_atomic_facts') \
    .select('id, content, status, created_at') \
    .gte('created_at', two_days_ago) \
    .execute()

print(f"最近2天创建的facts数量: {len(recent_facts.data) if recent_facts.data else 0}")

if recent_facts.data:
    # 按状态分组
    by_status = {}
    for f in recent_facts.data:
        s = f['status']
        if s not in by_status:
            by_status[s] = []
        by_status[s].append(f)

    for status, facts in by_status.items():
        print(f"\n  {status}: {len(facts)} 条")
        for f in facts[:5]:  # 只显示前5个
            print(f"    - {f['content'][:60]}...")
        if len(facts) > 5:
            print(f"    ... 还有 {len(facts) - 5} 条")

print()
print('=' * 80)
print('superseded facts 预览（最近10条）')
print('=' * 80)
print()

superseded = supabase.table('mem_l3_atomic_facts') \
    .select('content, context_json, created_at') \
    .eq('status', 'superseded') \
    .order('created_at', desc=True) \
    .limit(10) \
    .execute()

if superseded.data:
    for f in superseded.data:
        print(f"内容: {f['content'][:80]}...")
        print(f"原因: {f.get('context_json', {})}")
        print()
else:
    print("没有superseded facts")

print()
print('=' * 80)
print("检查完成")
print('=' * 80)
