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

"""Classes and functions used by more than one module in this package
"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

import collections
import os

# Useful snippet for inclusion in regular expression
PATH_RE_STR = """"([^"]+)"|(\S+)"""


BEFORE_AFTER = collections.namedtuple("BEFORE_AFTER", ["before", "after"])


def is_non_null(path):
    return path and path != "/dev/null"


def file_path_fm_pair(pair, strip=lambda x: x):
    def get_path(x):
        return x if isinstance(x, str) else x.path
    after = get_path(pair.after)
    if is_non_null(after):
        return strip(after)
    before = get_path(pair.before)
    if is_non_null(before):
        return strip(before)
    return None


def file_outcome_fm_pair(pair):
    def get_path(x):
        return x if isinstance(x, str) else x.path
    if get_path(pair.after) == "/dev/null":
        return -1
    if get_path(pair.before) == "/dev/null":
        return 1
    return 0


def file_data_consistent_with_strip_one(pair):
    strip = gen_strip_level_function(1)

    def get_path(x):
        return x if isinstance(x, str) else x.path
    before = get_path(pair.before)
    if not is_non_null(before):
        return None
    after = get_path(pair.after)
    if not is_non_null(after):
        return None
    try:
        return strip(before) == strip(after)
    except TooMayStripLevels:
        return False


class TextLines:
    """Manage a list of text lines
    """
    def __init__(self, contents=None):
        if contents is None:
            self.__lines = list()
        elif isinstance(contents, str):
            self.__lines = contents.splitlines(True)
        else:
            self.__lines = list(contents)

    @property
    def lines(self):
        return self.__lines

    def __str__(self):
        return "".join(self.__lines)

    def __iter__(self):
        return (line for line in self.__lines)

    def append(self, data):
        """Append text or lines of text to managed lines
        """
        if isinstance(data, str):
            self.__lines += data.splitlines(True)
        else:
            self.__lines += list(data)


class FilePathPlus:
    ADDED = "+"
    EXTANT = " "
    DELETED = "-"

    def __init__(self, path, status, expath=None):
        self.path = path
        self.status = status
        self.expath = expath

    def __str__(self):
        return "FilePathPlus(path={}, status=\"{}\", expath={})".format(self.path, self.status, self.expath)

    @staticmethod
    def fm_pair(pair, strip=lambda x: x):
        def get_path(x):
            return x if isinstance(x, str) else x.path
        path = None
        status = None
        after = get_path(pair.after)
        before = get_path(pair.before)
        if is_non_null(after):
            path = strip(after)
            status = FilePathPlus.EXTANT if is_non_null(before) else FilePathPlus.ADDED
        elif is_non_null(before):
            path = strip(before)
            status = FilePathPlus.DELETED
        else:
            return None
        return FilePathPlus(path=path, status=status, expath=None)


def gen_strip_level_function(level):
    """Return a function for stripping the specified levels off a file path"""
    def strip_n(path, level):
        try:
            return path.split(os.sep, level)[level]
        except IndexError:
            raise TooMayStripLevels(_("Strip level too large"), path, level)
    level = int(level)
    if level == 0:
        return lambda path: path
    return lambda path: path if path.startswith(os.sep) else strip_n(path, level)
