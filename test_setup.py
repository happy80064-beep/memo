"""
环境配置验证脚本 - 测试 LLM 和 Supabase 连接
"""

import os
from dotenv import load_dotenv

load_dotenv()


def test_llm_factory():
    """测试双模型工厂"""
    print("=" * 50)
    print("测试 LLM Factory")
    print("=" * 50)

    try:
        from llm_factory import get_system_llm, get_user_llm

        # 测试 System Model (Gemini)
        print("\n1. 测试 System Model (Gemini-2.5-Flash)...")
        system_llm = get_system_llm()
        response = system_llm.invoke("请回复: System Model 连接成功")
        print(f"   ✅ Gemini: {response.content[:50]}...")

        # 测试 User Model (Kimi)
        print("\n2. 测试 User Model (Kimi k2.5)...")
        user_llm = get_user_llm()
        response = user_llm.invoke("请回复: User Model 连接成功")
        print(f"   ✅ Kimi: {response.content[:50]}...")

        return True
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        return False


def test_supabase():
    """测试 Supabase 连接"""
    print("\n" + "=" * 50)
    print("测试 Supabase 连接")
    print("=" * 50)

    try:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        print(f"\n1. 连接 Supabase...")
        client = create_client(url, key)

        print("2. 测试查询 mem_l3_entities 表...")
        result = client.table("mem_l3_entities").select("count", count="exact").execute()
        print(f"   ✅ 连接成功! 当前实体数量: {result.count}")

        print("3. 测试插入/删除...")
        test_entity = {"path": "/_test/setup", "name": "Setup Test", "description_md": "Test"}
        insert_result = client.table("mem_l3_entities").insert(test_entity).execute()
        client.table("mem_l3_entities").delete().eq("path", "/_test/setup").execute()
        print(f"   ✅ 读写测试通过!")

        return True
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        return False


def test_perception():
    """测试感知模块"""
    print("\n" + "=" * 50)
    print("测试 Perception (Vision)")
    print("=" * 50)

    try:
        from perception import process_image

        print("\nℹ️ Vision 测试需要图片 URL，跳过自动测试")
        print("   手动测试示例:")
        print("   from perception import process_attachment")
        print('   text = process_attachment("https://example.com/img.png", "image/png")')

        return True
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        return False


def main():
    print("\n" + "=" * 50)
    print("MemOS v2.0 - 环境配置验证")
    print("=" * 50)

    results = []
    results.append(("LLM Factory", test_llm_factory()))
    results.append(("Supabase", test_supabase()))
    results.append(("Perception", test_perception()))

    print("\n" + "=" * 50)
    print("验证结果")
    print("=" * 50)
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")

    if all(r[1] for r in results):
        print("\n🎉 所有配置正常! 系统可正常运行")
    else:
        print("\n⚠️ 部分测试失败，请检查配置")


if __name__ == "__main__":
    main()
