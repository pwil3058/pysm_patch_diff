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


class DiffStat:
    """Class to encapsulate diffstat related code"""
    class Stats:
        """Class to hold diffstat statistics."""
        _ORDERED_KEYS = ["inserted", "deleted", "modified", "unchanged"]
        _FMT_DATA = {
            "inserted": "{0} insertion{1}(+)",
            "deleted": "{0} deletion{1}(-)",
            "modified": "{0} modification{1}(!)",
            "unchanged": "{0} unchanged line{1}(+)"
        }

        def __init__(self):
            self.counts = {}
            for key in self._ORDERED_KEYS:
                self.counts[key] = 0
            assert len(self.counts) == len(self._ORDERED_KEYS)

        def __add__(self, other):
            result = DiffStat.Stats()
            for key in self._ORDERED_KEYS:
                result.counts[key] = self.counts[key] + other.counts[key]
            return result

        def __len__(self):
            return len(self.counts)

        def __getitem__(self, key):
            if isinstance(key, int):
                key = self._ORDERED_KEYS[key]
            return self.counts[key]

        def get_total(self):
            """Get total lines
            """
            return sum(list(self))

        def get_total_changes(self):
            """Get total changed lines
            """
            return sum([self.counts[key] for key in self._ORDERED_KEYS[:-1]])

        def incr(self, key):
            """Increment the count for the given "key"
            """
            self.counts[key] += 1
            return self.counts[key]

        def as_string(self, joiner=", ", prefix=", "):
            """Format the statistics as a string
            """
            strings = []
            for key in self._ORDERED_KEYS:
                num = self.counts[key]
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
                count = scale(self.counts[key])
                char = self._FMT_DATA[key][-2]
                string += char * count
            return string

    class PathStats:
        """A file path and associated diffstat statistics
        """
        def __init__(self, path, diff_stats):
            self.path = path
            self.diff_stats = diff_stats

        def __eq__(self, other):
            return self.path == other.path

        def __ne__(self, other):
            return self.path != other.path

        def __lt__(self, other):
            return self.path < other.path

        def __gt__(self, other):
            return self.path > other.path

        def __le__(self, other):
            return self.path <= other.path

        def __ge__(self, other):
            return self.path >= other.path

        def __iadd__(self, other):
            if isinstance(other, DiffStat.PathStats):
                assert other.path != self.path
                self.diff_stats += other.diff_stats
            else:
                self.diff_stats += other
            return self

    class PathStatsList(list):
        """A list of path statistics
        """
        def __contains__(self, item):
            if isinstance(item, DiffStat.PathStats):
                return list.__contains__(self, item)
            for pstat in self:
                if pstat.path == item:
                    return True
            return False

        def list_format_string(self, quiet=False, comment=False, trim_names=False, max_width=80):
            """Return a formatted string for the list of statistics
            """
            if len(self) == 0 and quiet:
                return ""
            string = ""
            if trim_names:
                common_path = get_common_path([x.path for x in self])
                offset = len(common_path)
            else:
                offset = 0
            num_files = len(self)
            summation = DiffStat.Stats()
            if num_files > 0:
                len_longest_name = max([len(x.path) for x in self]) - offset
                fstr = "%s {0}{1} |{2:5} {3}\n" % ("#" if comment else "")
                largest_total = max(max([x.diff_stats.get_total() for x in self]), 1)
                avail_width = max(0, max_width - (len_longest_name + 9))
                if comment:
                    avail_width -= 1

                def scale(count):
                    """Scale the count to fit on a line"""
                    return (count * avail_width) // largest_total
                for stats in self:
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
