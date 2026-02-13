"""
验证提取结果
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print("=" * 50)
print("L3 Entities:")
print("=" * 50)
entities = client.table("mem_l3_entities").select("*").execute()
for e in entities.data:
    print(f"\nPath: {e['path']}")
    print(f"Name: {e['name']}")
    print(f"Type: {e['entity_type']}")
    print(f"Description: {e['description_md'][:100]}...")

print("\n" + "=" * 50)
print("Atomic Facts:")
print("=" * 50)
facts = client.table("mem_l3_atomic_facts").select("*, mem_l3_entities(path)").execute()
for f in facts.data:
    print(f"\nEntity: {f['mem_l3_entities']['path']}")
    print(f"Content: {f['content'][:80]}...")
    print(f"Status: {f['status']}")

print("\n" + "=" * 50)
print("L0 Buffer (Processed):")
print("=" * 50)
l0 = client.table("mem_l0_buffer").select("*").eq("processed", True).execute()
print(f"Processed: {len(l0.data)} messages")
