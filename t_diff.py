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
import os
import re
import sys

from . import a_diff
from . import diffstat
from . import pd_utils

from .pd_utils import DiffOutcome, ParseError

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


class Bug(Exception):
    """Exception to signal a bug
    """
    pass


# Useful named tuples to make code clearer
StartAndLength = collections.namedtuple("StartAndLength", ["start", "length"])
PathAndTimestamp = collections.namedtuple("PathAndTimestamp", ["path", "timestamp"])
PathAndOutcome = collections.namedtuple("PathAndOutcome", ["path", "outcome"])

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


class TextDiffHeader(collections.namedtuple("TextDiffHeader", ["lines", "before", "after"])):
    """Class to encapsulate diff header containing file path(s) and
    optional timestamps.
    """
    def __str__(self):
        return "".join(self.lines)

    def __iter__(self):
        return (line for line in self.lines)

    def get_file_path(self, strip=lambda x: x):
        """Get the stripped of the file path
        """
        for path in [self.after.path, self.before.path]:
            if path and path != "/dev/null":
                return strip(path)
        return None

    def get_outcome(self):
        """Get the expected outcome of applying the associated diff
        """
        if self.after.path == "/dev/null":
            return DiffOutcome.DELETED
        if self.before.path == "/dev/null":
            return DiffOutcome.CREATED
        return DiffOutcome.MODIFIED

    def get_file_path_and_outcome(self, strip=lambda x: x):
        """Get the file path that this diff applies to along with any
        extra relevant data
        """
        file_path = self.get_file_path(strip)
        outcome = self.get_outcome()
        return pd_utils.FilePathPlus(path=file_path, status=outcome, expath=None)

    @property
    def is_consistent_with_strip_level(self, strip_level, play_hard_ball=False):
        """Is the file data in the header compatible with being stripped
        at the given level.
        """
        strip = pd_utils.gen_strip_level_function(strip_level)

        try:
            if self.before.path and self.before.path != "/dev/null":
                if play_hard_ball and self.after.path and self.after.path != "/dev/null":
                    return strip(self.before.path) == strip(self.after.path)
                else:
                    strip(self.before.path)
            elif self.after.path and self.after.path != "/dev/null":
                strip(self.before.path)
            else:
                return False
        except pd_utils.TooManyStripLevels:
            return False
        else:
            return True


class TextDiffParser:
    """A base class for all classes that encapsulate diffs.
    """
    BEFORE_FILE_CRE = None
    AFTER_FILE_CRE = None
    diff_format = None

    @staticmethod
    def _get_file_data_at(cre, lines, index):
        match = cre.match(lines[index])
        if not match:
            return (None, index)
        file_path = match.group(2) if match.group(2) else match.group(3)
        return (PathAndTimestamp(file_path, match.group(4)), index + 1)

    @classmethod
    def get_before_file_data_at(cls, lines, index):
        """Get data for the "before" file the diff applies to
        """
        return cls._get_file_data_at(cls.BEFORE_FILE_CRE, lines, index)

    @classmethod
    def get_after_file_data_at(cls, lines, index):
        """Get data for the "after" file the diff applies to
        """
        return cls._get_file_data_at(cls.AFTER_FILE_CRE, lines, index)

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
        header = TextDiffHeader(lines[start_index:start_index + 2], before_file_data, after_file_data)
        return (TextDiff(cls.diff_format, header, hunks), index)

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


class TextDiffHunk(collections.namedtuple("TextDiffHunk", ["lines", "before", "after"])):
    """Class to encapsulate a single unified diff hunk
    """
    def __str__(self):
        return "".join(self.lines)

    def __iter__(self):
        return (line for line in self.lines)

    def _process_tws(self, fix=False):
        """If "fix" is True remove any trailing white space from
        changed lines and return a list of lines that were fixed
        otherwise return a list of changed lines that have tailing
        white space
        """
        return list()

    def get_diffstat_stats(self):
        """Return the "diffstat" statistics for this chunk
        """
        return diffstat.DiffStats()

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

    @staticmethod
    def _iter_lines(lines, skip_if_starts_with=None):
        """Iterate over lines skipping lines as directed
        """
        index = 1
        while index < len(lines):
            if skip_if_starts_with is None or not lines[index].startswith(skip_if_starts_with):
                if (index + 1) == len(lines) or not lines[index + 1].startswith("\\"):
                    yield lines[index][1:]
                else:
                    yield lines[index][1:].rstrip(os.linesep + "\n")
            index += 1
            if index < len(lines) and lines[index].startswith("\\"):
                index += 1

    def iter_before_lines(self):
        """Iterate over the lines in the "before" component of this hunk
        """
        return (line for line in self._iter_lines("+"))

    def iter_after_lines(self):
        """Iterate over the lines in the "after" component of this hunk
        """
        return (line for line in self._iter_lines("-"))

    def get_abstract_diff_hunk(self):
        """Return the AbstractHunk version of this hunk
        """
        # NB: convert starting line numbers to 0 based indices
        #<https://www.gnu.org/software/diffutils/manual/html_node/Detailed-Unified.html#Detailed-Unified>
        # If a hunk contains just one line, only its start line number appears. Otherwise its line numbers
        # look like ‘start,count’. An empty hunk is considered to start at the line that follows the hunk.
        #
        # If a hunk and its context contain two or more lines, its line numbers look like ‘start,count’.
        # Otherwise only its end line number appears. An empty hunk is considered to end at the line that
        # precedes the hunk.
        b_lines = list(self.iter_before_lines())
        b_start_index = (self.before.start - 1) if len(b_lines) else self.before.start
        before = a_diff.AbstractChunk(b_start_index, b_lines)
        after = a_diff.AbstractChunk(self.after.start - 1, list(self.iter_after_lines()))
        return a_diff.AbstractHunk(before, after)

class TextDiff(collections.namedtuple("TextDiff", ["diff_format", "header", "hunks"])):
    """A class to encapsulate "text" diffs regardless of format.
    """
    @property
    def diff_type(self):
        """Alias for "diff_format"
        """
        return self.diff_format

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
        return self.header.get_file_path(strip)

    def get_file_path_and_outcome(self, strip_level=0):
        """Get the file path that this diff applies to along with any
        extra relevant data
        """
        strip = pd_utils.gen_strip_level_function(strip_level)
        return self.header.get_file_path_and_outcome(strip)

    def get_outcome(self):
        """Get the "outcome" of applying this diff
        """
        return self.header.get_outcome()

    def apply_to_file(self, file_path, repd_file_path=None, rctx=sys, drop_atws=True):
        """Apply this diff to the given file
        """
        from ..bab import CmdResult
        ecode = CmdResult.OK
        try:
            with open(file_path, "r") as f_obj:
                text = f_obj.read()
        except FileNotFoundError:
            if self.header.get_outcome() != DiffOutcome.CREATED:
                rctx.stderr.write(_("{}: (expected) file not found.\n").format(repd_file_path))
                ecode = CmdResult.WARNING
            text = ""
        except EnvironmentError as edata:
            rctx.stderr.write("\"{0}\": {1}\n".format(repd_file_path, edata))
            return CmdResult.ERROR
        if drop_atws:
            atws_lines = self.fix_trailing_whitespace()
            if atws_lines:
                RCTX.stdout.write(_("\"{1}\": had added trailing white space at line(s) {{{1}}}: removed before application.\n").format(repd_file_path, ", ".join([str(line) for line in atws_lines])))
        else:
            atws_lines = self.report_trailing_whitespace()
            if atws_lines:
                ecode = CmdResult.WARNING
                RCTX.stderr.write(_("Warning: \"{0}\": has added trailing white space at line(s) {{{2}}}.\n").format(repd_file_path, ", ".join([str(line) for line in atws_lines])))
        adiff = a_diff.AbstractDiff(self.hunks)
        lines = text.splitlines(True)
        if adiff.first_mismatch_before(lines) == -1:
            new_text = "".join(adiff.apply_forwards(lines))
            ecode = max(ecode, CmdResult.OK)
        else:
            repd_file_path = repd_file_path if repd_file_path else file_path
            pd_ecode, new_text = pd_utils.apply_diff_to_text_using_patch(text, self, repd_file_path, rctx)
            ecode = max(ecode, pd_ecode)
        try:
            if not new_text and self.header.after.path == "/dev/null":
                os.remove(file_path)
            else:
                with open(file_path, "w") as f_obj:
                    f_obj.write(new_text)
        except EnvironmentError as edata:
            rctx.stderr.write("\"{0}\": {1}\n".format(repd_file_path, edata))
            return CmdResult.ERROR
        return ecode
