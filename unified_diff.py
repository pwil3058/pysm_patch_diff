#  Copyright 2016 Peter Williams <pwil3058@gmail.com>
#
# This software is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License only.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software; if not, write to:
#  The Free Software Foundation, Inc., 51 Franklin Street,
#  Fifth Floor, Boston, MA 02110-1301 USA

"""Create, parse and apply "unified" format diffs"""

import collections
import difflib
import os
import re

from . import t_diff
from . import diffstat
from . import pd_utils

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

DEBUG = False

_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])


class UnifiedDiffHunk(t_diff.TextDiffHunk):
    """Class to encapsulate a single unified diff hunk
    """
    def _process_tws(self, fix=False):
        """If "fix" is True remove any trailing white space from
        changed lines and return a list of lines that were fixed
        otherwise return a list of changed lines that have tailing
        white space
        """
        bad_lines = list()
        after_count = 0
        for index in range(len(self.lines)):
            if self.lines[index].startswith("+"):
                after_count += 1
                repl_line = t_diff.trim_trailing_ws(self.lines[index])
                if len(repl_line) != len(self.lines[index]):
                    bad_lines.append(str(self.after.start + after_count - 1))
                    if fix:
                        self.lines[index] = repl_line
            elif self.lines[index].startswith(" "):
                after_count += 1
            elif DEBUG and not self.lines[index].startswith("-"):
                raise t_diff.Bug("Unexpected end of unified diff hunk.")
        return bad_lines

    def get_diffstat_stats(self):
        """Return the "diffstat" statistics for this chunk
        """
        stats = diffstat.DiffStats()
        for index in range(len(self.lines)):
            if self.lines[index].startswith("-"):
                stats.incr("deleted")
            elif self.lines[index].startswith("+"):
                stats.incr("inserted")
            elif DEBUG and not self.lines[index].startswith(" "):
                raise t_diff.Bug("Unexpected end of unified diff hunk.")
        return stats

    def iter_before_lines(self):
        """Iterate over the lines in the "before" component of this hunk
        """
        return (line for line in self._iter_lines(self.lines, "+"))

    def iter_after_lines(self):
        """Iterate over the lines in the "after" component of this hunk
        """
        return (line for line in self._iter_lines(self.lines, "-"))


class UnifiedDiffParser(t_diff.TextDiffParser):
    """Class to parse "unified" diffs
    """
    diff_format = "unified"
    BEFORE_FILE_CRE = re.compile(r"^--- ({0})(\s+{1})?(.*)$".format(pd_utils.PATH_RE_STR, t_diff.EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile(r"^\+\+\+ ({0})(\s+{1})?(.*)$".format(pd_utils.PATH_RE_STR, t_diff.EITHER_TS_RE_STR))
    HUNK_DATA_CRE = re.compile(r"^@@\s+-(\d+)(,(\d+))?\s+\+(\d+)(,(\d+))?\s+@@\s*(.*)$")

    @staticmethod
    def get_hunk_at(lines, index):
        match = UnifiedDiffParser.HUNK_DATA_CRE.match(lines[index])
        if not match:
            return (None, index)
        start_index = index
        before_length = int(match.group(3)) if match.group(3) is not None else 1
        after_length = int(match.group(6)) if match.group(6) is not None else 1
        index += 1
        before_count = after_count = 0
        try:
            while before_count < before_length or after_count < after_length:
                if lines[index].startswith("-"):
                    before_count += 1
                elif lines[index].startswith("+"):
                    after_count += 1
                elif lines[index].startswith(" "):
                    before_count += 1
                    after_count += 1
                elif not lines[index].startswith("\\"):
                    raise t_diff.ParseError(_("Unexpected end of unified diff hunk."), index)
                index += 1
            if index < len(lines) and lines[index].startswith("\\"):
                index += 1
        except IndexError:
            raise t_diff.ParseError(_("Unexpected end of patch text."))
        before_chunk = _CHUNK(int(match.group(1)), before_length)
        after_chunk = _CHUNK(int(match.group(4)), after_length)
        return (UnifiedDiffHunk(lines[start_index:index], before_chunk, after_chunk), index)


def get_diff_at(lines, index, raise_if_malformed):
    """If there is a valid unified diff in "lines" starting at "index"
    extract and return it along with the index for the first line after
    the diff.
    """
    return UnifiedDiffParser.get_diff_at(lines, index, raise_if_malformed)


def parse_diff_lines(lines):
    """Parse list of lines and return a valid "unified" diff or raise exception"""
    diff, index = UnifiedDiffParser.get_diff_at(lines, 0, raise_if_malformed=True)
    if not diff or index < len(lines):
        raise t_diff.ParseError(_("Not a valid \"unified\" diff."), index)
    return diff


def parse_diff_text(text):
    """Parse text and return a valid "unified" diff or raise exception"""
    return parse_diff_lines(text.splitlines(True))


def generate_diff_lines(before, after, num_context_lines=3):
    """Generate the text lines of a text diff from the provided
    before and after data using "unified" diff format.
    """
    return t_diff.generate_diff_lines(difflib.unified_diff, before, after, num_context_lines)


def generate_diff(before, after, num_context_lines=3):
    """Generate the text based diff from the provided
    before and after data.
    """
    diff_lines = generate_diff_lines(before, after, num_context_lines)
    return parse_diff_lines(diff_lines) if diff_lines else None
