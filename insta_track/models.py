from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class RelationKind(StrEnum):
    FOLLOWERS = "followers"
    FOLLOWING = "following"


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    """One fetch of a target's followers or following list at a point in time."""

    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshots_target_kind_id", "target", "kind", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # UTC, naive
    target: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)

    entries: Mapped[list["SnapshotEntry"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class SnapshotEntry(Base):
    """A single account present in a snapshot."""

    __tablename__ = "snapshot_users"

    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False)

    snapshot: Mapped[Snapshot] = relationship(back_populates="entries")
