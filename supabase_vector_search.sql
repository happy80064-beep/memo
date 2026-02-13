-- Supabase 向量搜索函数
-- 在 SQL Editor 中执行

-- 启用向量扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建向量匹配函数
CREATE OR REPLACE FUNCTION match_entities(
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INT
)
RETURNS TABLE(
  id UUID,
  path TEXT,
  name TEXT,
  description_md TEXT,
  entity_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    mem_l3_entities.id,
    mem_l3_entities.path,
    mem_l3_entities.name,
    mem_l3_entities.description_md,
    mem_l3_entities.entity_type,
    1 - (mem_l3_entities.embedding <=> query_embedding) AS similarity
  FROM mem_l3_entities
  WHERE mem_l3_entities.embedding IS NOT NULL
    AND 1 - (mem_l3_entities.embedding <=> query_embedding) > match_threshold
  ORDER BY mem_l3_entities.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 创建文本搜索函数（备用）
CREATE OR REPLACE FUNCTION search_entities_by_text(
  search_query TEXT,
  result_limit INT DEFAULT 5
)
RETURNS TABLE(
  id UUID,
  path TEXT,
  name TEXT,
  description_md TEXT,
  entity_type TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    mem_l3_entities.id,
    mem_l3_entities.path,
    mem_l3_entities.name,
    mem_l3_entities.description_md,
    mem_l3_entities.entity_type
  FROM mem_l3_entities
  WHERE
    mem_l3_entities.name ILIKE '%' || search_query || '%'
    OR mem_l3_entities.description_md ILIKE '%' || search_query || '%'
    OR mem_l3_entities.path ILIKE '%' || search_query || '%'
  ORDER BY
    CASE
      WHEN mem_l3_entities.name ILIKE '%' || search_query || '%' THEN 1
      WHEN mem_l3_entities.path ILIKE '%' || search_query || '%' THEN 2
      ELSE 3
    END
  LIMIT result_limit;
END;
$$;

COMMENT ON FUNCTION match_entities IS '基于向量相似度搜索实体';
COMMENT ON FUNCTION search_entities_by_text IS '基于文本搜索实体';
