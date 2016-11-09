### -*- coding: utf-8 -*-
###
###  Copyright (C) 2016 Peter Williams <pwil3058@gmail.com>
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

import os

from gi.repository import Gtk

from ..gtx import actions
from ..gtx import apath
from ..gtx import dialogue

from .. import wsm_icons

from ... import CONFIG_DIR_PATH

SAVED_PGND_FILE_NAME = os.sep.join([CONFIG_DIR_PATH, "playgrounds"])

class PgndPathView(apath.AliasPathView):
    SAVED_FILE_NAME = SAVED_PGND_FILE_NAME

class PgndPathTable(apath.AliasPathTable):
    VIEW = PgndPathView

class PgndPathDialog(apath.PathSelectDialog):
    PATH_TABLE = PgndPathTable
    def __init__(self, suggestion=None, parent=None):
        apath.PathSelectDialog.__init__(self, label=_("Playground/Directory"), suggestion=suggestion, parent=parent)

class AskInitPgndDialog(dialogue.QuestionDialog, dialogue.ClientMixin):
    def __init__(self):
        buttons = (Gtk.STOCK_NO, Gtk.ResponseType.NO, Gtk.STOCK_YES, Gtk.ResponseType.YES)
        qtn =os.linesep.join([_("Directory {} has not been initialised.").format(os.getcwd()),
                               _("Do you wish to initialise it?")])
        dialogue.QuestionDialog.__init__(self, qtn=qtn, buttons=buttons)
        self.connect("response", self._response_cb)
    def _response_cb(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            from ..pm_gui import pm_gui_ifce
            req_back_end = pm_gui_ifce.choose_backend(dialog)
            if req_back_end:
                result = pm_gui_ifce.init_current_dir(req_back_end)
                dialog.report_any_problems(result)
        dialog.destroy()

class PgndOpenDialog(PgndPathDialog):
    def __init__(self, **kwargs):
        PgndPathDialog.__init__(self, **kwargs)
        self.connect("response", self._response_cb)
    def _response_cb(self, open_dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            newpg = open_dialog.get_path()
            if newpg:
                with open_dialog.showing_busy():
                    result = chdir(newpg)
                open_dialog.report_any_problems(result)
                if not result.is_ok:
                    return # Give them the option to try again
            else:
                open_dialog.inform_user(_("\"Playground/Directory\" field must contain a directory path"))
                return
            open_dialog.destroy()
            from ..pm_gui import pm_gui_ifce
            if not pm_gui_ifce.PM.in_valid_pgnd:
                AskInitPgndDialog().run()
        else:
            open_dialog.destroy()

class NewPgndDialog(dialogue.CancelOKDialog, dialogue.ClientMixin):
    def __init__(self, **kwargs):
        from . import pm_gui_ifce
        dialogue.CancelOKDialog.__init__(self, **kwargs)
        avail_backends = pm_gui_ifce.avail_backends()
        if not avail_backends:
            info_label = Gtk.Label(pm_gui_ifce.backend_requirements())
            self.get_content_area().add(info_label)
            self.show_all()
            return
        if len(avail_backends) > 1:
            self._backend = None
            be_chooser = Gtk.ComboBoxText()
            for abe in avail_backends:
                be_chooser.append_text(abe)
            be_chooser.connect("changed", self._be_chooser_change_cb)
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            hbox.pack_start(Gtk.Label(_("Choose backend:")), expand=False, fill=True, padding=0)
            hbox.pack_start(be_chooser, expand=False, fill=True, padding=0)
            self.get_content_area().pack_start(hbox, expand=False, fill=True, padding=0)
        else:
            self._backend = avail_backends[0]
        self._path_reader = dialogue.EnterDirPathWidget(prompt=_("New Playground Directory Path:"))
        self.get_content_area().pack_start(self._path_reader, expand=False, fill=True, padding=0)
        self.connect("response", self._response_cb)
        self.set_default_response(Gtk.ResponseType.OK)
        self.show_all()
    def _be_chooser_change_cb(self, combo):
        self._backend = combo.get_active_text()
    def _response_cb(self, open_dialog, response_id):
        from . import pm_gui_ifce
        if response_id == Gtk.ResponseType.OK:
            if not self._backend:
                self.inform_user(_("Required backend must be specified."))
                return
            if not self._path_reader.path:
                self.inform_user(_("Directory path for new playground must be specified."))
                return
            with self.showing_busy():
                result = pm_gui_ifce.create_new_playground(self._path_reader.path, self._backend)
            self.report_any_problems(result)
            if result.is_ok:
                with self.showing_busy():
                    result = chdir(self._path_reader.path)
                self.report_any_problems(result)
        open_dialog.destroy()

def generate_local_playground_menu(label=_("Playgrounds")):
    return PgndPathView.generate_alias_path_menu(label, lambda newtgnd: chdir(newtgnd))

def add_playground_path(path):
    return PgndPathView.append_saved_path(path)

def chdir(newdir):
    from ..bab import CmdResult
    events = 0
    try:
        os.chdir(newdir)
        retval = CmdResult.ok()
    except OSError as err:
        import errno
        ecode = errno.errorcode[err.errno]
        emsg = err.strerror
        retval = CmdResult.error(stderr="{0}: \"{1}\" : {2}".format(ecode, newdir, emsg))
        newdir = os.getcwd()
    # NB regardless of success of os.chdir() we need to check the interfaces
    from ..bab import enotify
    from ..bab import options
    from ..gtx.console import LOG
    from ..pm_gui import pm_gui_ifce
    pm_gui_ifce.reset_pm_ifce()
    if pm_gui_ifce.PM.in_valid_pgnd:
        # move down to the root dir
        newdir = pm_gui_ifce.PM.get_playground_root()
        os.chdir(newdir)
        from ..gtx import recollect
        PgndPathView.append_saved_path(newdir)
        recollect.set("workspace", "last_used", newdir)
    from ..scm_gui import scm_gui_ifce
    scm_gui_ifce.reset_scm_ifce()
    options.reload_pgnd_options()
    CURDIR = os.getcwd()
    LOG.start_cmd(_("New Working Directory: {0}\n").format(CURDIR))
    LOG.append_stdout(retval.stdout)
    LOG.append_stderr(retval.stderr)
    if pm_gui_ifce.PM.in_valid_pgnd:
        LOG.append_stdout('In valid repository\n')
    else:
        LOG.append_stderr('NOT in valid repository\n')
    LOG.end_cmd()
    enotify.notify_events(enotify.E_CHANGE_WD, new_wd=CURDIR)
    return retval

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("pm_change_wd", Gtk.STOCK_OPEN, _("Open"), "",
         _("Change current working directory"),
         lambda _action: PgndOpenDialog().run()
        ),
        ("pm_create_new_pgnd", wsm_icons.STOCK_NEW_PLAYGROUND, _("_New"), "",
         _("Create a new intitialized playground"),
         lambda _action=None: NewPgndDialog().run()
        ),
    ])
