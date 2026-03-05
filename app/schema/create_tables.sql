CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS summaries (
  id SERIAL PRIMARY KEY,
  repo_id TEXT NOT NULL,
  file_path TEXT NOT NULL,
  summary TEXT NOT NULL,
  embedding vector(768),         -- nomic-embed-text; change to 1536 for other models
  last_updated_commit TEXT,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  UNIQUE (repo_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_summaries_repo_path ON summaries (repo_id, file_path);
CREATE INDEX IF NOT EXISTS idx_summaries_embedding ON summaries USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
