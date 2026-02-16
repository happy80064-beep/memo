"""
实体合并工具 - Entity Merger
自动检测相似实体并生成合并建议
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Tuple, Set
from difflib import SequenceMatcher
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


class EntityMerger:
    """实体合并管理器"""

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )

    def get_all_entities(self) -> List[Dict]:
        """获取所有实体"""
        result = self.supabase.table("mem_l3_entities") \
            .select("id, path, name, description_md, entity_type, created_at") \
            .execute()
        return result.data or []

    def calculate_similarity(self, entity1: Dict, entity2: Dict) -> float:
        """
        计算两个实体的相似度
        返回 0-1 之间的分数
        """
        scores = []

        # 1. 名称相似度（最重要）
        name1 = entity1.get('name', '')
        name2 = entity2.get('name', '')
        if name1 and name2:
            name_sim = SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
            scores.append(('name', name_sim, 0.5))  # 权重50%

        # 2. 路径相似度
        path1 = entity1.get('path', '')
        path2 = entity2.get('path', '')
        if path1 and path2:
            # 提取路径最后一部分比较
            path_name1 = path1.split('/')[-1] if '/' in path1 else path1
            path_name2 = path2.split('/')[-1] if '/' in path2 else path2
            path_sim = SequenceMatcher(None, path_name1.lower(), path_name2.lower()).ratio()
            scores.append(('path', path_sim, 0.3))  # 权重30%

        # 3. 描述相似度（如果有描述）
        desc1 = entity1.get('description_md', '') or ''
        desc2 = entity2.get('description_md', '') or ''
        if desc1 and desc2 and len(desc1) > 20 and len(desc2) > 20:
            desc_sim = SequenceMatcher(None, desc1[:200], desc2[:200]).ratio()
            scores.append(('description', desc_sim, 0.2))  # 权重20%

        if not scores:
            return 0.0

        # 加权平均
        total_weight = sum(weight for _, _, weight in scores)
        weighted_sum = sum(score * weight for _, score, weight in scores)

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def find_duplicate_groups(self, threshold: float = 0.7) -> List[List[Dict]]:
        """
        查找相似实体组
        threshold: 相似度阈值，默认0.7
        """
        entities = self.get_all_entities()
        n = len(entities)

        # 构建相似度图
        similarity_graph = defaultdict(set)

        print(f"分析 {n} 个实体之间的相似度...")

        for i in range(n):
            for j in range(i + 1, n):
                sim = self.calculate_similarity(entities[i], entities[j])
                if sim >= threshold:
                    similarity_graph[entities[i]['id']].add((entities[j]['id'], sim))
                    similarity_graph[entities[j]['id']].add((entities[i]['id'], sim))

        # 使用并查集找连通分量（相似实体组）
        parent = {e['id']: e['id'] for e in entities}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # 合并相似的实体
        for entity_id, similar_entities in similarity_graph.items():
            for similar_id, _ in similar_entities:
                union(entity_id, similar_id)

        # 分组
        groups = defaultdict(list)
        for entity in entities:
            root = find(entity['id'])
            if root in similarity_graph or any(entity['id'] == eid for eid, _ in similarity_graph.get(entity['id'], [])):
                groups[root].append(entity)

        # 只返回包含多个实体的组
        return [group for group in groups.values() if len(group) > 1]

    def get_entity_facts(self, entity_id: str) -> List[Dict]:
        """获取实体的原子事实"""
        result = self.supabase.table("mem_l3_atomic_facts") \
            .select("id, content, status, created_at, valid_from") \
            .eq("entity_id", entity_id) \
            .eq("status", "active") \
            .execute()
        return result.data or []

    def generate_merge_report(self, groups: List[List[Dict]]) -> Dict:
        """生成合并建议报告"""
        reports = []

        for i, group in enumerate(groups, 1):
            report = {
                "group_id": i,
                "entities": [],
                "suggested_primary": None,
                "total_facts": 0,
                "merge_strategy": "",
                "risks": []
            }

            # 分析每个实体
            for entity in group:
                facts = self.get_entity_facts(entity['id'])
                entity_info = {
                    "id": entity['id'],
                    "path": entity['path'],
                    "name": entity['name'],
                    "fact_count": len(facts),
                    "facts": [f['content'] for f in facts[:5]],  # 只显示前5个
                    "created_at": entity['created_at']
                }
                report['entities'].append(entity_info)
                report['total_facts'] += len(facts)

            # 建议主实体（事实最多、路径最规范、创建最早的）
            primary_candidates = sorted(
                report['entities'],
                key=lambda x: (-x['fact_count'], len(x['path']), x['created_at'])
            )
            report['suggested_primary'] = primary_candidates[0]

            # 合并策略
            report['merge_strategy'] = f"以 '{report['suggested_primary']['path']}' 为主实体，迁移其他 {len(group)-1} 个实体的 {report['total_facts'] - report['suggested_primary']['fact_count']} 条事实"

            # 风险提示
            if len(group) > 3:
                report['risks'].append("实体数量较多，建议分批合并")

            # 检查是否有重复事实
            all_facts = []
            for entity in report['entities']:
                all_facts.extend(entity['facts'])
            if len(all_facts) != len(set(all_facts)):
                report['risks'].append("存在重复事实，合并后会自动去重")

            reports.append(report)

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "total_groups": len(groups),
            "total_entities_to_merge": sum(len(g) for g in groups),
            "reports": reports
        }

    def preview_merge(self, group: List[Dict], primary_entity: Dict) -> Dict:
        """预览合并后的结果"""
        preview = {
            "primary_entity": {
                "id": primary_entity['id'],
                "path": primary_entity['path'],
                "name": primary_entity['name']
            },
            "entities_to_merge": [],
            "facts_after_merge": [],
            "conflicts": []
        }

        # 收集所有事实
        all_facts = []
        for entity in group:
            if entity['id'] == primary_entity['id']:
                continue

            facts = self.get_entity_facts(entity['id'])
            preview['entities_to_merge'].append({
                "id": entity['id'],
                "path": entity['path'],
                "facts_to_migrate": len(facts)
            })

            for fact in facts:
                all_facts.append({
                    "content": fact['content'],
                    "from_entity": entity['path'],
                    "created_at": fact['created_at']
                })

        # 去重
        seen_contents = set()
        for fact in all_facts:
            if fact['content'] not in seen_contents:
                preview['facts_after_merge'].append(fact)
                seen_contents.add(fact['content'])
            else:
                preview['conflicts'].append(f"重复事实已去重: {fact['content'][:50]}...")

        # 加上主实体原有的事实
        primary_facts = self.get_entity_facts(primary_entity['id'])
        for fact in primary_facts:
            if fact['content'] not in seen_contents:
                preview['facts_after_merge'].append({
                    "content": fact['content'],
                    "from_entity": primary_entity['path'],
                    "created_at": fact['created_at']
                })

        return preview

    def execute_merge(self, group: List[Dict], primary_entity: Dict, confirmed: bool = False) -> Dict:
        """
        执行实体合并
        confirmed: 是否已确认执行（False时只预览）
        """
        if not confirmed:
            return {
                "status": "preview",
                "preview": self.preview_merge(group, primary_entity)
            }

        results = {
            "status": "executed",
            "primary_entity": primary_entity['path'],
            "migrated_facts": 0,
            "marked_entities": [],
            "errors": []
        }

        # 迁移事实
        for entity in group:
            if entity['id'] == primary_entity['id']:
                continue

            facts = self.get_entity_facts(entity['id'])

            for fact in facts:
                try:
                    # 更新事实的entity_id到主实体
                    self.supabase.table("mem_l3_atomic_facts") \
                        .update({"entity_id": primary_entity['id']}) \
                        .eq("id", fact['id']) \
                        .execute()
                    results['migrated_facts'] += 1
                except Exception as e:
                    results['errors'].append(f"迁移事实失败 {fact['id']}: {str(e)}")

            # 标记旧实体为已合并
            try:
                self.supabase.table("mem_l3_entities") \
                    .update({
                        "status": "merged",
                        "merged_into": primary_entity['id'],
                        "description_md": f"[已合并到 {primary_entity['path']}]"
                    }) \
                    .eq("id", entity['id']) \
                    .execute()
                results['marked_entities'].append(entity['path'])
            except Exception as e:
                results['errors'].append(f"标记实体失败 {entity['path']}: {str(e)}")

        return results


def main():
    """主函数：生成合并建议报告"""
    merger = EntityMerger()

    print("=" * 70)
    print("实体合并分析工具")
    print("=" * 70)

    # 查找相似实体组
    print("\n正在分析实体相似度...")
    groups = merger.find_duplicate_groups(threshold=0.6)

    if not groups:
        print("\n未发现相似实体组（阈值0.6）")
        print("可以尝试降低阈值重新检测")
        return

    # 生成报告
    report = merger.generate_merge_report(groups)

    print(f"\n发现 {report['total_groups']} 组相似实体")
    print(f"共涉及 {report['total_entities_to_merge']} 个实体")
    print("\n" + "=" * 70)

    # 显示详细报告
    for r in report['reports']:
        print(f"\n【相似组 #{r['group_id']}】")
        print(f"建议主实体: {r['suggested_primary']['path']}")
        print(f"包含实体数: {len(r['entities'])}")
        print(f"总事实数: {r['total_facts']}")
        print(f"合并策略: {r['merge_strategy']}")

        if r['risks']:
            print(f"风险提示: {', '.join(r['risks'])}")

        print("\n实体详情:")
        for entity in r['entities']:
            marker = "★ 主实体" if entity['id'] == r['suggested_primary']['id'] else "  从实体"
            print(f"  {marker}: {entity['path']}")
            print(f"           事实数: {entity['fact_count']}")
            if entity['facts']:
                print(f"           示例: {entity['facts'][0][:60]}...")

        # 显示预览
        print("\n合并后预览:")
        primary_entity = next(e for e in r['entities'] if e['id'] == r['suggested_primary']['id'])
        preview = merger.preview_merge(
            [e for e in merger.get_all_entities() if e['id'] in [ent['id'] for ent in r['entities']]],
            primary_entity
        )
        print(f"  合并后总事实数: {len(preview['facts_after_merge'])}")
        if preview['conflicts']:
            print(f"  需要处理的冲突: {len(preview['conflicts'])}")

        print("\n" + "-" * 70)

    # 保存报告
    report_file = f"merge_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n详细报告已保存: {report_file}")
    print("\n使用说明:")
    print("1. 查看报告，确认合并建议")
    print("2. 如需执行合并，调用 merger.execute_merge() 并设置 confirmed=True")


if __name__ == "__main__":
    main()
