# Copyright (C) 2011-2015 Peter Williams <pwil3058@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""Classes and functions for operations on patch files"""

import collections
import re
import os
import email
import zlib
import hashlib

from . import gitbase85
from . import diffstat
from . import diff_preamble

from .diff_preamble import Preambles
from .pd_utils import TextLines as _Lines
from .pd_utils import PATH_RE_STR as _PATH_RE_STR
from .pd_utils import BEFORE_AFTER as _PAIR
from .pd_utils import FilePathPlus
from .pd_utils import gen_strip_level_function
from .pd_utils import file_path_fm_pair as _file_path_fm_pair
from .pd_utils import is_non_null as _is_non_null

# TODO: convert methods that return lists to iterators

# Useful named tuples to make code clearer
_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])
_HUNK = collections.namedtuple("_HUNK", ["offset", "start", "length", "numlines"])
_FILE_AND_TS = collections.namedtuple("_FILE_AND_TS", ["path", "timestamp"])
_FILE_AND_TWS_LINES = collections.namedtuple("_FILE_AND_TWS_LINES", ["path", "tws_lines"])
_DIFF_DATA = collections.namedtuple("_DIFF_DATA", ["file_data", "hunks"])

# Useful strings for including in regular expressions
_TIMESTAMP_RE_STR = "\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{9})? [-+]{1}\d{4}"
_ALT_TIMESTAMP_RE_STR = "[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4} [-+]{1}\d{4}"
_EITHER_TS_RE_STR = "(%s|%s)" % (_TIMESTAMP_RE_STR, _ALT_TIMESTAMP_RE_STR)


class ParseError(Exception):
    def __init__(self, message, lineno=None):
        self.message = message
        self.lineno = lineno


class TooMayStripLevels(Exception):
    def __init__(self, message, path, levels):
        self.message = message
        self.path = path
        self.levels = levels


class DataError(ParseError):
    pass

DEBUG = False


class Bug(Exception):
    pass


def _trim_trailing_ws(line):
    """Return the given line with any trailing white space removed"""
    return re.sub("[ \t]+$", "", line)


class Header:
    def __init__(self, text=""):
        lines = text.splitlines(True)
        descr_starts_at = 0
        for line in lines:
            if not line.startswith("#"):
                break
            descr_starts_at += 1
        self.comment_lines = _Lines(lines[:descr_starts_at])
        diffstat_starts_at = None
        index = descr_starts_at
        while index < len(lines):
            if diffstat.list_summary_starts_at(lines, index):
                diffstat_starts_at = index
                break
            index += 1
        if diffstat_starts_at is not None:
            self.description_lines = _Lines(lines[descr_starts_at:diffstat_starts_at])
            self.diffstat_lines = _Lines(lines[diffstat_starts_at:])
        else:
            self.description_lines = _Lines(lines[descr_starts_at:])
            self.diffstat_lines = _Lines()

    def __str__(self):
        return self.get_comments() + self.get_description() + self.get_diffstat()

    def iter_lines(self):
        for lines in [self.comment_lines, self.description_lines, self.diffstat_lines]:
            for line in lines:
                yield line

    def get_comments(self):
        return str(self.comment_lines)

    def get_description(self):
        return str(self.description_lines)

    def get_diffstat(self):
        return str(self.diffstat_lines)

    def set_comments(self, text):
        if text and not text.endswith("\n"):
            text += "\n"
        self.comment_lines = _Lines(text)

    def set_description(self, text):
        if text and not text.endswith("\n"):
            text += "\n"
        self.description_lines = _Lines(text)

    def set_diffstat(self, text):
        if text and not text.endswith("\n"):
            text += "\n"
        self.diffstat_lines = _Lines(text)


class DiffHunk(_Lines):
    def __init__(self, lines, before, after):
        _Lines.__init__(self, lines)
        self.before = before
        self.after = after

    def get_diffstat_stats(self):
        return diffstat.DiffStats()

    def fix_trailing_whitespace(self):
        return list()

    def report_trailing_whitespace(self):
        return list()


class Diff:
    subtypes = list()

    @staticmethod
    def _get_file_data_at(cre, lines, index):
        match = cre.match(lines[index])
        if not match:
            return (None, index)
        filepath = match.group(2) if match.group(2) else match.group(3)
        return (_FILE_AND_TS(filepath, match.group(4)), index + 1)

    @staticmethod
    def _get_diff_at(subtype, lines, start_index, raise_if_malformed=False):
        """generic function that works for unified and context diffs"""
        if len(lines) - start_index < 2:
            return (None, start_index)
        hunks = list()
        index = start_index
        before_file_data, index = subtype.get_before_file_data_at(lines, index)
        if not before_file_data:
            return (None, start_index)
        after_file_data, index = subtype.get_after_file_data_at(lines, index)
        if not after_file_data:
            if raise_if_malformed:
                raise ParseError(_("Missing unified diff after file data."), index)
            else:
                return (None, start_index)
        while index < len(lines):
            hunk, index = subtype.get_hunk_at(lines, index)
            if hunk is None:
                break
            hunks.append(hunk)
        if len(hunks) == 0:
            if raise_if_malformed:
                raise ParseError(_("Expected unified diff hunks not found."), index)
            else:
                return (None, start_index)
        return (subtype(lines[start_index:start_index + 2], _PAIR(before_file_data, after_file_data), hunks), index)

    @staticmethod
    def get_diff_at(lines, index, raise_if_malformed):
        for subtype in Diff.subtypes:
            diff, next_index = subtype.get_diff_at(lines, index, raise_if_malformed)
            if diff is not None:
                return (diff, next_index)
        return (None, index)

    @staticmethod
    def parse_lines(lines):
        """Parse list of lines and return a valid Diff or raise exception"""
        diff, index = Diff.get_diff_at(lines, 0, raise_if_malformed=True)
        if not diff or index < len(lines):
            raise ParseError(_("Not a valid diff."))
        return diff

    @staticmethod
    def parse_text(text):
        """Parse text and return a valid DiffPlus or raise exception"""
        return Diff.parse_lines(text.splitlines(True))

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
        elif isinstance(self.file_data, _PAIR):
            return _file_path_fm_pair(self.file_data, strip)
        else:
            return None

    def get_file_path_plus(self, strip_level=0):
        strip = gen_strip_level_function(strip_level)
        if isinstance(self.file_data, str):
            return FilePathPlus(path=strip(self.file_data), status=None, expath=None)
        elif isinstance(self.file_data, _PAIR):
            return FilePathPlus.fm_pair(self.file_data, strip)
        else:
            return None

    def get_outcome(self):
        if isinstance(self.file_data, _PAIR):
            return _file_outcome_fm_pair(self.file_data)
        return None


class UnifiedDiffHunk(DiffHunk):
    def __init__(self, lines, before, after):
        DiffHunk.__init__(self, lines, before, after)

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

    @staticmethod
    def get_diff_at(lines, start_index, raise_if_malformed=False):
        return Diff._get_diff_at(UnifiedDiff, lines, start_index, raise_if_malformed)

    def __init__(self, lines, file_data, hunks):
        Diff.__init__(self, "unified", lines, file_data, hunks)

Diff.subtypes.append(UnifiedDiff)


class ContextDiffHunk(DiffHunk):
    def __init__(self, lines, before, after):
        DiffHunk.__init__(self, lines, before, after)

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

    @staticmethod
    def get_diff_at(lines, start_index, raise_if_malformed=False):
        return Diff._get_diff_at(ContextDiff, lines, start_index, raise_if_malformed)

    def __init__(self, lines, file_data, hunks):
        Diff.__init__(self, "context", lines, file_data, hunks)

Diff.subtypes.append(ContextDiff)


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

Diff.subtypes.append(GitBinaryDiff)


class DiffPlus:
    """Class to hold diff (headerless) information relavent to a single file.
    Includes (optional) preambles and trailing junk such as quilt's separators."""
    @staticmethod
    def get_diff_plus_at(lines, start_index, raise_if_malformed=False):
        preambles, index = diff_preamble.get_preambles_at(lines, start_index, raise_if_malformed)
        if index >= len(lines):
            if preambles:
                return (DiffPlus(preambles, None), index)
            else:
                return (None, start_index)
        diff_data, index = Diff.get_diff_at(lines, index, raise_if_malformed)
        if not diff_data:
            if preambles:
                return (DiffPlus(preambles, None), index)
            else:
                return (None, start_index)
        return (DiffPlus(preambles, diff_data), index)

    @staticmethod
    def parse_lines(lines):
        """Parse list of lines and return a valid DiffPlus or raise exception"""
        diff_plus, index = DiffPlus.get_diff_plus_at(lines, 0, raise_if_malformed=True)
        if not diff_plus or index < len(lines):
            raise ParseError(_("Not a valid (optionally preambled) diff."))
        return diff_plus

    @staticmethod
    def parse_text(text):
        """Parse text and return a valid DiffPlus or raise exception"""
        return DiffPlus.parse_lines(text.splitlines(True))

    def __init__(self, preambles=None, diff=None, trailing_junk=None):
        self.preambles = preambles if isinstance(preambles, Preambles) else Preambles.fm_list(preambles)
        self.diff = diff
        self.trailing_junk = _Lines(trailing_junk)
        if DEBUG:
            assert isinstance(self.preambles, Preambles) and (self.diff is None or isinstance(self.diff, Diff))

    def __str__(self):
        if self.diff is not None:
            return str(self.preambles) + str(self.diff) + str(self.trailing_junk)
        else:
            return str(self.preambles) + str(self.trailing_junk)

    def iter_lines(self):
        for line in self.preambles.iter_lines():
            yield line
        if self.diff:
            for line in self.diff.iter_lines():
                yield line
        for line in self.trailing_junk:
            yield line

    def get_preamble_for_type(self, preamble_type):
        return self.preambles.get(preamble_type, None)

    def get_new_mode(self):
        git_preamble = self.get_preamble_for_type("git")
        if git_preamble is not None:
            for key in ["new mode", "new file mode"]:
                if key in git_preamble.extras:
                    return int(git_preamble.extras[key], 8)
        return None

    def is_compatible_with(self, git_hash):
        git_preamble = self.get_preamble_for_type("git")
        if git_preamble is not None:
            return git_preamble.is_compatible_with(git_hash)
        return None  # means "don't know"

    def get_outcome(self):
        return self.diff.get_outcome() if self.diff else None

    def fix_trailing_whitespace(self):
        if self.diff is None:
            return []
        return self.diff.fix_trailing_whitespace()

    def report_trailing_whitespace(self):
        if self.diff is None:
            return []
        return self.diff.report_trailing_whitespace()

    def get_diffstat_stats(self):
        if self.diff is None:
            return diffstat.DiffStats()
        return self.diff.get_diffstat_stats()

    def get_file_path(self, strip_level):
        path = self.diff.get_file_path(strip_level) if self.diff else None
        if not path:
            path = self.preambles.get_file_path(strip_level=strip_level)
        return path

    def get_file_path_plus(self, strip_level):
        path_plus = self.diff.get_file_path_plus(strip_level) if self.diff else None
        if not path_plus:
            path_plus = self.preambles.get_file_path_plus(strip_level=strip_level)
        elif path_plus.status == FilePathPlus.ADDED and path_plus.expath is None:
            path_plus.expath = self.preambles.get_file_expath(strip_level=strip_level)
        return path_plus

    def get_hash_digest(self):
        h = hashlib.sha1()
        h.update(str(self).encode())
        return h.digest()


class Patch:
    """Class to hold patch information relavent to multiple files with
    an optional header (or a single file with a header)."""
    @staticmethod
    def parse_lines(lines, num_strip_levels=0):
        """Parse list of lines and return a Patch instance"""
        diff_starts_at = None
        diff_pluses = list()
        index = 0
        last_diff_plus = None
        while index < len(lines):
            raise_if_malformed = diff_starts_at is not None
            starts_at = index
            diff_plus, index = DiffPlus.get_diff_plus_at(lines, index, raise_if_malformed)
            if diff_plus:
                if diff_starts_at is None:
                    diff_starts_at = starts_at
                diff_pluses.append(diff_plus)
                last_diff_plus = diff_plus
                continue
            elif last_diff_plus:
                last_diff_plus.trailing_junk.append(lines[index])
            index += 1
        patch = Patch(num_strip_levels=num_strip_levels)
        patch.diff_pluses = diff_pluses
        patch.set_header("".join(lines[0:diff_starts_at]))
        return patch

    @staticmethod
    def parse_text(text, num_strip_levels=0):
        """Parse text and return a Patch instance."""
        return Patch.parse_lines(text.splitlines(True), num_strip_levels=num_strip_levels)

    @staticmethod
    def parse_email_text(text, num_strip_levels=0):
        """Parse email text and return a Patch instance."""
        msg = email.message_from_string(text)
        subject = msg.get("Subject")
        if subject:
            # email may have inapproriate newlines (and they play havoc with REs) so fix them
            text = re.sub("\r\n", os.linesep, msg.get_payload())
        else:
            text = msg.get_payload()
        patch = Patch.parse_text(text, num_strip_levels=num_strip_levels)
        if subject:
            descr = patch.get_description()
            patch.set_description("\n".join([subject, descr]))
        return patch

    @staticmethod
    def parse_text_file(filepath, num_strip_levels=0):
        """Parse a text file and return a Patch instance."""
        patch = Patch.parse_text(open(filepath).read(), num_strip_levels=num_strip_levels)
        patch.source_name = filepath
        return patch

    @staticmethod
    def parse_email_file(filepath, num_strip_levels=0):
        """Parse a text file and return a Patch instance."""
        patch = Patch.parse_email_text(open(filepath).read(), num_strip_levels=num_strip_levels)
        patch.source_name = filepath
        return patch

    def __init__(self, num_strip_levels=0):
        self.source_name = None
        self.num_strip_levels = int(num_strip_levels)
        self.header = Header()
        self.diff_pluses = list()

    def _adjusted_strip_level(self, strip_level):
        return int(strip_level) if strip_level is not None else self.num_strip_levels

    def set_strip_level(self, strip_level):
        self.num_strip_levels = int(strip_level)

    def estimate_strip_level(self):
        trues = 0
        for diff_plus in self.diff_pluses:
            if "git" in diff_plus.preambles:
                # git patches will always have a strip level of 1
                return 1
            check = _file_data_consistent_with_strip_one(diff_plus.diff.file_data)
            if check is True:
                trues += 1
            elif check is False:
                return 0
        return 1 if trues > 0 else None

    def check_relevance(self, strip_level=None, path=None):
        relevance = collections.namedtuple("relevance", ["goodness", "missing", "unexpected"])
        fpath = (lambda fp: fp) if path is None else lambda fp: os.path.join(path, fp)
        missing = list()
        unexpected = list()
        fpluses = self.get_file_paths_plus(strip_level)
        for fplus in fpluses:
            fppath = fpath(fplus.path)
            exists = os.path.exists(fppath)
            if fplus.status == FilePathPlus.ADDED:
                num_created += 1
                if exists:
                    unexpected.append(fppath)
            else:
                num_expected += 1
                if not exists:
                    missing.append(fppath)
        badness = 100 if len(fpluses) == 0 else (100 * len(missing) * len(unexpected)) // len(fpluses)
        return relevance(goodness=100-badness, missing=missing, unexpected=unexpected)

    def get_header(self):
        return self.header

    def set_header(self, text):
        self.header = Header(text)

    def get_comments(self):
        return "" if self.header is None else self.header.get_comments()

    def set_comments(self, text):
        if not self.header:
            self.header = Header(text)
        else:
            self.header.set_comments(text)

    def get_description(self):
        return "" if self.header is None else self.header.get_description()

    def set_description(self, text):
        if not self.header:
            self.header = Header(text)
        else:
            self.header.set_description(text)

    def get_header_diffstat(self):
        return "" if self.header is None else self.header.get_diffstat()

    def set_header_diffstat(self, text=None, strip_level=None):
        if not self.header:
            self.header = Header()
        if text is None:
            stats = self.get_diffstat_stats(strip_level)
            text = "-\n\n%s\n" %  diffstat.format_diffstat_list(stats)
        self.header.set_diffstat(text)

    def __str__(self):
        string = "" if self.header is None else str(self.header)
        for diff_plus in self.diff_pluses:
            string += str(diff_plus)
        return string

    def iter_lines(self):
        for line in self.header:
            yield line
        for diff_plus in self.diff_pluses:
            for line in diff_plus:
                yield line

    def get_file_paths(self, strip_level=None):
        strip_level = self._adjusted_strip_level(strip_level)
        return [diff_plus.get_file_path(strip_level=strip_level) for diff_plus in self.diff_pluses]

    def iterate_file_paths(self, strip_level=None):
        strip_level = self._adjusted_strip_level(strip_level)
        for diff_plus in self.diff_pluses:
            yield diff_plus.get_file_path(strip_level=strip_level)

    def get_file_paths_plus(self, strip_level=None):
        strip_level = self._adjusted_strip_level(strip_level)
        return [diff_plus.get_file_path_plus(strip_level=strip_level) for diff_plus in self.diff_pluses]

    def iterate_file_paths_plus(self, strip_level=None):
        strip_level = self._adjusted_strip_level(strip_level)
        for diff_plus in self.diff_pluses:
            yield diff_plus.get_file_path_plus(strip_level=strip_level)

    def get_diffstat_stats(self, strip_level=None):
        sl = self._adjusted_strip_level(strip_level)
        return list(diffstat.PathDiffStats.iter_fm_diff_pluses(self.diff_pluses, sl))

    def fix_trailing_whitespace(self, strip_level=None):
        strip_level = self._adjusted_strip_level(strip_level)
        reports = []
        for diff_plus in self.diff_pluses:
            bad_lines = diff_plus.fix_trailing_whitespace()
            if bad_lines:
                path = diff_plus.get_file_path(strip_level=strip_level)
                reports.append(_FILE_AND_TWS_LINES(path, bad_lines))
        return reports

    def report_trailing_whitespace(self, strip_level=None):
        strip_level = self._adjusted_strip_level(strip_level)
        reports = []
        for diff_plus in self.diff_pluses:
            bad_lines = diff_plus.report_trailing_whitespace()
            if bad_lines:
                path = diff_plus.get_file_path(strip_level=strip_level)
                reports.append(_FILE_AND_TWS_LINES(path, bad_lines))
        return reports

    def get_hash_digest(self):
        h = hashlib.sha1()
        h.update(str(self).encode())
        return h.digest()
