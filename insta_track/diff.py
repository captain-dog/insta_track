from dataclasses import dataclass

from insta_track.models import RelationKind
from insta_track.repository import Accounts


@dataclass(frozen=True)
class DiffLabels:
    title: str
    added: str
    removed: str


LABELS = {
    RelationKind.FOLLOWERS: DiffLabels("Followers", "New followers", "Lost followers"),
    RelationKind.FOLLOWING: DiffLabels("Following", "Newly followed", "Unfollowed"),
}


@dataclass(frozen=True)
class RelationDiff:
    kind: RelationKind
    previous_count: int
    current_count: int
    added: list[str]
    removed: list[str]
    is_initial: bool

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


def compute_diff(kind: RelationKind, previous: Accounts | None, current: Accounts) -> RelationDiff:
    """Compare by user id so that renamed accounts are not reported as changes.

    `previous=None` means there is no earlier snapshot: every account counts as added.
    """
    baseline = previous or {}
    return RelationDiff(
        kind=kind,
        previous_count=len(baseline),
        current_count=len(current),
        added=sorted(name for user_id, name in current.items() if user_id not in baseline),
        removed=sorted(name for user_id, name in baseline.items() if user_id not in current),
        is_initial=previous is None,
    )


def format_diff(diff: RelationDiff) -> str:
    labels = LABELS[diff.kind]
    if not diff.has_changes:
        return f"{labels.title}: {diff.current_count} (no changes)"

    header = f"{labels.title}: {diff.previous_count} → {diff.current_count}"
    if diff.is_initial:
        header += " (initial snapshot)"
    lines = [header]
    if diff.added:
        lines += [f"{labels.added}:"] + [f"  + {name}" for name in diff.added]
    if diff.removed:
        lines += [f"{labels.removed}:"] + [f"  - {name}" for name in diff.removed]
    return "\n".join(lines)
