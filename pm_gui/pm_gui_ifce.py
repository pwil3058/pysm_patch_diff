### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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

"""
Provide an interface for the GUI to access the PM controlling the patches
"""

import os

from . import pm_wspce

_BACKEND = {}
_MISSING_BACKEND = {}

def add_backend(newifce):
    if newifce.is_available:
        _BACKEND[newifce.name] = newifce
    else:
        _MISSING_BACKEND[newifce.name] = newifce

def backend_requirements():
    msg = _("No back ends are available. At least one of:") + os.linesep
    for key in list(_MISSING_BACKEND.keys()):
        msg += "\t" + _MISSING_BACKEND[key].requires() + os.linesep
    msg += _("must be installed/available for \"gquilt\" to do.anything useful.")
    return msg

def report_backend_requirements(parent=None):
    from ..gtx import dialogue
    dialogue.main_window.inform_user(backend_requirements(), parent=parent)

def avail_backends():
    return list(_BACKEND.keys())

def choose_backend(helper):
    available_backends = avail_backends()
    if len(available_backends) == 0:
        helper.inform_user(backend_requirements())
        return None
    elif len(available_backends) == 1:
        return available_backends[0]
    return helper.choose_from_list(alist=available_backends, prompt=_("Choose PM back end:"))

def playground_type(dirpath=None):
    # TODO: cope with nested playgrounds of different type and go for closest
    # TODO: give preference to quilt if both found to allow quilt to be used on hg?
    for bname in list(_BACKEND.keys()):
        if _BACKEND[bname].dir_is_in_valid_pgnd(dirpath):
            return bname
    return None

def create_new_playground(pgdir, backend=None):
    if backend:
        return _BACKEND[backend].create_new_playground(pgdir)
    else:
        return PM.create_new_playground(pgdir)

class _NULL_BACKEND:
    name = "null"
    cmd_label = "null"
    in_valid_pgnd = False
    pgnd_is_mutable = False
    has_add_files = False
    has_finish_patch = False
    has_guards = False
    has_refresh_non_top = False
    is_extdiff_for_full_patch_ok = False
    is_poppable = False
    is_pushable = False
    all_applied_patches_refreshed = False
    # no caching so no state ergo all methods will be static/class methods
    # "do" methods should never be called for the null interface
    # so we won't provide them
    # "get" methods may be called so return the approriate "nothing"
    @staticmethod
    def get_applied_patches():
        return []
    @staticmethod
    def get_applied_patch_count():
        return 0
    @staticmethod
    def get_author_name_and_email():
        return None
    @staticmethod
    def get_base_patch():
        return None
    @staticmethod
    def get_combined_patch_diff_text(file_path_list=None):
        return ""
    @staticmethod
    def get_combined_patch_file_db():
        from ..gtx import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_default_new_patch_save_file():
        return None
    @staticmethod
    def get_description_is_finish_ready(patch_name):
        return False
    @staticmethod
    def get_extension_enabled(extension):
        return False
    @staticmethod
    def get_named_patch_diff_text(patch_name, file_path_list=None):
        return ""
    @staticmethod
    def get_next_patch():
        return None
    @staticmethod
    def get_patch_description(patch_name):
        return ""
    @staticmethod
    def get_patch_file_db(patch_name):
        from ..gtx import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_patch_file_path(patch_name):
        return None
    @staticmethod
    def get_patch_files(patch_name, with_status=False):
        return []
    @staticmethod
    def get_patch_guards(patch_name):
        return []
    @staticmethod
    def get_patch_list_data():
        from ..pm_gui import NullPatchListData
        return NullPatchListData()
    @staticmethod
    def get_patch_text(patch_name):
        return ""
    @staticmethod
    def get_playground_root(dir_name=None):
        return None
    @staticmethod
    def get_selected_guards():
        return []
    @staticmethod
    def get_top_patch():
        return None
    @staticmethod
    def get_top_patch_diff_text(file_path_list=None):
        return ""
    @staticmethod
    def get_top_patch_file_db():
        from ..gtx import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_ws_update_clean_up_ready(applied_count=None):
        return False
    @staticmethod
    def get_ws_update_merge_ready(unapplied_count=None):
        return False
    @staticmethod
    def get_ws_update_pull_ready(applied_count=None):
        return False
    @staticmethod
    def get_ws_update_qsave_ready(unapplied_count, applied_count):
        return False
    @staticmethod
    def get_ws_update_ready(applied_count=None):
        return False
    @staticmethod
    def get_ws_update_to_ready(applied_count=None):
        return False
    @staticmethod
    def is_patch_applied(patch_name):
        return False
    @staticmethod
    def launch_extdiff_for_patch(patch_name=None, file_path_list=None):
        return
    @staticmethod
    def launch_extdiff_for_top_patch(file_path_list=None):
        return

PM = _NULL_BACKEND

def reset_pm_ifce(dir_path=None):
    global PM
    pgt = playground_type(dir_path)
    PM = _NULL_BACKEND if pgt is None else _BACKEND[pgt]
    return PM


def init():
    import os
    from ..bab import options
    from ..bab import enotify
    orig_dir = os.getcwd()
    options.load_global_options()
    reset_pm_ifce()
    if PM.in_valid_pgnd:
        root = PM.get_playground_root()
        os.chdir(root)
        from ..pm_gui import pm_wspce
        from ..gtx import recollect
        pm_wspce.add_playground_path(root)
        recollect.set("workspace", "last_used", root)
    from ..scm_gui import scm_gui_ifce
    scm_gui_ifce.reset_scm_ifce()
    curr_dir = os.getcwd()
    options.reload_pgnd_options()
    from ..gtx.console import LOG
    LOG.start_cmd("Working Directory: {0}\n".format(curr_dir))
    if PM.in_valid_pgnd:
        LOG.append_stdout("In valid repository\n")
    else:
        LOG.append_stderr("NOT in valid repository\n")
    LOG.end_cmd()
    # NB: need to send either enotify.E_CHANGE_WD or E_NEW_PM|E_NEW_SCM to ensure action sates get set
    if not os.path.samefile(orig_dir, curr_dir):
        enotify.notify_events(enotify.E_CHANGE_WD, new_wd=curr_dir)
    else:
        from ..pm import E_NEW_PM
        from ..scm import E_NEW_SCM
        enotify.notify_events(E_NEW_PM|E_NEW_SCM)
    from ..gtx import auto_update
    auto_update.set_initialize_event_flags(check_interfaces)

def init_current_dir(backend):
    import os
    from ..bab import enotify
    result = create_new_playground(os.getcwd(), backend)
    events = 0
    curr_pm = PM
    reset_pm_ifce()
    if curr_pm != PM:
        from ..pm import E_NEW_PM
        events |= E_NEW_PM
    from ..scm_gui import scm_gui_ifce
    curr_scm = scm_gui_ifce.SCM
    scm_gui_ifce.reset_scm_ifce()
    if curr_scm != scm_gui_ifce.SCM:
        from ..scm import E_NEW_SCM
        events |= E_NEW_SCM
    if PM.in_valid_pgnd:
        from ..pm_gui import pm_wspce
        from ..gtx import recollect
        curr_dir = os.getcwd()
        pm_wspce.add_playground_path(curr_dir)
        recollect.set("workspace", "last_used", curr_dir)
    if events:
        enotify.notify_events(events)
    return result

def check_interfaces(args):
    from ..bab import enotify
    events = 0
    curr_pm = PM
    reset_pm_ifce()
    if curr_pm != PM:
        from ..pm import E_NEW_PM
        events |= E_NEW_PM
        if PM.in_valid_pgnd:
            import os
            from ..bab import options
            from ..gtx import recollect
            from ..pm_gui import pm_wspce
            newdir = PM.get_playground_root()
            if not os.path.samefile(newdir, os.getcwd()):
                os.chdir(newdir)
                events |= enotify.E_CHANGE_WD
            pm_wspce.add_playground_path(newdir)
            recollect.set("workspace", "last_used", newdir)
            options.load_pgnd_options()
    from ..scm_gui import scm_gui_ifce
    curr_scm = scm_gui_ifce.SCM
    scm_gui_ifce.reset_scm_ifce()
    if curr_scm != scm_gui_ifce.SCM and not enotify.E_CHANGE_WD & events:
        from ..scm import E_NEW_SCM
        events |= E_NEW_SCM
    return events

def get_author_name_and_email():
    # TODO: generalise get_author_name_and_email() and use for both SCM and PM
    import email.utils
    from ..bab import utils
    from ..bab import options
    from ..scm_gui import scm_gui_ifce
    DEFAULT_NAME_EVARS = ["GECOS", "GIT_AUTHOR_NAME", "LOGNAME"]
    DEFAULT_EMAIL_EVARS = ["EMAIL_ADDRESS", "GIT_AUTHOR_EMAIL"]
    # first check for OUR definitions in the current pgnd
    email_addr = options.get("user", "email", pgnd_only=True)
    if email_addr:
        name = options.get("user", "name")
        return email.utils.formataddr((name if name else utils.get_first_in_envar(DEFAULT_NAME_EVARS, default="unknown"), email_addr,))
    # then ask the managers in order of relevance
    for mgr in [PM, scm_gui_ifce.SCM]:
        anae = mgr.get_author_name_and_email()
        if anae:
            return anae
    # then check for OUR global definitions
    email_addr = options.get("user", "email")
    if email_addr:
        name = options.get("user", "name")
        return email.utils.formataddr((name if name else utils.get_first_in_envar(DEFAULT_NAME_EVARS, default="unknown"), email_addr,))
    email_addr = utils.get_first_in_envar(DEFAULT_EMAIL_EVARS, default=None)
    if email_addr:
        name = options.get("user", "name")
        return email.utils.formataddr((name if name else utils.get_first_in_envar(DEFAULT_NAME_EVARS, default="unknown"), email_addr,))
    user = os.environ.get("LOGNAME", None)
    host = os.environ.get("HOSTNAME", None)
    if user and host:
        return email.utils.formataddr((user, "@".join([user, host]),))
    else:
        return _("Who knows? :-)")
