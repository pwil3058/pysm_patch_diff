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
import re

from . import diffstat
from . import gitbase85

from .pd_utils import TextLines as _Lines
from .pd_utils import PATH_RE_STR as _PATH_RE_STR
from .pd_utils import BEFORE_AFTER
from .pd_utils import gen_strip_level_function
from .pd_utils import file_path_fm_pair as _file_path_fm_pair
from .pd_utils import FilePathPlus


__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


DEBUG = False


class ParseError(Exception):
    def __init__(self, message, lineno=None):
        self.message = message
        self.lineno = lineno


class DataError(ParseError):
    pass


class Bug(Exception):
    pass


# Useful named tuples to make code clearer
_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])
_HUNK = collections.namedtuple("_HUNK", ["offset", "start", "length", "numlines"])
_FILE_AND_TS = collections.namedtuple("_FILE_AND_TS", ["path", "timestamp"])

# Useful strings for including in regular expressions
_TIMESTAMP_RE_STR = "\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{9})? [-+]{1}\d{4}"
_ALT_TIMESTAMP_RE_STR = "[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4} [-+]{1}\d{4}"
_EITHER_TS_RE_STR = "(%s|%s)" % (_TIMESTAMP_RE_STR, _ALT_TIMESTAMP_RE_STR)


def _trim_trailing_ws(line):
    """Return the given line with any trailing white space removed"""
    return re.sub("[ \t]+$", "", line)


class Diff:
    @staticmethod
    def _get_file_data_at(cre, lines, index):
        match = cre.match(lines[index])
        if not match:
            return (None, index)
        filepath = match.group(2) if match.group(2) else match.group(3)
        return (_FILE_AND_TS(filepath, match.group(4)), index + 1)

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
        return (cls(lines[start_index:start_index + 2], BEFORE_AFTER(before_file_data, after_file_data), hunks), index)

    def __init__(self, diff_type, lines, file_data, hunks):
        self.header = _Lines(lines)
        self.diff_type = diff_type
        self.file_data = file_data
        self.hunks = list() if hunks is None else hunks

    def __str__(self):
        return str(self.header) + "".join([str(hunk) for hunk in self.hunks])

    def iter_lines(self):
        for line in self.header:
            yield line
        for hunk in self.hunks:
            for line in hunk:
                yield line

    def fix_trailing_whitespace(self):
        bad_lines = list()
        for hunk in self.hunks:
            bad_lines += hunk.fix_trailing_whitespace()
        return bad_lines

    def report_trailing_whitespace(self):
        bad_lines = list()
        for hunk in self.hunks:
            bad_lines += hunk.report_trailing_whitespace()
        return bad_lines

    def get_diffstat_stats(self):
        stats = diffstat.DiffStats()
        for hunk in self.hunks:
            stats += hunk.get_diffstat_stats()
        return stats

    def get_file_path(self, strip_level=0):
        strip = gen_strip_level_function(strip_level)
        if isinstance(self.file_data, str):
            return strip(self.file_data)
        elif isinstance(self.file_data, BEFORE_AFTER):
            return _file_path_fm_pair(self.file_data, strip)
        else:
            return None

    def get_file_path_plus(self, strip_level=0):
        strip = gen_strip_level_function(strip_level)
        if isinstance(self.file_data, str):
            return FilePathPlus(path=strip(self.file_data), status=None, expath=None)
        elif isinstance(self.file_data, BEFORE_AFTER):
            return FilePathPlus.fm_pair(self.file_data, strip)
        else:
            return None

    def get_outcome(self):
        if isinstance(self.file_data, BEFORE_AFTER):
            return _file_outcome_fm_pair(self.file_data)
        return None


class UnifiedDiffHunk(_Lines):
    def __init__(self, lines, before, after):
        _Lines.__init__(self, lines)
        self.before = before
        self.after = after

    def _process_tws(self, fix=False):
        bad_lines = list()
        after_count = 0
        for index in range(len(self.lines)):
            if self.lines[index].startswith("+"):
                after_count += 1
                repl_line = _trim_trailing_ws(self.lines[index])
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
        return self._process_tws(fix=True)

    def report_trailing_whitespace(self):
        return self._process_tws(fix=False)


class UnifiedDiff(Diff):
    BEFORE_FILE_CRE = re.compile("^--- ({0})(\s+{1})?(.*)$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile("^\+\+\+ ({0})(\s+{1})?(.*)$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    HUNK_DATA_CRE = re.compile("^@@\s+-(\d+)(,(\d+))?\s+\+(\d+)(,(\d+))?\s+@@\s*(.*)$")

    @staticmethod
    def get_before_file_data_at(lines, index):
        return Diff._get_file_data_at(UnifiedDiff.BEFORE_FILE_CRE, lines, index)

    @staticmethod
    def get_after_file_data_at(lines, index):
        return Diff._get_file_data_at(UnifiedDiff.AFTER_FILE_CRE, lines, index)

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
        Diff.__init__(self, "unified", lines, file_data, hunks)


class ContextDiffHunk(_Lines):
    def __init__(self, lines, before, after):
        _Lines.__init__(self, lines)
        self.before = before
        self.after = after

    def _process_tws(self, fix=False):
        bad_lines = list()
        for index in range(self.after.offset + 1, self.after.offset + self.after.numlines):
            if self.lines[index].startswith("+ ") or self.lines[index].startswith("! "):
                repl_line = self.lines[index][:2] + _trim_trailing_ws(self.lines[index][2:])
                after_count = index - (self.after.offset + 1)
                if len(repl_line) != len(self.lines[index]):
                    bad_lines.append(str(self.after.start + after_count))
                    if fix:
                        self.lines[index] = repl_line
            elif DEBUG and not self.lines[index].startswith("  "):
                raise Bug("Unexpected end of context diff hunk.")
        return bad_lines

    def get_diffstat_stats(self):
        stats = diffstat.DiffStats()
        for index in range(self.before.offset + 1, self.before.offset + self.before.numlines):
            if self.lines[index].startswith("- "):
                stats.incr("deleted")
            elif self.lines[index].startswith("! "):
                stats.incr("modified")
            elif DEBUG and not self.lines[index].startswith("  "):
                raise Bug("Unexpected end of context diff \"before\" hunk.")
        for index in range(self.after.offset + 1, self.after.offset + self.after.numlines):
            if self.lines[index].startswith("+ "):
                stats.incr("inserted")
            elif self.lines[index].startswith("! "):
                stats.incr("modified")
            elif DEBUG and not self.lines[index].startswith("  "):
                raise Bug("Unexpected end of context diff \"after\" hunk.")
        return stats

    def fix_trailing_whitespace(self):
        return self._process_tws(fix=True)

    def report_trailing_whitespace(self):
        return self._process_tws(fix=False)


class ContextDiff(Diff):
    BEFORE_FILE_CRE = re.compile("^\*\*\* ({0})(\s+{1})?$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile("^--- ({0})(\s+{1})?$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    HUNK_START_CRE = re.compile("^\*{15}\s*(.*)$")
    HUNK_BEFORE_CRE = re.compile("^\*\*\*\s+(\d+)(,(\d+))?\s+\*\*\*\*\s*(.*)$")
    HUNK_AFTER_CRE = re.compile("^---\s+(\d+)(,(\d+))?\s+----(.*)$")

    @staticmethod
    def get_before_file_data_at(lines, index):
        return Diff._get_file_data_at(ContextDiff.BEFORE_FILE_CRE, lines, index)

    @staticmethod
    def get_after_file_data_at(lines, index):
        return Diff._get_file_data_at(ContextDiff.AFTER_FILE_CRE, lines, index)

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
        match = ContextDiff.HUNK_BEFORE_CRE.match(lines[index])
        if not match:
            return (None, index)
        return (ContextDiff._chunk(match), index + 1)

    @staticmethod
    def _get_after_chunk_at(lines, index):
        match = ContextDiff.HUNK_AFTER_CRE.match(lines[index])
        if not match:
            return (None, index)
        return (ContextDiff._chunk(match), index + 1)

    @staticmethod
    def get_hunk_at(lines, index):
        if not ContextDiff.HUNK_START_CRE.match(lines[index]):
            return (None, index)
        start_index = index
        before_start_index = index + 1
        before_chunk, index = ContextDiff._get_before_chunk_at(lines, before_start_index)
        if not before_chunk:
            return (None, index)
        before_count = after_count = 0
        try:
            after_chunk = None
            while before_count < before_chunk.length:
                after_start_index = index
                after_chunk, index = ContextDiff._get_after_chunk_at(lines, index)
                if after_chunk is not None:
                    break
                before_count += 1
                index += 1
            if after_chunk is None:
                if lines[index].startswith("\ "):
                    before_count += 1
                    index += 1
                after_start_index = index
                after_chunk, index = ContextDiff._get_after_chunk_at(lines, index)
                if after_chunk is None:
                    raise ParseError(_("Failed to find context diff \"after\" hunk."), index)
            while after_count < after_chunk.length:
                if not lines[index].startswith(("! ", "+ ", "  ")):
                    if after_count == 0:
                        break
                    raise ParseError(_("Unexpected end of context diff hunk."), index)
                after_count += 1
                index += 1
            if index < len(lines) and lines[index].startswith("\ "):
                after_count += 1
                index += 1
        except IndexError:
            raise ParseError(_("Unexpected end of patch text."))
        before_hunk = _HUNK(before_start_index - start_index,
                            before_chunk.start,
                            before_chunk.length,
                            after_start_index - before_start_index)
        after_hunk = _HUNK(after_start_index - start_index,
                           after_chunk.start,
                           after_chunk.length,
                           index - after_start_index)
        return (ContextDiffHunk(lines[start_index:index], before_hunk, after_hunk), index)

    def __init__(self, lines, file_data, hunks):
        Diff.__init__(self, "context", lines, file_data, hunks)


class GitBinaryDiffData(_Lines):
    LITERAL, DELTA = ("literal", "delta")

    def __init__(self, lines, method, size_raw, data_zipped):
        _Lines.__init__(self, lines)
        self.method = method
        self.size_raw = size_raw
        self.data_zipped = data_zipped

    @property
    def size_zipped(self):
        return len(self.data_zipped)

    @property
    def data_raw(self):
        return zlib.decompress(bytes(self.data_zipped))


class GitBinaryDiff(Diff):
    START_CRE = re.compile("^GIT binary patch$")
    DATA_START_CRE = re.compile("^(literal|delta) (\d+)$")
    DATA_LINE_CRE = gitbase85.LINE_CRE
    BLANK_LINE_CRE = re.compile("^\s*$")

    @staticmethod
    def get_data_at(lines, start_index):
        smatch = False if start_index >= len(lines) else GitBinaryDiff.DATA_START_CRE.match(lines[start_index])
        if not smatch:
            return (None, start_index)
        method = smatch.group(1)
        size = int(smatch.group(2))
        index = start_index + 1
        while index < len(lines) and GitBinaryDiff.DATA_LINE_CRE.match(lines[index]):
            index += 1
        end_data = index
        # absorb the blank line if there is one
        if GitBinaryDiff.BLANK_LINE_CRE.match(lines[index]):
            has_blank = True
            index += 1
        else:
            has_blank = False
        dlines = lines[start_index:index]
        try:
            data_zipped = gitbase85.decode_lines(lines[start_index + 1:end_data])
        except AssertionError:
            raise DataError(_("Inconsistent git binary patch data."), lineno=start_index)
        raw_size = len(zlib.decompress(bytes(data_zipped)))
        if raw_size != size:
            emsg = _("Git binary patch expected {0} bytes. Got {1} bytes.").format(size, raw_size)
            raise DataError(emsg, lineno=start_index)
        return (GitBinaryDiffData(dlines, method, raw_size, data_zipped), index)

    @staticmethod
    def get_diff_at(lines, start_index, raise_if_malformed=True):
        if not GitBinaryDiff.START_CRE.match(lines[start_index]):
            return (None, start_index)
        forward, index = GitBinaryDiff.get_data_at(lines, start_index + 1)
        if forward is None and raise_if_malformed:
            raise ParseError(_("No content in GIT binary patch text."))
        reverse, index = GitBinaryDiff.get_data_at(lines, index)
        return (GitBinaryDiff(lines[start_index:index], forward, reverse), index)

    def __init__(self, lines, forward, reverse):
        Diff.__init__(self, "git_binary", lines, None, None)
        self.forward = forward
        self.reverse = reverse

    def get_outcome(self):
        return None

# NB. these are ordered by likelihood of being encountered
DIFF_TYPES = [UnifiedDiff, GitBinaryDiff, ContextDiff]

def get_diff_at(lines, index, raise_if_malformed):
    """If there is a valid unified, context or git binary diff in
    "lines" starting at "index" extract and return it along with the
    index for the first line after the diff.
    """
    for diff_type in DIFF_TYPES:
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
