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

"""Module to manage various type of "diff" instances
"""

import collections
import difflib
import os
import re
import sys
import zlib

from . import a_diff
from . import diffstat
from . import gitbase85
from . import gitdelta
from . import pd_utils


__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


DEBUG = False


class ParseError(Exception):
    """Exception to signal parsing error
    """
    def __init__(self, message, lineno=None):
        Exception.__init__(self)
        self.message = message
        self.lineno = lineno


class DataError(ParseError):
    """Exception to signal git binary patch data error
    """
    pass


class Bug(Exception):
    """Exception to signal a bug
    """
    pass


# Useful named tuples to make code clearer
_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])
_HUNK = collections.namedtuple("_HUNK", ["offset", "start", "length", "numlines"])
_FILE_AND_TS = collections.namedtuple("_FILE_AND_TS", ["path", "timestamp"])

# Useful strings for including in regular expressions
_TIMESTAMP_RE_STR = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{9})? [-+]{1}\d{4}"
_ALT_TIMESTAMP_RE_STR = r"[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4} [-+]{1}\d{4}"
_EITHER_TS_RE_STR = "(%s|%s)" % (_TIMESTAMP_RE_STR, _ALT_TIMESTAMP_RE_STR)


# Diff line generator functions
_DLGF = {"unified": difflib.unified_diff, "context": difflib.context_diff}


def _trim_trailing_ws(line):
    """Return the given line with any trailing white space removed
    """
    return re.sub(r"[ \t]+$", "", line)


def _to_text_lines(content):
    """Convert "content" to a list if text lines
    """
    if isinstance(content, (list, tuple)):
        return content
    elif isinstance(content, str):
        return content.splitlines(True)
    else:
        return content.decode().splitlines(True)


class Diff:
    """A base class for all classes that encapsulate diffs.
    """
    diff_type = None

    @staticmethod
    def _get_file_data_at(cre, lines, index):
        match = cre.match(lines[index])
        if not match:
            return (None, index)
        file_path = match.group(2) if match.group(2) else match.group(3)
        return (_FILE_AND_TS(file_path, match.group(4)), index + 1)

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
        return (cls(lines[start_index:start_index + 2], file_data, hunks), index)

    @classmethod
    def parse_lines(cls, lines):
        """Parse list of lines and return a valid Diff or raise exception"""
        diff, index = cls.get_diff_at(lines, 0, raise_if_malformed=True)
        if not diff or index < len(lines):
            raise ParseError(_("Not a valid \"{}\" diff.").format(cls.diff_type), index)
        return diff

    @classmethod
    def parse_text(cls, text):
        """Parse text and return a valid DiffPlus or raise exception"""
        return cls.parse_lines(text.splitlines(True))

    @classmethod
    def generate_diff_lines(cls, before, after, num_context_lines=3):
        """Generate the text lines of a text diff from the provided
        before and after data.
        """
        before_lines = _to_text_lines(before.content)
        after_lines = _to_text_lines(after.content)
        diff_lines = []
        dlgf = _DLGF[cls.diff_type]
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

    @classmethod
    def generate_diff(cls, before, after, num_context_lines=3):
        """Generate the text based diff from the provided
        before and after data.
        """
        diff_lines = cls.generate_diff_lines(before, after, num_context_lines)
        return cls.parse_lines(diff_lines) if diff_lines else None

    def __init__(self, lines, file_data, hunks):
        self.header = pd_utils.TextLines(lines)
        self.file_data = file_data
        self.hunks = list() if hunks is None else hunks

    def __str__(self):
        return str(self.header) + "".join([str(hunk) for hunk in self.hunks])

    def iter_lines(self):
        """Iterate over the lines in this diff
        """
        for line in self.header:
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


def get_diff_at(lines, index, raise_if_malformed):
    """If there is a valid unified, context or git binary diff in
    "lines" starting at "index" extract and return it along with the
    index for the first line after the diff.
    """
    from . import context_diff
    from . import git_binary_diff
    from . import unified_diff
    # NB. these are ordered by likelihood of being encountered
    for diff_type in [unified_diff.UnifiedDiff, git_binary_diff.GitBinaryDiff, context_diff.ContextDiff]:
        diff, next_index = diff_type.get_diff_at(lines, index, raise_if_malformed)
        if diff is not None:
            return (diff, next_index)
    return (None, index)


def diff_parse_lines(lines):
    """Parse list of lines and return a valid Diff or raise exception"""
    diff, index = get_diff_at(lines, 0, raise_if_malformed=True)
    if not diff or index < len(lines):
        raise ParseError(_("Not a valid diff."))
    return diff


def diff_parse_text(text):
    """Parse text and return a valid DiffPlus or raise exception"""
    return diff_parse_lines(text.splitlines(True))


def _TEMP_use_patch_on_text(text, diff, err_file_path):
    import tempfile
    from ..bab import runext
    from ..bab import CmdResult
    tmp_file_path = None
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f_obj:
        tmp_file_path = f_obj.name
        f_obj.write(text)
    patch_cmd = ["patch", "--merge", "--force", "-p1", "--batch", tmp_file_path]
    result = runext.run_cmd(patch_cmd, input_text=str(diff).encode())
    try:
        with open(tmp_file_path, "r") as f_obj:
            text = f_obj.read()
        os.remove(tmp_file_path)
    except FileNotFoundError:
        text = ""
    # move all but the first line of stdout to stderr
    # drop first line so that reports can be made relative to subdir
    olines = result.stdout.splitlines(True)
    prefix = "{0}: ".format(err_file_path)
    # Put file name at start of line so they make sense on their own
    if len(olines) > 1:
        stderr = prefix + prefix.join(olines[1:] + result.stderr.splitlines(True))
    elif result.stderr:
        stderr = prefix + prefix.join(result.stderr.splitlines(True))
    else:
        stderr = ""
    return CmdResult(result.ecode, text, stderr)
