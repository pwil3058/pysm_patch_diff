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
            from ..pm_gui import ifce as pm_gui_ifce
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
            from ..pm_gui import ifce as pm_gui_ifce
            if not pm_gui_ifce.PM.in_valid_pgnd:
                AskInitPgndDialog().run()
        else:
            open_dialog.destroy()

def generate_local_playground_menu(label=_("Playgrounds")):
    return PgndPathView.generate_alias_path_menu(label, lambda newtgnd: pm_wspce.chdir(newtgnd))

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
    from ..pm_gui import ifce as pm_ifce
    pm_ifce.get_ifce()
    if pm_ifce.PM.in_valid_pgnd:
        # move down to the root dir
        newdir = pm_ifce.PM.get_playground_root()
        os.chdir(newdir)
        from ..gtx import recollect
        PgndPathView.append_saved_path(newdir)
        recollect.set("workspace", "last_used", newdir)
    from ..scm_gui import ifce as scm_ifce
    scm_ifce.get_ifce()
    options.reload_pgnd_options()
    CURDIR = os.getcwd()
    LOG.start_cmd(_("New Working Directory: {0}\n").format(CURDIR))
    LOG.append_stdout(retval.stdout)
    LOG.append_stderr(retval.stderr)
    if pm_ifce.PM.in_valid_pgnd:
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
    ])
