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
from . import diffs

from .diff_preamble import Preambles

from .pd_utils import TextLines as _Lines
from .pd_utils import FilePathPlus

# TODO: convert methods that return lists to iterators

# Useful named tuples to make code clearer
_FILE_AND_TWS_LINES = collections.namedtuple("_FILE_AND_TWS_LINES", ["path", "tws_lines"])
_DIFF_DATA = collections.namedtuple("_DIFF_DATA", ["file_data", "hunks"])


DEBUG = False


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
        diff_data, index = diffs.get_diff_at(lines, index, raise_if_malformed)
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
            assert isinstance(self.preambles, Preambles) and (self.diff is None or isinstance(self.diff, diffs.Diff))

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
