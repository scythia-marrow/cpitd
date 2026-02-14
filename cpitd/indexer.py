"""Hash index for detecting line-level clones across (and within) files.

Maps hash-tree node hashes to their source locations. Collisions at any
tree level indicate potential code clones.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from cpitd.winnowing import HashTreeNode

_MAX_BUCKET_SIZE = 100  # skip trivial-line buckets (e.g. "}", "pass")


@dataclass(frozen=True, slots=True)
class NodeLocation:
    """A hash-tree node tied to its source file."""

    file_path: str
    node: HashTreeNode


@dataclass(frozen=True, slots=True)
class CloneMatch:
    """Two source locations sharing a tree-node hash."""

    left: NodeLocation
    right: NodeLocation
    level: int
    shared_hash: int


def _ranges_overlap(a: HashTreeNode, b: HashTreeNode) -> bool:
    """Return True if two nodes' line ranges overlap."""
    return a.start_line <= b.end_line and b.start_line <= a.end_line


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

    def find_clones(self, *, min_token_count: int = 10) -> list[CloneMatch]:
        """Find all location pairs sharing a hash-tree node hash.

        Args:
            min_token_count: Ignore nodes with fewer tokens than this.

        Returns:
            List of CloneMatch objects for each shared hash.
        """
        matches: list[CloneMatch] = []
        for hash_value, locations in self._index.items():
            if len(locations) < 2 or len(locations) > _MAX_BUCKET_SIZE:
                continue
            for i, left in enumerate(locations):
                if left.node.token_count < min_token_count:
                    continue
                for right in locations[i + 1 :]:
                    if right.node.token_count < min_token_count:
                        continue
                    # Allow same-file matches only when ranges don't overlap
                    if left.file_path == right.file_path and _ranges_overlap(
                        left.node, right.node
                    ):
                        continue
                    matches.append(
                        CloneMatch(
                            left=left,
                            right=right,
                            level=left.node.level,
                            shared_hash=hash_value,
                        )
                    )
        return matches
