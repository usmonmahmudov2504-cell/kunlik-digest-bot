-- AvtoPost — Master Bot ma'lumotlar bazasi (SQLite, yengil)
-- 6 jadval: clients, patterns, channels, sources, channel_sources, schedules, posts_log

PRAGMA journal_mode = WAL;     -- ko'p o'qish/yozishda tezroq, yengil
PRAGMA foreign_keys = ON;

-- Mijozlar
CREATE TABLE IF NOT EXISTS clients (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  tg_user_id  INTEGER,
  plan        TEXT DEFAULT 'free',
  is_active   INTEGER DEFAULT 1,
  created_at  TEXT DEFAULT (datetime('now'))
);

-- Brend qoliplari (qayta ishlatiladigan -> ko'p kanal bittasini bo'lishadi)
CREATE TABLE IF NOT EXISTS patterns (
  id          INTEGER PRIMARY KEY,
  name        TEXT,
  header      TEXT,
  footer      TEXT,                    -- {channel} -> kanal username bilan to'ldiriladi
  hashtags    TEXT,
  rewrite_lvl INTEGER DEFAULT 1,       -- 0=tozalash, 1=+shablon, 2=+spin
  emoji_map   TEXT                     -- JSON: {"kalit":"emoji"}
);

-- Mijoz kanallari
CREATE TABLE IF NOT EXISTS channels (
  id          INTEGER PRIMARY KEY,
  client_id   INTEGER REFERENCES clients(id),
  pattern_id  INTEGER REFERENCES patterns(id),
  tg_chat     TEXT NOT NULL,           -- @username yoki -100... chat_id
  title       TEXT,
  tz          TEXT DEFAULT 'Asia/Tashkent',
  markup      INTEGER DEFAULT 0,       -- narx ustamasi (%) -> do'kon postlarini qimmatroq
  is_active   INTEGER DEFAULT 1
);

-- Manba kanallar (skraping)
CREATE TABLE IF NOT EXISTS sources (
  id          INTEGER PRIMARY KEY,
  kind        TEXT DEFAULT 'tg',       -- tg / rss
  ref         TEXT NOT NULL,           -- @manba yoki RSS url
  is_active   INTEGER DEFAULT 1
);

-- Kanal <-> manba (M:N) + filtr kalit so'zlari
CREATE TABLE IF NOT EXISTS channel_sources (
  channel_id  INTEGER REFERENCES channels(id),
  source_id   INTEGER REFERENCES sources(id),
  keywords    TEXT,                    -- "ai,startup" (bo'sh = hammasi)
  PRIMARY KEY (channel_id, source_id)
);

-- Jadval (har kanal, har post turi alohida vaqt)
CREATE TABLE IF NOT EXISTS schedules (
  id          INTEGER PRIMARY KEY,
  channel_id  INTEGER REFERENCES channels(id),
  post_type   TEXT,                    -- 'scrape' / 'digest' / 'quote'
  cron        TEXT,                    -- "0 7 * * *"
  next_run    TEXT,                    -- keyingi ishga tushish (UTC ISO)
  is_active   INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_sched_due ON schedules(is_active, next_run);

-- Yuborilgan postlar (dedup + tarix)
CREATE TABLE IF NOT EXISTS posts_log (
  id           INTEGER PRIMARY KEY,
  channel_id   INTEGER REFERENCES channels(id),
  source_id    INTEGER,
  src_msg_id   INTEGER,
  content_hash TEXT,
  posted_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_log_dedup ON posts_log(channel_id, content_hash);
