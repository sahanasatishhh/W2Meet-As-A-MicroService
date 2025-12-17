CREATE TABLE IF NOT EXISTS useravail (
  email TEXT PRIMARY KEY,
  availabilities JSONB NOT NULL,
  preferences TEXT,
  created_at TIMESTAMP
);
