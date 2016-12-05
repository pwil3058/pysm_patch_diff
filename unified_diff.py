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
import os
import re

from . import a_diff
from . import diffs
from . import diffstat
from . import pd_utils

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

DEBUG = False

_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])


class UnifiedDiffHunk(pd_utils.TextLines):
    """Class to encapsulate a single unified diff hunk
    """
    def __init__(self, lines, before, after):
        pd_utils.TextLines.__init__(self, lines)
        self.before = before
        self.after = after

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
                repl_line = diffs._trim_trailing_ws(self.lines[index])
                if len(repl_line) != len(self.lines[index]):
                    bad_lines.append(str(self.after.start + after_count - 1))
                    if fix:
                        self.lines[index] = repl_line
            elif self.lines[index].startswith(" "):
                after_count += 1
            elif DEBUG and not self.lines[index].startswith("-"):
                raise Bug("Unexpected end of unified diff hunk.")
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
                raise Bug("Unexpected end of unified diff hunk.")
        return stats

    def fix_trailing_whitespace(self):
        """Fix any lines that would introduce trailing white space when
        the chunk is applied and return a list of the changed lines
        """
        return self._process_tws(fix=True)

    def report_trailing_whitespace(self):
        """Return a list of lines that will introduce tailing white
        space when the chunk is applied
        """
        return self._process_tws(fix=False)

    def _iter_lines(self, skip_if_starts_with):
        """Iterate over lines skipping lines as directed
        """
        index = 1
        while index < len(self.lines):
            if not self.lines[index].startswith(skip_if_starts_with):
                if (index + 1) == len(self.lines) or not self.lines[index + 1].startswith("\\"):
                    yield self.lines[index][1:]
                else:
                    yield self.lines[index][1:].rstrip(os.linesep + "\n")
            index += 1
            if index < len(self.lines) and self.lines[index].startswith("\\"):
                index += 1

    def iter_before_lines(self):
        """Iterate over the lines in the "before" component of this hunk
        """
        return (line for line in self._iter_lines("+"))

    def iter_after_lines(self):
        """Iterate over the lines in the "after" component of this hunk
        """
        return (line for line in self._iter_lines("-"))

    def get_before_lines_list(self):
        """Get the list of lines in the "before" component of this hunk
        """
        return list(self.iter_before_lines())

    def get_after_lines_list(self):
        """Get the list of lines in the "after" component of this hunk
        """
        return list(self.iter_after_lines())


class UnifiedDiff(diffs.Diff):
    """Class to encapsulate a unified diff
    """
    diff_type = "unified"
    BEFORE_FILE_CRE = re.compile(r"^--- ({0})(\s+{1})?(.*)$".format(pd_utils.PATH_RE_STR, diffs._EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile(r"^\+\+\+ ({0})(\s+{1})?(.*)$".format(pd_utils.PATH_RE_STR, diffs._EITHER_TS_RE_STR))
    HUNK_DATA_CRE = re.compile(r"^@@\s+-(\d+)(,(\d+))?\s+\+(\d+)(,(\d+))?\s+@@\s*(.*)$")

    @staticmethod
    def get_before_file_data_at(lines, index):
        return diffs.Diff._get_file_data_at(UnifiedDiff.BEFORE_FILE_CRE, lines, index)

    @staticmethod
    def get_after_file_data_at(lines, index):
        return diffs.Diff._get_file_data_at(UnifiedDiff.AFTER_FILE_CRE, lines, index)

    @staticmethod
    def get_hunk_at(lines, index):
        match = UnifiedDiff.HUNK_DATA_CRE.match(lines[index])
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
                    raise ParseError(_("Unexpected end of unified diff hunk."), index)
                index += 1
            if index < len(lines) and lines[index].startswith("\\"):
                index += 1
        except IndexError:
            raise ParseError(_("Unexpected end of patch text."))
        before_chunk = _CHUNK(int(match.group(1)), before_length)
        after_chunk = _CHUNK(int(match.group(4)), after_length)
        return (UnifiedDiffHunk(lines[start_index:index], before_chunk, after_chunk), index)

    def __init__(self, lines, file_data, hunks):
        diffs.Diff.__init__(self, lines, file_data, hunks)

    def apply_to_lines(self, lines):
        """Apply this diff to the given "lines" and return the resulting lines.
        """
        return a_diff.AbstractDiff(self.hunks).apply_forwards(lines)

    def apply_to_file(self, file_path, err_file_path=None):
        from ..bab import CmdResult
        try:
            with open(file_path, "r") as f_obj:
                text = f_obj.read()
        except FileNotFoundError:
            text = ""
        adiff = a_diff.AbstractDiff(self.hunks)
        lines = text.splitlines(True)
        if adiff.first_mismatch_before(lines) == -1:
            new_text = "".join(adiff.apply_forwards(lines))
            ecode = CmdResult.OK
            stderr = ""
        else:
            err_file_path = err_file_path if err_file_path else file_path
            ecode, new_text, stderr = pd_utils.apply_diff_to_text_using_patch(text, self, err_file_path)
        if not new_text and self.file_data.after.path == "/dev/null":
            os.remove(file_path)
        else:
            with open(file_path, "w") as f_obj:
                f_obj.write(new_text)
        return CmdResult(ecode, "", stderr)
