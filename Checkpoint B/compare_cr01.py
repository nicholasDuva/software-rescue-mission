"""Task 5 evidence: CR-01 changes only what it is meant to change.

Runs the transcript from compare_behaviour.py against the Task 4 commit and
against the working tree. The transcript never uses `express`, so it covers
only behaviour that CR-01 must preserve. Before comparing, the CR-01 wording
in the working-tree output is turned back into the old wording:

- the error message for an invalid fulfillment value;
- the fulfillment choices in CLI usage and error text, and the new help text;
- the menu fulfillment prompt.

Every other difference counts as a regression. Run from the repository root:

    python "Checkpoint B/compare_cr01.py"
"""

import json
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_behaviour  # noqa: E402

TASK4_COMMIT = "6bbf807"  # "Task 4: Defect fixes"

WORDING = [  # (CR-01 wording, Task 4 wording)
    ("Fulfillment must be pickup, delivery or express.",
     "Fulfillment must be pickup or delivery."),
    ("{pickup,delivery,express}", "{pickup,delivery}"),
    ("(choose from pickup, delivery, express)", "(choose from pickup, delivery)"),
    ("Fulfillment [pickup/delivery/express]", "Fulfillment [pickup/delivery]"),
]
# The --fulfillment help text is new: drop its indented lines from --help output.
HELP_TEXT = re.compile(r"(--fulfillment \{pickup,delivery\}\n)(?: {24}.*\n)+")


def old_wording(value):
    """Return a copy of a transcript record with every string in the Task 4 wording."""
    if isinstance(value, dict):
        return {key: old_wording(item) for key, item in value.items()}
    if isinstance(value, list):
        return [old_wording(item) for item in value]
    if isinstance(value, str):
        for new, old in WORDING:
            value = value.replace(new, old)
        return HELP_TEXT.sub(r"\1", value)
    return value


def main():
    with tempfile.TemporaryDirectory() as name:
        compare_behaviour.extract_baseline(TASK4_COMMIT, Path(name))
        before = compare_behaviour.read_transcript(Path(name))
    after = compare_behaviour.read_transcript(compare_behaviour.REPO_ROOT)

    raw_differences = regressions = 0
    for section in before:
        old, new = before[section], after[section]
        raw = sum(1 for pair in zip(old, new) if pair[0] != pair[1])
        restored = [old_wording(record) for record in new]
        left = [index for index, pair in enumerate(zip(old, restored)) if pair[0] != pair[1]]
        if len(old) != len(new):
            left.append(min(len(old), len(new)))
        raw_differences += raw
        regressions += len(left)
        print(f"{section:<9} {len(old):>6} records: {raw:>4} differ, "
              f"{len(left)} left after restoring the old wording")
        for index in left[:3]:
            print("  task 4:", json.dumps(old[index])[:600])
            print("  cr-01: ", json.dumps(restored[index])[:600])
    print(f"Task 4 commit {TASK4_COMMIT} vs working tree: {raw_differences} differences, "
          + ("all of them CR-01 wording only" if not regressions
             else f"{regressions} NOT explained by CR-01"))
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
