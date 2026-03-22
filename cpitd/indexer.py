"""Hash index for detecting line-level clones across (and within) files.

Maps hash-tree node hashes to their source locations. Collisions at any
tree level indicate potential code clones. Groups are first class citizens
to ensure that output scales linearly with the number of duplicated regions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from cpitd.types import frozen_slots
from cpitd.winnowing import HashTreeNode

_MAX_BUCKET_SIZE = 100  # skip trivial-line buckets (e.g. "}", "pass")


@frozen_slots
class NodeLocation:
    """A hash-tree node tied to its source file."""

    file_path: str
    node: HashTreeNode


@frozen_slots
class CloneMatchGroup:
    """Multiple source locations sharing a tree-node hash."""

    locations: tuple[NodeLocation, ...]
    level: int
    shared_hash: int


@dataclass
class LineHashIndex:
    """Index mapping hash-tree node hashes to source locations.

    Accumulate tree nodes from multiple files, then query for hash
    collisions that indicate potential clones.
    """

    _index: dict[int, list[NodeLocation]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, file_path: str, tree: list[list[HashTreeNode]]) -> None:
        """Add all nodes from a file's hash tree to the index."""
        for level in tree:
            for node in level:
                self._index[node.hash_value].append(
                    NodeLocation(file_path=file_path, node=node)
                )

    def find_clones(self, *, min_token_count: int = 10) -> list[CloneMatchGroup]:
        """Find all location groups sharing a hash-tree node hash.

        Args:
            min_token_count: Ignore nodes with fewer tokens than this.

        Returns:
            One CloneMatchGroup per shared hash, each containing all
            locations that share that hash. O(N) in the number of
            locations.
        """
        groups: list[CloneMatchGroup] = []
        for hash_value, locations in self._index.items():
            if len(locations) < 2 or len(locations) > _MAX_BUCKET_SIZE:
                continue
            # Sub-group by level to avoid mixing tree levels
            by_level: dict[int, list[NodeLocation]] = defaultdict(list)
            for loc in locations:
                if loc.node.token_count >= min_token_count:
                    by_level[loc.node.level].append(loc)
            for level, level_locs in by_level.items():
                if len(level_locs) < 2:
                    continue
                groups.append(
                    CloneMatchGroup(
                        locations=tuple(level_locs),
                        level=level,
                        shared_hash=hash_value,
                    )
                )
        return groups
