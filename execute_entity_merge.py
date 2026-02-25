# -*- coding: utf-8 -*-
"""
执行人物实体合并 - 一次性解决所有重复实体
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

class EntityMerger:
    """实体合并执行器"""

    def __init__(self):
        self.supabase = supabase
        self.stats = {
            "merged_entities": 0,
            "migrated_facts": 0,
            "skipped_facts": 0,
            "errors": []
        }

    def get_entity_by_path(self, path):
        """通过路径获取实体"""
        result = self.supabase.table('mem_l3_entities') \
            .select('id, path, name') \
            .eq('path', path) \
            .execute()
        return result.data[0] if result.data else None

    def get_entity_facts(self, entity_id, status='active'):
        """获取实体的指定状态事实"""
        result = self.supabase.table('mem_l3_atomic_facts') \
            .select('id, content, status, context_json') \
            .eq('entity_id', entity_id) \
            .eq('status', status) \
            .execute()
        return result.data or []

    def migrate_fact(self, fact, target_entity_id, target_path):
        """迁移单个事实"""
        try:
            # 检查目标实体是否已有相同事实（去重）
            existing = self.supabase.table('mem_l3_atomic_facts') \
                .select('id') \
                .eq('entity_id', target_entity_id) \
                .eq('content', fact['content']) \
                .eq('status', 'active') \
                .execute()

            if existing.data:
                print(f"    跳过重复: {fact['content'][:40]}...")
                self.stats["skipped_facts"] += 1
                return True

            # 插入新事实到目标实体
            context = fact.get('context_json', {}) or {}
            context.update({
                'migrated_from': fact.get('entity_id'),
                'migrated_at': datetime.utcnow().isoformat()
            })

            self.supabase.table('mem_l3_atomic_facts').insert({
                'entity_id': target_entity_id,
                'content': fact['content'],
                'status': 'active',
                'source_type': 'manual_entry',
                'context_json': context
            }).execute()

            # 标记源事实为superseded
            self.supabase.table('mem_l3_atomic_facts') \
                .update({
                    'status': 'superseded',
                    'context_json': {
                        'superseded_reason': '实体合并',
                        'migrated_to': target_path,
                        'migrated_at': datetime.utcnow().isoformat()
                    }
                }) \
                .eq('id', fact['id']) \
                .execute()

            print(f"    已迁移: {fact['content'][:50]}...")
            self.stats["migrated_facts"] += 1
            return True

        except Exception as e:
            print(f"    错误: {e}")
            self.stats["errors"].append(f"迁移事实失败: {fact['id']}: {e}")
            return False

    def simple_merge(self, source_path, target_path, phase_name):
        """简单合并：将源实体的所有active事实迁移到目标实体"""
        print(f"\n【{phase_name}】")
        print(f"合并: {source_path} -> {target_path}")
        print("-" * 70)

        source = self.get_entity_by_path(source_path)
        if not source:
            print(f"  源实体不存在: {source_path}")
            return

        target = self.get_entity_by_path(target_path)
        if not target:
            print(f"  目标实体不存在: {target_path}")
            return

        facts = self.get_entity_facts(source['id'], 'active')
        if not facts:
            print(f"  没有active事实需要迁移")
        else:
            print(f"  迁移 {len(facts)} 条事实...")
            for fact in facts:
                self.migrate_fact(fact, target['id'], target_path)

        # 标记源实体为已合并
        self.supabase.table('mem_l3_entities') \
            .update({
                'description_md': f"[已合并到 {target_path}] 原实体: {source['name']}"
            }) \
            .eq('id', source['id']) \
            .execute()

        print(f"  ✓ 完成")
        self.stats["merged_entities"] += 1

    def split_grandparents_facts(self, source_path, grandpa_path, grandma_path):
        """拆分爷爷奶奶合称的事实"""
        print(f"\n【拆分爷爷奶奶事实】")
        print(f"源: {source_path}")
        print(f"爷爷 -> {grandpa_path}")
        print(f"奶奶 -> {grandma_path}")
        print("-" * 70)

        source = self.get_entity_by_path(source_path)
        if not source:
            print(f"  源实体不存在: {source_path}")
            return

        grandpa = self.get_entity_by_path(grandpa_path)
        grandma = self.get_entity_by_path(grandma_path)

        facts = self.get_entity_facts(source['id'], 'active')
        if not facts:
            print(f"  没有active事实")
            return

        print(f"  分析 {len(facts)} 条事实...")

        for fact in facts:
            content = fact['content']
            target_id = None
            target_path_str = None

            # 判断事实属于爷爷还是奶奶
            if '爷爷' in content and '奶奶' not in content:
                if grandpa:
                    target_id = grandpa['id']
                    target_path_str = grandpa_path
                    print(f"    分配给爷爷: {content[:40]}...")
            elif '奶奶' in content and '爷爷' not in content:
                if grandma:
                    target_id = grandma['id']
                    target_path_str = grandma_path
                    print(f"    分配给奶奶: {content[:40]}...")
            elif '爷爷' in content and '奶奶' in content:
                # 同时涉及两人，拆分到两人
                if grandpa:
                    print(f"    分配给爷爷: {content[:40]}...")
                    self.migrate_fact(fact, grandpa['id'], grandpa_path)
                if grandma:
                    print(f"    分配给奶奶: {content[:40]}...")
                    # 复制一份给奶奶
                    self.supabase.table('mem_l3_atomic_facts').insert({
                        'entity_id': grandma['id'],
                        'content': content,
                        'status': 'active',
                        'source_type': 'manual_entry',
                        'context_json': {
                            'split_from': fact['id'],
                            'split_at': datetime.utcnow().isoformat()
                        }
                    }).execute()
                    self.stats["migrated_facts"] += 1
                continue
            else:
                # 无法判断，默认给爷爷
                if grandpa:
                    target_id = grandpa['id']
                    target_path_str = grandpa_path
                    print(f"    默认分配给爷爷: {content[:40]}...")

            if target_id:
                self.migrate_fact(fact, target_id, target_path_str)

        # 标记源实体
        self.supabase.table('mem_l3_entities') \
            .update({
                'description_md': f"[已拆分] 事实已拆分到 {grandpa_path} 和 {grandma_path}"
            }) \
            .eq('id', source['id']) \
            .execute()

        print(f"  ✓ 完成")
        self.stats["merged_entities"] += 1

    def execute_all_merges(self):
        """执行所有合并操作"""
        print("=" * 70)
        print("开始执行人物实体合并")
        print("=" * 70)

        # Phase 1: 李俊杰相关
        self.simple_merge('/people/user', '/people/li-jun-jie', 'Phase 1: 李俊杰')
        self.simple_merge('/people/俊杰', '/people/li-jun-jie', 'Phase 1: 李俊杰')
        self.simple_merge('/people/jun-jie', '/people/li-jun-jie', 'Phase 1: 李俊杰')
        self.simple_merge('/people/li-junjie', '/people/li-jun-jie', 'Phase 1: 李俊杰')

        # Phase 2: 李佳泽相关
        self.simple_merge('/people/user-child', '/people/li-jiaze', 'Phase 2: 李佳泽')
        self.simple_merge('/people/child-of-user', '/people/li-jiaze', 'Phase 2: 李佳泽')
        self.simple_merge('/people/son', '/people/li-jiaze', 'Phase 2: 李佳泽')
        self.simple_merge('/people/6-bao', '/people/li-jiaze', 'Phase 2: 李佳泽')
        self.simple_merge('/people/jia-ze', '/people/li-jiaze', 'Phase 2: 李佳泽')
        self.simple_merge('/people/jiaze', '/people/li-jiaze', 'Phase 2: 李佳泽')
        self.simple_merge('/people/李佳泽', '/people/li-jiaze', 'Phase 2: 李佳泽')

        # Phase 3: 贾雪云相关
        self.simple_merge('/people/jiaze-s-mother', '/people/jia-xueyun', 'Phase 3: 贾雪云')
        self.simple_merge('/people/jia-jie', '/people/jia-xueyun', 'Phase 3: 贾雪云')
        self.simple_merge('/people/贾雪云', '/people/jia-xueyun', 'Phase 3: 贾雪云')
        self.simple_merge('/people/jia-xue-yun', '/people/jia-xueyun', 'Phase 3: 贾雪云')

        # Phase 4: 家庭关系合并
        self.simple_merge('/people/jun-jie-s-father', '/people/li-guodong', 'Phase 4: 家庭关系')
        self.simple_merge('/people/jun-jie-s-mother', '/people/yang-guihua', 'Phase 4: 家庭关系')
        self.simple_merge('/people/俊杰的妈妈', '/people/yang-guihua', 'Phase 4: 家庭关系')
        self.simple_merge('/people/user-grandmother', '/people/gao-jianqiu', 'Phase 4: 家庭关系')

        # Phase 5: 爷爷奶奶拆分
        self.split_grandparents_facts('/people/jiaze-s-grandparents', '/people/li-guodong', '/people/yang-guihua')
        self.split_grandparents_facts('/people/jiazes-grandparents', '/people/li-guodong', '/people/yang-guihua')

        # Phase 6: 去重
        self.simple_merge('/people/yang-gui-hua', '/people/yang-guihua', 'Phase 6: 去重')
        self.simple_merge('/people/李国栋', '/people/li-guodong', 'Phase 6: 去重')
        self.simple_merge('/people/li-guo-dong', '/people/li-guodong', 'Phase 6: 去重')

        # 打印统计
        print("\n" + "=" * 70)
        print("合并完成统计")
        print("=" * 70)
        print(f"合并实体数: {self.stats['merged_entities']}")
        print(f"迁移事实数: {self.stats['migrated_facts']}")
        print(f"跳过重复数: {self.stats['skipped_facts']}")
        if self.stats['errors']:
            print(f"错误数: {len(self.stats['errors'])}")
            for error in self.stats['errors']:
                print(f"  - {error}")
        print("=" * 70)

if __name__ == "__main__":
    merger = EntityMerger()
    merger.execute_all_merges()
