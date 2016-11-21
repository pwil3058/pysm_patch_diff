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
from . import gitbase85

from .diffstat import DiffStat
# TODO: convert methods that return lists to iterators
_CHUNK = collections.namedtuple("_CHUNK", ["start", "length"])
_HUNK = collections.namedtuple("_HUNK", ["offset", "start", "length", "numlines"])
_PAIR = collections.namedtuple("_PAIR", ["before", "after"])
_FILE_AND_TS = collections.namedtuple("_FILE_AND_TS", ["path", "timestamp"])
_FILE_AND_TWS_LINES = collections.namedtuple("_FILE_AND_TWS_LINES", ["path", "tws_lines"])
_DIFF_DATA = collections.namedtuple("_DIFF_DATA", ["file_data", "hunks"])
_PATH_RE_STR = """"([^"]+)"|(\S+)"""
_TIMESTAMP_RE_STR = "\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{9})? [-+]{1}\d{4}"
_ALT_TIMESTAMP_RE_STR = "[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4} [-+]{1}\d{4}"
_EITHER_TS_RE_STR = "(%s|%s)" % (_TIMESTAMP_RE_STR, _ALT_TIMESTAMP_RE_STR)



class DataError(ParseError):
    pass


class Bug(Exception):
    pass

    """Return a function for stripping the specified levels off a file path"""
            raise TooMayStripLevels(_("Strip level too large"), path, level)
    """Return the given line with any trailing white space removed"""
    return re.sub("[ \t]+$", "", line)


        return "".join(self.lines)



    def __init__(self, text=""):
            if not line.startswith("#"):






        if text and not text.endswith("\n"):
            text += "\n"

        if text and not text.endswith("\n"):
            text += "\n"

        if text and not text.endswith("\n"):
            text += "\n"

    return path and path != "/dev/null"

    def get_path(x):
        return x if isinstance(x, str) else x.path

    def get_path(x):
        return x if isinstance(x, str) else x.path


    def get_path(x):
        return x if isinstance(x, str) else x.path

    ADDED = "+"
    EXTANT = " "
    DELETED = "-"


        def get_path(x):
            return x if isinstance(x, str) else x.path



        """Parse list of lines and return a valid Preamble or raise exception"""
            raise ParseError(_("Not a valid preamble."))

        """Parse text and return a valid Preamble or raise exception"""





        "old mode": re.compile("^(old mode)\s+(\d*)$"),
        "new mode": re.compile("^(new mode)\s+(\d*)$"),
        "deleted file mode": re.compile("^(deleted file mode)\s+(\d*)$"),
        "new file mode":  re.compile("^(new file mode)\s+(\d*)$"),
        "copy from": re.compile("^(copy from)\s+({0})$".format(_PATH_RE_STR)),
        "copy to": re.compile("^(copy to)\s+({0})$".format(_PATH_RE_STR)),
        "rename from": re.compile("^(rename from)\s+({0})$".format(_PATH_RE_STR)),
        "rename to": re.compile("^(rename to)\s+({0})$".format(_PATH_RE_STR)),
        "similarity index": re.compile("^(similarity index)\s+((\d*)%)$"),
        "dissimilarity index": re.compile("^(dissimilarity index)\s+((\d*)%)$"),
        "index": re.compile("^(index)\s+(([a-fA-F0-9]+)..([a-fA-F0-9]+)( (\d*))?)$"),


        Preamble.__init__(self, "git", lines=lines, file_data=file_data, extras=extras)



        for key in ["copy from", "rename from"]:

            return None  # means "don't know"

    CRE = re.compile("^diff(\s.+)\s+({0})\s+({1})$".format(_PATH_RE_STR, _PATH_RE_STR))

        if not match or (match.group(1) and match.group(1).find("--git") != -1):

        Preamble.__init__(self, "diff", lines=lines, file_data=file_data, extras=extras)




        Preamble.__init__(self, "index", lines=lines, file_data=file_data, extras=extras)


    path_precedence = ["index", "git", "diff"]
    expath_precedence = ["git", "index", "diff"]

            preamble, index = Preamble.get_preamble_at(lines, index,
                                                       raise_if_malformed,
                                                       exclude_subtypes_in=already_seen)

        """Parse list of lines and return a valid Preambles list or raise exception"""
            raise ParseError(_("Not a valid preamble list."))

        """Parse text and return a valid Preambles list or raise exception"""


        return "".join([str(preamble) for preamble in self])












        """generic function that works for unified and context diffs"""
                raise ParseError(_("Missing unified diff after file data."), index)
                raise ParseError(_("Expected unified diff hunks not found."), index)


        """Parse list of lines and return a valid Diff or raise exception"""
            raise ParseError(_("Not a valid diff."))

        """Parse text and return a valid DiffPlus or raise exception"""


        return str(self.header) + "".join([str(hunk) for hunk in self.hunks])









            if self.lines[index].startswith("+"):
            elif self.lines[index].startswith(" "):
            elif DEBUG and not self.lines[index].startswith("-"):
                raise Bug("Unexpected end of unified diff hunk.")

            if self.lines[index].startswith("-"):
                stats.incr("deleted")
            elif self.lines[index].startswith("+"):
                stats.incr("inserted")
            elif DEBUG and not self.lines[index].startswith(" "):
                raise Bug("Unexpected end of unified diff hunk.")



    BEFORE_FILE_CRE = re.compile("^--- ({0})(\s+{1})?(.*)$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile("^\+\+\+ ({0})(\s+{1})?(.*)$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))



                if lines[index].startswith("-"):
                elif lines[index].startswith("+"):
                elif lines[index].startswith(" "):
                elif not lines[index].startswith("\\"):
                    raise ParseError(_("Unexpected end of unified diff hunk."), index)
            if index < len(lines) and lines[index].startswith("\\"):
            raise ParseError(_("Unexpected end of patch text."))


        Diff.__init__(self, "unified", lines, file_data, hunks)


            if self.lines[index].startswith("+ ") or self.lines[index].startswith("! "):
            elif DEBUG and not self.lines[index].startswith("  "):
                raise Bug("Unexpected end of context diff hunk.")

            if self.lines[index].startswith("- "):
                stats.incr("deleted")
            elif self.lines[index].startswith("! "):
                stats.incr("modified")
            elif DEBUG and not self.lines[index].startswith("  "):
                raise Bug("Unexpected end of context diff \"before\" hunk.")
            if self.lines[index].startswith("+ "):
                stats.incr("inserted")
            elif self.lines[index].startswith("! "):
                stats.incr("modified")
            elif DEBUG and not self.lines[index].startswith("  "):
                raise Bug("Unexpected end of context diff \"after\" hunk.")



    BEFORE_FILE_CRE = re.compile("^\*\*\* ({0})(\s+{1})?$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    AFTER_FILE_CRE = re.compile("^--- ({0})(\s+{1})?$".format(_PATH_RE_STR, _EITHER_TS_RE_STR))
    HUNK_START_CRE = re.compile("^\*{15}\s*(.*)$")
    HUNK_BEFORE_CRE = re.compile("^\*\*\*\s+(\d+)(,(\d+))?\s+\*\*\*\*\s*(.*)$")
    HUNK_AFTER_CRE = re.compile("^---\s+(\d+)(,(\d+))?\s+----(.*)$")






                if lines[index].startswith("\ "):
                    raise ParseError(_("Failed to find context diff \"after\" hunk."), index)
                if not lines[index].startswith(("! ", "+ ", "  ")):
                    raise ParseError(_("Unexpected end of context diff hunk."), index)
            if index < len(lines) and lines[index].startswith("\ "):
            raise ParseError(_("Unexpected end of patch text."))
        before_hunk = _HUNK(before_start_index - start_index,
                            before_chunk.start,
                            before_chunk.length,
                            after_start_index - before_start_index)
        after_hunk = _HUNK(after_start_index - start_index,
                           after_chunk.start,
                           after_chunk.length,
                           index - after_start_index)


        Diff.__init__(self, "context", lines, file_data, hunks)

    LITERAL, DELTA = ("literal", "delta")




    START_CRE = re.compile("^GIT binary patch$")
    DATA_START_CRE = re.compile("^(literal|delta) (\d+)$")

            raise DataError(_("Inconsistent git binary patch data."), lineno=start_index)
            emsg = _("Git binary patch expected {0} bytes. Got {1} bytes.").format(size, raw_size)
            raise DataError(emsg, lineno=start_index)

            raise ParseError(_("No content in GIT binary patch text."))

        Diff.__init__(self, "git_binary", lines, None, None)


    """Class to hold diff (headerless) information relavent to a single file.
    Includes (optional) preambles and trailing junk such as quilt's separators."""

        """Parse list of lines and return a valid DiffPlus or raise exception"""
            raise ParseError(_("Not a valid (optionally preambled) diff."))

        """Parse text and return a valid DiffPlus or raise exception"""





        git_preamble = self.get_preamble_for_type("git")
            for key in ["new mode", "new file mode"]:

        git_preamble = self.get_preamble_for_type("git")
        return None  # means "don't know"








    """Class to hold patch information relavent to multiple files with
    an optional header (or a single file with a header)."""
        """Parse list of lines and return a Patch instance"""
        patch.set_header("".join(lines[0:diff_starts_at]))

        """Parse text and return a Patch instance."""

        """Parse email text and return a Patch instance."""
        subject = msg.get("Subject")
            text = re.sub("\r\n", os.linesep, msg.get_payload())
            patch.set_description("\n".join([subject, descr]))

        """Parse a text file and return a Patch instance."""

        """Parse a text file and return a Patch instance."""




            if diff_plus.preambles.get_index_for_type("git") is not None:

        relevance = collections.namedtuple("relevance", ["goodness", "missing", "unexpected"])



        return "" if self.header is None else self.header.get_comments()


        return "" if self.header is None else self.header.get_description()


        return "" if self.header is None else self.header.get_diffstat()

            text = "-\n\n%s\n" % stats.list_format_string()

        string = "" if self.header is None else str(self.header)







        def fds(diff_plus):
            file_path = diff_plus.get_file_path(strip_level=strip_level)
            d_stats = diff_plus.get_diffstat_stats()
            return DiffStat.PathStats(file_path, d_stats)
        return DiffStat.PathStatsList((fds(diff_plus) for diff_plus in self.diff_pluses))


