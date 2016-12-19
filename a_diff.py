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

import sys

from collections import namedtuple

from ..bab import CmdResult

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


def lines_contains_sub_lines_at(lines, sub_lines, index):
    """Does "lines" contain "sub_lines" starting at "index"?
    """
    return lines[index:index + len(sub_lines)] == sub_lines


def find_first_sub_lines(lines, sub_lines, offset=0):
    """Find index of the first instance of "sub_lines" in "lines".
    Return None if not found.
    """
    for index in range(offset, len(lines) - len(sub_lines) + 1):
        if lines_contains_sub_lines_at(lines, sub_lines, index):
            return index
    return None


def find_last_sub_lines(lines, sub_lines, offset=0):
    """Find index of the last instance of "sub_lines" in "lines".
    Return None if not found.
    """
    for index in reversed(range(offset, len(lines) - len(sub_lines) + 1)):
        if lines_contains_sub_lines_at(lines, sub_lines, index):
            return index
    return None


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
    def matches_lines(self, lines, offset=0):
        """Do "lines" match this chunk?
        """
        return lines_contains_sub_lines_at(lines, self.lines, self.start_index + offset)

    def find_first_in_lines(self, lines):
        """Find first occurence of our lines in "lines"
        """
        return find_first_sub_lines(lines, self.lines)

    def find_last_in_lines(self, lines):
        """Find last occurence of our lines in "lines"
        """
        return find_last_sub_lines(lines, self.lines)


class AbstractHunk(namedtuple("AbstractHunk", ["before", "after", "pre_cntxt_len", "post_cntxt_len"])):
    """Class to encapsulate a single chunk of an abstract diff
    """
    def get_before_compromised_posn(self, lines, offset=0, fuzz_factor=2):
        """If it exists find the position in "lines" where this hunk will
        apply reducing context if/as necessary.  Return the position
        and any context reductions that were used.
        """
        for context_redn in range(min(fuzz_factor, max(self.pre_cntxt_len, self.post_cntxt_len)) + 1):
            pre_context_redn = min(context_redn, self.pre_cntxt_len)
            post_context_redn = min(context_redn, self.post_cntxt_len)
            fm = pre_context_redn if pre_context_redn else None
            to = -post_context_redn if post_context_redn else None
            start_index = find_first_sub_lines(lines, self.before.lines[fm:to], offset)
            if start_index is not None:
                return (start_index, pre_context_redn, post_context_redn)
        return (None, None, None)

class AbstractDiff:
    """Class to encapsulate an abstract diff as a list of abstract hunks.
    """
    def __init__(self, hunks):
        self._hunks = [hunk.get_abstract_diff_hunk() for hunk in hunks]

    def first_before_mismatch(self, lines, skipping=0, offset=0):
        """Find the fist chunk whose before hunk doesn't match "lines"
        skipping the given number of hunks at the start and applying
        the given offset
        """
        for index in range(skipping, len(self._hunks)):
            if not self._hunks[index].before.matches_lines(lines, offset):
                return index
        return None

    def first_after_mismatch(self, lines, skipping=0, offset=0):
        """Find the fist chunk whose before hunk doesn't match "lines"
        skipping the given number of hunks at the start and applying
        the given offset
        """
        for index in range(skipping, len(self._hunks)):
            if not self._hunks[index].after.matches_lines(lines, offset):
                return index
        return None

    def apply_forwards(self, lines, rctx=sys, repd_file_path=None):
        """Apply this diff to lines and return the result as a list of
        lines.
        """
        result = []
        lines_index = 0
        ecode = CmdResult.OK
        num_hunks_done = 0
        current_offset = 0
        while num_hunks_done < len(self._hunks):
            first_mismatch = self.first_before_mismatch(lines, num_hunks_done, current_offset)
            for hunk in self._hunks[num_hunks_done:first_mismatch]:
                result += lines[lines_index:hunk.before.start_index + current_offset]
                result += hunk.after.lines
                lines_index = hunk.before.start_index + current_offset + len(hunk.before.lines)
                num_hunks_done += 1
            if first_mismatch is None:
                break
            m_hunk = self._hunks[first_mismatch]
            alt_start_index, pre_context_redn, post_context_redn = m_hunk.get_before_compromised_posn(lines, lines_index)
            if alt_start_index is None:
                # TODO: handle case where hunk is already applied
                ecode = max(ecode, CmdResult.ERROR)
                before_hlen = len(m_hunk.before.lines) - m_hunk.post_cntxt_len
                if (m_hunk.before.start_index + current_offset + before_hlen) > len(lines):
                    # We've run out of lines to patch
                    rctx.stderr.write(_("{}: Unexpected end of file: ").format(repd_file_path))
                    if (len(self._hunks) - num_hunks_done) > 1:
                        rctx.stderr.write(_("Hunks #{}-{} could NOT be applied.\n").format(num_hunks_done+1, len(self._hunks)))
                    else:
                        rctx.stderr.write(_("Hunk #{} could NOT be applied.\n").format(num_hunks_done+1))
                    break
                result += lines[lines_index:m_hunk.before.start_index + current_offset]
                lines_index = m_hunk.before.start_index + current_offset
                result += ["<<<<<<<\n"]
                l1 = len(result)
                result += lines[lines_index:lines_index + before_hlen]
                lines_index += before_hlen
                result += ["=======\n"]
                result += m_hunk.after.lines[:-m_hunk.post_cntxt_len if m_hunk.post_cntxt_len else None]
                result += [">>>>>>>\n"]
                l2 = len(result)
                rctx.stderr.write(_("{}: Hunk #{} NOT MERGED at {}-{}.\n").format(repd_file_path, first_mismatch + 1, l1, l2))
            else:
                ecode = max(ecode, CmdResult.WARNING)
                fm = pre_context_redn if pre_context_redn else None
                to = -post_context_redn if post_context_redn else None
                result += lines[lines_index:alt_start_index]
                result += m_hunk.after.lines[fm:to]
                lines_index = alt_start_index + len(m_hunk.before.lines) - pre_context_redn - post_context_redn
                current_offset = alt_start_index - m_hunk.before.start_index - pre_context_redn
                nnl = len(m_hunk.after.lines) - m_hunk.pre_cntxt_len - m_hunk.post_cntxt_len
                sp = len(result) - nnl - (m_hunk.post_cntxt_len - post_context_redn) + 1
                if nnl > 1:
                    rctx.stderr.write(_("{}: Hunk #{} merged at {}-{}.\n").format(repd_file_path, first_mismatch + 1, sp, sp + nnl - 1))
                else:
                    rctx.stderr.write(_("{}: Hunk #{} merged at {}.\n").format(repd_file_path, first_mismatch + 1, sp))
            num_hunks_done += 1
        result += lines[lines_index:]
        return (ecode, result)
