"""Scoped, rebuildable Neo4j projection; canonical data always wins."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from neo4j import GraphDatabase, Query

from t1d_memory.contracts import Episode


class GraphUnavailable(Exception):
    """Redacted dependency failure; no driver diagnostics are returned."""


class GraphIndex(Protocol):
    def replace(
        self, study: UUID, patient: UUID, episodes: list[Episode], watermark: datetime
    ) -> None: ...
    def similarities(
        self,
        study: UUID,
        patient: UUID,
        ids: list[str],
        foods: tuple[str, ...],
        cutoff: datetime,
        watermark: datetime,
    ) -> dict[str, float]: ...
    def close(self) -> None: ...


class Neo4jIndex:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self.driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
            connection_timeout=3,
            connection_acquisition_timeout=3,
            max_transaction_retry_time=0,
            max_connection_pool_size=5,
        )

    def replace(
        self, study: UUID, patient: UUID, episodes: list[Episode], watermark: datetime
    ) -> None:
        # Serialize complete scope replacement. CAS prevents older concurrent rebuilds
        # replacing a newer projection. Every food node is scoped too.
        try:
            with self.driver.session(database="neo4j") as schema:
                schema.run(
                    "CREATE CONSTRAINT t1d_memory_scope IF NOT EXISTS "
                    "FOR (s:T1DMemoryScope) REQUIRE (s.study,s.patient) IS UNIQUE"
                ).consume()
                schema.run(
                    "CREATE CONSTRAINT t1d_memory_episode IF NOT EXISTS "
                    "FOR (e:T1DMemoryEpisode) REQUIRE (e.study,e.patient,e.id) IS UNIQUE"
                ).consume()
                schema.run(
                    "CREATE CONSTRAINT t1d_memory_food IF NOT EXISTS "
                    "FOR (f:T1DMemoryFood) REQUIRE (f.study,f.patient,f.label) IS UNIQUE"
                ).consume()
            with (
                self.driver.session(database="neo4j") as session,
                session.begin_transaction(timeout=5) as tx,
            ):
                tx.run(
                    "MERGE (s:T1DMemoryScope {study:$study,patient:$patient}) "
                    "SET s.lock=coalesce(s.lock,0)+1",
                    study=str(study),
                    patient=str(patient),
                ).consume()
                row = tx.run(
                    "MATCH (s:T1DMemoryScope {study:$study,patient:$patient}) "
                    "RETURN s.watermark AS watermark",
                    study=str(study),
                    patient=str(patient),
                ).single()
                if (
                    row is not None
                    and row["watermark"]
                    and row["watermark"] > watermark.isoformat()
                ):
                    raise GraphUnavailable()
                tx.run(
                    "MATCH (e:T1DMemoryEpisode {study:$study,patient:$patient}) DETACH DELETE e",
                    study=str(study),
                    patient=str(patient),
                ).consume()
                tx.run(
                    "MATCH (f:T1DMemoryFood {study:$study,patient:$patient}) DETACH DELETE f",
                    study=str(study),
                    patient=str(patient),
                ).consume()
                tx.run(
                    "UNWIND $episodes AS item "
                    "CREATE (e:T1DMemoryEpisode {id:item.id,study:$study,patient:$patient,"
                    "available:item.available,ending:item.ending}) "
                    "WITH e,item UNWIND item.foods AS food "
                    "MERGE (f:T1DMemoryFood {study:$study,patient:$patient,label:food}) "
                    "CREATE (e)-[:T1D_CONTAINS {study:$study,patient:$patient}]->(f)",
                    study=str(study),
                    patient=str(patient),
                    episodes=[
                        {
                            "id": str(e.id),
                            "available": e.available_at.isoformat(),
                            "ending": e.end_at.isoformat(),
                            "foods": list(e.foods),
                        }
                        for e in episodes
                    ],
                ).consume()
                tx.run(
                    "MATCH (s:T1DMemoryScope {study:$study,patient:$patient}) "
                    "SET s.watermark=$watermark",
                    study=str(study),
                    patient=str(patient),
                    watermark=watermark.isoformat(),
                ).consume()
                tx.commit()
        except Exception:
            raise GraphUnavailable() from None

    def similarities(
        self,
        study: UUID,
        patient: UUID,
        ids: list[str],
        foods: tuple[str, ...],
        cutoff: datetime,
        watermark: datetime,
    ) -> dict[str, float]:
        try:
            with self.driver.session(database="neo4j") as session:
                state = session.run(
                    Query(
                        "MATCH (s:T1DMemoryScope {study:$study,patient:$patient}) "
                        "RETURN s.watermark AS watermark",
                        timeout=5,
                    ),
                    study=str(study),
                    patient=str(patient),
                ).single()
                if (
                    state is None
                    or state["watermark"] != watermark.isoformat()
                    or watermark > cutoff
                ):
                    raise GraphUnavailable()
                # No unbounded graph traversal or cross-patient expansion.
                rows = session.run(
                    Query(
                        "MATCH (e:T1DMemoryEpisode {study:$study,patient:$patient}) "
                        "WHERE e.id IN $ids AND datetime(e.available)<=datetime($cutoff) "
                        "AND datetime(e.ending)<=datetime($cutoff) "
                        "OPTIONAL MATCH (e)-[r:T1D_CONTAINS {study:$study,patient:$patient}]->"
                        "(f:T1DMemoryFood {study:$study,patient:$patient}) "
                        "RETURN e.id AS id,collect(f.label) AS foods",
                        timeout=5,
                    ),
                    study=str(study),
                    patient=str(patient),
                    ids=ids,
                    cutoff=cutoff.isoformat(),
                )
                result = {}
                for row in rows:
                    historical = set(row["foods"])
                    target = set(foods)
                    result[str(row["id"])] = len(historical & target) / len(historical | target)
                # Missing graph entries are an incomplete index, not zero similarity.
                if set(result) != set(ids):
                    raise GraphUnavailable()
                final = session.run(
                    Query(
                        "MATCH (s:T1DMemoryScope {study:$study,patient:$patient}) "
                        "RETURN s.watermark AS watermark",
                        timeout=5,
                    ),
                    study=str(study),
                    patient=str(patient),
                ).single()
                if final is None or final["watermark"] != watermark.isoformat():
                    raise GraphUnavailable()
                return result
        except Exception:
            raise GraphUnavailable() from None

    def close(self) -> None:
        self.driver.close()
