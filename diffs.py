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

"""Module to parse various type of "diff" instances when we don't
know what type of diff the text (lines) contain
"""

from . import context_diff
from . import git_binary_diff
from . import unified_diff

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"


class ParseError(Exception):
    """Exception to signal parsing error
    """
    def __init__(self, message, lineno=None):
        Exception.__init__(self)
        self.message = message
        self.lineno = lineno


def get_diff_at(lines, index, raise_if_malformed):
    """If there is a valid unified, context or git binary diff in
    "lines" starting at "index" extract and return it along with the
    index for the first line after the diff.
    """
    # NB. these are ordered by likelihood of being encountered (these days)
    for diff_type in [unified_diff, git_binary_diff, context_diff]:
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
