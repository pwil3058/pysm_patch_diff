from . import diff_preamble
from .diff_preamble import Preambles
from .pd_utils import TextLines as _Lines
from .pd_utils import PATH_RE_STR as _PATH_RE_STR
from .pd_utils import BEFORE_AFTER as _PAIR
from .pd_utils import FilePathPlus
from .pd_utils import gen_strip_level_function
from .pd_utils import file_path_fm_pair as _file_path_fm_pair
from .pd_utils import is_non_null as _is_non_null
        return diffstat.DiffStats()
        stats = diffstat.DiffStats()
        stats = diffstat.DiffStats()
        stats = diffstat.DiffStats()
        preambles, index = diff_preamble.get_preambles_at(lines, start_index, raise_if_malformed)
            return diffstat.DiffStats()
        patch = Patch.parse_text(text, num_strip_levels=num_strip_levels)
            text = "-\n\n%s\n" %  diffstat.format_diffstat_list(stats)
        sl = self._adjusted_strip_level(strip_level)
        return list(diffstat.PathDiffStats.iter_fm_diff_pluses(self.diff_pluses, sl))