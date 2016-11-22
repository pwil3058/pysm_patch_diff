### Copyright (C) 2011-2016 Peter Williams <pwil3058@gmail.com>
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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Widget to display a complete patch"""

from gi.repository import Gtk

from ...gtx import recollect
from ...gtx import textview

from . import diff

def _framed(label, widget):
    frame = Gtk.Frame(label=label)
    frame.add(widget)
    return frame

class PatchWidget(Gtk.VBox):
    class TWSDisplay(diff.TwsLineCountDisplay):
        LABEL = _("File(s) that add TWS: ")

    def __init__(self, patch, label, header_aspect_ratio = 0.15):
        Gtk.VBox.__init__(self)
        self.epatch = patch
        #
        self.status_box = Gtk.HBox()
        self.status_box.show_all()
        self.tws_display = self.TWSDisplay()
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        hbox = Gtk.HBox()
        hbox.pack_start(self.status_box, expand=False, fill=True, padding=0)
        self._label = Gtk.Label(label)
        hbox.pack_start(self._label, expand=False, fill=True, padding=0)
        hbox.pack_end(self.tws_display, expand=False, fill=True, padding=0)
        self.pack_start(hbox, expand=False, fill=True, padding=0)
        #
        self._vpaned = Gtk.VPaned()
        self.pack_start(self._vpaned, expand=True, fill=True, padding=0)
        #
        self.header_nbook = Gtk.Notebook()
        self.header_nbook.popup_enable()
        self._vpaned.add1(_framed(_("Header"), self.header_nbook))
        #
        self.description = textview.Widget(aspect_ratio=header_aspect_ratio)
        self.description.set_contents(self.epatch.get_description())
        self.description.view.set_editable(False)
        self.description.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.description, Gtk.Label(_("Description")))
        #
        self.diffstats = textview.Widget(aspect_ratio=header_aspect_ratio)
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self.diffstats.view.set_editable(False)
        self.diffstats.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.diffstats, Gtk.Label(_("Diff Statistics")))
        #
        self.comments = textview.Widget(aspect_ratio=header_aspect_ratio)
        self.comments.set_contents(self.epatch.get_comments())
        self.comments.view.set_editable(False)
        self.comments.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.comments, Gtk.Label(_("Comments")))
        #
        self.diffs_nbook = diff.DiffPlusNotebook(self.epatch.diff_pluses)
        self._vpaned.add2(_framed(_("File Diffs"), self.diffs_nbook))
        #
        self.show_all()

    def set_label(self, label_text):
        self._label.set_text(label_text)

    def set_patch(self, epatch):
        if epatch.get_hash_digest() == self.epatch.get_hash_digest():
            return
        self.epatch = epatch
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        self.comments.set_contents(self.epatch.get_comments())
        self.description.set_contents(self.epatch.get_description())
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self.diffs_nbook.set_diff_pluses(self.epatch.diff_pluses)

    def set_paned_notify_fm_recollect(self, section, oname):
        self._vpaned.set_position(recollect.get(section, oname))
        self._vpaned.connect("notify", self._paned_notify_cb, section, oname)

    def _paned_notify_cb(self, widget, parameter, section, oname):
        if parameter.name == "position":
            recollect.set(section, oname, str(widget.get_position()))
