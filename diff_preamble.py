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


import collections
import os
import re

from .pd_utils import TextLines, PATH_RE_STR, BEFORE_AFTER
from .pd_utils import FilePathPlus
from .pd_utils import file_path_fm_pair as _file_path_fm_pair
from .pd_utils import gen_strip_level_function

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


class ParseError(Exception):
    """Exception to signal parsing error
    """
    def __init__(self, message, lineno=None):
        Exception.__init__(self)
        self.message = message
        self.lineno = lineno


class _Preamble(TextLines):
    """Generic diff preamble
    """
    preamble_type_id = None

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        """Parse "lines" starting at "index" for a "cls" style preamble.
        Return a "cls" preamble and the index of the first line after the
        preamble if found else return None and the index unchanged.
        """
        print(cls, lines, index, raise_if_malformed)
        return (NotImplemented, index)

    @classmethod
    def parse_lines(cls, lines):
        """Parse list of lines and return a valid preamble or raise exception"""
        preamble, index = cls.get_preamble_at(lines, 0, raise_if_malformed=True)
        if not preamble or index < len(lines):
            raise ParseError(_("Not a valid \"{}\" diff.").format(cls.preamble_type_id), index)
        return preamble

    @classmethod
    def parse_text(cls, text):
        """Parse text and return a valid preamble or raise exception"""
        return cls.parse_lines(text.splitlines(True))

    @staticmethod
    def generate_preamble_lines(file_path, before, after, came_from=None):
        """Generate preamble lines
        """
        print(file_path, before, after, came_from)
        return NotImplemented

    @classmethod
    def generate_preamble(cls, file_path, before, after, came_from=None):
        """Generate "clc" preamble
        """
        return cls.parse_lines(cls.generate_preamble_lines(file_path, before, after, came_from))

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

    @staticmethod
    def get_file_expath(strip_level=0):
        """Extract the previous path of the file from the preamble
        """
        return None


class GitPreamble(_Preamble):
    """Encapsulation of "git" diff preamble used in patches
    """
    preamble_type_id = "git"
    DIFF_CRE = re.compile(r"^diff\s+--git\s+({0})\s+({1})$".format(PATH_RE_STR, PATH_RE_STR))
    EXTRAS_CRES = {
        "old mode": re.compile(r"^(old mode)\s+(\d*)$"),
        "new mode": re.compile(r"^(new mode)\s+(\d*)$"),
        "deleted file mode": re.compile(r"^(deleted file mode)\s+(\d*)$"),
        "new file mode":  re.compile(r"^(new file mode)\s+(\d*)$"),
        "copy from": re.compile(r"^(copy from)\s+({0})$".format(PATH_RE_STR)),
        "copy to": re.compile(r"^(copy to)\s+({0})$".format(PATH_RE_STR)),
        "rename from": re.compile(r"^(rename from)\s+({0})$".format(PATH_RE_STR)),
        "rename to": re.compile(r"^(rename to)\s+({0})$".format(PATH_RE_STR)),
        "similarity index": re.compile(r"^(similarity index)\s+((\d*)%)$"),
        "dissimilarity index": re.compile(r"^(dissimilarity index)\s+((\d*)%)$"),
        "index": re.compile(r"^(index)\s+(([a-fA-F0-9]+)..([a-fA-F0-9]+)( (\d*))?)$"),
    }

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        """Parse "lines" starting at "index" for a "git" style preamble.
        Return a GitPreamble and the index of the first line after the
        preamble if found else return None and the index unchanged.
        """
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

    @staticmethod
    def generate_preamble_lines(file_path, before, after, came_from=None):
        if came_from:
            lines = ["diff --git {0} {1}\n".format(os.path.join("a", came_from.file_path), os.path.join("b", file_path)), ]
        else:
            lines = ["diff --git {0} {1}\n".format(os.path.join("a", file_path), os.path.join("b", file_path)), ]
        if before is None:
            if after is not None:
                lines.append("new file mode {0:07o}\n".format(after.lstats.st_mode))
        elif after is None:
            lines.append("deleted file mode {0:07o}\n".format(before.lstats.st_mode))
        else:
            if before.lstats.st_mode != after.lstats.st_mode:
                lines.append("old mode {0:07o}\n".format(before.lstats.st_mode))
                lines.append("new mode {0:07o}\n".format(after.lstats.st_mode))
        if came_from:
            if came_from.as_rename:
                lines.append("rename from {0}\n".format(came_from.file_path))
                lines.append("rename to {0}\n".format(file_path))
            else:
                lines.append("copy from {0}\n".format(came_from.file_path))
                lines.append("copy to {0}\n".format(file_path))
        if before or after:
            hash_line = "index {0}".format(before.git_hash if before else "0" * 48)
            hash_line += "..{0}".format(after.git_hash if after else "0" * 48)
            hash_line += " {0:07o}\n".format(after.lstats.st_mode) if after and before and before.lstats.st_mode == after.lstats.st_mode else "\n"
            lines.append(hash_line)
        return lines

    def __init__(self, lines, file_data, extras=None):
        _Preamble.__init__(self, lines=lines, file_data=file_data, extras=extras)

    def get_file_path(self, strip_level=0):
        """Extract the file path from this preamble
        """
        strip = gen_strip_level_function(strip_level)
        return _file_path_fm_pair(self.file_data, strip)

    def get_file_path_plus(self, strip_level=0):
        """Extract the file path plus status data from this preamble
        """
        path_plus = _Preamble.get_file_path_plus(self, strip_level=strip_level)
        if path_plus and path_plus.status == FilePathPlus.ADDED:
            path_plus.expath = self.get_file_expath(strip_level=strip_level)
        return path_plus

    def get_file_expath(self, strip_level=0):
        """Get the path of the file that this file is a rename or copy of
        """
        for key in ["copy from", "rename from"]:
            if key in self.extras:
                strip = gen_strip_level_function(strip_level)
                return strip(self.extras[key])
        return None

    def is_compatible_with(self, git_hash):
        """Is the "before" git hash in the preamble compatible with "git_hash"?
        """
        try:
            before_hash = self.extras["index"].split("..")[0]
            if len(before_hash) > len(git_hash):
                return before_hash.startswith(git_hash)
            else:
                return git_hash.startswith(before_hash)
        except KeyError:
            return None  # means "don't know"


class DiffPreamble(_Preamble):
    """Encapsulate the simple "diff" style diff preamble
    """
    preamble_type_id = "diff"
    CRE = re.compile(r"^diff(\s.+)\s+({0})\s+({1})$".format(PATH_RE_STR, PATH_RE_STR))

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        """Parse "lines" starting at "index" for a "diff" style preamble.
        Return a DiffPreamble and the index of the first line after the
        preamble if found else return None and the index unchanged.
        """
        match = cls.CRE.match(lines[index])
        if not match or (match.group(1) and match.group(1).find("--git") != -1):
            return (None, index)
        file1 = match.group(3) if match.group(3) else match.group(4)
        file2 = match.group(6) if match.group(6) else match.group(7)
        next_index = index + 1
        return (cls(lines[index:next_index], BEFORE_AFTER(file1, file2), match.group(1)), next_index)

    @staticmethod
    def generate_preamble_lines(file_path, before=None, after=None, came_from=None):
        return ["diff {0} {1}\n".format(os.path.join("a", file_path), os.path.join("b", file_path)), ]

    def __init__(self, lines, file_data, extras=None):
        _Preamble.__init__(self, lines=lines, file_data=file_data, extras=extras)

    def get_file_path(self, strip_level=0):
        """Extract the file path from this preamble
        """
        strip = gen_strip_level_function(strip_level)
        return _file_path_fm_pair(self.file_data, strip)


class IndexPreamble(_Preamble):
    """Encapsulate the simple "Index" style diff preamble
    """
    preamble_type_id = "index"
    FILE_RCE = re.compile(r"^Index:\s+({0})(.*)$".format(PATH_RE_STR))
    SEP_RCE = re.compile(r"^==*$")

    @classmethod
    def get_preamble_at(cls, lines, index, raise_if_malformed):
        """Parse "lines" starting at "index" for an "Index" style preamble.
        Return a IndexPreamble and the index of the first line after the
        preamble if found else return None and the index unchanged.
        """
        match = cls.FILE_RCE.match(lines[index])
        if not match:
            return (None, index)
        filepath = match.group(2) if match.group(2) else match.group(3)
        next_index = index + (2 if (index + 1) < len(lines) and cls.SEP_RCE.match(lines[index + 1]) else 1)
        return (cls(lines[index:next_index], filepath), next_index)

    @staticmethod
    def generate_preamble_lines(file_path, before=None, after=None, came_from=None):
        return ["Index: {1}\n".format(file_path), ]

    def __init__(self, lines, file_data, extras=None):
        _Preamble.__init__(self, lines=lines, file_data=file_data, extras=extras)

    def get_file_path(self, strip_level=0):
        """Extract the file path from this preamble
        """
        strip = gen_strip_level_function(strip_level)
        return strip(self.file_data)


class Preambles(collections.OrderedDict):
    """Maintain an ordered list of the preambles preceding a diff.
    This caters for the case where patch generators get overexcited
    and include more than one preamble type for a file's diff within a
    patch (used to be common but now rare)
    """
    path_precedence = ["index", "git", "diff"]
    expath_precedence = ["git", "index", "diff"]

    def __str__(self):
        return "".join(self.iter_lines())

    def iter_lines(self):
        """Iterate over the lines in all preambles in the order in which
        they were encountered.
        """
        return (line for preamble in self.values() for line in preamble)

    @classmethod
    def fm_list(cls, list_arg):
        """Create a Preambles instance from a list of preambles
        """
        preambles = cls()
        for preamble in list_arg:
            preambles[preamble.preamble_type_id] = preamble
        return preambles

    def get_file_path(self, strip_level=0):
        """Extract the file path from the preambles
        """
        for preamble_type_id in self.path_precedence:
            preamble = self.get(preamble_type_id)
            if preamble:
                path = preamble.get_file_path(strip_level=strip_level)
                if path:
                    return path
        return None

    def get_file_path_plus(self, strip_level=0):
        """Extract the file path and status from the preambles
        """
        for preamble_type_id in self.path_precedence:
            preamble = self.get(preamble_type_id)
            if preamble:
                path_plus = preamble.get_file_path_plus(strip_level=strip_level)
                if path_plus:
                    return path_plus
        return None

    def get_file_expath(self, strip_level=0):
        """Get the path of the file that this file is a rename or copy of
        """
        for preamble_type_id in self.expath_precedence:
            preamble = self.get(preamble_type_id)
            if preamble:
                expath = preamble.get_file_expath(strip_level=strip_level)
                if expath:
                    return expath
        return None

DIFF_PREAMBLE_TYPES = [GitPreamble, DiffPreamble, IndexPreamble]
DIFF_PREAMBLE_TYPE_IDS = [dpt.preamble_type_id for dpt in DIFF_PREAMBLE_TYPES]


def get_preamble_at(lines, index, raise_if_malformed, exclude_subtypes_in=None):
    """Parse "lines" starting at "index" looking for a preamble
    """
    for subtype in DIFF_PREAMBLE_TYPES:
        if exclude_subtypes_in and subtype in exclude_subtypes_in:
            continue
        preamble, next_index = subtype.get_preamble_at(lines, index, raise_if_malformed)
        if preamble is not None:
            return (preamble, next_index)
    return (None, index)


def get_preambles_at(lines, index, raise_if_malformed):
    """Parse "lines" starting at "index" looking for a preambles
    """
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


def preamble_parse_lines(lines):
    """Parse "lines" and return the preamble contained therein
    """
    preamble, index = get_preamble_at(lines, 0, raise_if_malformed=True)
    assert index == len(lines), "{}:{}:{}".format(preamble, index, lines)
    return preamble
