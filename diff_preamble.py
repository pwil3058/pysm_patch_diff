import os
class ParseError(Exception):
    """Exception to signal parsing error
    """
    def __init__(self, message, lineno=None):
        Exception.__init__(self)
        self.message = message
        self.lineno = lineno


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

    @staticmethod
    def generate_preamble_lines(file_path, before=None, after=None, came_from=None):
        return ["diff {0} {1}\n".format(os.path.join("a", file_path), os.path.join("b", file_path)), ]

    @staticmethod
    def generate_preamble_lines(file_path, before=None, after=None, came_from=None):
        return ["Index: {1}\n".format(file_path), ]

