-- =============================================================================
-- MemOS v2.0 - AI Memory System Database Schema
-- Platform: Supabase (PostgreSQL 15+)
-- Features: 文件系统隐喻 + 事实版本控制 (读写分离设计)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. 启用必要的扩展
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- 用于文本模糊搜索

-- -----------------------------------------------------------------------------
-- 2. 清理现有表 (按依赖顺序逆序删除)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mem_l3_atomic_facts CASCADE;
DROP TABLE IF EXISTS mem_l3_entities CASCADE;
DROP TABLE IF EXISTS mem_l2_profile CASCADE;
DROP TABLE IF EXISTS mem_l1_timeline CASCADE;
DROP TABLE IF EXISTS mem_l0_buffer CASCADE;

-- -----------------------------------------------------------------------------
-- 3. 核心表结构
-- -----------------------------------------------------------------------------

-- ============================================================================
-- L0: 缓冲与多模态层 (Buffer & Multimodal Layer)
-- 用途: 存储原始对话流和附件信息，等待批处理
-- ============================================================================
CREATE TABLE mem_l0_buffer (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role            TEXT NOT NULL CHECK (role IN ('user', 'ai')),
    content         TEXT NOT NULL,
    meta_data       JSONB DEFAULT '{}'::jsonb,
    -- meta_data 结构示例:
    -- {
    --   "attachments": [
    --     {"url": "https://...", "mime_type": "image/png", "filename": "screenshot.png"}
    --   ],
    --   "source_app": "claude-code",
    --   "session_id": "uuid",
    --   "timestamp_ms": 1700000000000
    -- }
    processed       BOOLEAN DEFAULT false,

    -- 生命周期管理
    archived_at     TIMESTAMPTZ,           -- 归档时间
    archive_tier    TEXT CHECK (archive_tier IN ('warm', 'cold')),  -- warm=7天, cold=90天

    created_at      TIMESTAMPTZ DEFAULT now(),

    -- 索引提示: 查询未处理记录时使用
    CONSTRAINT chk_role CHECK (role IN ('user', 'ai'))
);

COMMENT ON TABLE mem_l0_buffer IS '原始对话缓冲层，存储待处理的对话流和附件';
COMMENT ON COLUMN mem_l0_buffer.meta_data IS '附件URL、mime_type、来源APP等元数据';
COMMENT ON COLUMN mem_l0_buffer.processed IS '是否已被批处理消费';
COMMENT ON COLUMN mem_l0_buffer.archived_at IS '归档时间，用于生命周期管理';
COMMENT ON COLUMN mem_l0_buffer.archive_tier IS '归档层级: warm(7天+), cold(90天+)';


-- ============================================================================
-- L1: 每日摘要层 (Daily Timeline)
-- 用途: 存储每日对话的压缩摘要，用于长期时间线检索
-- ============================================================================
CREATE TABLE mem_l1_timeline (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date            DATE NOT NULL UNIQUE,
    summary         TEXT NOT NULL,
    embedding       VECTOR(1536),  -- 使用 OpenAI text-embedding-3-small 维度

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE mem_l1_timeline IS '每日对话压缩摘要，用于时间线级记忆检索';
COMMENT ON COLUMN mem_l1_timeline.date IS '摘要对应的日期';
COMMENT ON COLUMN mem_l1_timeline.summary IS 'AI生成的当日对话压缩摘要';
COMMENT ON COLUMN mem_l1_timeline.embedding IS '摘要的向量嵌入，用于语义检索';


-- ============================================================================
-- L2: 用户画像层 (User Profile)
-- 用途: 存储习惯、偏好和认知模式 (长期稳定的用户特征)
-- ============================================================================
CREATE TABLE mem_l2_profile (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category        TEXT NOT NULL CHECK (category IN ('habit', 'mental_model', 'preference', 'skill')),
    content         TEXT NOT NULL,
    confidence      DECIMAL(3,2) NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'disputed')),

    -- 溯源信息
    source_facts    UUID[] DEFAULT '{}',
    first_observed  TIMESTAMPTZ DEFAULT now(),
    last_confirmed  TIMESTAMPTZ DEFAULT now(),

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE mem_l2_profile IS '用户画像层，存储推断出的习惯、偏好和认知模式';
COMMENT ON COLUMN mem_l2_profile.category IS '画像类型: habit(习惯), mental_model(认知模式), preference(偏好), skill(技能)';
COMMENT ON COLUMN mem_l2_profile.confidence IS '置信度 0.0-1.0，基于观察次数和一致性';
COMMENT ON COLUMN mem_l2_profile.status IS '状态: active(活跃), archived(归档), disputed(存疑)';
COMMENT ON COLUMN mem_l2_profile.source_facts IS '来源原子事实ID数组，用于溯源';


-- ============================================================================
-- L3: 实体/文件夹层 (Entities - 读优化)
-- 用途: 模拟文件系统结构，存储AI编译后的Markdown档案
-- 设计: 这是"读模型"，描述性内容由原子事实动态编译生成
-- ============================================================================
CREATE TABLE mem_l3_entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- 文件系统隐喻核心字段
    path            TEXT NOT NULL UNIQUE,
    -- 路径示例:
    -- "/"                          - 根目录
    -- "/work"                      - 工作领域
    -- "/work/projects"             - 项目文件夹
    -- "/work/projects/ironman"     - 具体项目
    -- "/people/alice"              - 人物档案
    -- "/concepts/vector-db"        - 概念知识

    name            TEXT NOT NULL,
    description_md  TEXT NOT NULL DEFAULT '',
    -- AI编译后的Markdown档案，格式示例:
    -- # IronMan项目
    --
    -- ## 概述
    -- 这是一个AI记忆系统重构项目...
    --
    -- ## 关键事实
    -- - 启动时间: 2024-01-15
    -- - 技术栈: Supabase + Next.js
    --
    -- ## 相关实体
    -- - [Supabase](/concepts/supabase)
    -- - [Claude Code](/tools/claude-code)

    -- 元数据
    is_pinned       BOOLEAN DEFAULT false,
    entity_type     TEXT DEFAULT 'folder' CHECK (entity_type IN ('folder', 'file', 'person', 'project', 'concept')),
    tags            TEXT[] DEFAULT '{}',

    -- 编译追踪
    last_compiled_at TIMESTAMPTZ DEFAULT now(),
    compile_version INTEGER DEFAULT 1,

    -- 向量检索 (基于 description_md 生成)
    embedding       VECTOR(1536),

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE mem_l3_entities IS '实体层(读模型)，模拟文件系统，存储AI编译后的Markdown档案';
COMMENT ON COLUMN mem_l3_entities.path IS '文件系统路径，唯一标识符，如 /work/projects/ironman';
COMMENT ON COLUMN mem_l3_entities.description_md IS 'AI编译后的Markdown档案，用于读取和展示';
COMMENT ON COLUMN mem_l3_entities.is_pinned IS '全局置顶标记，重要实体快速访问';
COMMENT ON COLUMN mem_l3_entities.last_compiled_at IS '上次编译时间，用于判断缓存有效性';
COMMENT ON COLUMN mem_l3_entities.embedding IS '基于description_md的向量嵌入，用于语义搜索';


-- ============================================================================
-- L3: 原子事实/Git Log层 (Atomic Facts - 写优化)
-- 用途: 存储关于实体的离散事实，支持版本回溯(事实的版本控制)
-- 设计: 这是"写模型"，所有事实写入此处，定期编译到 entities.description_md
-- ============================================================================
CREATE TABLE mem_l3_atomic_facts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- 外键关联
    entity_id       UUID NOT NULL REFERENCES mem_l3_entities(id) ON DELETE CASCADE,

    -- 事实内容
    content         TEXT NOT NULL,
    -- 内容示例:
    -- "项目启动日期: 2024-01-15"
    -- "用户偏好使用空格缩进而非Tab"
    -- "会议结论: 采用PostgreSQL而非MySQL"

    -- 版本控制状态机
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'disputed', 'retracted')),
    -- active:     当前有效的事实
    -- superseded: 被更新版本替代
    -- disputed:   存在冲突，待人工确认
    -- retracted:  被明确撤回的错误事实

    -- 版本链接 (自我引用实现版本链)
    superseded_by   UUID REFERENCES mem_l3_atomic_facts(id) ON DELETE SET NULL,
    -- 当 status='superseded' 时，指向新版本
    -- 形成版本链: fact_v1 -> fact_v2 -> fact_v3

    -- 溯源与上下文
    source_type     TEXT DEFAULT 'inference' CHECK (source_type IN ('direct_statement', 'inference', 'imported', 'manual_entry')),
    source_ref      TEXT,
    -- source_ref: 对话ID、文档URL、或L0_buffer记录ID

    context_json    JSONB DEFAULT '{}'::jsonb,
    -- 上下文示例:
    -- {
    --   "conversation_id": "uuid",
    --   "confidence": 0.95,
    --   "extractor_model": "claude-sonnet-4"
    -- }

    -- 时间戳
    valid_from      TIMESTAMPTZ DEFAULT now(),
    valid_until     TIMESTAMPTZ,
    -- valid_until: 当 status='superseded' 时设置

    created_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE mem_l3_atomic_facts IS '原子事实层(写模型)，存储离散事实，支持版本控制和时间旅行';
COMMENT ON COLUMN mem_l3_atomic_facts.entity_id IS '关联的实体ID';
COMMENT ON COLUMN mem_l3_atomic_facts.content IS '离散事实文本，单条原子陈述';
COMMENT ON COLUMN mem_l3_atomic_facts.status IS '事实状态: active(有效), superseded(被替代), disputed(存疑), retracted(撤回)';
COMMENT ON COLUMN mem_l3_atomic_facts.superseded_by IS '新版本事实ID，形成版本链';
COMMENT ON COLUMN mem_l3_atomic_facts.valid_from IS '事实生效时间';
COMMENT ON COLUMN mem_l3_atomic_facts.valid_until IS '事实失效时间(被替代时设置)';


-- -----------------------------------------------------------------------------
-- 4. 索引优化
-- -----------------------------------------------------------------------------

-- L0: 缓冲层索引
CREATE INDEX idx_l0_processed_created ON mem_l0_buffer(processed, created_at)
    WHERE processed = false;
CREATE INDEX idx_l0_meta_data_gin ON mem_l0_buffer USING GIN (meta_data);

-- L0: 归档索引
CREATE INDEX idx_l0_archive_tier ON mem_l0_buffer(archive_tier, archived_at)
    WHERE archive_tier IS NOT NULL;
CREATE INDEX idx_l0_warm_archive ON mem_l0_buffer(archived_at)
    WHERE archive_tier = 'warm';
CREATE INDEX idx_l0_created_at ON mem_l0_buffer(created_at);

-- L1: 时间线索引
CREATE INDEX idx_l1_date ON mem_l1_timeline(date DESC);

-- L2: 画像层索引
CREATE INDEX idx_l2_category_status ON mem_l2_profile(category, status);
CREATE INDEX idx_l2_confidence ON mem_l2_profile(confidence DESC)
    WHERE status = 'active';

-- L3 Entities: 路径检索索引 (text_pattern_ops 加速 LIKE 查询)
CREATE INDEX idx_l3_path ON mem_l3_entities(path text_pattern_ops);
CREATE INDEX idx_l3_path_gist ON mem_l3_entities USING GIST (path gist_trgm_ops);
CREATE INDEX idx_l3_is_pinned ON mem_l3_entities(is_pinned)
    WHERE is_pinned = true;
CREATE INDEX idx_l3_entity_type ON mem_l3_entities(entity_type);
CREATE INDEX idx_l3_tags_gin ON mem_l3_entities USING GIN (tags);

-- L3 Atomic Facts: 外键和状态索引
CREATE INDEX idx_l3_facts_entity_id ON mem_l3_atomic_facts(entity_id);
CREATE INDEX idx_l3_facts_entity_status ON mem_l3_atomic_facts(entity_id, status)
    WHERE status = 'active';
CREATE INDEX idx_l3_facts_status ON mem_l3_atomic_facts(status);
CREATE INDEX idx_l3_facts_superseded ON mem_l3_atomic_facts(superseded_by)
    WHERE superseded_by IS NOT NULL;
CREATE INDEX idx_l3_facts_valid_time ON mem_l3_atomic_facts(valid_from, valid_until);

-- -----------------------------------------------------------------------------
-- 5. 向量索引 (HNSW - 近似最近邻搜索)
-- -----------------------------------------------------------------------------

-- L1: 每日摘要向量索引
CREATE INDEX idx_l1_embedding_hnsw ON mem_l1_timeline
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- L3 Entities: 基于 description_md 的向量索引
CREATE INDEX idx_l3_embedding_hnsw ON mem_l3_entities
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- -----------------------------------------------------------------------------
-- 6. 函数与触发器
-- -----------------------------------------------------------------------------

-- 自动更新 updated_at 字段
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 应用到各表
CREATE TRIGGER trigger_l1_timeline_updated_at
    BEFORE UPDATE ON mem_l1_timeline
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_l2_profile_updated_at
    BEFORE UPDATE ON mem_l2_profile
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_l3_entities_updated_at
    BEFORE UPDATE ON mem_l3_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 事实版本控制触发器: 当事实被替代时自动设置 valid_until
CREATE OR REPLACE FUNCTION update_fact_validity()
RETURNS TRIGGER AS $$
BEGIN
    -- 如果被标记为 superseded，且没有设置 valid_until
    IF NEW.status = 'superseded' AND NEW.valid_until IS NULL THEN
        NEW.valid_until = now();
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_l3_facts_validity
    BEFORE UPDATE ON mem_l3_atomic_facts
    FOR EACH ROW EXECUTE FUNCTION update_fact_validity();

-- 实体编译触发器: 更新 last_compiled_at 和 compile_version
CREATE OR REPLACE FUNCTION update_entity_compile_info()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_compiled_at = now();
    NEW.compile_version = OLD.compile_version + 1;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_l3_entities_compile
    BEFORE UPDATE OF description_md ON mem_l3_entities
    FOR EACH ROW
    WHEN (OLD.description_md IS DISTINCT FROM NEW.description_md)
    EXECUTE FUNCTION update_entity_compile_info();


-- -----------------------------------------------------------------------------
-- 7. 视图 (便利查询)
-- -----------------------------------------------------------------------------

-- 活跃实体视图: 只返回当前有效的事实
CREATE VIEW view_l3_active_facts AS
SELECT f.*, e.path as entity_path
FROM mem_l3_atomic_facts f
JOIN mem_l3_entities e ON f.entity_id = e.id
WHERE f.status = 'active';

COMMENT ON VIEW view_l3_active_facts IS '当前活跃的原子事实，排除被替代/撤回的内容';

-- 实体完整档案视图: 包含实体信息和活跃事实列表
CREATE VIEW view_l3_entity_profile AS
SELECT
    e.*,
    COUNT(f.id) FILTER (WHERE f.status = 'active') as active_facts_count,
    COUNT(f.id) FILTER (WHERE f.status = 'superseded') as superseded_facts_count,
    MAX(f.created_at) as latest_fact_at
FROM mem_l3_entities e
LEFT JOIN mem_l3_atomic_facts f ON e.id = f.entity_id
GROUP BY e.id;

COMMENT ON VIEW view_l3_entity_profile IS '实体完整档案，包含事实统计信息';

-- 时间旅行视图: 查询特定时间点的实体状态
CREATE OR REPLACE FUNCTION get_entity_facts_at_time(entity_uuid UUID, at_time TIMESTAMPTZ)
RETURNS TABLE (
    fact_id UUID,
    content TEXT,
    status TEXT,
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT f.id, f.content, f.status, f.valid_from, f.valid_until
    FROM mem_l3_atomic_facts f
    WHERE f.entity_id = entity_uuid
      AND f.valid_from <= at_time
      AND (f.valid_until IS NULL OR f.valid_until > at_time);
END;
$$ language 'plpgsql';

COMMENT ON FUNCTION get_entity_facts_at_time IS '时间旅行函数：查询实体在特定时间点的所有有效事实';


-- -----------------------------------------------------------------------------
-- 8. Row Level Security (RLS) 策略模板 (Supabase)
-- -----------------------------------------------------------------------------

-- 启用RLS
ALTER TABLE mem_l0_buffer ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_l1_timeline ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_l2_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_l3_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_l3_atomic_facts ENABLE ROW LEVEL SECURITY;

-- 注意: 实际策略需要根据认证方案配置，以下是示例模板

-- 示例: 只允许服务角色访问 (替换为实际策略)
-- CREATE POLICY "service_role_only" ON mem_l0_buffer
--     FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 示例: 基于用户ID的隔离 (如果支持多用户)
-- ALTER TABLE mem_l3_entities ADD COLUMN user_id UUID REFERENCES auth.users(id);
-- CREATE POLICY "user_isolation" ON mem_l3_entities
--     FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());


-- =============================================================================
-- 初始化完成
-- =============================================================================
-- 设计要点总结:
-- 1. L3层采用读写分离: entities(读模型) + atomic_facts(写模型)
-- 2. 事实版本控制: 通过 status + superseded_by 实现Git式版本链
-- 3. 文件系统隐喻: path字段支持树形结构，支持模糊搜索
-- 4. 向量检索: 所有摘要和描述均有embedding，支持语义搜索
-- 5. 时间旅行: valid_from/valid_until 支持查询历史状态
-- =============================================================================
