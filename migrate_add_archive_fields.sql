-- =============================================================================
-- Migration: 添加 L0 Buffer 归档字段
-- 用于现有数据库升级
-- =============================================================================

-- 添加归档字段
ALTER TABLE mem_l0_buffer
ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS archive_tier TEXT CHECK (archive_tier IN ('warm', 'cold'));

-- 添加注释
COMMENT ON COLUMN mem_l0_buffer.archived_at IS '归档时间，用于生命周期管理';
COMMENT ON COLUMN mem_l0_buffer.archive_tier IS '归档层级: warm(7天+), cold(90天+)';

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_l0_archive_tier ON mem_l0_buffer(archive_tier, archived_at)
    WHERE archive_tier IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_l0_warm_archive ON mem_l0_buffer(archived_at)
    WHERE archive_tier = 'warm';

CREATE INDEX IF NOT EXISTS idx_l0_created_at ON mem_l0_buffer(created_at);

-- =============================================================================
-- 验证
-- =============================================================================
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'mem_l0_buffer'
ORDER BY ordinal_position;
