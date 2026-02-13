"""
Lifecycle Manager - L0 Buffer 数据生命周期管理

策略:
- Warm Archive: 7天前的数据标记为归档，不参与检索
- Cold Archive: 90天前的数据导出到 Storage 并物理删除
"""

import os
import json
import gzip
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from io import BytesIO

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


class L0LifecycleManager:
    """L0 Buffer 生命周期管理器"""

    # 时间配置
    WARM_ARCHIVE_DAYS = 7    # 7天后进入温归档
    COLD_ARCHIVE_DAYS = 90   # 90天后进入冷归档

    # Storage 配置
    STORAGE_BUCKET = "logs_archive"
    STORAGE_PREFIX = "l0_buffer"

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )

    # =========================================================================
    # Warm Archive (7天)
    # =========================================================================

    def warm_archive(self) -> Dict:
        """
        温归档: 将7天前的已处理数据标记为归档状态
        - 不参与向量检索
        - 保留在数据库中便于查询
        """
        print("=" * 60)
        print("执行 Warm Archive (7天)")
        print("=" * 60)

        cutoff_date = datetime.utcnow() - timedelta(days=self.WARM_ARCHIVE_DAYS)

        # 查找需要归档的记录
        result = self.supabase.table("mem_l0_buffer") \
            .select("count", count="exact") \
            .eq("processed", True) \
            .is_("archived_at", "null") \
            .lt("created_at", cutoff_date.isoformat()) \
            .execute()

        total_count = result.count

        if total_count == 0:
            print(f"没有需要温归档的数据 (截止日期: {cutoff_date.date()})")
            return {"archived": 0, "cutoff_date": cutoff_date.isoformat()}

        print(f"找到 {total_count} 条记录待归档")

        # 分批更新，避免单次操作过大
        batch_size = 1000
        archived_count = 0

        while archived_count < total_count:
            # 获取一批记录
            batch = self.supabase.table("mem_l0_buffer") \
                .select("id") \
                .eq("processed", True) \
                .is_("archived_at", "null") \
                .lt("created_at", cutoff_date.isoformat()) \
                .limit(batch_size) \
                .execute()

            if not batch.data:
                break

            # 更新这批记录
            ids = [r["id"] for r in batch.data]

            # 使用 RPC 或逐条更新
            for record_id in ids:
                self.supabase.table("mem_l0_buffer") \
                    .update({
                        "archived_at": datetime.utcnow().isoformat(),
                        "archive_tier": "warm"
                    }) \
                    .eq("id", record_id) \
                    .execute()

            archived_count += len(ids)
            print(f"  已归档: {archived_count}/{total_count}")

        print(f"[OK] Warm Archive 完成: {archived_count} 条记录")
        return {
            "archived": archived_count,
            "cutoff_date": cutoff_date.isoformat(),
            "tier": "warm"
        }

    # =========================================================================
    # Cold Archive (90天)
    # =========================================================================

    def cold_archive(self) -> Dict:
        """
        冷归档: 将90天前的温归档数据导出并删除
        1. 导出为 JSONL
        2. 上传到 Supabase Storage
        3. 物理删除
        """
        print("\n" + "=" * 60)
        print("执行 Cold Archive (90天)")
        print("=" * 60)

        cutoff_date = datetime.utcnow() - timedelta(days=self.COLD_ARCHIVE_DAYS)

        # 查找需要冷归档的记录
        result = self.supabase.table("mem_l0_buffer") \
            .select("count", count="exact") \
            .eq("archive_tier", "warm") \
            .lt("archived_at", cutoff_date.isoformat()) \
            .execute()

        total_count = result.count

        if total_count == 0:
            print(f"没有需要冷归档的数据 (截止日期: {cutoff_date.date()})")
            return {"exported": 0, "deleted": 0, "storage_path": None}

        print(f"找到 {total_count} 条记录待冷归档")

        # 分批处理
        batch_size = 5000
        all_records = []
        deleted_count = 0

        # 生成导出文件名
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.STORAGE_PREFIX}_{timestamp}_{cutoff_date.strftime('%Y%m%d')}.jsonl.gz"

        # 确保 Storage Bucket 存在
        self._ensure_storage_bucket()

        # 使用流式处理避免内存溢出
        buffer = BytesIO()
        compressor = gzip.GzipFile(fileobj=buffer, mode='wb')

        processed = 0

        while processed < total_count:
            # 获取一批记录
            batch = self.supabase.table("mem_l0_buffer") \
                .select("*") \
                .eq("archive_tier", "warm") \
                .lt("archived_at", cutoff_date.isoformat()) \
                .limit(batch_size) \
                .execute()

            if not batch.data:
                break

            # 写入 JSONL
            for record in batch.data:
                # 清理内部字段
                clean_record = {
                    "id": record["id"],
                    "role": record["role"],
                    "content": record["content"],
                    "meta_data": record.get("meta_data", {}),
                    "processed": record["processed"],
                    "created_at": record["created_at"],
                    "archived_at": record.get("archived_at"),
                    "_archived_reason": "cold_archive_90d"
                }

                line = json.dumps(clean_record, ensure_ascii=False) + "\n"
                compressor.write(line.encode('utf-8'))

            processed += len(batch.data)
            print(f"  已处理: {processed}/{total_count}")

        # 关闭压缩
        compressor.close()
        buffer.seek(0)

        # 上传到 Storage
        try:
            storage_path = self._upload_to_storage(filename, buffer)
            print(f"[OK] 已上传: {storage_path}")
        except Exception as e:
            print(f"[ERROR] 上传失败: {e}")
            return {"exported": 0, "deleted": 0, "error": str(e)}

        # 验证上传成功后删除数据
        print("验证上传并删除本地数据...")

        # 分批删除
        deleted_count = 0
        while deleted_count < total_count:
            # 获取要删除的 ID
            batch = self.supabase.table("mem_l0_buffer") \
                .select("id") \
                .eq("archive_tier", "warm") \
                .lt("archived_at", cutoff_date.isoformat()) \
                .limit(batch_size) \
                .execute()

            if not batch.data:
                break

            # 批量删除
            ids = [r["id"] for r in batch.data]

            for record_id in ids:
                self.supabase.table("mem_l0_buffer") \
                    .delete() \
                    .eq("id", record_id) \
                    .execute()

            deleted_count += len(ids)
            print(f"  已删除: {deleted_count}/{total_count}")

        print(f"[OK] Cold Archive 完成: {deleted_count} 条记录已归档到 {storage_path}")

        return {
            "exported": processed,
            "deleted": deleted_count,
            "storage_path": storage_path,
            "filename": filename,
            "cutoff_date": cutoff_date.isoformat(),
            "tier": "cold"
        }

    def _ensure_storage_bucket(self):
        """确保 Storage Bucket 存在"""
        try:
            # 尝试获取 bucket
            self.supabase.storage.get_bucket(self.STORAGE_BUCKET)
        except Exception:
            # Bucket 不存在，创建
            try:
                self.supabase.storage.create_bucket(
                    self.STORAGE_BUCKET,
                    options={"public": False}
                )
                print(f"[INFO] 创建 Storage Bucket: {self.STORAGE_BUCKET}")
            except Exception as e:
                print(f"[WARN] 创建 Bucket 失败 (可能已存在): {e}")

    def _upload_to_storage(self, filename: str, data: BytesIO) -> str:
        """上传文件到 Supabase Storage"""
        # 添加日期前缀便于管理
        today = datetime.utcnow().strftime("%Y/%m")
        storage_path = f"{self.STORAGE_PREFIX}/{today}/{filename}"

        # 上传
        self.supabase.storage \
            .from_(self.STORAGE_BUCKET) \
            .upload(storage_path, data.getvalue())

        return storage_path

    # =========================================================================
    # 查询归档状态
    # =========================================================================

    def get_stats(self) -> Dict:
        """获取 L0 Buffer 统计信息"""
        print("\n" + "=" * 60)
        print("L0 Buffer 统计")
        print("=" * 60)

        stats = {}

        # 活跃数据
        result = self.supabase.table("mem_l0_buffer") \
            .select("count", count="exact") \
            .is_("archived_at", "null") \
            .execute()
        stats["active"] = result.count
        print(f"活跃数据: {result.count}")

        # 温归档
        result = self.supabase.table("mem_l0_buffer") \
            .select("count", count="exact") \
            .eq("archive_tier", "warm") \
            .execute()
        stats["warm"] = result.count
        print(f"温归档 (7天+): {result.count}")

        # 冷归档文件数
        try:
            files = self.supabase.storage \
                .from_(self.STORAGE_BUCKET) \
                .list(self.STORAGE_PREFIX)
            stats["cold_files"] = len(files)
            print(f"冷归档文件数: {len(files)}")

            # 计算总大小
            total_size = sum(f.get("metadata", {}).get("size", 0) for f in files)
            stats["cold_size_bytes"] = total_size
            print(f"冷归档总大小: {total_size / 1024 / 1024:.2f} MB")
        except Exception as e:
            print(f"冷归档统计失败: {e}")
            stats["cold_files"] = 0
            stats["cold_size_bytes"] = 0

        return stats

    # =========================================================================
    # 主运行流程
    # =========================================================================

    def run(self, dry_run: bool = False):
        """执行完整的生命周期管理"""
        print("=" * 60)
        print(f"MemOS L0 Lifecycle Manager")
        print(f"启动时间: {datetime.utcnow().isoformat()}")
        print("=" * 60)

        if dry_run:
            print("[DRY RUN] 模拟运行，不实际修改数据")
            return self.get_stats()

        results = {}

        # 1. Warm Archive
        results["warm"] = self.warm_archive()

        # 2. Cold Archive
        results["cold"] = self.cold_archive()

        # 3. 统计
        results["stats"] = self.get_stats()

        print("\n" + "=" * 60)
        print("生命周期管理完成")
        print("=" * 60)

        return results


# =============================================================================
# 命令行入口
# =============================================================================

if __name__ == "__main__":
    import sys

    manager = L0LifecycleManager()

    # 检查是否需要更新表结构（添加归档字段）
    print("检查表结构...")
    try:
        # 尝试查询 archived_at 字段
        manager.supabase.table("mem_l0_buffer") \
            .select("archived_at") \
            .limit(1) \
            .execute()
    except Exception as e:
        print("[WARN] 可能需要添加归档字段到 mem_l0_buffer 表:")
        print("""
        ALTER TABLE mem_l0_buffer
        ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS archive_tier TEXT DEFAULT NULL;
        """)
        print(e)
        sys.exit(1)

    # 解析命令
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "--stats":
            manager.get_stats()
        elif cmd == "--warm":
            manager.warm_archive()
        elif cmd == "--cold":
            manager.cold_archive()
        elif cmd == "--dry-run":
            manager.run(dry_run=True)
        else:
            print(f"未知命令: {cmd}")
            print("用法: python lifecycle_manager.py [--stats|--warm|--cold|--dry-run]")
    else:
        # 完整运行
        manager.run()
