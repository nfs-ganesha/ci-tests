#!/usr/bin/env python

import re
import sys
import json

def main(fp=sys.stdin):
    """Convert checkpatch output into a gerrit-compatible JSON"""
    comments = {}
    while True:
        line = fp.readline()
        fileline = fp.readline()
        if not fileline.strip():
            break
        while True:
            newline = fp.readline()
            if not newline.strip():
                break
            line += newline

        match = re.search('FILE: (.*):([0-9]*):', fileline)
        if match is not None:
            filename = match.group(1)
            lineno   = match.group(2)
            report = { 'line': lineno, 'message': line.strip() }
        else:
            filename = '/COMMIT_MSG'
            report = { 'message': line.strip() }

        file_comments = comments.setdefault(filename, [])
        file_comments.append(report)

    if comments:
        output = {
            'comments': comments,
            'message': 'Checkpatch %s' % line.strip()
        }
    else:
        output = {
            'message': 'Checkpatch OK',
            'notify': 'NONE'
        }
    print json.dumps(output)

if __name__ == '__main__':
    main()
