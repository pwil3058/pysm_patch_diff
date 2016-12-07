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

"""Create, parse and apply "git" binary diffs"""

import collections
import re
import zlib

from . import gitbase85
from . import gitdelta
from . import pd_utils

from .pd_utils import ParseError

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


class DataError(Exception):
    """Exception to signal parsing error
    """
    def __init__(self, message, lineno=None):
        Exception.__init__(self)
        self.message = message
        self.lineno = lineno


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

class GitBinaryDiff(collections.namedtuple("GitBinaryDiff", ["lines", "forward", "reverse"])):
    """Class to encapsulate a git binary diff
    """
    diff_type = "git_binary"

    def __str__(self):
        return "".join(self.lines)

    def iter_lines(self):
        """Iterate over the lines in this diff
        """
        return (line for line in self.lines)

    @staticmethod
    def fix_trailing_whitespace():
        """Fix any lines that would introduce trailing white space when
        the diff is applied and return a list of the changed lines
        """
        return []

    @staticmethod
    def report_trailing_whitespace():
        """Return a list of lines that will introduce tailing white
        space when the diff is applied
        """
        return []

    @staticmethod
    def get_file_path(*args, **kwargs):
        """Get the file path that this diff applies to
        """
        return None

    @staticmethod
    def get_file_path_plus(*args, **kwargs):
        """Get the file path that this diff applies to along with any
        extra relevant data
        """
        return (None, None)

    @staticmethod
    def get_diffstat_stats():
        """Return the "diffstat" statistics for this diff
        """
        from . import diffstat
        return diffstat.DiffStats()

    @staticmethod
    def get_outcome():
        """Get the "outcome" of applying this diff
        """
        # TODO: implement get_outcome() for GitBinaryDiff
        return None


START_CRE = re.compile(r"^GIT binary patch$")
DATA_START_CRE = re.compile(r"^(literal|delta) (\d+)$")
BLANK_LINE_CRE = re.compile(r"^\s*$")


def get_data_at(lines, start_index):
    """If there is a valid git binary diff data in "lines" starting
    at "index" extract and return it along with the index for the
    first line after the data.
    """
    smatch = False if start_index >= len(lines) else DATA_START_CRE.match(lines[start_index])
    if not smatch:
        return (None, start_index)
    method = smatch.group(1)
    size = int(smatch.group(2))
    index = start_index + 1
    while index < len(lines) and gitbase85.LINE_CRE.match(lines[index]):
        index += 1
    end_data = index
    # absorb the blank line if there is one
    if BLANK_LINE_CRE.match(lines[index]):
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


def get_diff_at(lines, start_index, raise_if_malformed=True):
    """If there is a valid git binary diff in "lines" starting at
    "index" extract and return it along with the index for the
    first line after the diff.
    """
    if not START_CRE.match(lines[start_index]):
        return (None, start_index)
    forward, index = get_data_at(lines, start_index + 1)
    if forward is None and raise_if_malformed:
        raise ParseError(_("No content in GIT binary patch text."))
    reverse, index = get_data_at(lines, index)
    return (GitBinaryDiff(lines[start_index:index], forward, reverse), index)


def parse_diff_lines(lines):
    """Parse list of lines and return a valid "unified" diff or raise exception"""
    diff, index = get_diff_at(lines, 0, raise_if_malformed=True)
    if not diff or index < len(lines):
        raise ParseError(_("Not a valid \"unified\" diff."), index)
    return diff


def parse_diff_text(text):
    """Parse text and return a valid "unified" diff or raise exception"""
    return parse_diff_lines(text.splitlines(True))


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


def generate_diff(before, after):
    """Generate the git binary diff from the provided
    before and after data.
    """
    diff_lines = generate_diff_lines(before, after)
    return parse_diff_lines(diff_lines) if diff_lines else None
