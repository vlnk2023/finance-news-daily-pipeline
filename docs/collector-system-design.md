# Telegram 采集系统设计方案

V1 的关键架构决策已固化在 `docs/architecture-decisions-v1.md`。后续实现
SQLite 存储、FTS5、spool、API 和实体抽取时，应以该决策文档为准。

## 背景

当前项目已经具备一个最小可用实现：

- `scripts/fetch_finance_news_daily.py` 负责同步抓取单个 Telegram 静态公开页。
- `collector.parsers.telegram_parser.TelegramParser` 负责解析 `https://t.me/s/FinanceNewsDaily` 的消息 HTML。
- `src/config/feed-registry.json` 保存 Finance News Daily 的 feed 配置。

这个实现适合验证解析路径，但还不是完整采集系统。完整系统需要支持增量抓取、去重、异步扩展、持久化存储、缓存、重试、限速和日志。

## 目标

构建一个模块化 Telegram 公开频道采集系统，优先支持 `https://t.me/s/<channel>` 静态页。

核心目标：

- 增量抓取，避免重复处理已采集消息。
- 支持多个频道并发抓取。
- 保存历史消息、全文索引、轻量实体关系和可选缓存。
- Fetcher、Parser、Deduplicator、Consumer、Storage 各模块独立。
- 具备网络异常重试、限速和日志，方便长期运行。

## 数据流

```text
feed-registry.json
  -> Runner
  -> TelegramFetcher
  -> TelegramParser
  -> Deduplicator
  -> Consumer
  -> SQLite messages table
  -> SQLite FTS5 full-text index
  -> SQLite lightweight entity graph
  -> optional Redis latest cache
  -> optional DuckDB / FAISS offline analytics
```

推荐处理流程：

1. Runner 读取 `feed-registry.json` 中 enabled 的 Telegram feed。
2. Fetcher 根据 feed URL 抓取 HTML。
3. Parser 将 HTML 解析为标准消息结构。
4. Deduplicator 用 `source_id + message_id` 判断是否已经处理。
5. Consumer 将新消息写入 SQLite 主表、FTS5 全文索引、实体关系表或下游队列。
6. Runner 记录本次运行结果、耗时、异常和抓取数量。

## 标准消息结构

Parser 输出建议统一为以下结构：

```python
{
    "source_id": "tg_finance_news_daily",
    "source_name": "Finance News Daily",
    "platform": "telegram",
    "message_id": "12345",
    "guid": "tg_finance_news_daily:12345",
    "url": "https://t.me/FinanceNewsDaily/12345",
    "title": "新闻标题",
    "summary": "完整消息正文...",
    "raw_text_full": "完整原始文本...",
    "pub_str": "2026-05-05T08:30:00+00:00",
    "external_url": "https://example.com/article",
    "preview_title": "链接预览标题",
    "collected_at": "2026-05-05T20:00:00+08:00",
}
```

注意：

- `message_id` 来自 Telegram 消息链接最后一段数字。
- `guid` 建议使用 `source_id + message_id`，避免不同频道消息 ID 冲突。
- `pub_str` 保留 Telegram 原始发布时间。
- `collected_at` 由采集系统生成。

## 模块设计

### Runner

职责：

- 读取 feed registry。
- 根据 `runs_per_day`、`scheduled_times_local`、`timezone` 判断是否运行。
- 分发多个 feed 的抓取任务。
- 汇总运行结果。

建议文件：

- `collector/runner.py`
- `collector/config/feed_registry.py`

### Fetcher

职责：

- 根据 URL 抓取 Telegram 静态公开页 HTML。
- 设置合理 User-Agent。
- 支持 timeout、retries、backoff、rate limit。
- 后续可以替换为异步实现。

建议文件：

- `collector/fetchers/telegram_fetcher.py`

同步版本接口：

```python
class TelegramFetcher:
    def fetch(self, url: str, timeout_ms: int) -> str:
        ...
```

异步版本接口：

```python
class AsyncTelegramFetcher:
    async def fetch(self, url: str, timeout_ms: int) -> str:
        ...
```

### Parser

职责：

- 只负责 HTML -> 标准消息结构。
- 不负责网络请求。
- 不负责数据库去重。

当前已有：

- `collector/parsers/telegram_parser.py`

后续优化：

- 从链接预览卡片提取外部链接。
- 支持 trailing slash、fragment 等更多消息 URL 形态。
- 增加真实 Telegram HTML fixture 测试。
- 更稳健地处理无正文、媒体消息、转发消息、置顶消息。

### Deduplicator

职责：

- 判断消息是否已经处理。
- 写入已处理 message key。
- 支持 SQLite 唯一约束去重，后续可加 Redis seen key 做热路径加速。

建议文件：

- `collector/dedup/deduplicator.py`

推荐唯一键：

```text
source_id + ":" + message_id
```

接口：

```python
class Deduplicator:
    def is_seen(self, source_id: str, message_id: str) -> bool:
        ...

    def mark_seen(self, source_id: str, message_id: str) -> None:
        ...
```

批量接口更适合高吞吐：

```python
class Deduplicator:
    def filter_new(self, items: list[dict]) -> list[dict]:
        ...

    def mark_seen_batch(self, items: list[dict]) -> None:
        ...
```

### Consumer

职责：

- 接收新消息。
- 写入 SQLite 主消息表。
- 写入 SQLite FTS5 全文索引。
- 写入 SQLite 实体和关系表。
- 可选写入 Redis 最新消息缓存。
- 可选写入 DuckDB 历史分析表和 FAISS 向量索引。
- 可选推送到消息队列或后续分析流程。

建议文件：

- `collector/consumers/message_consumer.py`

接口：

```python
class MessageConsumer:
    def consume(self, items: list[dict]) -> None:
        ...
```

### Storage / Index

建议拆分：

- `collector/storage/sqlite_store.py`
- `collector/storage/sqlite_fts.py`
- `collector/storage/sqlite_graph.py`
- `collector/storage/redis_cache.py`
- `collector/storage/duckdb_store.py`
- `collector/storage/faiss_index.py`

SQLite 用途：

- 保存完整消息历史。
- 通过唯一索引实现增量去重。
- 通过 FTS5 提供全文搜索。
- 通过实体表和关系表承接小规模图谱查询。
- 单文件数据库，无服务部署成本，适合轻量 VPS。

Redis 可选用途：

- 保存最近 N 条消息。
- 缓存最近关键词搜索结果。
- 在频道很多时保存 seen key 做热路径加速。
- 保存每个 feed 的 last run 状态。

DuckDB 用途：

- 保存离线历史快照或归档数据。
- 承接大批量历史分析、聚合、回测和导出。
- 用本地文件即可运行，不需要单独部署数据库服务。

FAISS 用途：

- 保存文本 embedding 向量索引。
- 支持语义搜索、相似新闻召回和聚类。
- 可与 DuckDB 的历史消息表通过 `guid` 关联。

不建议在轻量 VPS 版本中引入 PostgreSQL / Elasticsearch / RediSearch，除非后续出现强事务、多租户、跨机集群或超大规模搜索需求。

## 增量抓取设计

每条消息必须具备唯一键：

```text
unique_key = source_id + ":" + message_id
```

处理规则：

1. Parser 必须提取 `message_id`。
2. Deduplicator 检查 `unique_key` 是否存在。
3. 只把未见过的消息交给 Consumer。
4. Consumer 写库成功后，Deduplicator 标记 seen。
5. SQLite 对 `source_id, message_id` 建唯一索引，作为在线去重入口和最终防线。
6. Redis seen key 只作为可选热缓存，不作为必要组件。

SQLite 主表结构示例：

```sql
CREATE TABLE telegram_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'telegram',
    message_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    raw_text_full TEXT NOT NULL,
    pub_at TEXT,
    external_url TEXT,
    preview_title TEXT,
    media_json TEXT,
    collected_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, message_id)
);
```

SQLite FTS5 全文索引表示例：

```sql
CREATE VIRTUAL TABLE telegram_messages_fts USING fts5(
    title,
    summary,
    raw_text_full,
    source_name,
    external_url UNINDEXED,
    content='telegram_messages',
    content_rowid='id'
);
```

插入时同步 FTS5：

```sql
INSERT INTO telegram_messages_fts(rowid, title, summary, raw_text_full, source_name, external_url)
VALUES (?, ?, ?, ?, ?, ?);
```

关键词查询示例：

```sql
SELECT m.*
FROM telegram_messages_fts f
JOIN telegram_messages m ON m.id = f.rowid
WHERE telegram_messages_fts MATCH ?
ORDER BY m.pub_at DESC
LIMIT ?;
```

FTS5 支持：

- 关键词搜索。
- 布尔搜索，例如 `stock OR FED`。
- 前缀匹配，例如 `financ*`。
- 用 `bm25()` 做相关度排序。
- 给标题、正文设置不同权重。

SQLite 轻量实体关系表示例：

```sql
CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    UNIQUE (entity_type, normalized_name)
);

CREATE TABLE message_entities (
    message_id INTEGER NOT NULL REFERENCES telegram_messages(id),
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL DEFAULT 'MENTIONS',
    confidence REAL,
    PRIMARY KEY (message_id, entity_id, relation_type)
);

CREATE TABLE entity_relations (
    source_entity_id INTEGER NOT NULL REFERENCES entities(id),
    target_entity_id INTEGER NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_entity_id, target_entity_id, relation_type)
);
```

SQLite 可以覆盖小规模实体关系查询；DuckDB / FAISS 适合承接更重的历史批处理和语义检索。

重要约束：

- RedisGraph 已经到达 EOL，不建议把新项目直接绑定到 RedisGraph API。
- 在轻量 VPS 场景，优先用 SQLite 关系表实现“小图谱”，避免引入额外服务。
- 如果后续需要复杂图谱推理，再抽象 `GraphIndex` 接口并接入专门图存储。

## 第二阶段轻量架构

第二阶段建议走“SQLite + FTS5 优先”的轻量路线，不部署 Elasticsearch / PostgreSQL / RediSearch。

核心层：

- SQLite 保存消息历史、增量去重状态和实体关系。
- FTS5 保存标题、摘要、正文全文索引，支持关键词、布尔、前缀和相关度排序。
- SQLite 关系表保存公司、人物、事件、外链等实体关系，覆盖小规模图谱查询。

可选实时缓存：

- Redis 缓存最新 N 条消息。
- Redis 缓存最近关键词查询结果。
- Redis 在频道数量增加后保存 seen key，加速去重热路径。

历史层：

- DuckDB 可选保存历史消息快照和分析表。
- FAISS 保存文本 embedding，支持语义搜索、相似新闻、主题聚类。
- SQLite / DuckDB 和 FAISS 通过 `guid` 关联。

前端 API 层：

- 查询最新消息：默认读 SQLite，启用 Redis 后读缓存。
- 全文搜索：读 SQLite FTS5。
- 图谱交互：读 SQLite 实体关系表。
- 历史分析：读 SQLite 或 DuckDB。
- 语义搜索：读 FAISS，再用 SQLite / DuckDB 回填消息详情。

这一方案的优点：

- 轻量：单文件数据库，无服务部署成本，适合 2 核 1GB VPS。
- 零运维：SQLite 随 Python 标准库可用，FTS5 通常随系统 SQLite 编译提供。
- 性能足够：几十万条 Telegram 消息的关键词搜索和历史查询完全可承载。
- 可扩展：新增频道、多媒体、实体抽取时，只需扩展 SQLite 表和 FTS 字段。
- 前端友好：列表、搜索、详情页、小规模实体关系查询都可以直接由 SQLite 支撑。

## 异步扩展设计

多个频道抓取时，建议使用 `asyncio + aiohttp`。

关键点：

- 使用全局并发限制，例如 `asyncio.Semaphore(5)`。
- 使用频道级限速，避免同一频道短时间重复请求。
- 每个请求使用 timeout。
- 单个 feed 失败不影响其他 feed。

伪代码：

```python
async def collect_feed(feed):
    html = await fetcher.fetch(feed["url"], feed["collect"]["timeout_ms"])
    items = parser.parse(html)
    new_items = deduplicator.filter_new(items)
    await consumer.consume(new_items)
    await deduplicator.mark_seen_batch(new_items)


async def collect_all(feeds):
    semaphore = asyncio.Semaphore(5)

    async def guarded(feed):
        async with semaphore:
            return await collect_feed(feed)

    return await asyncio.gather(
        *(guarded(feed) for feed in feeds),
        return_exceptions=True,
    )
```

## 重试策略

建议对网络请求增加重试：

- HTTP 429、500、502、503、504 可重试。
- 连接超时、读取超时可重试。
- 404、403 通常不重试，直接记录异常。

退避策略：

```text
sleep = min(base_delay * 2 ** attempt, max_delay)
```

建议默认：

- retries: 2
- base_delay: 1s
- max_delay: 30s
- 每次重试加少量 jitter。

## 限速策略

Telegram 静态页不是正式 API，长期采集需要保守限速。

建议：

- 全局并发：3 到 5。
- 单频道最小间隔：30 到 120 秒。
- 遇到 429 后指数退避。
- 不要高频刷新同一个频道。
- 遵守 feed 配置里的 `runs_per_day` 和 `scheduled_times_local`。

## 日志设计

使用 Python 标准 `logging`，后续可切换到结构化 JSON 日志。

建议记录：

- feed_id、source_id、url。
- HTTP status、耗时、重试次数。
- parse 出的 item 数量。
- 新消息数量、重复消息数量。
- 写入存储成功/失败数量。
- 异常堆栈。

示例字段：

```text
event=feed_collected feed_id=tg_finance_news_daily fetched=20 new=3 duplicate=17 elapsed_ms=850
```

## 配置设计

当前 `src/config/feed-registry.json` 可以继续使用。后续建议扩展全局配置：

```json
{
  "collector": {
    "max_concurrency": 5,
    "default_timeout_ms": 12000,
    "default_retries": 2,
    "rate_limit": {
      "per_feed_min_interval_seconds": 60
    }
  },
  "storage": {
    "sqlite_path": "data/news.sqlite3",
    "sqlite_fts_table": "telegram_messages_fts",
    "redis_url": "",
    "duckdb_path": "",
    "faiss_index_path": ""
  }
}
```

敏感配置不要提交到仓库，使用环境变量覆盖。

## 推荐目录结构

```text
finance_news_daily_collector/
  collector/
    config/
      feed_registry.py
    consumers/
      message_consumer.py
    dedup/
      deduplicator.py
    fetchers/
      telegram_fetcher.py
    parsers/
      telegram_parser.py
    storage/
      sqlite_store.py
      sqlite_fts.py
      sqlite_graph.py
      redis_cache.py
      duckdb_store.py
      faiss_index.py
    runner.py
  scripts/
    fetch_finance_news_daily.py
    run_collector.py
  src/config/
    feed-registry.json
  tests/
    fixtures/
      telegram_finance_news_daily.html
    test_telegram_parser.py
    test_deduplicator.py
    test_runner.py
```

## 分阶段实现计划

### 阶段 1：完善单频道可靠采集

- 保留当前同步 Fetcher。
- 增加可注入 RateLimiter。
- 增加 Runner 和异步调度入口。
- 增加日志。
- 增加重试和 timeout。
- 增加真实 HTML fixture 测试。

### 阶段 2：接入 SQLite + FTS5 存储检索层

- 增加 SQLite 主消息表。
- 增加 SQLite 唯一索引，实现增量去重。
- 增加 FTS5 全文索引。
- 增加实体表和关系表，支持小规模图谱查询。
- Consumer 统一写入 SQLite 主表、FTS5 和实体关系表。

### 阶段 3：可选接入 Redis 热缓存

- Redis 缓存最新 N 条消息。
- Redis 缓存最近关键词查询结果。
- Redis 可选保存 seen key，加速频道数量增加后的热路径去重。
- 仍以 SQLite 唯一索引作为最终一致性防线。

### 阶段 4：接入 DuckDB / FAISS 离线增强层

- DuckDB 可选保存历史快照和离线分析表。
- FAISS 保存文本向量索引。
- 用 `guid` 关联 SQLite / DuckDB 历史表和 FAISS 向量结果。
- 增加历史回放和离线重建索引脚本。

### 阶段 5：支持更高性能的异步抓取

- 增加 `AsyncTelegramFetcher`。
- Runner 支持读取多个 enabled feed。
- 增加全局并发限制和频道级限速。
- 单 feed 失败不影响整体运行。

### 阶段 6：前端查询和可视化 API

- 最新消息 API。
- 全文搜索 API。
- 语义搜索 API。
- 轻量实体关系查询和可视化 API。

## 当前实现差距

当前代码已经具备：

- 单频道抓取入口。
- Telegram 静态页 parser。
- message ID 提取。
- feed registry 配置。
- 同步 Runner 和异步调度入口。
- 重试、timeout、轻量限速和日志。

仍缺少：

- SQLite 主消息表。
- SQLite 唯一索引增量去重。
- SQLite FTS5 全文索引。
- SQLite 实体和关系表。
- 可选 Redis 热缓存。
- 可选 DuckDB / FAISS 历史和语义检索层。
- 真正基于 aiohttp 的异步 Fetcher。
- 真实页面 fixture 和更完整测试。

## 参考

- Redis deprecated modules documentation: https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/deprecated-features/
- Redis Software 7.4.6 release notes: https://redis.io/docs/latest/operate/rs/release-notes/rs-7-4-2-releases/rs-7-4-6-279/
