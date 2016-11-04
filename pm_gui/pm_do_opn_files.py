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

"""Provide Patch Manager "do" operations that act on files"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

from ..gtx import xtnl_edit

from . import ifce as pm_gui_ifce

class PMDoOpnFilesMixin:
    def pm_do_add_files(self, file_paths):
        do_op = lambda absorb=False, force=False : pm_gui_ifce.PM.do_add_files_to_top_patch(file_paths, absorb=absorb, force=force)
        refresh_op = lambda : pm_gui_ifce.PM.do_refresh_overlapped_files(file_paths)
        return self.do_op_force_refresh_or_absorb(do_op, refresh_op)

    def pm_do_add_new_file(self, open_for_edit=False):
        from ..bab import os_utils
        new_file_path = self.ask_file_path(_("Enter path for new file"), existing=False)
        if not new_file_path:
            return
        with self.showing_busy():
            result = os_utils.os_create_file(new_file_path)
        self.report_any_problems(result)
        if not result.is_ok:
            return result
        result = self.pm_do_add_files([new_file_path])
        if result.is_ok and open_for_edit:
            xtnl_edit.edit_files_extern([new_file_path])
        return result

    def pm_do_copy_file(self, file_path):
        destn = self.ask_destination([file_path])
        if not destn:
            return
        do_op = lambda destn, overwrite=False : pm_gui_ifce.PM.do_copy_file_to_top_patch(file_path, destn, overwrite=overwrite)
        return self.do_op_rename_overwrite_or_cancel(destn, do_op)

    def pm_do_copy_files(self, file_paths):
        destn = self.ask_destination(file_paths)
        if not destn:
            return
        do_op = lambda destn, overwrite=False : pm_gui_ifce.PM.do_copy_files(file_paths, destn, overwrite=overwrite)
        return self.do_op_rename_overwrite_or_cancel(destn, do_op)

    def pm_do_delete_files(self, file_paths):
        if len(file_paths) == 0:
            return
        emsg = '\n'.join(file_paths + ["", _('Confirm delete selected file(s) in top patch?')])
        if not self.ask_ok_cancel(emsg):
            return
        with self.showing_busy():
            result = pm_gui_ifce.PM.do_delete_files_in_top_patch(file_paths)
        self.report_any_problems(result)
        return result

    def pm_do_drop_files(self, file_paths):
        if len(file_paths) == 0:
            return
        emsg = '\n'.join(file_paths + ["", _('Confirm drop selected file(s) from patch?')])
        if not self.ask_ok_cancel(emsg):
            return
        with self.showing_busy():
            result = pm_gui_ifce.PM.do_drop_files_from_patch(file_paths, patch_name=None)
        self.report_any_problems(result)

    def pm_do_edit_files(self, file_paths):
        if len(file_paths) == 0:
            return
        new_file_paths = pm_gui_ifce.PM.get_filepaths_not_in_patch(None, file_paths)
        if new_file_paths and not self.pm_do_add_files(new_file_paths).is_ok:
            return
        xtnl_edit.edit_files_extern(file_paths)

    def pm_do_extdiff_for_file(self, file_path, patch_name=None):
        from ..patch_diff_gui import diff
        files = pm_gui_ifce.PM.get_extdiff_files_for(file_path=file_path, patch_name=patch_name)
        self.report_any_problems(diff.launch_external_diff(files.original_version, files.patched_version))

    def pm_do_move_files(self, file_paths):
        destn = self.ask_destination(file_paths)
        if not destn:
            return
        do_op = lambda destn, force=False, overwrite=False : pm_gui_ifce.PM.do_move_files(file_paths, destn, force=force, overwrite=overwrite)
        refresh_op = lambda : pm_gui_ifce.PM.do_refresh_overlapped_files(file_paths)
        return self.do_op_force_refresh_overwrite_or_rename(destn, do_op, refresh_op)

    @staticmethod
    def _launch_reconciliation_tool(file_a, file_b, file_c):
        from ..bab import options
        from ..bab import runext
        from ..bab import CmdResult
        reconciler = options.get("reconcile", "tool")
        if not reconciler:
            return CmdResult.warning(_("No reconciliation tool is defined.\n"))
        try:
            runext.run_cmd_in_bgnd([reconciler, file_a, file_b, file_c])
        except OSError as edata:
            return CmdResult.error(stderr=_("Error lanuching reconciliation tool \"{0}\": {1}\n").format(reconciler, edata.strerror))
        return CmdResult.ok()

    def pm_do_reconcile_file(self, file_path):
        file_paths = pm_gui_ifce.PM.get_reconciliation_paths(file_path=file_path)
        self.report_any_problems(self._launch_reconciliation_tool(file_paths.original_version, file_paths.patched_version, file_paths.stashed_version))

    def pm_do_rename_file(self, file_path):
        destn = self.ask_destination([file_path])
        if not destn:
            return
        do_op = lambda destn, force=False, overwrite=False : pm_gui_ifce.PM.do_rename_file_in_top_patch(file_path, destn, force=force, overwrite=overwrite)
        refresh_op = lambda : pm_gui_ifce.PM.do_refresh_overlapped_files([file_path])
        return self.do_op_force_refresh_overwrite_or_rename(destn, do_op, refresh_op)
