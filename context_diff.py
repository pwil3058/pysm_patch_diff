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

"""Create, parse and apply "context" format diffs"""

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

# Useful named tuples to make code clearer
_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])
_HUNK = collections.namedtuple("_HUNK", ["offset", "start", "length", "numlines"])


class ContextDiffHunk(t_diff.TextDiffHunk):
    """Class to encapsulate a single context diff hunk
    """
    LEN_LINE_PREFIX = 2
    def _process_tws(self, fix=False):
        """If "fix" is True remove any trailing white space from
        changed lines and return a list of lines that were fixed
        otherwise return a list of changed lines that have tailing
        white space
        """
        bad_lines = list()
        for index in range(self.after.offset + 1, self.after.offset + self.after.numlines):
            if self.lines[index].startswith("+ ") or self.lines[index].startswith("! "):
                repl_line = self.lines[index][:2] + t_diff.trim_trailing_ws(self.lines[index][2:])
                after_count = index - (self.after.offset + 1)
                if len(repl_line) != len(self.lines[index]):
                    bad_lines.append(str(self.after.start + after_count))
                    if fix:
                        self.lines[index] = repl_line
            elif DEBUG and not self.lines[index].startswith("  "):
                raise t_diff.Bug("Unexpected end of context diff hunk.")
        return bad_lines

    def get_diffstat_stats(self):
        """Return the "diffstat" statistics for this chunk
        """
        stats = diffstat.DiffStats()
        for index in range(self.before.offset + 1, self.before.offset + self.before.numlines):
            if self.lines[index].startswith("- "):
                stats.incr("deleted")
            elif self.lines[index].startswith("! "):
                stats.incr("modified")
            elif DEBUG and not self.lines[index].startswith("  "):
                raise t_diff.Bug("Unexpected end of context diff \"before\" hunk.")
        for index in range(self.after.offset + 1, self.after.offset + self.after.numlines):
            if self.lines[index].startswith("+ "):
                stats.incr("inserted")
            elif self.lines[index].startswith("! "):
                stats.incr("modified")
            elif DEBUG and not self.lines[index].startswith("  "):
                raise t_diff.Bug("Unexpected end of context diff \"after\" hunk.")
        return stats

    def iter_before_lines(self):
        """Iterate over the lines in the "before" component of this hunk
        """
        if self.before.numlines == 1:
            start = self.after.offset
            end = self.after.offset + self.after.numlines
            return (line for line in self._iter_lines(self.lines[start:end], "+"))
        else:
            start = self.before.offset
            end = self.before.offset + self.before.numlines
            return (line for line in self._iter_lines(self.lines[start:end]))

    def iter_after_lines(self):
        """Iterate over the lines in the "after" component of this hunk
        """
        start = self.after.offset
        end = self.after.offset + self.after.numlines
        return (line for line in self._iter_lines(self.lines[start:end]))


class ContextDiffParser(t_diff.TextDiffParser):
    """Class to parse "context" diffs
    """
    diff_format = "context"
    BEFORE_FILE_CRE = re.compile(r"^\*\*\* ({0})(\s+{1})?$".format(pd_utils.PATH_RE_STR, t_diff.EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile(r"^--- ({0})(\s+{1})?$".format(pd_utils.PATH_RE_STR, t_diff.EITHER_TS_RE_STR))
    HUNK_START_CRE = re.compile(r"^\*{15}\s*(.*)$")
    HUNK_BEFORE_CRE = re.compile(r"^\*\*\*\s+(\d+)(,(\d+))?\s+\*\*\*\*\s*(.*)$")
    HUNK_AFTER_CRE = re.compile(r"^---\s+(\d+)(,(\d+))?\s+----(.*)$")

    @staticmethod
    def _chunk(match):
        start = int(match.group(1))
        finish = int(match.group(3)) if match.group(3) is not None else start
        if start == 0 and finish == 0:
            length = 0
        else:
            length = finish - start + 1
        return _CHUNK(start, length)

    @staticmethod
    def _get_before_chunk_at(lines, index):
        """Extract the context diff "before" chunk from "lines" starting
        at "index"."""
        match = ContextDiffParser.HUNK_BEFORE_CRE.match(lines[index])
        if not match:
            return (None, index)
        return (ContextDiffParser._chunk(match), index + 1)

    @staticmethod
    def _get_after_chunk_at(lines, index):
        """Extract the context diff "after" chunk from "lines" starting
        at "index"."""
        match = ContextDiffParser.HUNK_AFTER_CRE.match(lines[index])
        if not match:
            return (None, index)
        return (ContextDiffParser._chunk(match), index + 1)

    @staticmethod
    def get_hunk_at(lines, index):
        if not ContextDiffParser.HUNK_START_CRE.match(lines[index]):
            return (None, index)
        start_index = index
        before_start_index = index + 1
        before_chunk, index = ContextDiffParser._get_before_chunk_at(lines, before_start_index)
        if not before_chunk:
            return (None, index)
        before_count = after_count = 0
        try:
            after_chunk = None
            while before_count < before_chunk.length:
                after_start_index = index
                after_chunk, index = ContextDiffParser._get_after_chunk_at(lines, index)
                if after_chunk is not None:
                    break
                before_count += 1
                index += 1
            if after_chunk is None:
                if lines[index].startswith(r"\ "):
                    before_count += 1
                    index += 1
                after_start_index = index
                after_chunk, index = ContextDiffParser._get_after_chunk_at(lines, index)
                if after_chunk is None:
                    raise t_diff.ParseError(_("Failed to find context diff \"after\" hunk."), index)
            while after_count < after_chunk.length:
                if not lines[index].startswith(("! ", "+ ", "  ")):
                    if after_count == 0:
                        break
                    raise t_diff.ParseError(_("Unexpected end of context diff hunk."), index)
                after_count += 1
                index += 1
            if index < len(lines) and lines[index].startswith(r"\ "):
                after_count += 1
                index += 1
        except IndexError:
            raise t_diff.ParseError(_("Unexpected end of patch text."))
        before_hunk = _HUNK(before_start_index - start_index,
                            before_chunk.start,
                            before_chunk.length,
                            after_start_index - before_start_index)
        after_hunk = _HUNK(after_start_index - start_index,
                           after_chunk.start,
                           after_chunk.length,
                           index - after_start_index)
        return (ContextDiffHunk(lines[start_index:index], before_hunk, after_hunk), index)


def get_diff_at(lines, index, raise_if_malformed):
    """If there is a valid context diff in "lines" starting at "index"
    extract and return it along with the index for the first line after
    the diff.
    """
    return ContextDiffParser.get_diff_at(lines, index, raise_if_malformed)


def parse_diff_lines(lines):
    """Parse list of lines and return a valid "context" diff or raise exception"""
    diff, index = ContextDiffParser.get_diff_at(lines, 0, raise_if_malformed=True)
    if not diff or index < len(lines):
        raise t_diff.ParseError(_("Not a valid \"context\" diff."), index)
    return diff


def parse_diff_text(text):
    """Parse text and return a valid "context" diff or raise exception"""
    return parse_diff_lines(text.splitlines(True))


def generate_diff_lines(before, after, num_context_lines=3):
    """Generate the text lines of a text diff from the provided
    before and after data using "context" diff format.
    """
    return t_diff.generate_diff_lines(difflib.context_diff, before, after, num_context_lines)


def generate_diff(before, after, num_context_lines=3):
    """Generate the text based diff from the provided
    before and after data.
    """
    diff_lines = generate_diff_lines(before, after, num_context_lines)
    return parse_diff_lines(diff_lines) if diff_lines else None
