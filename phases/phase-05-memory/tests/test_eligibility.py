"""Synthetic boundary checks, runnable without installing application dependencies."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

from t1d_memory.eligibility import EpisodeSnapshot, RetrievalQuery, Scope, SourceRevision, eligible


def uid(number: int) -> UUID:
    return UUID(int=number)


class EligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.time = datetime(2026, 11, 1, 12, tzinfo=UTC)
        self.scope = Scope(uid(1), uid(2))
        self.source = SourceRevision(uid(3), self.scope, self.time, self.time, True, True)
        self.episode = EpisodeSnapshot(
            uid(4),
            uid(3),
            self.scope,
            self.time,
            self.time,
            self.time,
            True,
            False,
            (self.source,),
        )
        self.query = RetrievalQuery(self.scope, self.time, uid(5), self.time)

    def test_inclusive_cutoff_and_equivalent_offset(self) -> None:
        self.assertTrue(eligible(self.query, self.episode))
        query = replace(self.query, cutoff=self.time.astimezone(timezone(timedelta(hours=5.5))))
        self.assertTrue(eligible(query, self.episode))

    def test_foreign_study_and_patient(self) -> None:
        for scope in (Scope(uid(9), uid(2)), Scope(uid(1), uid(9))):
            self.assertFalse(eligible(self.query, replace(self.episode, scope=scope)))

    def test_foreign_constituent_lineage(self) -> None:
        source = replace(self.source, scope=Scope(uid(1), uid(9)))
        self.assertFalse(eligible(self.query, replace(self.episode, sources=(source,))))

    def test_target_and_unreviewed_and_withdrawn(self) -> None:
        self.assertFalse(
            eligible(replace(self.query, target_anchor_revision_id=uid(3)), self.episode)
        )
        self.assertFalse(eligible(self.query, replace(self.episode, human_confirmed=False)))
        self.assertFalse(eligible(self.query, replace(self.episode, withdrawn=True)))

    def test_future_response_and_derivation(self) -> None:
        later = self.time + timedelta(seconds=1)
        self.assertFalse(
            eligible(self.query, replace(self.episode, ends_at=later, derived_at=later))
        )
        self.assertFalse(eligible(self.query, replace(self.episode, derived_at=later)))

    def test_late_annotation_and_backfill(self) -> None:
        later = self.time + timedelta(seconds=1)
        annotation = replace(self.source, revision_id=uid(6), available_at=later)
        episode = replace(self.episode, sources=(self.source, annotation), derived_at=later)
        self.assertFalse(eligible(self.query, episode))
        # Even an inconsistent backdated derivation cannot bypass source availability.
        self.assertFalse(eligible(self.query, replace(episode, derived_at=self.time)))

    def test_stale_or_quarantined_latest_revision(self) -> None:
        for source in (
            replace(self.source, latest_at_cutoff=False),
            replace(self.source, usable=False),
        ):
            self.assertFalse(eligible(self.query, replace(self.episode, sources=(source,))))

    def test_bad_lineage(self) -> None:
        for sources in (
            (),
            (self.source, self.source),
            (replace(self.source, revision_id=uid(6)),),
        ):
            with self.assertRaises(ValueError):
                replace(self.episode, sources=sources)

    def test_invalid_times(self) -> None:
        with self.assertRaises(ValueError):
            replace(self.query, cutoff=self.time.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            replace(self.query, cutoff=self.time + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            replace(self.episode, ends_at=self.time - timedelta(seconds=1))
        with self.assertRaises(ValueError):
            replace(self.source, available_at=self.time - timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
