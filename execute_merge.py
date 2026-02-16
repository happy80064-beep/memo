"""
执行实体合并 - 按用户确认的方案
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


class EntityMergeExecutor:
    """实体合并执行器"""

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )

    def get_entity_by_path(self, path: str) -> dict:
        """通过路径获取实体"""
        result = self.supabase.table("mem_l3_entities") \
            .select("id, path, name, description_md") \
            .eq("path", path) \
            .execute()
        return result.data[0] if result.data else None

    def get_entity_facts(self, entity_id: str) -> list:
        """获取实体的原子事实"""
        result = self.supabase.table("mem_l3_atomic_facts") \
            .select("id, content, status, created_at") \
            .eq("entity_id", entity_id) \
            .eq("status", "active") \
            .execute()
        return result.data or []

    def execute_merge(self, primary_path: str, duplicate_paths: list, dry_run: bool = True) -> dict:
        """
        执行实体合并

        Args:
            primary_path: 主实体路径
            duplicate_paths: 要合并的从实体路径列表
            dry_run: True=预览, False=实际执行
        """
        results = {
            "status": "preview" if dry_run else "executed",
            "primary_entity": primary_path,
            "timestamp": datetime.utcnow().isoformat(),
            "migrations": [],
            "errors": []
        }

        # 获取主实体
        primary = self.get_entity_by_path(primary_path)
        if not primary:
            results["errors"].append(f"主实体不存在: {primary_path}")
            return results

        primary_facts = self.get_entity_facts(primary['id'])
        results["primary_facts_before"] = len(primary_facts)

        print(f"\n{'='*70}")
        print(f"合并到主实体: {primary_path}")
        print(f"主实体当前事实数: {len(primary_facts)}")
        print(f"{'='*70}")

        # 处理每个从实体
        for dup_path in duplicate_paths:
            dup_entity = self.get_entity_by_path(dup_path)
            if not dup_entity:
                results["errors"].append(f"从实体不存在: {dup_path}")
                continue

            dup_facts = self.get_entity_facts(dup_entity['id'])
            print(f"\n处理从实体: {dup_path}")
            print(f"  事实数: {len(dup_facts)}")

            migration = {
                "from_path": dup_path,
                "from_id": dup_entity['id'],
                "facts_migrated": 0,
                "facts_skipped": 0,
                "details": []
            }

            # 迁移事实
            for fact in dup_facts:
                # 检查是否已存在（去重）
                existing = any(f['content'] == fact['content'] for f in primary_facts)

                if existing:
                    migration["facts_skipped"] += 1
                    migration["details"].append({
                        "fact_id": fact['id'],
                        "content": fact['content'][:60],
                        "action": "skipped",
                        "reason": "duplicate"
                    })
                    print(f"    [跳过重复] {fact['content'][:60]}...")
                else:
                    if not dry_run:
                        try:
                            # 更新事实的entity_id
                            self.supabase.table("mem_l3_atomic_facts") \
                                .update({"entity_id": primary['id']}) \
                                .eq("id", fact['id']) \
                                .execute()
                            migration["facts_migrated"] += 1
                            print(f"    [已迁移] {fact['content'][:60]}...")
                        except Exception as e:
                            results["errors"].append(f"迁移失败 {fact['id']}: {str(e)}")
                            migration["facts_skipped"] += 1
                    else:
                        migration["facts_migrated"] += 1
                        print(f"    [预览-将迁移] {fact['content'][:60]}...")

            # 标记从实体为已合并
            if not dry_run and migration["facts_migrated"] > 0:
                try:
                    self.supabase.table("mem_l3_entities") \
                        .update({
                            "status": "merged",
                            "merged_into": primary['id'],
                            "description_md": f"[已合并到 {primary_path}]"
                        }) \
                        .eq("id", dup_entity['id']) \
                        .execute()
                    print(f"  [已标记] 实体已标记为合并状态")
                except Exception as e:
                    results["errors"].append(f"标记实体失败 {dup_path}: {str(e)}")

            results["migrations"].append(migration)

        # 统计
        total_migrated = sum(m["facts_migrated"] for m in results["migrations"])
        total_skipped = sum(m["facts_skipped"] for m in results["migrations"])

        print(f"\n{'='*70}")
        print(f"合并统计:")
        print(f"  迁移事实数: {total_migrated}")
        print(f"  跳过重复数: {total_skipped}")
        print(f"  合并后总事实数: {len(primary_facts) + total_migrated}")
        print(f"{'='*70}")

        return results


def main():
    """执行确认的合并方案"""
    executor = EntityMergeExecutor()

    print("="*70)
    print("实体合并执行器")
    print("="*70)

    # 方案1：合并李国栋相关实体
    print("\n【方案1】合并李国栋实体")
    print("-"*70)

    # 先预览
    result1 = executor.execute_merge(
        primary_path="/people/li-guodong",
        duplicate_paths=["/people/li-guo-dong", "/people/李国栋"],
        dry_run=True
    )

    print("\n是否执行？(输入 'yes' 执行，其他取消):")
    # 自动执行（用户已确认）
    print("用户已确认，执行合并...")
    result1 = executor.execute_merge(
        primary_path="/people/li-guodong",
        duplicate_paths=["/people/li-guo-dong", "/people/李国栋"],
        dry_run=False
    )

    # 方案2：合并user-father相关实体
    print("\n【方案2】合并user-father实体")
    print("-"*70)

    result2 = executor.execute_merge(
        primary_path="/people/user-father",
        duplicate_paths=["/people/father", "/people/wo-ba"],
        dry_run=False
    )

    # 保存结果
    # 方案3：合并李俊杰相关实体
    print("\n【方案3】合并李俊杰实体")
    print("-"*70)

    result3 = executor.execute_merge(
        primary_path="/people/li-jun-jie",
        duplicate_paths=["/people/li-junjie", "/people/jun-jie"],
        dry_run=False
    )

    results = {
        "executed_at": datetime.utcnow().isoformat(),
        "merges": [result1, result2, result3]
    }

    result_file = f"merge_executed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"合并完成！结果已保存: {result_file}")
    print(f"{'='*70}")

    # 验证
    print("\n验证合并结果...")
    primary = executor.get_entity_by_path("/people/li-guodong")
    if primary:
        facts = executor.get_entity_facts(primary['id'])
        print(f"\n/people/li-guodong 现在的事实数: {len(facts)}")
        for f in facts:
            print(f"  - {f['content']}")


if __name__ == "__main__":
    main()
