"""Hash index for detecting fingerprint collisions across files.

Maps fingerprint hashes to their source locations. Collisions indicate
potential code clones.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from cpitd.winnowing import Fingerprint


@dataclass(frozen=True, slots=True)
class FingerprintLocation:
    """A fingerprint tied to its source file."""

    file_path: str
    fingerprint: Fingerprint


@dataclass(frozen=True, slots=True)
class ClonePair:
    """A pair of file locations sharing a fingerprint hash."""

    left: FingerprintLocation
    right: FingerprintLocation
    shared_hash: int


@dataclass
class FingerprintIndex:
    """Index mapping fingerprint hashes to source locations.

    Accumulate fingerprints from multiple files, then query for
    hash collisions that indicate potential clones.
    """

    _index: dict[int, list[FingerprintLocation]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, file_path: str, fingerprints: list[Fingerprint]) -> None:
        """Add all fingerprints from a file to the index."""
        for fp in fingerprints:
            self._index[fp.hash_value].append(
                FingerprintLocation(file_path=file_path, fingerprint=fp)
            )

    def find_clones(self, *, min_shared: int = 1) -> list[ClonePair]:
        """Find all file pairs sharing at least `min_shared` fingerprint hashes.

        Args:
            min_shared: Minimum number of shared hashes to report a pair.

        Returns:
            List of ClonePair objects for each shared fingerprint.
        """
        pairs: list[ClonePair] = []
        for hash_value, locations in self._index.items():
            if len(locations) < 2:
                continue
            # Generate all cross-file pairs for this hash
            for i, left in enumerate(locations):
                for right in locations[i + 1 :]:
                    if left.file_path != right.file_path:
                        pairs.append(
                            ClonePair(
                                left=left,
                                right=right,
                                shared_hash=hash_value,
                            )
                        )
        return pairs
