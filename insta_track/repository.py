from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from insta_track.models import RelationKind, Snapshot, SnapshotEntry

# user_id -> username
Accounts = dict[int, str]


@dataclass(frozen=True)
class StoredSnapshot:
    taken_at: datetime
    accounts: Accounts


class SnapshotRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def get_latest(self, target: str, kind: RelationKind) -> StoredSnapshot | None:
        with self._session_factory() as session:
            snapshot = session.scalars(
                select(Snapshot)
                .where(Snapshot.target == target, Snapshot.kind == kind)
                .order_by(Snapshot.id.desc())
                .limit(1)
            ).first()
            if snapshot is None:
                return None
            accounts = {entry.user_id: entry.username for entry in snapshot.entries}
            return StoredSnapshot(taken_at=snapshot.taken_at, accounts=accounts)

    def save(
        self, target: str, taken_at: datetime, accounts_by_kind: dict[RelationKind, Accounts]
    ) -> None:
        """Persist snapshots of one check in a single transaction."""
        with self._session_factory.begin() as session:
            for kind, accounts in accounts_by_kind.items():
                session.add(
                    Snapshot(
                        taken_at=taken_at,
                        target=target,
                        kind=kind,
                        entries=[
                            SnapshotEntry(user_id=user_id, username=username)
                            for user_id, username in accounts.items()
                        ],
                    )
                )
