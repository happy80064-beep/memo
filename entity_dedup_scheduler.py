# -*- coding: utf-8 -*-
"""
定时实体去重任务 - 增量匹配版本
每天 02:30 运行，检查最近24小时的新实体与历史实体匹配
"""
import os
import sys
import json
import asyncio
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
from langchain_core.messages import SystemMessage, HumanMessage

from llm_factory import get_system_llm

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

llm = get_system_llm()

# 飞书配置（用于发送报告）
FEISHU_REPORT_CHAT_ID = os.getenv("FEISHU_REPORT_CHAT_ID", "")  # 报告推送的聊天ID


def get_recent_entities(hours: int = 24):
    """获取最近N小时创建的实体（非待编译）"""
    since = datetime.now() - timedelta(hours=hours)

    result = supabase.table("mem_l3_entities") \
        .select("id, path, name, description_md, created_at") \
        .eq("entity_type", "person") \
        .gte("created_at", since.isoformat()) \
        .execute()

    # 过滤掉待编译的
    entities = []
    for e in result.data:
        desc = e.get("description_md", "")
        if desc and "待编译" not in desc:
            entities.append(e)

    return entities


def get_historical_entities():
    """获取历史实体（非待编译，创建时间超过24小时）"""
    since = datetime.now() - timedelta(hours=24)

    result = supabase.table("mem_l3_entities") \
        .select("id, path, name, description_md") \
        .eq("entity_type", "person") \
        .lt("created_at", since.isoformat()) \
        .execute()

    # 过滤掉待编译的
    entities = []
    for e in result.data:
        desc = e.get("description_md", "")
        if desc and "待编译" not in desc:
            entities.append(e)

    return entities


def get_active_facts_count(entity_id: str) -> int:
    """获取实体的 active facts 数量"""
    result = supabase.table("mem_l3_atomic_facts") \
        .select("id", count="exact") \
        .eq("entity_id", entity_id) \
        .eq("status", "active") \
        .execute()
    return result.count


def migrate_facts(from_entity_id: str, to_entity_id: str) -> int:
    """迁移 facts 从源实体到目标实体"""
    facts = supabase.table("mem_l3_atomic_facts") \
        .select("*") \
        .eq("entity_id", from_entity_id) \
        .execute()

    migrated = 0
    for fact in facts.data:
        try:
            supabase.table("mem_l3_atomic_facts") \
                .update({"entity_id": to_entity_id}) \
                .eq("id", fact["id"]) \
                .execute()
            migrated += 1
        except Exception as ex:
            print(f"    迁移 fact 失败: {ex}")

    return migrated


def delete_entity(entity_id: str, path: str) -> bool:
    """删除实体（确认 facts 已迁移）"""
    # 检查是否还有 facts
    remaining = get_active_facts_count(entity_id)

    if remaining > 0:
        print(f"  还有 {remaining} 个 facts 未迁移，保留实体: {path}")
        return False

    try:
        supabase.table("mem_l3_entities") \
            .delete() \
            .eq("id", entity_id) \
            .execute()
        print(f"  已删除实体: {path}")
        return True
    except Exception as e:
        print(f"  删除失败 {path}: {e}")
        return False


def ai_judge_same_person(new_entity: dict, existing_entities: list) -> str:
    """
    使用 AI 判断新实体是否与某个已有实体为同一人
    返回: "NEW" | "UNCLEAR" | 匹配实体的ID
    """
    if not existing_entities:
        return "NEW"

    # 构建候选列表
    candidates_text = ""
    for i, e in enumerate(existing_entities[:10]):  # 最多10个候选
        desc = e.get("description_md", "")[:200]
        candidates_text += f"[{i}] {e['name']} (path: {e['path']})\n描述: {desc}\n\n"

    new_desc = new_entity.get("description_md", "")[:300]

    prompt = f"""你是一个实体去重专家。判断新创建的人物实体是否已存在于已有实体列表中。

【新实体】
Name: {new_entity['name']}
Path: {new_entity['path']}
描述: {new_desc}

【已有实体候选（最多10个）】
{candidates_text}

判断标准：
- 如果新实体与某个已有实体明显是同一人（姓名相同、相似，或描述信息一致）→ 回复 "MATCH: [编号]"
- 如果是全新的人物，不存在于列表中 → 回复 "NEW"
- 如果信息不足无法确定 → 回复 "UNCLEAR"

重要提示：
- 只有非常确定是同一人时才回复 MATCH
- 如果不确定，优先回复 UNCLEAR 而不是随意匹配

只回复以下格式之一：
MATCH: 0
MATCH: 1
NEW
UNCLEAR
"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        result = response.content.strip()

        # 解析结果
        if result.startswith("MATCH:"):
            try:
                idx = int(result.split(":")[1].strip())
                if 0 <= idx < len(existing_entities):
                    return existing_entities[idx]["id"]
            except:
                pass
            return "UNCLEAR"
        elif result == "NEW":
            return "NEW"
        else:
            return "UNCLEAR"

    except Exception as e:
        print(f"AI 判断失败: {e}")
        return "UNCLEAR"


def cleanup_stale_todo_entities(days: int = 30) -> int:
    """清理超过N天仍是待编译状态的实体"""
    since = datetime.now() - timedelta(days=days)

    # 查找超期待编译实体
    stale = supabase.table("mem_l3_entities") \
        .select("id, path, name") \
        .eq("entity_type", "person") \
        .lt("created_at", since.isoformat()) \
        .like("description_md", "%待编译%") \
        .execute()

    deleted = 0
    for entity in stale.data:
        # 检查是否有 facts
        facts_count = get_active_facts_count(entity["id"])

        if facts_count == 0:
            # 没有 facts 且长期待编译，删除
            try:
                supabase.table("mem_l3_entities") \
                    .delete() \
                    .eq("id", entity["id"]) \
                    .execute()
                print(f"  删除超期待编译实体: {entity['path']}")
                deleted += 1
            except Exception as e:
                print(f"  删除失败 {entity['path']}: {e}")

    return deleted


def generate_report(merged_list: list, kept_list: list, deleted_stale: int) -> str:
    """生成报告文本"""
    total_checked = len(merged_list) + len(kept_list)

    report = f"""🤖 MemOS 每日实体去重报告

📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 统计：
- 检查新实体：{total_checked} 个
- 成功合并：{len(merged_list)} 个
- 保留为新实体：{len(kept_list)} 个
"""

    if merged_list:
        report += f"\n✅ 合并详情：\n"
        for item in merged_list:
            report += f"• {item['from']} → {item['to']} (迁移 {item['facts']} 个 facts)\n"

    if kept_list:
        report += f"\n📋 保留为新实体：\n"
        for item in kept_list:
            report += f"• {item['name']} ({item['reason']})\n"

    if deleted_stale > 0:
        report += f"\n🗑️ 清理超期待编译实体：{deleted_stale} 个\n"

    return report


async def send_report_to_feishu(report: str):
    """发送报告到飞书"""
    if not FEISHU_REPORT_CHAT_ID:
        print("未配置 FEISHU_REPORT_CHAT_ID，跳过发送报告")
        return

    try:
        # 动态导入避免循环依赖
        from feishu_bot import send_feishu_message
        await send_feishu_message(FEISHU_REPORT_CHAT_ID, report)
        print("报告已发送到飞书")
    except Exception as e:
        print(f"发送飞书报告失败: {e}")


def daily_incremental_dedup():
    """主函数：每日增量去重"""
    print(f"[{datetime.now().isoformat()}] 开始每日增量去重...")
    print()

    # 1. 获取最近24小时的新实体
    new_entities = get_recent_entities(hours=24)
    print(f"找到 {len(new_entities)} 个最近24小时的非待编译新实体")

    if not new_entities:
        print("没有需要处理的新实体")
        return

    # 2. 获取历史实体
    historical = get_historical_entities()
    print(f"找到 {len(historical)} 个历史实体作为匹配候选")
    print()

    # 3. 处理每个新实体
    merged_list = []
    kept_list = []

    for new in new_entities:
        print(f"处理新实体: {new['path']} ({new['name']})")

        # AI 匹配
        match_id = ai_judge_same_person(new, historical)

        if match_id == "NEW":
            print(f"  → 判定为新实体，保留")
            kept_list.append({
                "name": new["name"],
                "reason": "AI判定为新人物"
            })

        elif match_id == "UNCLEAR":
            print(f"  → 信息不足，保留待后续处理")
            kept_list.append({
                "name": new["name"],
                "reason": "信息不足无法判断"
            })

        else:
            # 找到匹配，执行合并
            match_entity = None
            for h in historical:
                if h["id"] == match_id:
                    match_entity = h
                    break

            if match_entity:
                print(f"  → 匹配到: {match_entity['path']}")

                # 迁移 facts
                migrated = migrate_facts(new["id"], match_id)
                print(f"  迁移了 {migrated} 个 facts")

                # 删除新实体
                deleted = delete_entity(new["id"], new["path"])

                if deleted:
                    merged_list.append({
                        "from": new["path"],
                        "to": match_entity["path"],
                        "facts": migrated
                    })
            else:
                print(f"  → 匹配ID未找到，保留")
                kept_list.append({
                    "name": new["name"],
                    "reason": "匹配目标未找到"
                })

    print()

    # 4. 清理超期待编译实体
    deleted_stale = cleanup_stale_todo_entities(days=30)
    if deleted_stale > 0:
        print(f"清理了 {deleted_stale} 个超期待编译实体")

    # 5. 生成并发送报告
    report = generate_report(merged_list, kept_list, deleted_stale)
    print()
    print("=" * 60)
    print(report)
    print("=" * 60)

    # 异步发送飞书报告
    try:
        asyncio.run(send_report_to_feishu(report))
    except Exception as e:
        print(f"发送报告失败: {e}")

    print(f"[{datetime.now().isoformat()}] 去重完成")


if __name__ == "__main__":
    daily_incremental_dedup()
