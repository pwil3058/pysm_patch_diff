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

"""Abstract diff representation to facilitate application of diffs
"""

from collections import namedtuple

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


def lines_contains_sub_lines_at(lines, sub_lines, index):
    """Does "lines" contain "sub_lines" starting at "index"?
    """
    return lines[index:index + len(sub_lines)] == sub_lines


def find_first_sub_lines(lines, sub_lines):
    """Find index of the first instance of "sub_lines" in "lines".
    Return -1 if not found.
    """
    for index in range(len(lines) - len(sub_lines) + 1):
        if lines_contains_sub_lines_at(lines, sub_lines, index):
            return index
    return -1


def find_last_sub_lines(lines, sub_lines):
    """Find index of the last instance of "sub_lines" in "lines".
    Return -1 if not found.
    """
    for index in reversed(range(len(lines) - len(sub_lines) + 1)):
        if lines_contains_sub_lines_at(lines, sub_lines, index):
            return index
    return -1


def first_inequality_fm_head(lines1, lines2):
    """Find the first index from their fronts that lines1 and lines2
    disagree.
    """
    index = 0
    while index < min(len(lines1), len(lines2)):
        if lines1[index] != lines2[index]:
            return index
        index += 1
    return index


def first_inequality_fm_tail(lines1, lines2):
    """Find the first index from their tails that lines1 and lines2
    disagree.
    """
    index = -1
    while index >= -min(len(lines1), len(lines2)):
        if lines1[index] != lines2[index]:
            return index
        index -= 1
    return index


class AbstractChunk(namedtuple("AbstractChunk", ["start_index", "lines"])):
    """Class to encapsulate before/after components of AbstractHunk
    """
    def matches_lines(self, lines):
        """Do "lines" match this chunk?
        """
        return lines_contains_sub_lines_at(lines, self.lines, self.index)

    def find_first_in_lines(self, lines):
        """Find first occurence of our lines in "lines"
        """
        return find_first_sub_lines(lines, self.lines)

    def find_last_in_lines(self, lines):
        """Find last occurence of our lines in "lines"
        """
        return find_last_sub_lines(lines, self.lines)


class AbstractHunk(namedtuple("AbstractHunk", ["before", "after"])):
    """Class to encapsulate a single chunk of an abstract diff
    """
    @property
    def pre_cntxt_len(self):
        """Number of lines of context at start of this hunk
        """
        return first_inequality_fm_head(self.before.lines, self.after.lines)

    @property
    def post_cntxt_len(self):
        """Number of lines of context at end of this hunk
        """
        return abs(first_inequality_fm_tail(self.before.lines, self.after.lines)) - 1


class AbstractDiff:
    """Class to encapsulate an abstract diff as a list of abstract hunks.
    """
    def __init__(self, hunks):
        self._hunks = list()
        for hunk in hunks:
            before = AbstractChunk(hunk.before.start, hunk.get_before_lines_list())
            after = AbstractChunk(hunk.after.start, hunk.get_after_lines_list())
            self._hunks.append(AbstractHunk(before, after))

    def first_mismatch_before(self, lines):
        """Find the fist chunk whose before hunk doesn't match "lines"
        """
        for index in range(len(self._hunks)):
            if not self._hunks[index].before.matches_lines(lines):
                return index
        return -1

    def first_mismatch_after(self, lines):
        """Find the fist chunk whose before hunk doesn't match "lines"
        """
        for index in range(len(self._hunks)):
            if not self._hunks[index].after.matches_lines(lines):
                return index
        return -1

    def apply_forwards(self, lines):
        """Apply this diff to lines and return the result as a list of
        lines.
        """
        assert self.first_mismatch_before(lines) == -1
        result = []
        index = 0
        for hunk in self._hunks:
            result += lines[index:hunk.before.start_index]
            result += hunk.after.lines
            index += len(hunk.before.lines)
        assert self.first_mismatch_after(result) == -1
        return result
