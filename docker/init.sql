-- Claude Usage Monitoring: schema + views for dashboard
-- Data source: local ~/.claude logs only (Claude Code Max does NOT provide an API)

CREATE TABLE IF NOT EXISTS claude_usage (
  id SERIAL PRIMARY KEY,
  user_name TEXT NOT NULL,
  machine TEXT NOT NULL,
  project TEXT,
  model TEXT,
  input_tokens INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  total_tokens INT NOT NULL DEFAULT 0,
  session_id TEXT,
  message_uuid TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_name, machine, session_id, message_uuid)
);

CREATE INDEX IF NOT EXISTS idx_claude_usage_created_at ON claude_usage (created_at);
CREATE INDEX IF NOT EXISTS idx_claude_usage_user ON claude_usage (user_name);
CREATE INDEX IF NOT EXISTS idx_claude_usage_project ON claude_usage (project);

-- Views for Grafana (simpler queries)

CREATE OR REPLACE VIEW v_daily_usage AS
SELECT
  created_at::date AS day,
  user_name,
  project,
  SUM(total_tokens) AS total_tokens,
  COUNT(*) AS turn_count
FROM claude_usage
GROUP BY created_at::date, user_name, project;

CREATE OR REPLACE VIEW v_developer_ranking AS
SELECT
  user_name,
  SUM(total_tokens) AS total_tokens,
  COUNT(*) AS turn_count
FROM claude_usage
GROUP BY user_name
ORDER BY total_tokens DESC;

CREATE OR REPLACE VIEW v_project_usage AS
SELECT
  COALESCE(project, '(none)') AS project,
  SUM(total_tokens) AS total_tokens,
  COUNT(*) AS turn_count
FROM claude_usage
GROUP BY project
ORDER BY total_tokens DESC;
