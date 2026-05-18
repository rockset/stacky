"""Tests for stacky.commands.recreate."""

import unittest

from stacky.commands.recreate import parse_stack_info


class TestParseStackInfo(unittest.TestCase):
    def test_simple_linear_stack(self):
        text = "\n".join([
            " ┌── feat-c",
            " ├── feat-b",
            " ├── feat-a",
            "* main",
        ])
        edges = parse_stack_info(text)
        self.assertEqual(edges, [
            ("feat-c", "main"),
            ("feat-b", "main"),
            ("feat-a", "main"),
            ("main", None),
        ])

    def test_branched_stack(self):
        # Two children of feat-a, plus a sibling chain rooted at main.
        text = "\n".join([
            " │   ┌── feat-a-c2",
            " │   ┌── feat-a-c1",
            " ├── feat-a",
            " ├── feat-b",
            "* main",
        ])
        edges = parse_stack_info(text)
        self.assertEqual(edges, [
            ("feat-a-c2", "feat-a"),
            ("feat-a-c1", "feat-a"),
            ("feat-a", "main"),
            ("feat-b", "main"),
            ("main", None),
        ])

    def test_strips_status_markers_and_pr_suffix(self):
        text = "\n".join([
            " ┌── ! feat-x",
            " ├── !~ feat-y (#42 some title)",
            "* main",
        ])
        edges = parse_stack_info(text)
        self.assertEqual(edges, [
            ("feat-x", "main"),
            ("feat-y", "main"),
            ("main", None),
        ])

    def test_full_frostdb_example(self):
        # The exact tree the user reconstructed by hand.
        text = "\n".join([
            " ┌── ! ynannapaneni/adding-p-validation-for-hybrid",
            " ├── ! ynannapaneni/FDBCORE-XX-simulator-for-log-system-v2",
            " ├── !~ ynannapaneni/FDBCORE-XX-agentbox-git-ignore",
            " │           ┌── ynannapaneni/FDBCORE-4496-dmi-uses-real-time-stream-manager",
            " │       ┌── ynannapaneni/FDBCORE-45165-rsm-on-connection-closed",
            " │   ┌── ynannapaneni/FDBCORE-45165-component-test-for-realtime-delivery-framework",
            " ├── ! ynannapaneni/FDBCORE-44860-real-time-mutation-delivery-framework",
            " ├── !~ ynannapaneni/FDBCORE-40432-fix-bw-lag-metric-spike-issues",
            " │       ┌── ynannapaneni/FDBCORE-37707-adding-hybrid-worker-dd-queue",
            " │   ┌── ynannapaneni/FDBCORE-33707-adding-dd-queue-unit-tests",
            " ├── ! ynannapaneni/FDBCORE-33707-creating-relocate-data-for-shard",
            " ├── !~ frostdb_4",
            " ├── !~ frostdb_3",
            " ├── !~ frostdb_2",
            "* main",
        ])
        edges = dict(parse_stack_info(text))
        self.assertEqual(edges["main"], None)
        self.assertEqual(edges["frostdb_2"], "main")
        self.assertEqual(edges["frostdb_3"], "main")
        self.assertEqual(edges["frostdb_4"], "main")
        self.assertEqual(
            edges["ynannapaneni/FDBCORE-45165-component-test-for-realtime-delivery-framework"],
            "ynannapaneni/FDBCORE-44860-real-time-mutation-delivery-framework",
        )
        self.assertEqual(
            edges["ynannapaneni/FDBCORE-45165-rsm-on-connection-closed"],
            "ynannapaneni/FDBCORE-45165-component-test-for-realtime-delivery-framework",
        )
        self.assertEqual(
            edges["ynannapaneni/FDBCORE-4496-dmi-uses-real-time-stream-manager"],
            "ynannapaneni/FDBCORE-45165-rsm-on-connection-closed",
        )
        self.assertEqual(
            edges["ynannapaneni/FDBCORE-37707-adding-hybrid-worker-dd-queue"],
            "ynannapaneni/FDBCORE-33707-adding-dd-queue-unit-tests",
        )
        self.assertEqual(
            edges["ynannapaneni/FDBCORE-33707-adding-dd-queue-unit-tests"],
            "ynannapaneni/FDBCORE-33707-creating-relocate-data-for-shard",
        )
        self.assertEqual(
            edges["ynannapaneni/FDBCORE-33707-creating-relocate-data-for-shard"],
            "main",
        )

    def test_empty_input(self):
        self.assertEqual(parse_stack_info(""), [])
        self.assertEqual(parse_stack_info("   \n  \n"), [])


if __name__ == "__main__":
    unittest.main()
