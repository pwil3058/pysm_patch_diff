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
                    yield self.lines[index][1:].rstrip(os.linesep, "\n")
            index += 1
            if index < len(lines) and self.lines[index + 1].startswith("\\"):
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


class UnifiedDiff(Diff):
    """Class to encapsulate a unified diff
    """
    diff_type = "unified"
    BEFORE_FILE_CRE = re.compile(r"^--- ({0})(\s+{1})?(.*)$".format(pd_utils.PATH_RE_STR, _EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile(r"^\+\+\+ ({0})(\s+{1})?(.*)$".format(pd_utils.PATH_RE_STR, _EITHER_TS_RE_STR))
    HUNK_DATA_CRE = re.compile(r"^@@\s+-(\d+)(,(\d+))?\s+\+(\d+)(,(\d+))?\s+@@\s*(.*)$")

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
        Diff.__init__(self, lines, file_data, hunks)

    def apply_to_lines(self, lines):
        """Apply this diff to the given "lines" and return the resulting lines.
        """
        return a_diff.AbstractDiff(self.hunks).apply_forwards(lines)


class ContextDiffHunk(pd_utils.TextLines):
    """Class to encapsulate a single context diff hunk
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
        """Return the "diffstat" statistics for this chunk
        """
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
        """Fix any lines that would introduce trailing white space when
        the chunk is applied and return a list of the changed lines
        """
        return self._process_tws(fix=True)

    def report_trailing_whitespace(self):
        """Return a list of lines that will introduce tailing white
        space when the chunk is applied
        """
        return self._process_tws(fix=False)


class ContextDiff(Diff):
    """Class to encapsulate a context diff
    """
    diff_type = "context"
    BEFORE_FILE_CRE = re.compile(r"^\*\*\* ({0})(\s+{1})?$".format(pd_utils.PATH_RE_STR, _EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile(r"^--- ({0})(\s+{1})?$".format(pd_utils.PATH_RE_STR, _EITHER_TS_RE_STR))
    HUNK_START_CRE = re.compile(r"^\*{15}\s*(.*)$")
    HUNK_BEFORE_CRE = re.compile(r"^\*\*\*\s+(\d+)(,(\d+))?\s+\*\*\*\*\s*(.*)$")
    HUNK_AFTER_CRE = re.compile(r"^---\s+(\d+)(,(\d+))?\s+----(.*)$")

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
        """Extract the context diff "before" chunk from "lines" starting
        at "index"."""
        match = ContextDiff.HUNK_BEFORE_CRE.match(lines[index])
        if not match:
            return (None, index)
        return (ContextDiff._chunk(match), index + 1)

    @staticmethod
    def _get_after_chunk_at(lines, index):
        """Extract the context diff "after" chunk from "lines" starting
        at "index"."""
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
                if lines[index].startswith(r"\ "):
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
            if index < len(lines) and lines[index].startswith(r"\ "):
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
        Diff.__init__(self, lines, file_data, hunks)


class ZippedData:
    """Class to encapsulate zipped data
    """
    ZLIB_COMPRESSION_LEVEL = 6

    def __init__(self, data):
        if data is not None:
            try:
                self.raw_len = len(data)
                self.zipped_data = zlib.compress(bytes(data), self.ZLIB_COMPRESSION_LEVEL)
            except TypeError as edata:
                print("ZIP:", len(data), ":", data, "|")
                raise edata
        else:
            self.raw_len = None
            self.zipped_data = None

    def __bool__(self):
        return self.zipped_data is not None

    @property
    def raw_data(self):
        """The unzipped version of the encapsulated zipped data
        """
        return zlib.decompress(self.zipped_data)

    @property
    def zipped_len(self):
        """The length of the zipped data
        """
        return len(self.zipped_data)


class GitBinaryDiffData(pd_utils.TextLines):
    """Class to encapsulate the data component of a git binary patch
    """
    LITERAL, DELTA = ("literal", "delta")

    def __init__(self, lines, method, size_raw, data_zipped):
        pd_utils.TextLines.__init__(self, lines)
        self.method = method
        self.size_raw = size_raw
        self.data_zipped = data_zipped

    @property
    def size_zipped(self):
        """Size of the data when compressed
        """
        return len(self.data_zipped)

    @property
    def data_raw(self):
        """Non compressed version of the data.
        """
        return zlib.decompress(bytes(self.data_zipped))


class GitBinaryDiff(Diff):
    """Class to encapsulate a git binary diff
    """
    diff_type = "git_binary"
    START_CRE = re.compile(r"^GIT binary patch$")
    DATA_START_CRE = re.compile(r"^(literal|delta) (\d+)$")
    DATA_LINE_CRE = gitbase85.LINE_CRE
    BLANK_LINE_CRE = re.compile(r"^\s*$")

    @staticmethod
    def get_data_at(lines, start_index):
        """If there is a valid git binary diff data in "lines" starting
        at "index" extract and return it along with the index for the
        first line after the data.
        """
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
            index += 1
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
        """If there is a valid git binary diff in "lines" starting at
        "index" extract and return it along with the index for the
        first line after the diff.
        """
        if not GitBinaryDiff.START_CRE.match(lines[start_index]):
            return (None, start_index)
        forward, index = GitBinaryDiff.get_data_at(lines, start_index + 1)
        if forward is None and raise_if_malformed:
            raise ParseError(_("No content in GIT binary patch text."))
        reverse, index = GitBinaryDiff.get_data_at(lines, index)
        return (GitBinaryDiff(lines[start_index:index], forward, reverse), index)

    @staticmethod
    def generate_diff_lines(before, after):
        """Generate the text lines of a git binary diff from the provided
        before and after data.
        """

        def _component_lines(fm_data, to_data):
            delta = None
            if fm_data.raw_len and to_data.raw_len:
                delta = ZippedData(gitdelta.diff_delta(fm_data.raw_data, to_data.raw_data))
            if delta and delta.zipped_len < to_data.zipped_len:
                lines = ["delta {0}\n".format(delta.raw_len)] + gitbase85.encode_to_lines(delta.zipped_data) + ["\n"]
            else:
                lines = ["literal {0}\n".format(to_data.raw_len)] + gitbase85.encode_to_lines(to_data.zipped_data) + ["\n"]
            return lines

        if before.content == after.content:
            return []
        orig = ZippedData(before.content)
        darned = ZippedData(after.content)
        return ["GIT binary patch\n"] + _component_lines(orig, darned) + _component_lines(darned, orig)

    @classmethod
    def generate_diff(cls, before, after):
        """Generate the git binary diff from the provided
        before and after data.
        """
        diff_lines = cls.generate_diff_lines(before, after)
        return cls.parse_lines(diff_lines) if diff_lines else None

    def __init__(self, lines, forward, reverse):
        Diff.__init__(self, lines, None, None)
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


def apply_diff_to_file(file_path, diff, delete_empty=False, rel_subdir=lambda x:x):
    from ..bab import runext
    from ..bab import CmdResult
    patch_cmd_hdr = ["patch", "--merge", "--force", "-p1", "--batch", ]
    patch_cmd = patch_cmd_hdr + (["--remove-empty-files", file_path] if delete_empty else [file_path])
    result = runext.run_cmd(patch_cmd, input_text=str(diff).encode())
    # move all but the first line of stdout to stderr
    # drop first line so that reports can be made relative to subdir
    olines = result.stdout.splitlines(True)
    prefix = "{0}: ".format(rel_subdir(file_path))
    # Put file name at start of line so they make sense on their own
    if len(olines) > 1:
        stderr = prefix + prefix.join(olines[1:] + result.stderr.splitlines(True))
    elif result.stderr:
        stderr = prefix + prefix.join(result.stderr.splitlines(True))
    else:
        stderr = ""
    return CmdResult(result.ecode, "", stderr)
