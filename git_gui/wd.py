### Copyright (C) 2005-2015 Peter Williams <pwil3058@gmail.com>
###
### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.
###
### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.
###
### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import collections
import os
import shutil

from gi.repository import Gtk
from gi.repository import GObject

from .. import scm
from ..scm.gui import scm_gui_ifce
from ..scm.gui import scm_actions
from ..scm.gui import scm_wspce

from ..git import git_utils

from ..bab import enotify
from ..bab import os_utils
from ..bab import utils

from ..gtx import actions
from ..gtx import dialogue
from ..gtx import file_tree
from ..gtx import xtnl_edit
from .. import wsm_icons

from ..git_gui import git_do_opn

class WDTreeModel(file_tree.FileTreeModel):
    UPDATE_EVENTS = os_utils.E_FILE_CHANGES|scm.E_NEW_SCM|scm.E_FILE_CHANGES|scm.E_WD_CHANGES
    AU_FILE_CHANGE_EVENT = scm.E_FILE_CHANGES|os_utils.E_FILE_CHANGES # event returned by auto_update() if changes found
    @staticmethod
    def _get_file_db():
        return scm_gui_ifce.SCM.get_wd_file_db()

AC_ONLY_SUBMODULES_SELECTED = actions.ActionCondns.new_flag()

def get_masked_seln_conditions(seln):
    if seln is None:
        return actions.MaskedCondns(0, AC_ONLY_SUBMODULES_SELECTED)
    sub_module_paths = git_utils.get_submodule_paths()
    model, selection = seln.get_selected_rows()
    for model_iter in selection:
        if model[model_iter][0].path[2:] not in sub_module_paths:
            return actions.MaskedCondns(0, AC_ONLY_SUBMODULES_SELECTED)
    return actions.MaskedCondns(AC_ONLY_SUBMODULES_SELECTED, AC_ONLY_SUBMODULES_SELECTED)

class WDTreeView(file_tree.FileTreeView, enotify.Listener, scm_actions.WDListenerMixin, git_do_opn.DoOpnMixin):
    MODEL = WDTreeModel
    UI_DESCR = \
    """
    <ui>
      <menubar name="wd_files_menubar">
        <menu name="wd_files_menu" action="wd_files_menu_files">
          <menuitem action="refresh_files"/>
        </menu>
      </menubar>
      <popup name="files_popup">
          <menuitem action="new_file"/>
        <separator/>
          <menuitem action="copy_fs_items"/>
          <menuitem action="move_fs_items"/>
          <menuitem action="rename_fs_item"/>
          <menuitem action="delete_fs_items"/>
      </popup>
      <popup name="scmic_files_popup">
        <placeholder name="selection_indifferent"/>
        <separator/>
        <placeholder name="selection">
          <separator/>
          <menuitem action="wd_edit_selected_files"/>
          <separator/>
          <menuitem action="wd_add_files_to_index"/>
          <menuitem action="wd_remove_files_in_index"/>
          <separator/>
          <menuitem action="wd_cd_to_submodule"/>
          <menuitem action="wd_remove_submodules"/>
        </placeholder>
        <separator/>
        <placeholder name="unique_selection"/>
          <menuitem action="copy_file_to_index"/>
          <menuitem action="rename_file_in_index"/>
          <menuitem action="launch_diff_tool_re_head"/>
        <separator/>
          <menuitem action="copy_fs_items"/>
          <menuitem action="move_fs_items"/>
          <menuitem action="rename_fs_item"/>
          <menuitem action="delete_fs_items"/>
        <placeholder name="no_selection"/>
        <separator/>
        <separator/>
        <placeholder name="make_selections"/>
        <separator/>
      </popup>
      <popup name="pmic_files_popup"/>
    </ui>
    """
    def __init__(self, show_hidden=False, hide_clean=False):
        file_tree.FileTreeView.__init__(self, show_hidden=show_hidden, hide_clean=hide_clean)
        enotify.Listener.__init__(self)
        scm_actions.WDListenerMixin.__init__(self)
        self._update_popup_cb()
        self.add_notification_cb(enotify.E_CHANGE_WD, self._update_popup_cb)
        self.get_selection().connect('changed', lambda seln: self.action_groups.update_condns(get_masked_seln_conditions(seln)))
    def _update_popup_cb(self, **kwargs):
        if scm_gui_ifce.SCM.in_valid_wspce:
            self.set_popup("/scmic_files_popup")
        else:
            self.set_popup(self.DEFAULT_POPUP)
    def populate_action_groups(self):
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ('wd_files_menu_files', None, _('Working Directory')),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|actions.AC_SELN_UNIQUE|file_tree.AC_ONLY_FILES_SELECTED].add_actions(
            [
                ("copy_file_to_index", Gtk.STOCK_COPY, _("Copy"), None,
                 _("Make a copy of the selected file in the index"),
                 lambda _action=None: self.git_do_copy_file_to_index(self.get_selected_fsi_path())
                ),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|AC_ONLY_SUBMODULES_SELECTED|actions.AC_SELN_UNIQUE].add_actions(
            [
                ("wd_cd_to_submodule", Gtk.STOCK_REMOVE, _("Change Directory"), None,
                 _("Chanage working directory to the selected submodule's root directory"),
                 lambda _action=None: scm_wspce.chdir(self.get_selected_fsi_path())
                ),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|AC_ONLY_SUBMODULES_SELECTED|actions.AC_SELN_MADE].add_actions(
            [
                ("wd_remove_submodules", Gtk.STOCK_REMOVE, _("Remove Submodules"), None,
                 _("Remove the selected subdirectories"),
                 lambda _action=None: self.git_do_remove_files_in_index(self.get_selected_fsi_paths())
                ),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|actions.AC_SELN_UNIQUE].add_actions(
            [
                ("rename_file_in_index", wsm_icons.STOCK_RENAME, _("Rename"), None,
                 _("Rename the selected file/directory in the index (i.e. git mv)"),
                 lambda _action=None: self.git_do_rename_fsi_in_index(self.get_selected_fsi_path())
                ),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|actions.AC_SELN_UNIQUE|file_tree.AC_ONLY_FILES_SELECTED].add_actions(
            [
                ("launch_diff_tool_re_head", wsm_icons.STOCK_DIFF, _("Difftool"), None,
                 _("Launch difftool for the selected file w.r.t. HEAD"),
                 lambda _action=None: scm_gui_ifce.SCM.launch_difftool("HEAD", "--", self.get_selected_fsi_path())
                ),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|actions.AC_SELN_MADE].add_actions(
            [
                ("wd_add_files_to_index", Gtk.STOCK_ADD, _("Add"), None,
                 _("Run \"git add\" on the selected files/directories"),
                 lambda _action=None: self.git_do_add_fsis_to_index(self.get_selected_fsi_paths())
                ),
            ])
        self.action_groups[scm_actions.AC_IN_SCM_PGND|actions.AC_SELN_MADE|file_tree.AC_ONLY_FILES_SELECTED].add_actions(
            [
                ("wd_edit_selected_files", Gtk.STOCK_EDIT, _("Edit"), None,
                 _("Open the selected files for editing"),
                 lambda _action=None: xtnl_edit.edit_files_extern(self.get_selected_fsi_paths())
                ),
                # TODO: extend the "Remove" command to include directories
                ("wd_remove_files_in_index", Gtk.STOCK_REMOVE, _("Remove"), None,
                 _("Run \"git rm\" on the selected files"),
                 lambda _action=None: self.git_do_remove_files_in_index(self.get_selected_fsi_paths())
                ),
            ])

class WDFileTreeWidget(file_tree.FileTreeWidget):
    MENUBAR = "/wd_files_menubar"
    BUTTON_BAR_ACTIONS = ["show_hidden_files", "hide_clean_files"]
    TREE_VIEW = WDTreeView
    @staticmethod
    def get_menu_prefix():
        return scm_gui_ifce.SCM.name
