        from .pd_utils import DiffOutcome
        file_path, outcome = self.diff.get_file_path_and_outcome(strip_level) if self.diff else (None, None)
        if not file_path:
            return self.preambles.get_file_path_plus(strip_level=strip_level)
        elif outcome == DiffOutcome.CREATED:
            return FilePathPlus(file_path, FilePathPlus.ADDED, self.preambles.get_file_expath(strip_level=strip_level))
        elif outcome == DiffOutcome.DELETED:
            return FilePathPlus(file_path, FilePathPlus.DELETED, None)
        else:
            return FilePathPlus(file_path, FilePathPlus.EXTANT, None)