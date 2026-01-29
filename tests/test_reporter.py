"""Tests for the reporter module."""

import io
import json

from cpitd.reporter import CloneReport, aggregate_clone_pairs, format_human, format_json
from cpitd.indexer import ClonePair, FingerprintLocation
from cpitd.winnowing import Fingerprint


def _make_pair(file_a: str, file_b: str, hash_value: int) -> ClonePair:
    fp_a = Fingerprint(hash_value=hash_value, line=1, column=0, token_index=0)
    fp_b = Fingerprint(hash_value=hash_value, line=5, column=0, token_index=10)
    return ClonePair(
        left=FingerprintLocation(file_path=file_a, fingerprint=fp_a),
        right=FingerprintLocation(file_path=file_b, fingerprint=fp_b),
        shared_hash=hash_value,
    )


class TestAggregate:
    def test_groups_by_file_pair(self):
        pairs = [
            _make_pair("a.py", "b.py", 1),
            _make_pair("a.py", "b.py", 2),
            _make_pair("a.py", "c.py", 3),
        ]
        reports = aggregate_clone_pairs(pairs)
        assert len(reports) == 2

    def test_empty_pairs(self):
        reports = aggregate_clone_pairs([])
        assert reports == []


class TestFormatHuman:
    def test_no_clones_message(self):
        out = io.StringIO()
        format_human([], out)
        assert "No clones detected" in out.getvalue()

    def test_reports_file_pairs(self):
        reports = [
            CloneReport(
                file_a="a.py",
                file_b="b.py",
                shared_hashes=3,
                locations_a=[(1, 0)],
                locations_b=[(5, 0)],
            )
        ]
        out = io.StringIO()
        format_human(reports, out)
        output = out.getvalue()
        assert "a.py" in output
        assert "b.py" in output
        assert "3" in output


class TestFormatJson:
    def test_valid_json(self):
        reports = [
            CloneReport(
                file_a="a.py",
                file_b="b.py",
                shared_hashes=2,
                locations_a=[(1, 0), (3, 4)],
                locations_b=[(10, 0), (12, 4)],
            )
        ]
        out = io.StringIO()
        format_json(reports, out)
        data = json.loads(out.getvalue())
        assert data["total_pairs"] == 1
        assert len(data["clone_pairs"]) == 1
        assert data["clone_pairs"][0]["file_a"] == "a.py"

    def test_empty_reports_json(self):
        out = io.StringIO()
        format_json([], out)
        data = json.loads(out.getvalue())
        assert data["total_pairs"] == 0
