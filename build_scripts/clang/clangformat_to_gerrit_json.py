#!/usr/bin/env python3

import re
import sys
import json

def main(fp=sys.stdin):
    """
    Convert git clang-format --diff output into Gerrit-compatible JSON with clear messages.
    Handles multiple files, all types of hunks, and exact line numbers.
    """

    comments = {}
    current_file = None
    old_line = None
    new_line = None

    # Regex patterns
    hunk_re = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    file_re = re.compile(r"\+\+\+ b/(.+)")

    removed_lines = []
    added_lines = []

    for raw_line in fp:
        line = raw_line.rstrip("\n")

        # Detect new file
        file_match = file_re.match(line)
        if file_match:
            # Flush pending hunks for previous file
            if removed_lines or added_lines:
                emit_hunk_comments(current_file, removed_lines, added_lines, comments)
                removed_lines.clear()
                added_lines.clear()

            current_file = file_match.group(1)
            old_line = None
            new_line = None
            continue

        # Detect hunk start
        hunk_match = hunk_re.match(line)
        if hunk_match:
            # Flush previous hunk
            if removed_lines or added_lines:
                emit_hunk_comments(current_file, removed_lines, added_lines, comments)
                removed_lines.clear()
                added_lines.clear()

            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(3))
            continue

        if current_file is None or old_line is None or new_line is None:
            continue

        # Removed line (from original file)
        if line.startswith('-') and not line.startswith('---'):
            removed_lines.append((old_line, line[1:]))
            old_line += 1
            continue

        # Added line (in new file)
        if line.startswith('+') and not line.startswith('+++'):
            added_lines.append((new_line, line[1:]))
            new_line += 1
            continue

        # Context line: advance both counters
        if not line.startswith('@@'):
            old_line += 1
            new_line += 1

    # Flush last pending hunk
    if removed_lines or added_lines:
        emit_hunk_comments(current_file, removed_lines, added_lines, comments)

    # Output JSON
    if comments:
        output = {
            'comments': comments,
            'message': 'clang-format found style deviations'
        }
    else:
        output = {
            'message': 'clang-format OK',
            'notify': 'NONE'
        }

    print(json.dumps(output, indent=2))


def emit_hunk_comments(current_file, removed_lines, added_lines, comments):
    """Emit a single comment per hunk with clear, reviewer-friendly messages."""
    if not current_file:
        return

    msg_lines = []
    line_no = None

    # Modified lines (removed + added)
    if removed_lines and added_lines:
        line_no = added_lines[0][0]
        msg_lines.append("clang-format expects formatting for these lines:")
        for (_, r) in removed_lines:
            if r.strip() == "":
                msg_lines.append("    - Extra blank line to be removed")
            else:
                msg_lines.append(f"    - {r}")
        msg_lines.append("→ to be replaced with:")
        for (_, a) in added_lines:
            if a.strip() == "":
                msg_lines.append("    + Blank line to be added")
            else:
                msg_lines.append(f"    + {a}")

    # Removed-only lines
    elif removed_lines:
        line_no = removed_lines[0][0]
        msg_lines.append("clang-format expects to remove the following lines:")
        for (_, r) in removed_lines:
            if r.strip() == "":
                msg_lines.append("    - Extra blank line to be removed")
            else:
                msg_lines.append(f"    - {r}")

    # Added-only lines
    elif added_lines:
        line_no = added_lines[0][0]
        msg_lines.append("clang-format expects to add the following lines:")
        for (_, a) in added_lines:
            if a.strip() == "":
                msg_lines.append("    + Blank line to be added")
            else:
                msg_lines.append(f"    + {a}")

    if msg_lines:
        comments.setdefault(current_file, []).append({
            'line': line_no,
            'message': "\n".join(msg_lines),
            'unresolved': True
        })


if __name__ == '__main__':
    main()
