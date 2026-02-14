-- ============================================================================
-- Migration: 完善 L1 Timeline 和 L2 Profile 表结构
-- ============================================================================

-- ============================================================================
-- L1 Timeline: 每日快照
-- ============================================================================

-- 确保 L1 表有完整字段
ALTER TABLE mem_l1_timeline
ADD COLUMN IF NOT EXISTS events JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS people_involved TEXT[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS key_activities TEXT[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0;

-- L1 索引
CREATE INDEX IF NOT EXISTS idx_l1_date ON mem_l1_timeline(date DESC);
CREATE INDEX IF NOT EXISTS idx_l1_topics ON mem_l1_timeline USING GIN (topics);

-- ============================================================================
-- L2 Profile: 画像洞察
-- ============================================================================

-- 确保 L2 表有完整字段
ALTER TABLE mem_l2_profile
ADD COLUMN IF NOT EXISTS evidence TEXT[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS first_observed TIMESTAMPTZ DEFAULT now(),
ADD COLUMN IF NOT EXISTS last_confirmed TIMESTAMPTZ DEFAULT now();

-- 更新 status 约束（如果不存在）
ALTER TABLE mem_l2_profile
DROP CONSTRAINT IF EXISTS mem_l2_profile_status_check;

ALTER TABLE mem_l2_profile
ADD CONSTRAINT mem_l2_profile_status_check
CHECK (status IN ('active', 'archived', 'disputed'));

-- L2 索引
CREATE INDEX IF NOT EXISTS idx_l2_category ON mem_l2_profile(category, status);
CREATE INDEX IF NOT EXISTS idx_l2_confidence ON mem_l2_profile(confidence DESC)
    WHERE status = 'active';

-- ============================================================================
-- 注释
-- ============================================================================

COMMENT ON TABLE mem_l1_timeline IS '每日快照：何时、何人、发生了什么事';
COMMENT ON COLUMN mem_l1_timeline.events IS '事件列表 [{time, who, what, type}]';
COMMENT ON COLUMN mem_l1_timeline.people_involved IS '涉及的人物';
COMMENT ON COLUMN mem_l1_timeline.topics IS '讨论主题';
COMMENT ON COLUMN mem_l1_timeline.key_activities IS '关键活动';
COMMENT ON COLUMN mem_l1_timeline.message_count IS '当天消息数量';

COMMENT ON TABLE mem_l2_profile IS '画像洞察：模式、偏好、经验教训';
COMMENT ON COLUMN mem_l2_profile.evidence IS '支持证据列表';
COMMENT ON COLUMN mem_l2_profile.context IS '上下文信息';
COMMENT ON COLUMN mem_l2_profile.first_observed IS '首次观察时间';
COMMENT ON COLUMN mem_l2_profile.last_confirmed IS '最后确认时间';

-- ============================================================================
-- 验证
-- ============================================================================

SELECT 'L1 Timeline columns:' as info;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'mem_l1_timeline'
ORDER BY ordinal_position;

SELECT 'L2 Profile columns:' as info;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'mem_l2_profile'
ORDER BY ordinal_position;
