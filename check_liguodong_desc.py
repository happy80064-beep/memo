# -*- coding: utf-8 -*-
"""
检查李国栋实体的description内容
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
print('检查关键人物实体的 description_md')
print('=' * 80)
print()

paths = [
    '/people/li-guodong',
    '/people/li-jiaze',
    '/people/yang-yong',
    '/people/yang-guihua',
    '/people/jia-xueyun'
]

for path in paths:
    entity = supabase.table('mem_l3_entities') \
        .select('path, name, description_md') \
        .eq('path', path) \
        .execute()

    if entity.data:
        e = entity.data[0]
        desc = e.get('description_md', '')

        print(f"\n{'='*60}")
        print(f"实体: {path}")
        print(f"姓名: {e['name']}")
        print(f"描述长度: {len(desc)} 字符")

        # 检查关键词
        keywords = ['父亲', '爸爸', '母亲', '妈妈', '儿子', '用户', '生日']
        found = [k for k in keywords if k in desc]
        print(f"包含关键词: {found}")

        # 显示描述前300字符
        if desc:
            print(f"\n描述预览:")
            print(desc[:500])
            if len(desc) > 500:
                print("...")
    else:
        print(f"\n实体 {path} 不存在")

print("\n" + "=" * 80)
