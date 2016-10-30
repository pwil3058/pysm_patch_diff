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

"""Helper functions, classes and mixins for Patch Management GUIs"""

__all__ = ["PatchListData", "NullPatchListData", "InterfaceMixin"]
__author__ = "Peter Williams <pwil3058@gmail.com>"

from .. import pm

from ..bab import CmdResult

from ..gtx import table

class PatchListData(table.TableData):
    @property
    def selected_guards(self):
        return self._selected_guards

class NullPatchListData(table.NullTableData):
    @property
    def selected_guards(self):
        return []

class InterfaceMixin:
    @classmethod
    def _add_extra_patch_file_paths(cls, file_paths):
        patch_file_paths = cls.get_patch_files()
        ep_file_paths_set = {fp for fp in file_paths if fp not in patch_file_paths}
        if ep_file_paths_set:
            return cls.do_add_files(ep_file_paths_set)
        return CmdResult.ok()
    @classmethod
    def do_export_patch_as(cls, patch_name, export_file_name=None, force=False, overwrite=False):
        if not force:
            result = cls._check_patch_export_status(patch_name)
            if result:
                return result
        if not export_file_name:
            export_file_name = utils.convert_patchname_to_filename(patch_name)
        if not overwrite and os.path.exists(export_file_name):
            emsg = _("{0}: file already exists.\n").format(export_file_name)
            return CmdResult.error(stderr=emsg) + CmdResult.Suggest.OVERWRITE_OR_RENAME
        # NB we don't use shutil.copyfile() here as names may dictate (de)compression
        return utils.set_file_contents(export_file_name, cls.get_patch_text(patch_name))
    @classmethod
    def do_set_patch_description(cls, patch_name, description, overwrite=False):
        from ..gtx import console
        result = pm.set_patch_file_description(cls.get_patch_file_path(patch_name), description, overwrite=overwrite)
        if result.is_ok:
            console.LOG.append_entry(_("set description for \"{0}\" patch.\n{1}\n").format(patch_name, description))
        return result
    @classmethod
    def get_patch_description(cls, patch_name):
        return pm.get_patch_file_description(cls.get_patch_file_path(patch_name))
