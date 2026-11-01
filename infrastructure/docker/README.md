# Optional local development stores

User approved this limited Phase 01 scope addition on 2026-11-01. These services are optional, not connected to the API, and not a production deployment. No clinical tables, extensions, graph schemas, embeddings or migrations are created. No Redis/worker is needed for this phase.

## Compatibility boundary
Verified on 2026-11-01 using Docker 29.9.2 and Compose v5.6.1 on Docker Desktop linux/aarch64. Both configured images pulled as linux/arm64, Compose validation passed, and both services passed health, authenticated access and non-destructive restart/persistence checks. Observed RepoDigests and exact results are in [Phase 01 review](../../docs/phase-01-review.md). Patch tags can be republished; observed digests are recorded without silently changing deployment settings.

The TimescaleDB upstream Dockerfile includes pgvector build steps, but no exact image digest plus PostgreSQL/TimescaleDB/pgvector combination has been executed or verified here. Rather than claim it works, this is a plain PostgreSQL development fallback. It does **not** provide TimescaleDB or pgvector and does not replace ADR-002's approved later-phase design. Phase 02 must verify extensions, versions, licensing and migration strategy before selecting its real image. No `CREATE EXTENSION` is run now.

## Setup, health and shutdown
Use a running Docker engine with the Compose plugin (Compose v5.6.1 was verified here); Docker installation itself remains outside the repository. From the repository root:

```sh
cp infrastructure/docker/.env.example infrastructure/docker/.env
```

Fill both password fields with different locally generated random values, at least 24 characters, using letters/digits/underscore/hyphen. Do not paste secrets into Git, chat, logs or shell history. Blank passwords fail Compose interpolation. The `t1d_local` and `neo4j` names are development database identities, not real application accounts.

```sh
docker compose --env-file infrastructure/docker/.env -f infrastructure/docker/compose.yml --profile stores config --quiet
docker compose --env-file infrastructure/docker/.env -f infrastructure/docker/compose.yml --profile stores up -d --wait
docker compose --env-file infrastructure/docker/.env -f infrastructure/docker/compose.yml --profile stores ps
docker compose --env-file infrastructure/docker/.env -f infrastructure/docker/compose.yml --profile stores stop
```

Use `config --quiet` rather than dumping interpolated configuration containing passwords. All host ports bind `127.0.0.1`; defaults are PostgreSQL 5433, Neo4j HTTP 7475 and Bolt 7688. Resolve port collisions through the ignored env file, then restart only this project's services. Do not expose these unencrypted development endpoints or use real health data. Environment credentials are inspectable by users controlling Docker; they are development-only and not a secret-management architecture.

Named volumes persist on stop and normal down. Never use volume-deleting commands without checking ownership and explicit permission. Initial passwords configure new data volumes; changing the environment value does not rotate an existing database's password. Rotate through the database's supported authenticated admin workflow, update the local env value, and restart/recheck health. Never delete a data volume as an implicit password reset. PostgreSQL health checks whether the server accepts connections; Neo4j checks an authenticated trivial query. Neither establishes research or clinical validity.

## Upstream verification references
- [Official PostgreSQL image](https://hub.docker.com/_/postgres) and [published PostgreSQL 17 tags](https://hub.docker.com/_/postgres/tags?name=17.).
- [Official Neo4j image/tags](https://hub.docker.com/_/neo4j) and [Docker authentication setup](https://neo4j.com/docs/operations-manual/current/docker/introduction/).
- [TimescaleDB image source](https://github.com/timescale/timescaledb-docker/blob/main/Dockerfile).


## Authentication and persistence verification findings
Host PostgreSQL TCP on 5433 and Neo4j HTTP on 7475 accepted the generated passwords; deliberately incorrect credentials were rejected on host PostgreSQL and Neo4j Bolt. PostgreSQL's default image trusts socket/loopback connections inside its own container; external host connections use SCRAM. Container access therefore remains a trusted development boundary. `pg_isready` alone does not prove authentication. Do not claim container-local loopback requires a password or reuse this as a production authentication design.

Read-only PostgreSQL cluster identity and Neo4j database identity, plus actual named-volume mounts, remained unchanged across `restart --timeout 30` followed by `up -d --wait --wait-timeout 180`. No application rows, graph nodes, marker files, schemas or volumes were created/deleted for the test. PostgreSQL contained zero user tables and Neo4j zero nodes. This verifies a container restart, not backup/restore or recreation. Services were left running and healthy.

The initial local `.env` was generated with two distinct random 256-bit values, exclusive creation and mode 0600; no values are committed. New developers should create their own credentials. Never overwrite an existing file or reset existing volumes implicitly. Runtime inventory confirmed TimescaleDB/pgvector are absent; the later extension compatibility gate remains open.
