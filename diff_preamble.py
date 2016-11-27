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

"""Extract various diff preambles from text lines"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


import collections
import re

from .pd_utils import TextLines, PATH_RE_STR, BEFORE_AFTER
from .pd_utils import FilePathPlus
from .pd_utils import file_path_fm_pair as _file_path_fm_pair
from .pd_utils import gen_strip_level_function


class _Preamble(TextLines):
    """Generic diff preamble
    """
    preamble_type_id = None
    def __init__(self, lines, file_data, extras=None):
        TextLines.__init__(self, lines)
        self.file_data = file_data
        self.extras = extras if extras else {}

    def get_file_path(self, strip_level=0):
        """Extract the file path from the preamble
        """
        strip = gen_strip_level_function(strip_level)
        if isinstance(self.file_data, str):
            return strip(self.file_data)
        elif isinstance(self.file_data, BEFORE_AFTER):
            return _file_path_fm_pair(self.file_data, strip)
        else:
            return None

    def get_file_path_plus(self, strip_level=0):
        """Extract the file path and status from the preamble
        """
        if isinstance(self.file_data, str):
            return FilePathPlus(path=self.get_file_path(strip_level), status=None, expath=None)
        elif isinstance(self.file_data, BEFORE_AFTER):
            return FilePathPlus.fm_pair(self.file_data, gen_strip_level_function(strip_level))
        else:
            return None

    def get_file_expath(self, strip_level=0):
        """Extract the previous path of the file from the preamble
        """
        return None


class GitPreamble(_Preamble):
    preamble_type_id = "git"
    DIFF_CRE = re.compile("^diff\s+--git\s+({0})\s+({1})$".format(PATH_RE_STR, PATH_RE_STR))
    EXTRAS_CRES = {
        "old mode": re.compile("^(old mode)\s+(\d*)$"),
        "new mode": re.compile("^(new mode)\s+(\d*)$"),
        "deleted file mode": re.compile("^(deleted file mode)\s+(\d*)$"),
        "new file mode":  re.compile("^(new file mode)\s+(\d*)$"),
        "copy from": re.compile("^(copy from)\s+({0})$".format(PATH_RE_STR)),
        "copy to": re.compile("^(copy to)\s+({0})$".format(PATH_RE_STR)),
        "rename from": re.compile("^(rename from)\s+({0})$".format(PATH_RE_STR)),
        "rename to": re.compile("^(rename to)\s+({0})$".format(PATH_RE_STR)),
        "similarity index": re.compile("^(similarity index)\s+((\d*)%)$"),
        "dissimilarity index": re.compile("^(dissimilarity index)\s+((\d*)%)$"),
        "index": re.compile("^(index)\s+(([a-fA-F0-9]+)..([a-fA-F0-9]+)( (\d*))?)$"),
    }

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        match = cls.DIFF_CRE.match(lines[index])
        if not match:
            return (None, index)
        file1 = match.group(3) if match.group(3) else match.group(4)
        file2 = match.group(6) if match.group(6) else match.group(7)
        extras = {}
        next_index = index + 1
        while next_index < len(lines):
            found = False
            for cre in cls.EXTRAS_CRES:
                match = cls.EXTRAS_CRES[cre].match(lines[next_index])
                if match:
                    extras[match.group(1)] = match.group(2)
                    next_index += 1
                    found = True
                    break
            if not found:
                break
        return (cls(lines[index:next_index], BEFORE_AFTER(file1, file2), extras), next_index)

    def __init__(self, lines, file_data, extras=None):
        _Preamble.__init__(self, lines=lines, file_data=file_data, extras=extras)

    def get_file_path(self, strip_level=0):
        strip = gen_strip_level_function(strip_level)
        return _file_path_fm_pair(self.file_data, strip)

    def get_file_path_plus(self, strip_level=0):
        path_plus = _Preamble.get_file_path_plus(self, strip_level=strip_level)
        if path_plus and path_plus.status == FilePathPlus.ADDED:
            path_plus.expath = self.get_file_expath(strip_level=strip_level)
        return path_plus

    def get_file_expath(self, strip_level=0):
        for key in ["copy from", "rename from"]:
            if key in self.extras:
                strip = gen_strip_level_function(strip_level)
                return strip(self.extras[key])
        return None

    def is_compatible_with(self, git_hash):
        try:
            before_hash, _dummy = self.extras["index"].split("..")
            if len(before_hash) > len(git_hash):
                return before_hash.startswith(git_hash)
            else:
                return git_hash.startswith(before_hash)
        except KeyError:
            return None  # means "don't know"


class DiffPreamble(_Preamble):
    preamble_type_id = "diff"
    CRE = re.compile("^diff(\s.+)\s+({0})\s+({1})$".format(PATH_RE_STR, PATH_RE_STR))

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        match = cls.CRE.match(lines[index])
        if not match or (match.group(1) and match.group(1).find("--git") != -1):
            return (None, index)
        file1 = match.group(3) if match.group(3) else match.group(4)
        file2 = match.group(6) if match.group(6) else match.group(7)
        next_index = index + 1
        return (cls(lines[index:next_index], BEFORE_AFTER(file1, file2), match.group(1)), next_index)

    def __init__(self, lines, file_data, extras=None):
        _Preamble.__init__(self, lines=lines, file_data=file_data, extras=extras)

    def get_file_path(self, strip_level=0):
        strip = gen_strip_level_function(strip_level)
        return _file_path_fm_pair(self.file_data, strip)


class IndexPreamble(_Preamble):
    preamble_type_id = "index"
    FILE_RCE = re.compile("^Index:\s+({0})(.*)$".format(PATH_RE_STR))
    SEP_RCE = re.compile("^==*$")

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        match = cls.FILE_RCE.match(lines[index])
        if not match:
            return (None, index)
        filepath = match.group(2) if match.group(2) else match.group(3)
        next_index = index + (2 if (index + 1) < len(lines) and cls.SEP_RCE.match(lines[index + 1]) else 1)
        return (cls(lines[index:next_index], filepath), next_index)

    def __init__(self, lines, file_data, extras=None):
        _Preamble.__init__(self, lines=lines, file_data=file_data, extras=extras)

    def get_file_path(self, strip_level=0):
        strip = gen_strip_level_function(strip_level)
        return strip(self.file_data)


class Preambles(collections.OrderedDict):
    path_precedence = ["index", "git", "diff"]
    expath_precedence = ["git", "index", "diff"]

    def __str__(self):
        return "".join(self.iter_lines())

    def iter_lines(self):
        return (line for preamble in self.values() for line in preamble)

    @classmethod
    def fm_list(cls, list_arg):
        preambles = cls()
        for pramble in list_arg:
            preambles[preamble.preamble_type_id] = preamble
        return preambles

    def get_file_path(self, strip_level=0):
        for preamble_type_id in self.path_precedence:
            preamble = self.get(preamble_type_id)
            if preamble:
                path = preamble.get_file_path(strip_level=strip_level)
                if path:
                    return path
        return None

    def get_file_path_plus(self, strip_level=0):
        for preamble_type_id in self.path_precedence:
            preamble = self.get(preamble_type_id)
            if preamble:
                path_plus = preamble.get_file_path_plus(strip_level=strip_level)
                if path_plus:
                    return path_plus
        return None

    def get_file_expath(self, strip_level=0):
        for preamble_type_id in self.expath_precedence:
            preamble = self.get(preamble_type_id)
            if preamble:
                expath = preamble.get_file_expath(strip_level=strip_level)
                if path:
                    return expath
        return None

DIFF_PREAMBLE_TYPES = [GitPreamble, DiffPreamble, IndexPreamble]
DIFF_PREAMBLE_TYPE_IDS = [dpt.preamble_type_id for dpt in DIFF_PREAMBLE_TYPES]

def get_preamble_at(lines, index, raise_if_malformed, exclude_subtypes_in=None):
    for subtype in DIFF_PREAMBLE_TYPES:
        if exclude_subtypes_in and subtype in exclude_subtypes_in:
            continue
        preamble, next_index = subtype.get_preamble_at(lines, index, raise_if_malformed)
        if preamble is not None:
            return (preamble, next_index)
    return (None, index)

def get_preambles_at(lines, index, raise_if_malformed):
    preambles = Preambles()
    # make sure we don't get more than one preamble of the same type
    already_seen = set()
    while index < len(lines):
        preamble, index = get_preamble_at(lines, index, raise_if_malformed, exclude_subtypes_in=already_seen)
        if preamble:
            already_seen.add(type(preamble))
            preambles[preamble.preamble_type_id] = preamble
        else:
            break
    return (preambles, index)
