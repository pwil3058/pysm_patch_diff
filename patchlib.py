

from .diffs import Diff
        self.preambles = preambles if isinstance(preambles, Preambles) else Preambles.fm_list(preambles)
        for line in self.preambles.iter_lines():
            yield line