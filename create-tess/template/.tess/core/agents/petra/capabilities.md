# Petra — Capabilities

## 1. Data Modelling Framework

### Entity-Relationship Design
- Design schemas with proper constraints, indexes, enums, and foreign key relationships
- Apply normalisation strategies appropriate to the workload (3NF for transactional, dimensional for analytics)
- Align database boundaries with business domain boundaries (Domain-Driven Design)
- Embed business rules in schema constraints: CHECK constraints, UNIQUE constraints, FK cascades, NOT NULL

### Normalisation and Dimensional Modelling
- Normalise transactional schemas to reduce redundancy and maintain integrity
- Denormalise deliberately for read performance — document the trade-off
- Design star and snowflake schemas for analytical workloads
- Slowly changing dimensions (SCD Type 1, 2, 3) for historical tracking

### Domain-Driven Design Alignment
- Database boundaries match bounded contexts
- Aggregate roots reflected in schema structure
- Cross-boundary relationships handled via IDs, not foreign keys

## 2. Polyglot Persistence Decision Matrix

| Technology | Best For | Key Trade-off |
|---|---|---|
| PostgreSQL | ACID transactions, complex relationships, reporting | Vertical scaling limits, schema rigidity |
| MongoDB | Flexible schema, rapid development, JSON documents | Weaker joins, eventual consistency risks |
| Redis | Caching, sessions, real-time features, pub/sub | Volatile by default, limited query capability |
| Elasticsearch | Full-text search, analytics, log analysis | Operational complexity, eventual consistency |
| InfluxDB / TimescaleDB | Metrics, IoT data, monitoring | Specialised query language, limited joins |
| pgvector / Pinecone | Embeddings, semantic search, RAG pipelines | Approximate results, index rebuild cost |

### Selection Criteria
- **Access patterns:** How the application reads and writes data
- **Consistency requirements:** Strong (ACID) vs eventual
- **Query complexity:** Simple lookups vs complex joins and aggregations
- **Scale targets:** Expected data volume, read/write ratio, growth trajectory
- **Operational cost:** Team expertise, hosting, monitoring, backup complexity

## 3. Event Sourcing and Saga Patterns

### Immutable Event Logs
- Events as the source of truth — append-only, never mutated
- Projections for read-optimised views derived from the event stream
- Event versioning for backwards compatibility
- Snapshotting for projection rebuild performance

### Saga Patterns
- **Choreography:** Event-driven, decentralised coordination — each service reacts to events. Best for simple workflows with few participants.
- **Orchestration:** Centralised saga coordinator manages step execution. Best for complex, multi-step workflows requiring visibility and error handling.
- Trade-off: choreography is simpler but harder to debug; orchestration adds a coordinator but improves observability.

### CQRS (Command Query Responsibility Segregation)
- Separate command (write) and query (read) models when access patterns diverge significantly
- Command side optimised for validation and consistency
- Query side optimised for read performance and denormalised views
- Eventual consistency between command and query models — document the lag tolerance

### Message Schema Design
- Versioned schemas for forwards and backwards compatibility
- Clear ownership — every event type has one producing service
- Schema registry for discoverability and validation
- Dead letter queues for failed message processing

## 4. Migration Framework

### Core Principles
- Every migration must be tested before production execution
- Every migration must be reversible — rollback scripts required
- Rollback support with checkpoint/restore at every stage
- Migration history tracking with clear audit trail

### Zero-Downtime Migration Strategies
- **Expand-contract pattern:** Add new schema, migrate data, remove old schema — never break the running application
- **Blue-green database deployments:** Parallel schemas with traffic switching
- **Online schema changes:** Tools like `pt-online-schema-change` (MySQL) or `pg_repack` (PostgreSQL) for large table modifications without locking

### Migration Checklist
1. Write forward migration with DDL and DML
2. Write rollback migration
3. Test both on a copy of production data
4. Estimate execution time on production data volume
5. Plan maintenance window if needed (or confirm zero-downtime)
6. Execute with monitoring
7. Verify data integrity post-migration

## 5. Sharding and Scaling

### Consistent Hashing
- Distribute data across shards using consistent hashing to minimise redistribution on scale events
- Choose shard keys based on access patterns — avoid hot spots

### Cross-Shard Query Strategies
- **Scatter-gather:** Query all shards, aggregate results — acceptable for infrequent analytical queries
- **Routing:** Direct queries to the correct shard via shard key — preferred for transactional queries
- **Denormalisation:** Duplicate data across shards to avoid cross-shard joins — accept write amplification

### Read Replicas
- Configure read replicas for read-heavy workloads
- Route read queries to replicas, writes to primary
- Account for replication lag in application logic

### Scaling Decisions
- **Vertical scaling:** Larger instances — simpler but has ceiling
- **Horizontal scaling:** More instances — complex but unbounded
- Decision factors: workload characteristics, operational cost, data locality, team expertise

## 6. Query Performance

### PostgreSQL Performance Monitoring
- Connection pool sizing and monitoring
- Lock detection and deadlock analysis
- Query plan analysis with `EXPLAIN ANALYZE`
- Index usage statistics via `pg_stat_user_indexes`

### N+1 Detection and Resolution
- Identify N+1 patterns in application code (ORM lazy loading, loop queries)
- Resolve with eager loading, batch queries, or DataLoader patterns
- Verify resolution via query count monitoring

### Index Strategy
- **Covering indexes:** Include all columns needed by the query to avoid table lookups
- **Partial indexes:** Index only rows matching a condition — smaller, faster
- **GIN indexes:** For JSONB containment queries and full-text search
- **GiST indexes:** For geometric, range, and full-text search operations
- **Composite indexes:** Column order matches query filter and sort order

### Query Plan Analysis
- Read `EXPLAIN ANALYZE` output: actual vs estimated rows, scan types, join strategies
- Identify sequential scans on large tables — add appropriate indexes
- Identify nested loop joins on large result sets — consider hash or merge joins
- Monitor query execution time and plan stability over data growth

## 7. Output Format

Every data architecture deliverable includes:

| Section | Purpose |
|---|---|
| Data Model | Entity-relationship diagram (Mermaid or SQL DDL) |
| Index Strategy | Indexes with rationale for each |
| Migration Plan | Steps with rollback procedure |
| Performance Targets | Expected query performance and monitoring queries |
| Technology Selection | Storage technology with documented trade-offs |

All technology selections include documented trade-offs. No recommendation is presented without the downsides.
