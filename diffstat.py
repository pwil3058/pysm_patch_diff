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

"""Generate/pars diff statistics in format of "diffstat" program.
"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

import collections
import os
import re


class ErrorMalformedDiffStatSummary(Exception):
    """Exception to signify malformed diffstat summary
    """
    pass


def get_common_path(filelist):
    """Return the longest common path componet for the files in the list"""
    # Extra wrapper required because os.path.commonprefix() is string oriented
    # rather than file path oriented (which is strange)
    return os.path.dirname(os.path.commonprefix(filelist))


EMPTY_CRE = re.compile("^#? 0 files changed$")
END_CRE = re.compile(r"^#? (\d+) files? changed" +
                     r"(, (\d+) insertions?\(\+\))?" +
                     r"(, (\d+) deletions?\(-\))?" +
                     r"(, (\d+) modifications?\(\!\))?$")
FSTATS_CRE = re.compile(r"^#? (\S+)\s*\|((binary)|(\s*(\d+)(\s+\+*-*\!*)?))$")
BLANK_LINE_CRE = re.compile(r"^\s*$")
DIVIDER_LINE_CRE = re.compile(r"^---$")


def get_summary_length_starting_at(lines, index):
    """If there is a diffstat summary starting at line "index" in the
    given list of lines return the number of lines it contains or else
    return 0
    """
    start = index
    if DIVIDER_LINE_CRE.match(lines[index]):
        index += 1
    while index < len(lines) and BLANK_LINE_CRE.match(lines[index]):
        index += 1
    if index >= len(lines):
        return 0
    if EMPTY_CRE.match(lines[index]):
        return index - start
    count = 0
    while index < len(lines) and FSTATS_CRE.match(lines[index]):
        count += 1
        index += 1
    if index < len(lines) and END_CRE.match(lines[index]):
        return index - start
    elif count == 0:
        return 0
    raise ErrorMalformedDiffStatSummary()


def list_summary_starts_at(lines, index):
    """Return True if lines[index] is the start of a valid "list" diffstat summary"""
    return get_summary_length_starting_at(lines, index) != 0


def format_diffstat_list(diff_stats_list, quiet=False, trim_names=False, comment=False, max_width=80):
    """Return a formatted string for the list of statistics
    """
    import math
    if len(diff_stats_list) == 0 and quiet:
        return ""
    string = ""
    if trim_names:
        common_path = get_common_path([x.path for x in diff_stats_list])
        offset = len(common_path)
    else:
        offset = 0
    num_files = len(diff_stats_list)
    summation = DiffStats()
    if num_files > 0:
        len_longest_name = max([len(x.path) for x in diff_stats_list]) - offset
        largest_total = max(max([x.diff_stats.get_total() for x in diff_stats_list]), 1)
        sig_digits = int(math.log10(largest_total)) + 1
        fstr = "%s {0}{1} | {2:%s} {3}\n" % ("#" if comment else "", sig_digits)
        avail_width = max(0, max_width - (len_longest_name + 4 + sig_digits))
        if comment:
            avail_width -= 1

        def scale(count):
            """Scale the count to fit on a line"""
            return min((count * avail_width) // largest_total, count)
        for stats in diff_stats_list:
            summation += stats.diff_stats
            total = stats.diff_stats.get_total()
            name = stats.path[offset:]
            spaces = " " * (len_longest_name - len(name))
            bar = stats.diff_stats.as_bar(scale)
            string += fstr.format(name, spaces, total, bar)
    if num_files > 0 or not quiet:
        if comment:
            string += "#"
        string += " {0} file{1} changed".format(num_files, "" if num_files == 1 else "s")
        string += summation.as_string()
        string += "\n"
    return string


class DiffStats:
    """Class to hold one set diffstat statistics."""
    _ORDERED_KEYS = ["inserted", "deleted", "modified", "unchanged"]
    _FMT_DATA = {
        "inserted": "{0} insertion{1}(+)",
        "deleted": "{0} deletion{1}(-)",
        "modified": "{0} modification{1}(!)",
        "unchanged": "{0} unchanged line{1}(+)"
    }

    def __init__(self):
        self._counts = {}
        for key in self._ORDERED_KEYS:
            self._counts[key] = 0
        assert len(self._counts) == len(self._ORDERED_KEYS)

    def __iadd__(self, other):
        for key in self._ORDERED_KEYS:
            self._counts[key] += other[key]
        return self

    def __len__(self):
        return len(self._counts)

    def __getitem__(self, key):
        if isinstance(key, int):
            key = self._ORDERED_KEYS[key]
        return self._counts[key]

    def get_total(self):
        """Get total lines
        """
        return sum(list(self))

    def get_total_changes(self):
        """Get total changed lines
        """
        return sum([self._counts[key] for key in self._ORDERED_KEYS[:-1]])

    def incr(self, key):
        """Increment the count for the given "key"
        """
        self._counts[key] += 1
        return self._counts[key]

    def as_string(self, joiner=", ", prefix=", "):
        """Format the statistics as a string
        """
        strings = []
        for key in self._ORDERED_KEYS:
            num = self._counts[key]
            if num:
                strings.append(self._FMT_DATA[key].format(num, "" if num == 1 else "s"))
        if strings:
            return prefix + joiner.join(strings)
        else:
            return ""

    def as_bar(self, scale=lambda x: x):
        """Format the statistics as a bar
        """
        string = ""
        for key in self._ORDERED_KEYS:
            count = scale(self._counts[key])
            char = self._FMT_DATA[key][-2]
            string += char * count
        return string

class PathDiffStats(collections.namedtuple("PathDiffStats", ["path", "diff_stats"])):
    """Named tuple to hold a file path and associated "diffstat" stats
    """
    @classmethod
    def fm_diff_plus(cls, diff_plus, strip_level=None):
        """Create a PathDiffStats instance form a DiffPlus (or similar)
        """
        return cls(diff_plus.get_file_path(strip_level=strip_level), diff_plus.get_diffstat_stats())

    @classmethod
    def iter_fm_diff_pluses(cls, diff_pluses, strip_level=None):
        return (cls(dp.get_file_path(strip_level=strip_level), dp.get_diffstat_stats()) for dp in diff_pluses)
