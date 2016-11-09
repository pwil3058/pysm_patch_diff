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

"""<DOCSTRING GOES HERE>"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

import collections
import os

from gi.repository import GObject
from gi.repository import Gtk

from ..bab import utils

from ..gtx import actions
from ..gtx import dialogue
from ..gtx import icons
from ..gtx import recollect
from ..gtx import table
from ..gtx import text_edit
from ..gtx import tlview

from . import pm_gui_ifce
from . import pm_actions
from ..scm_gui import scm_actions

from .. import wsm_icons

from ... import APP_NAME

class PMDoOpnPatchesMixin:
    def pm_do_duplicate_patch(self, patch_name):
        DuplicatePatchDialog(patch_name, parent=self.get_toplevel()).run()

    def pm_do_export_named_patch(self, patch_name):
        suggestion = os.path.basename(utils.convert_patchname_to_filename(patch_name))
        if not os.path.dirname(suggestion):
            suggestion = os.path.join(recollect.get("export", "last_directory"), suggestion)
        PROMPT = _("Export as ...")
        export_filename = self.ask_file_path(PROMPT, suggestion=suggestion, existing=False)
        if export_filename is None:
            return
        force = False
        overwrite = False
        refresh_tried = False
        while True:
            with self.showing_busy():
                result = pm_gui_ifce.PM.do_export_patch_as(patch_name, export_filename, force=force, overwrite=overwrite)
            if refresh_tried:
                result = result - result.Suggest.REFRESH
            if result.suggests(result.Suggest.FORCE_OR_REFRESH):
                resp = self.ask_force_refresh_absorb_or_cancel(result)
                if resp == Gtk.ResponseType.CANCEL:
                    return
                elif resp == dialogue.Response.FORCE:
                    force = True
                elif resp == dialogue.Response.REFRESH:
                    refresh_tried = True
                    with self.showing_busy():
                        result = pm_gui_ifce.PM.do_refresh_patch()
                    self.report_any_problems(result)
                continue
            elif result.suggests_rename:
                resp = self.ask_rename_overwrite_or_cancel(result)
                if resp == Gtk.ResponseType.CANCEL:
                    return
                elif resp == dialogue.Response.OVERWRITE:
                    overwrite = True
                elif resp == dialogue.Response.RENAME:
                    export_filename = self.ask_file_path(PROMPT, suggestion=export_filename, existing=False)
                    if export_filename is None:
                        return
                continue
            self.report_any_problems(result)
            recollect.set("export", "last_directory", os.path.dirname(export_filename))
            break

    def pm_do_fold_patch(self, patch_name):
        refresh_tried = False
        force = False
        absorb = False
        while True:
            with self.showing_busy():
                result = pm_gui_ifce.PM.do_fold_named_patch(patch_name, absorb=absorb, force=force)
            if refresh_tried:
                result = result - result.Suggest.REFRESH
            if not (absorb or force) and result.suggests(result.Suggest.FORCE_ABSORB_OR_REFRESH):
                resp = self.ask_force_refresh_absorb_or_cancel(result)
                if resp == Gtk.ResponseType.CANCEL:
                    break
                elif resp == dialogue.Response.FORCE:
                    force = True
                elif resp == dialogue.Response.ABSORB:
                    absorb = True
                elif resp == dialogue.Response.REFRESH:
                    refresh_tried = True
                    with self.showing_busy():
                        patch_file_list = pm_gui_ifce.PM.get_filepaths_in_named_patch(patch_name)
                        top_patch_file_list = pm_gui_ifce.PM.get_filepaths_in_top_patch(patch_file_list)
                        file_paths = [file_path for file_path in patch_file_list if file_path not in top_patch_file_list]
                        result = pm_gui_ifce.PM.do_refresh_overlapped_files(file_paths)
                    self.report_any_problems(result)
                continue
            self.report_any_problems(result)
            break

    def pm_do_fold_to_patch(self, patch_name):
        while True:
            next_patch = pm_gui_ifce.PM.get_next_patch()
            if not next_patch:
                return
            with self.showing_busy():
                result = pm_gui_ifce.PM.do_fold_named_patch(next_patch)
            if not result.is_ok:
                self.report_any_problems(result)
                return
            if patch_name == next_patch:
                return

    def pm_do_pop_to(self, patch_name):
        while pm_gui_ifce.PM.is_poppable and not pm_gui_ifce.PM.is_top_patch(patch_name):
            if not pm_do_pop(self):
                break

    def pm_do_push_to(self, patch_name):
        while pm_gui_ifce.PM.is_pushable and not pm_gui_ifce.PM.is_top_patch(patch_name):
            if not pm_do_push(self):
                break

    def pm_do_refresh_named_patch(self, patch_name):
        with self.showing_busy():
            result = pm_gui_ifce.PM.do_refresh_patch(patch_name)
        self.report_any_problems(result)

    def pm_do_remove_patch(self, patch_name):
        if self.ask_ok_cancel(_("Confirm remove \"{0}\" patch?").format(patch_name)):
            with self.showing_busy():
                result = pm_gui_ifce.PM.do_remove_patch(patch_name)
            self.report_any_problems(result)

    def pm_do_rename_patch(self, patch_name):
        dialog = dialogue.ReadTextDialog(_("Rename Patch: {0}").format(patch_name), _("New Name:"), patch_name)
        while dialog.run() == Gtk.ResponseType.OK:
            new_name = dialog.entry.get_text()
            if patch_name == new_name:
                break
            with self.showing_busy():
                result = pm_gui_ifce.PM.do_rename_patch(patch_name, new_name)
            self.report_any_problems(result)
            if not result.suggests_rename:
                break
        dialog.destroy()

    def pm_do_set_guards_on_patch(self, patch_name):
        cguards = " ".join(pm_gui_ifce.PM.get_patch_guards(patch_name))
        dialog = dialogue.ReadTextDialog(_("Set Guards: {0}").format(patch_name), _("Guards:"), cguards)
        while True:
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                guards = dialog.entry.get_text()
                with self.showing_busy():
                    result = pm_gui_ifce.PM.do_set_patch_guards(patch_name, guards)
                self.report_any_problems(result)
                if result.suggests_edit:
                    continue
                dialog.destroy()
            else:
                dialog.destroy()
            break

def pm_do_pop(helper):
    refresh_tried = False
    while True:
        with helper.showing_busy():
            result = pm_gui_ifce.PM.do_pop_top_patch()
        if not refresh_tried and result.suggests_refresh:
            resp = helper.ask_force_refresh_absorb_or_cancel(result)
            if resp == Gtk.ResponseType.CANCEL:
                return False
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                with helper.showing_busy():
                    result = pm_gui_ifce.PM.do_refresh_patch()
                helper.report_any_problems(result)
            continue
        helper.report_any_problems(result)
        break
    return result.is_ok

def pm_do_pop_all(helper):
    while pm_gui_ifce.PM.is_poppable:
        if not pm_do_pop(helper):
            break

def pm_do_push(helper):
    force = False
    absorb = True
    refresh_tried = False
    while True:
        with helper.showing_busy():
            result = pm_gui_ifce.PM.do_push_next_patch(absorb=absorb, force=force)
        if refresh_tried:
            result = result - result.Suggest.REFRESH
        if not (absorb or force) and result.suggests(result.Suggest.FORCE_ABSORB_OR_REFRESH):
            resp = helper.ask_force_refresh_absorb_or_cancel(result)
            if resp == Gtk.ResponseType.CANCEL:
                return False
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.ABSORB:
                absorb = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                with helper.showing_busy():
                    file_paths = pm_gui_ifce.PM.get_filepaths_in_next_patch()
                    result = pm_gui_ifce.PM.do_refresh_overlapped_files(file_paths)
                helper.report_any_problems(result)
            continue
        helper.report_any_problems(result)
        break
    return result.is_ok

def pm_do_push_all(helper):
    while pm_gui_ifce.PM.is_pushable:
        if not pm_do_push(helper):
            break

def pm_do_initialize_curdir(helper):
    req_backend = pm_gui_ifce.choose_backend(dialogue.main_window)
    if not req_backend:
        return
    with helper.showing_busy():
        result = pm_gui_ifce.init_current_dir(req_backend)
    helper.report_any_problems(result)

def pm_do_refresh_top_patch(helper):
    with helper.showing_busy():
        result = pm_gui_ifce.PM.do_refresh_patch()
    helper.report_any_problems(result)

def pm_do_restore_patch(helper):
    dlg = RestorePatchDialog(parent=helper)
    while dlg.run() == Gtk.ResponseType.OK:
        with dlg.showing_busy():
            result = pm_gui_ifce.PM.do_restore_patch(dlg.get_restore_patch_name(), dlg.get_as_name())
        helper.report_any_problems(result)
        if not result.suggests_rename:
            break
    dlg.destroy()

def pm_do_select_guards(helper):
    cselected_guards = " ".join(pm_gui_ifce.PM.get_selected_guards())
    dialog = dialogue.ReadTextDialog(_("Select Guards: {0}").format(os.getcwd()), _("Guards:"), cselected_guards)
    while True:
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_guards = dialog.entry.get_text()
            with helper.showing_busy():
                result = pm_gui_ifce.PM.do_select_guards(selected_guards)
            helper.report_any_problems(result)
            if result.suggests_edit:
                continue
            dialog.destroy()
        else:
            dialog.destroy()
        break

def pm_do_scm_absorb_applied_patches(helper):
    with helper.showing_busy():
        result = pm_gui_ifce.PM.do_scm_absorb_applied_patches()
    helper.report_any_problems(result)
    return result.is_ok

class NewSeriesDescrDialog(dialogue.Dialog):
    class Widget(text_edit.DbMessageWidget):
        UI_DESCR = \
        """
            <ui>
              <menubar name="menubar">
                <menu name="ndd_menu" action="load_menu">
                  <separator/>
                  <menuitem action="text_edit_insert_from"/>
                </menu>
              </menubar>
              <toolbar name="toolbar">
                <toolitem action="text_edit_ack"/>
                <toolitem action="text_edit_sign_off"/>
                <toolitem action="text_edit_author"/>
              </toolbar>
            </ui>
        """
        get_user_name_and_email = lambda _self: pm_gui_ifce.get_author_name_and_email()
        def __init__(self):
            text_edit.DbMessageWidget.__init__(self)
        def populate_action_groups(self):
            self.action_groups[0].add_actions(
                [
                    ("load_menu", None, _("_File")),
                ])
    def __init__(self, parent=None):
        flags = Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        title = _("Patch Series Description: {0} -- {1}").format(utils.path_rel_home(os.getcwd()), APP_NAME)
        dialogue.Dialog.__init__(self, title, parent, flags,
                                 (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                  Gtk.STOCK_OK, Gtk.ResponseType.OK))
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.edit_descr_widget = self.Widget()
        hbox = Gtk.HBox()
        menubar = self.edit_descr_widget.ui_manager.get_widget("/menubar")
        hbox.pack_start(menubar, expand=False, fill=True, padding=0)
        toolbar = self.edit_descr_widget.ui_manager.get_widget("/toolbar")
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)
        toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
        hbox.pack_end(toolbar, expand=False, fill=False, padding=0)
        hbox.show_all()
        vbox = self.get_content_area()
        vbox.pack_start(hbox, expand=False, fill=True, padding=0)
        vbox.pack_start(self.edit_descr_widget, expand=True, fill=True, padding=0)
        self.set_focus_child(self.edit_descr_widget)
        self.edit_descr_widget.show_all()
    def get_descr(self):
        return self.edit_descr_widget.get_contents()

class DuplicatePatchDialog(NewSeriesDescrDialog, dialogue.ClientMixin):
    def __init__(self, patch_name, parent=None):
        self.patch_name = patch_name
        NewSeriesDescrDialog.__init__(self, parent=parent)
        self.set_title(_("Duplicate Patch: {0}: {1} -- {2}").format(patch_name, utils.path_rel_home(os.getcwd()), APP_NAME))
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label(_("Duplicate Patch Name:")), expand=False, fill=False, padding=0)
        self.new_name_entry = Gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.new_name_entry.set_text(patch_name + ".duplicate")
        hbox.pack_start(self.new_name_entry, expand=True, fill=True, padding=0)
        olddescr = pm_gui_ifce.PM.get_patch_description(patch_name)
        self.edit_descr_widget.set_contents(olddescr)
        hbox.show_all()
        self.get_content_area().pack_start(hbox, expand=True, fill=True, padding=0)
        self.get_content_area().reorder_child(hbox, 0)
        self.connect("response", self.response_cb)
    def get_new_patch_name(self):
        return self.new_name_entry.get_text()
    @staticmethod
    def response_cb(dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            refresh_tried = False
            while True:
                as_patch_name = dialog.get_new_patch_name()
                newdescription = dialog.get_descr()
                with dialog.showing_busy():
                    result = pm_gui_ifce.PM.do_duplicate_patch(dialog.patch_name, as_patch_name, newdescription)
                if not refresh_tried and result.suggests_refresh:
                    resp = dialog.ask_force_refresh_absorb_or_cancel(result)
                    if resp == Gtk.ResponseType.CANCEL:
                        break
                    elif resp == dialogue.Response.REFRESH:
                        refresh_tried = True
                        with dialog.showing_busy():
                            result = pm_gui_ifce.PM.do_refresh_patch()
                        dialog.report_any_problems(result)
                    continue # try again after the refresh
                dialog.report_any_problems(result)
                if result.suggests_rename:
                    return # give the user another chance
                break
        dialog.destroy()

class NewPatchDialog(NewSeriesDescrDialog, dialogue.ClientMixin):
    def __init__(self, parent=None):
        NewSeriesDescrDialog.__init__(self, parent=parent)
        self.set_title(_("New Patch: {0} -- {1}").format(utils.path_rel_home(os.getcwd()), APP_NAME))
        self.hbox = Gtk.HBox()
        self.hbox.pack_start(Gtk.Label(_("New Patch Name:")), expand=False, fill=False, padding=0)
        self.new_name_entry = Gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.hbox.pack_start(self.new_name_entry, expand=True, fill=True, padding=0)
        self.hbox.show_all()
        vbox = self.get_content_area()
        vbox.pack_start(self.hbox, expand=True, fill=True, padding=0)
        vbox.reorder_child(self.hbox, 0)
        self.connect("response", self._response_cb)
        self.show_all()
    def _response_cb(self, dlg, response):
        if response == Gtk.ResponseType.OK:
            with dlg.showing_busy():
                result = pm_gui_ifce.PM.do_create_new_patch(dlg.new_name_entry.get_text(), dlg.get_descr())
            dlg.report_any_problems(result)
            if not result.is_ok:
                return
        dlg.destroy()

class SeriesDescrEditDialog(dialogue.Dialog):
    class Widget(text_edit.DbMessageWidget):
        UI_DESCR = \
        """
            <ui>
              <menubar name="menubar">
                <menu name="ndd_menu" action="load_menu">
                  <separator/>
                  <menuitem action="text_edit_insert_from"/>
                </menu>
              </menubar>
              <toolbar name="toolbar">
                <toolitem action="text_edit_ack"/>
                <toolitem action="text_edit_sign_off"/>
                <toolitem action="text_edit_author"/>
              </toolbar>
            </ui>
        """
        get_user_name_and_email = lambda _self: pm_gui_ifce.get_author_name_and_email()
        def __init__(self):
            text_edit.DbMessageWidget.__init__(self)
            self.view.set_editable(True)
            self.load_text_fm_db()
        def populate_action_groups(self):
            self.action_groups[0].add_actions(
                [
                    ("load_menu", None, _("_File")),
                ])
        def get_text_fm_db(self):
            return pm_gui_ifce.PM.get_series_description()
        def set_text_in_db(self, text):
            return pm_gui_ifce.PM.do_set_series_description(text)
    def __init__(self, parent=None):
        flags = ~Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        title = _("Series Description: {0} -- {1}").format(utils.path_rel_home(os.getcwd()), APP_NAME)
        dialogue.Dialog.__init__(self, title, parent, flags, None)
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.edit_descr_widget = self.Widget()
        hbox = Gtk.HBox()
        menubar = self.edit_descr_widget.ui_manager.get_widget("/menubar")
        hbox.pack_start(menubar, expand=False, fill=True, padding=0)
        toolbar = self.edit_descr_widget.ui_manager.get_widget("/toolbar")
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)
        toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
        hbox.pack_end(toolbar, expand=False, fill=False, padding=0)
        hbox.show_all()
        vbox = self.get_content_area()
        vbox.pack_start(hbox, expand=False, fill=True, padding=0)
        vbox.pack_start(self.edit_descr_widget, expand=True, fill=True, padding=0)
        self.set_focus_child(self.edit_descr_widget)
        action_area = self.get_action_area()
        action_area.pack_start(self.edit_descr_widget.reload_button, expand=True, fill=True, padding=0)
        action_area.pack_start(self.edit_descr_widget.save_button, expand=True, fill=True, padding=0)
        action_area.show_all()
        self.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.connect("response", self._handle_response_cb)
        self.set_focus_child(self.edit_descr_widget.view)
        self.edit_descr_widget.show_all()
        self.show_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            if self.edit_descr_widget.view.get_buffer().get_modified():
                qtn = "\n".join([_("Unsaved changes to summary will be lost."), _("Close anyway?")])
                if dialogue.main_window.ask_yes_no(qtn):
                    self.destroy()
            else:
                self.destroy()

class PatchDescrEditDialog(dialogue.Dialog):
    class Widget(text_edit.DbMessageWidget):
        UI_DESCR = """
            <ui>
              <menubar name="menubar">
                <menu name="ndd_menu" action="load_menu">
                  <separator/>
                  <menuitem action="text_edit_insert_from"/>
                </menu>
              </menubar>
              <toolbar name="toolbar">
                <toolitem action="text_edit_ack"/>
                <toolitem action="text_edit_sign_off"/>
                <toolitem action="text_edit_author"/>
              </toolbar>
            </ui>
        """
        get_user_name_and_email = lambda _self: pm_gui_ifce.get_author_name_and_email()
        def __init__(self, patch):
            text_edit.DbMessageWidget.__init__(self)
            self.view.set_editable(True)
            self._patch = patch
            self.load_text_fm_db()
        def populate_action_groups(self):
            self.action_groups[0].add_actions(
                [
                    ("load_menu", None, _("_File")),
                ])
        def get_text_fm_db(self):
            return pm_gui_ifce.PM.get_patch_description(self._patch)
        def set_text_in_db(self, text):
            return pm_gui_ifce.PM.do_set_patch_description(self._patch, text)
    def __init__(self, patch, parent=None):
        flags = ~Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        title = _("Patch: {0} : {1} -- {2}").format(patch, utils.path_rel_home(os.getcwd()), APP_NAME)
        dialogue.Dialog.__init__(self, title, parent, flags, None)
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.edit_descr_widget = self.Widget(patch)
        hbox = Gtk.HBox()
        menubar = self.edit_descr_widget.ui_manager.get_widget("/menubar")
        hbox.pack_start(menubar, expand=False, fill=True, padding=0)
        toolbar = self.edit_descr_widget.ui_manager.get_widget("/toolbar")
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)
        toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
        hbox.pack_end(toolbar, expand=False, fill=False, padding=0)
        hbox.show_all()
        vbox = self.get_content_area()
        vbox.pack_start(hbox, expand=False, fill=True, padding=0)
        vbox.pack_start(self.edit_descr_widget, expand=True, fill=True, padding=0)
        self.set_focus_child(self.edit_descr_widget)
        action_area = self.get_action_area()
        action_area.pack_start(self.edit_descr_widget.reload_button, expand=True, fill=True, padding=0)
        action_area.pack_start(self.edit_descr_widget.save_button, expand=True, fill=True, padding=0)
        action_area.show_all()
        self.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.connect("response", self._handle_response_cb)
        self.set_focus_child(self.edit_descr_widget.view)
        self.edit_descr_widget.show_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            if self.edit_descr_widget.view.get_buffer().get_modified():
                qtn = "\n".join([_("Unsaved changes to summary will be lost."), _("Close anyway?")])
                if dialogue.main_window.ask_yes_no(qtn):
                    self.destroy()
            else:
                self.destroy()

class RestorePatchDialog(dialogue.Dialog):
    class Table(table.EditedEntriesTable):
        class VIEW(table.EditedEntriesTable.VIEW):
            class MODEL(table.EditedEntriesTable.VIEW.MODEL):
                ROW = collections.namedtuple("ROW", ["PatchName"])
                TYPES = ROW(PatchName=GObject.TYPE_STRING)
            SPECIFICATION = tlview.ViewSpec(
                properties={
                    "enable-grid-lines" : False,
                    "reorderable" : False,
                    "rules_hint" : False,
                    "headers-visible" : False,
                },
                selection_mode=Gtk.SelectionMode.SINGLE,
                columns=[
                    tlview.ColumnSpec(
                        title=_("Patch Name"),
                        properties={"expand": False, "resizable" : True},
                        cells=[
                            tlview.CellSpec(
                                cell_renderer_spec=tlview.CellRendererSpec(
                                    cell_renderer=Gtk.CellRendererText,
                                    expand=False,
                                    start=True,
                                    properties={"editable" : False},
                                ),
                                cell_data_function_spec=None,
                                attributes = {"text" : MODEL.col_index("PatchName")}
                            ),
                        ],
                    ),
                ]
            )
        def __init__(self):
            table.EditedEntriesTable.__init__(self, size_req=(480, 160))
            self.connect("key_press_event", self._key_press_cb)
            self.connect("button_press_event", self._handle_button_press_cb)
            self.view.set_contents()
        def get_selected_patch(self):
            data = self.view.get_selected_data_by_label(["PatchName"])
            if not data:
                return False
            return data[0]
        def _handle_button_press_cb(self, widget, event):
            if event.type == Gdk.EventType.BUTTON_PRESS:
                if event.button == 2:
                    self.seln.unselect_all()
                    return True
            return False
        def _key_press_cb(self, widget, event):
            if event.keyval == Gdk.keyval_from_name("Escape"):
                self.seln.unselect_all()
                return True
            return False
        @staticmethod
        def _fetch_contents():
            return [[name] for name in pm_gui_ifce.PM.get_kept_patch_names()]
    def __init__(self, parent):
        dialogue.Dialog.__init__(self, title=_("{0}: Restore Patch").format(APP_NAME), parent=parent,
                                 flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                 buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
                                )
        self.kept_patch_table = self.Table()
        vbox = self.get_content_area()
        vbox.pack_start(self.kept_patch_table, expand=True, fill=True, padding=0)
        #
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label(_("Restore Patch:")), expand=False, fill=True, padding=0)
        self.rpatch_name = Gtk.Entry()
        self.rpatch_name.set_editable(False)
        self.rpatch_name.set_width_chars(32)
        hbox.pack_start(self.rpatch_name, expand=True, fill=True, padding=0)
        vbox.pack_start(hbox, expand=False, fill=False, padding=0)
        #
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label(_("As Patch:")), expand=False, fill=True, padding=0)
        self.as_name = gutils.new_mutable_combox_text_with_entry()
        self.as_name.get_child().set_width_chars(32)
        self.as_name.get_child().connect("activate", self._as_name_cb)
        hbox.pack_start(self.as_name, expand=True, fill=True, padding=0)
        vbox.pack_start(hbox, expand=False, fill=False, padding=0)
        #
        self.show_all()
        self.kept_patch_table.seln.unselect_all()
        self.kept_patch_table.seln.connect("changed", self._selection_cb)
    def _selection_cb(self, _selection=None):
        rpatch = self.kept_patch_table.get_selected_patch()
        if rpatch:
            self.rpatch_name.set_text(rpatch[0])
    def _as_name_cb(self, entry=None):
        self.response(Gtk.ResponseType.OK)
    def get_restore_patch_name(self):
        return self.rpatch_name.get_text()
    def get_as_name(self):
        return self.as_name.get_text()

actions.CLASS_INDEP_AGS[pm_actions.AC_NOT_IN_PM_PGND].add_actions(
    [
        ("pm_init_cwd", wsm_icons.STOCK_INIT, _("_Initialize"), "",
         _("Create a patch series in the current directory"),
         lambda _action=None: pm_do_initialize_curdir(dialogue.main_window)
        ),
    ]
)

actions.CLASS_INDEP_AGS[pm_actions.AC_POP_POSSIBLE | pm_actions.AC_IN_PM_PGND].add_actions(
    [
        ("pm_pop", wsm_icons.STOCK_POP_PATCH, _("Pop"), None,
         _("Pop the top applied patch"),
         lambda _action=None: pm_do_pop(dialogue.main_window)
        ),
        ("pm_pop_all", wsm_icons.STOCK_POP_PATCH, _("Pop All"), None,
         _("Pop all applied patches"),
         lambda _action=None: pm_do_pop_all(dialogue.main_window)
        ),
        ("pm_refresh_top_patch", wsm_icons.STOCK_REFRESH_PATCH, _("Refresh"), None,
         _("Refresh the top patch"),
         lambda _action=None: pm_do_refresh_top_patch(dialogue.main_window)
        ),
    ]
)

actions.CLASS_INDEP_AGS[pm_actions.AC_PUSH_POSSIBLE | pm_actions.AC_IN_PM_PGND].add_actions(
    [
        ("pm_push", wsm_icons.STOCK_PUSH_PATCH, _("Push"), None,
         _("Apply the next unapplied patch"),
         lambda _action=None: pm_do_push(dialogue.main_window)
        ),
        ("pm_push_all", wsm_icons.STOCK_PUSH_PATCH, _("Push All"), None,
         _("Apply all unguarded unapplied patches."),
         lambda _action=None: pm_do_push_all(dialogue.main_window)
        ),
    ]
)

actions.CLASS_INDEP_AGS[pm_actions.AC_IN_PM_PGND].add_actions(
    [
        ("pm_new_patch", wsm_icons.STOCK_NEW_PATCH, _("New Patch"), None,
         _("Create a new patch"),
         lambda _action=None: NewPatchDialog().run()
        ),
        ("pm_restore_patch", wsm_icons.STOCK_IMPORT_PATCH, _("Restore Patch"), None,
         _("Restore a previously removed patch behind the top applied patch"),
         lambda _action=None: pm_do_restore_patch(dialogue.main_window)
        ),
        ("pm_select_guards", wsm_icons.STOCK_PATCH_GUARD_SELECT, _("Select"), None,
         _("Select which guards are in force"),
         lambda _action=None: pm_do_select_guards(dialogue.main_window)
        ),
        ("pm_edit_series_descr", Gtk.STOCK_EDIT, _("Description"), None,
         _("Edit the series' description"),
         lambda _action=None: SeriesDescrEditDialog(parent=dialogue.main_window).show()
        ),
    ]
)

actions.CLASS_INDEP_AGS[pm_actions.AC_ALL_APPLIED_REFRESHED | scm_actions.AC_IN_SCM_PGND | pm_actions.AC_IN_PM_PGND].add_actions(
    [
        ("pm_scm_absorb_applied_patches", wsm_icons.STOCK_FINISH_PATCH, _("Absorb All"), None,
         _("Absorb all applied patches into underlying SCM repository"),
         lambda _action=None: pm_do_scm_absorb_applied_patches(dialogue.main_window)
        ),
    ]
)
