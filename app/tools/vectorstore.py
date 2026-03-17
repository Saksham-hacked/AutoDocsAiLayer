from typing import List, Dict, Any
import asyncpg
from app.config import get_settings

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            settings.pg_dsn,
            statement_cache_size=0,  # required for pgbouncer/supabase pooler
            min_size=1,
            max_size=5,
        )
    return _pool


async def upsert_summary(repo_id: str, path: str, summary: str, embedding: List[float], commit_id: str):
    pool = await get_pool()
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO summaries (repo_id, file_path, summary, embedding, last_updated_commit, updated_at)
            VALUES ($1, $2, $3, $4::vector, $5, now())
            ON CONFLICT (repo_id, file_path)
            DO UPDATE SET summary = EXCLUDED.summary,
                          embedding = EXCLUDED.embedding,
                          last_updated_commit = EXCLUDED.last_updated_commit,
                          updated_at = now()
        """, repo_id, path, summary, vec_str, commit_id)


async def delete_summary(repo_id: str, path: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM summaries WHERE repo_id = $1 AND file_path = $2",
            repo_id, path
        )


async def retrieve_top_k(query_embedding: List[float], repo_id: str, k: int) -> List[Dict[str, Any]]:
    pool = await get_pool()
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT file_path, summary, last_updated_commit,
                   1 - (embedding <=> $1::vector) AS score
            FROM summaries
            WHERE repo_id = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """, vec_str, repo_id, k)
    return [dict(r) for r in rows]
