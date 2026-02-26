# -*- coding: utf-8 -*-
"""
检查表结构
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

print("检查 mem_l3_entities 表结构...")
print()

# 获取一条记录来看结构
sample = supabase.table('mem_l3_entities') \
    .select('*') \
    .limit(1) \
    .execute()

if sample.data:
    print("表字段:")
    for key in sample.data[0].keys():
        print(f"  - {key}")
else:
    print("表为空，无法获取字段信息")

print()
print("检查 mem_l3_atomic_facts 表结构...")
print()

sample2 = supabase.table('mem_l3_atomic_facts') \
    .select('*') \
    .limit(1) \
    .execute()

if sample2.data:
    print("表字段:")
    for key in sample2.data[0].keys():
        print(f"  - {key}")
else:
    print("表为空，无法获取字段信息")
