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

"""Module to provide functionality common to text diffs
"""

import collections
import difflib
import os
import re

from . import a_diff
from . import diffstat
from . import pd_utils


__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


class ParseError(Exception):
    """Exception to signal parsing error
    """
    def __init__(self, message, lineno=None):
        Exception.__init__(self)
        self.message = message
        self.lineno = lineno


class Bug(Exception):
    """Exception to signal a bug
    """
    pass


# Useful named tuples to make code clearer
StartAndLength = collections.namedtuple("StartAndLength", ["start", "length"])
PathAndTimestamp = collections.namedtuple("PathAndTimestamp", ["path", "timestamp"])

# Useful strings for including in regular expressions
_TIMESTAMP_RE_STR = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{9})? [-+]{1}\d{4}"
_ALT_TIMESTAMP_RE_STR = r"[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4} [-+]{1}\d{4}"
EITHER_TS_RE_STR = "(%s|%s)" % (_TIMESTAMP_RE_STR, _ALT_TIMESTAMP_RE_STR)


def trim_trailing_ws(line):
    """Return the given line with any trailing white space removed
    """
    return re.sub(r"[ \t]+$", "", line)


def to_text_lines(content):
    """Convert "content" to a list of text lines
    """
    if isinstance(content, (list, tuple)):
        return content
    elif isinstance(content, str):
        return content.splitlines(True)
    else:
        return content.decode().splitlines(True)


class TextDiffParser:
    """A base class for all classes that encapsulate diffs.
    """
    diff_format = None

    @staticmethod
    def _get_file_data_at(cre, lines, index):
        match = cre.match(lines[index])
        if not match:
            return (None, index)
        file_path = match.group(2) if match.group(2) else match.group(3)
        return (PathAndTimestamp(file_path, match.group(4)), index + 1)

    @staticmethod
    def get_before_file_data_at(lines, index):
        """Get data for the "before" file the diff applies to
        """
        print(lines[index:])
        return (NotImplemented, index)

    @staticmethod
    def get_after_file_data_at(lines, index):
        """Get data for the "after" file the diff applies to
        """
        print(lines[index:])
        return (NotImplemented, index)

    @staticmethod
    def get_hunk_at(lines, index):
        """Extract a diff hunk from lines starting at "index"
        """
        print(lines[index:])
        return (NotImplemented, index)

    @classmethod
    def get_diff_at(cls, lines, start_index, raise_if_malformed=False):
        """If there is a valid "cls" diff in "lines" starting at
        "index" extract and return it along with the index for the
        first line after the diff.
        """
        if len(lines) - start_index < 2:
            return (None, start_index)
        hunks = list()
        index = start_index
        before_file_data, index = cls.get_before_file_data_at(lines, index)
        if not before_file_data:
            return (None, start_index)
        after_file_data, index = cls.get_after_file_data_at(lines, index)
        if not after_file_data:
            if raise_if_malformed:
                raise ParseError(_("Missing unified diff after file data."), index)
            else:
                return (None, start_index)
        while index < len(lines):
            hunk, index = cls.get_hunk_at(lines, index)
            if hunk is None:
                break
            hunks.append(hunk)
        if len(hunks) == 0:
            if raise_if_malformed:
                raise ParseError(_("Expected unified diff hunks not found."), index)
            else:
                return (None, start_index)
        file_data = pd_utils.BEFORE_AFTER(before_file_data, after_file_data)
        return (TextDiff(cls.diff_format, lines[start_index:start_index + 2], file_data, hunks), index)

    @classmethod
    def parse_lines(cls, lines):
        """Parse list of lines and return a valid TextDiff or raise exception"""
        diff, index = cls.get_diff_at(lines, 0, raise_if_malformed=True)
        if not diff or index < len(lines):
            raise ParseError(_("Not a valid \"{}\" diff.").format(cls.diff_format), index)
        return diff

    @classmethod
    def parse_text(cls, text):
        """Parse text and return a valid DiffPlus or raise exception"""
        return cls.parse_lines(text.splitlines(True))


def generate_diff_lines(dlgf, before, after, num_context_lines=3):
    """Generate the text lines of a text diff from the provided
    before and after data using "dlgf" function to generate raw
    lines.
    """
    before_lines = to_text_lines(before.content)
    after_lines = to_text_lines(after.content)
    diff_lines = []
    for diff_line in dlgf(before_lines, after_lines,
                          fromfile=before.label, tofile=after.label,
                          fromfiledate=before.timestamp, tofiledate=after.timestamp,
                          n=num_context_lines):
        # NB: this can occur before the final line so we have to check all lines
        if diff_line.endswith((os.linesep, "\n")):
            diff_lines.append(diff_line)
        else:
            diff_lines.append(diff_line + "\n")
            diff_lines.append("\\ No newline at end of file\n")
    return diff_lines


class TextDiff:
    """A class to encapsulate "text" diffs regardless of format.
    """
    def __init__(self, diff_format, header_lines, file_data, hunks):
        self.diff_format = diff_format
        self.header_lines = pd_utils.TextLines(header_lines)
        self.file_data = file_data
        self.hunks = list() if hunks is None else hunks

    @property
    def diff_type(self):
        return self.diff_format

    def __str__(self):
        return str(self.header_lines) + "".join([str(hunk) for hunk in self.hunks])

    def iter_lines(self):
        """Iterate over the lines in this diff
        """
        for line in self.header_lines:
            yield line
        for hunk in self.hunks:
            for line in hunk:
                yield line

    def fix_trailing_whitespace(self):
        """Fix any lines that would introduce trailing white space when
        the diff is applied and return a list of the changed lines
        """
        bad_lines = list()
        for hunk in self.hunks:
            bad_lines += hunk.fix_trailing_whitespace()
        return bad_lines

    def report_trailing_whitespace(self):
        """Return a list of lines that will introduce tailing white
        space when the diff is applied
        """
        bad_lines = list()
        for hunk in self.hunks:
            bad_lines += hunk.report_trailing_whitespace()
        return bad_lines

    def get_diffstat_stats(self):
        """Return the "diffstat" statistics for this diff
        """
        stats = diffstat.DiffStats()
        for hunk in self.hunks:
            stats += hunk.get_diffstat_stats()
        return stats

    def get_file_path(self, strip_level=0):
        """Get the file path that this diff applies to
        """
        strip = pd_utils.gen_strip_level_function(strip_level)
        if isinstance(self.file_data, str):
            return strip(self.file_data)
        elif isinstance(self.file_data, pd_utils.BEFORE_AFTER):
            return pd_utils.file_path_fm_pair(self.file_data, strip)
        else:
            return None

    def get_file_path_plus(self, strip_level=0):
        """Get the file path that this diff applies to along with any
        extra relevant data
        """
        strip = pd_utils.gen_strip_level_function(strip_level)
        if isinstance(self.file_data, str):
            return pd_utils.FilePathPlus(path=strip(self.file_data), status=None, expath=None)
        elif isinstance(self.file_data, pd_utils.BEFORE_AFTER):
            return pd_utils.FilePathPlus.fm_pair(self.file_data, strip)
        else:
            return None

    def get_outcome(self):
        """Get the "outcome" of applying this diff
        """
        if isinstance(self.file_data, pd_utils.BEFORE_AFTER):
            return pd_utils.file_outcome_fm_pair(self.file_data)
        return None

    def apply_to_lines(self, lines):
        """Apply this diff to the given "lines" and return the resulting lines.
        """
        return a_diff.AbstractDiff(self.hunks).apply_forwards(lines)

    def apply_to_file(self, file_path, err_file_path=None):
        """Apply this diff to the given file
        """
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
