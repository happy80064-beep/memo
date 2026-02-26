# -*- coding: utf-8 -*-
"""
检查现有 description_md 的称呼风格
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
print('检查 description_md 中如何称呼用户')
print('=' * 80)
print()

# 检查几个关键实体
entities = [
    '/people/li-guodong',
    '/people/li-jiaze',
    '/people/yang-guihua',
    '/people/jia-xueyun'
]

for path in entities:
    entity = supabase.table('mem_l3_entities') \
        .select('path, name, description_md') \
        .eq('path', path) \
        .execute()

    if entity.data:
        desc = entity.data[0]['description_md']
        print(f"\n{'='*60}")
        print(f"实体: {path}")
        print(f"\n如何提及'用户'：")

        # 找出所有提到"用户"的句子
        import re
        sentences = re.findall(r'[^。]*用户[^。]*。', desc)
        for s in sentences[:5]:
            print(f"  • {s}")

        print(f"\n如何称呼实体自己：")
        # 找出自称的部分
        name = entity.data[0]['name']
        self_refs = re.findall(rf'[^。]*{name}[^。]*。', desc)
        for s in self_refs[:3]:
            print(f"  • {s}")

print("\n" + "=" * 80)
print("总结：description 使用的是'用户'还是'李俊杰'？")
print("=" * 80)
