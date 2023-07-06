# Copyright (C) 2021-2023 Himadri Sekhar Basu <hsb10@iitbbs.ac.in>
# 
# This file is part of LeapTime Manager.
# 
# LeapTime Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# LeapTime Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with LeapTime Manager. If not, see <http://www.gnu.org/licenses/>
# or write to the Free Software Foundation, Inc., 51 Franklin Street,
# Fifth Floor, Boston, MA 02110-1301, USA..
# 
# Author: Himadri Sekhar Basu <hsb10@iitbbs.ac.in>
#

# import the necessary modules!
import gettext
import gi
import locale
import logging
import os
import stat
import sys
import tarfile
import time

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk

# imports from current package
from LeaptimeManager.common import APP, LOCALE_DIR, DATA_LOG_DIR, _async, _print_timing
from LeaptimeManager.database_rw import databackup_db
from LeaptimeManager.dialogs import show_message

# i18n
locale.bindtextdomain(APP, LOCALE_DIR)
gettext.bindtextdomain(APP, LOCALE_DIR)
gettext.textdomain(APP)
_ = gettext.gettext

# logger
module_logger = logging.getLogger('LeaptimeManager.dataBackup')

# Constants
COL_NAME, COL_METHOD, COL_SOURCE, COL_DESTINATION, COL_CREATED, COL_REPEAT, COL_COMMENT = range(7)
META_FILE = ".meta"

class UserData_backend():
	
	def __init__(self) -> None:
		module_logger.info(_("Initializing User Data backend class..."))

class UserData():
	"""
	GUI class for backing up and restoring user data
	using rsync
	"""
	def __init__(self, builder, window, stack, button_back, button_forward, button_apply) -> None:
		module_logger.info(_("Initializing user data backup class..."))
		self.builder = builder
		self.window = window
		self.stack = stack
		self.db_manager = databackup_db()
		# inidicates whether an operation is taking place.
		self.operating = False
		
		# backup default settings
		self.tar_archive = None
		self.follow_links = True
		self.backup_name = ""
		
		# nav buttons
		self.button_back = button_back
		self.button_forward = button_forward
		self.button_apply = button_apply
		
		self.button_back.connect("clicked", self.back_callback)
		self.button_forward.connect("clicked", self.forward_callback)
		self.button_apply.connect("clicked", self.forward_callback)
		
		# entries
		self.backup_name_entry = self.builder.get_object("data_backup_name")
		self.backup_desc_entry = self.builder.get_object("data_backup_comment")
		
		# Existing backup list treeview
		self.allbackup_tree = self.builder.get_object("treeview_all_databackup_list")
		# Name column
		column = Gtk.TreeViewColumn(_("Name"), Gtk.CellRendererText(), text=COL_NAME)
		column.set_sort_column_id(COL_NAME)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		# Method column
		column = Gtk.TreeViewColumn(_("Method"), Gtk.CellRendererText(), text=COL_METHOD)
		column.set_sort_column_id(COL_METHOD)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		# Source column
		column = Gtk.TreeViewColumn(_("Source"), Gtk.CellRendererText(), text=COL_SOURCE)
		column.set_sort_column_id(COL_SOURCE)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		# Destination column
		column = Gtk.TreeViewColumn(_("Destination"), Gtk.CellRendererText(), text=COL_DESTINATION)
		column.set_sort_column_id(COL_DESTINATION)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		# Created on column
		column = Gtk.TreeViewColumn(_("Created"), Gtk.CellRendererText(), text=COL_CREATED)
		column.set_sort_column_id(COL_CREATED)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		# Repeat job column
		column = Gtk.TreeViewColumn(_("Repeat"), Gtk.CellRendererText(), text=COL_REPEAT)
		column.set_sort_column_id(COL_REPEAT)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		# Comment column
		column = Gtk.TreeViewColumn(_("Comment"), Gtk.CellRendererText(), text=COL_COMMENT)
		column.set_sort_column_id(COL_COMMENT)
		column.set_resizable(True)
		self.allbackup_tree.append_column(column)
		
		self.allbackup_tree.show()
		self.model = Gtk.TreeStore(str, str, str, str, str, str, str)  # name, method, source, destination, created, repeat, comment
		self.model.set_sort_column_id(COL_NAME, Gtk.SortType.ASCENDING)
		self.allbackup_tree.set_model(self.model)
		
		# Select source
		filechooser_src = self.builder.get_object("filechooserbutton_backup_source")
		filechooser_src.connect("file-set", self.on_select_src)
		
		# Select destination
		filechooser_dest = self.builder.get_object("filechooserbutton_backup_dest")
		filechooser_dest.connect("file-set", self.on_select_dest)
		
		# Combo box
		self.methods_combo = self.builder.get_object("methods_combo")
		self.methods_combo.set_active(0)
		self.methods_combo.connect("changed", self.method_combo_changed)
		
		# tarball combo
		self.tarballs_combo = self.builder.get_object("tar_format_combo")
		self.tarballs_combo.set_active(0)
		self.tarballs_combo.connect("changed", self.tar_format_combo_changed)
		
		# set up exclusions page
		self.iconTheme = Gtk.IconTheme.get_default()
		self.dir_icon = self.iconTheme.load_icon("folder-symbolic", 16, 0)
		self.file_icon = self.iconTheme.load_icon("folder-documents-symbolic", 16, 0)
		treeview = self.builder.get_object("treeview_excludes")
		renderer = Gtk.CellRendererPixbuf()
		column = Gtk.TreeViewColumn("", renderer)
		column.add_attribute(renderer, "pixbuf", 1)
		treeview.append_column(column)
		renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn("", renderer)
		column.add_attribute(renderer, "text", 0)
		treeview.append_column(column)
		self.excludes_model = Gtk.ListStore(str, GdkPixbuf.Pixbuf, str)
		self.excludes_model.set_sort_column_id(0, Gtk.SortType.ASCENDING)
		treeview.set_model(self.excludes_model)
		self.builder.get_object("button_add_file").connect("clicked", self.add_item_to_treeview, treeview, self.file_icon, Gtk.FileChooserAction.OPEN, False)
		self.builder.get_object("button_add_folder").connect("clicked", self.add_item_to_treeview, treeview, self.dir_icon, Gtk.FileChooserAction.SELECT_FOLDER, False)
		self.builder.get_object("button_remove_exclude").connect("clicked", self.remove_item_from_treeview, treeview)
		self.builder.get_object("treeview_excludes_selection").connect("changed", self.on_treeview_excludes_selection_changed)
		
		# set up inclusions page
		treeview = self.builder.get_object("treeview_includes")
		renderer = Gtk.CellRendererPixbuf()
		column = Gtk.TreeViewColumn("", renderer)
		column.add_attribute(renderer, "pixbuf", 1)
		treeview.append_column(column)
		renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('', renderer)
		column.add_attribute(renderer, "text", 0)
		treeview.append_column(column)
		self.includes_model = Gtk.ListStore(str, GdkPixbuf.Pixbuf, str)
		self.includes_model.set_sort_column_id(0, Gtk.SortType.ASCENDING)
		treeview.set_model(self.includes_model)
		self.builder.get_object("button_include_hidden_files").connect("clicked", self.add_item_to_treeview, treeview, self.file_icon, Gtk.FileChooserAction.OPEN, True)
		self.builder.get_object("button_include_hidden_dirs").connect("clicked", self.add_item_to_treeview, treeview, self.dir_icon, Gtk.FileChooserAction.SELECT_FOLDER, True)
		self.builder.get_object("button_remove_include").connect("clicked", self.remove_item_from_treeview, treeview)
		
	def back_callback(self, widget):
		# Back button
		page = self.stack.get_visible_child_name()
		module_logger.debug(_("Previous page: %s"), page)
		if page == "databackup_page1" or page == "datarestore_page1":
			# Show App backup main page
			self.load_mainpage()
		elif page == "databackup_page2":
			# show page 1 of data backup
			self.stack.set_visible_child_name("databackup_page1")
			self.backup_name_entry.set_text(self.backup_name)
			self.backup_desc_entry.set_text(self.backup_desc)
		elif page == "databackup_page3":
			# show page 2 (excludes page) of data backup
			self.stack.set_visible_child_name("databackup_page2")
			self.button_forward.show()
			self.button_apply.hide()
			# Cannot be returned from backup page 4 and 5
			# So, no back button for page 4 and 5
		
		page = self.stack.get_visible_child_name()
		module_logger.debug(_("Showing databackup page: %s on back button"), page)
	
	def forward_callback(self, widget):
		# Go forward
		page = self.stack.get_visible_child_name()
		module_logger.debug(_("Previous page: %s"), page)
		self.button_back.set_sensitive(True)
		if page == "databackup_page1":
			# Gather info from page 1
			self.prep_backup()
			# show page 2 of data backup
			self.stack.set_visible_child_name("databackup_page2")
		elif page == "databackup_page2":
			# Gather info from page 2
			self.calculate_excludes()
			# show page 3 (includes page) of data backup
			self.stack.set_visible_child_name("databackup_page3")
			self.button_forward.hide()
			self.button_apply.show()
			self.button_apply.set_label(_("Start Backup"))
		elif page == "databackup_page3":
			# Gather info from page 3
			self.calculate_includes()
			# show page 4 of data backup
			self.stack.set_visible_child_name("databackup_page4")
			self.button_back.hide()
			self.button_apply.hide()
			# start the actual backup in another thread
			_async(self.backup_data)
		
		page = self.stack.get_visible_child_name()
		module_logger.debug(_("Showing databackup page: %s on forward button"), page)
	
	def on_select_src(self, filechooser):
		self.source_dir = filechooser.get_filename()
	
	def on_select_dest(self, filechooser):
		self.dest_dir = filechooser.get_filename()
	
	def tar_format_combo_changed(self, combotext):
		self.tar_backup_format = combotext.get_active_text()
		module_logger.debug(_("Tarball format for backup: %s"),self.tar_backup_format)
	
	def method_combo_changed(self, combotext):
		self.backup_method = combotext.get_active_text()
		module_logger.debug(_("Using backup method: %s"),self.backup_method)
		if self.backup_method == "rsync":
			self.builder.get_object("tar_format_label").set_visible(False)
			self.builder.get_object("tar_format_combo").set_visible(False)
		else:
			self.builder.get_object("tar_format_label").set_visible(True)
			self.builder.get_object("tar_format_combo").set_visible(True)
	
	def on_treeview_excludes_selection_changed(self, selection):
		liststore, treeiter = selection.get_selected()
		self.builder.get_object("button_remove_exclude").set_sensitive((treeiter and liststore.get_value(treeiter, 2) != self.dest_dir))
	
	def add_item_to_treeview(self, widget, treeview, icon, mode, show_hidden=False):
		# Add a file or directory to treeview
		if mode == Gtk.FileChooserAction.OPEN:
			title= _("Data Backup - Select files")
		else:
			title= _("Data Backup - Select folders")
		dialog = Gtk.FileChooserDialog(title=title, parent=self.window, action=mode)
		dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
		dialog.set_current_folder(self.source_dir)
		dialog.set_select_multiple(True)
		dialog.set_show_hidden(show_hidden)
		if dialog.run() == Gtk.ResponseType.OK:
			filenames = dialog.get_filenames()
			for filename in filenames:
				if not filename.find(self.source_dir):
					found = False
					model = treeview.get_model()
					for row in model:
						if row[2] == filename:
							found = True
					if not found:
						treeview.get_model().append([filename[len(self.source_dir) + 1:], icon, filename])
				else:
					self.show_message(_("%s is not located in your source directory.") % filename)
		dialog.destroy()
	
	def remove_item_from_treeview(self, button, treeview):
		# Remove the item from the treeview
		model = treeview.get_model()
		selection = treeview.get_selection()
		selected_rows = selection.get_selected_rows()[1]
		args = [(model.get_iter(path)) for path in selected_rows]
		for iter in args:
			model.remove(iter)
	
	def prep_backup(self):
		module_logger.debug(_("Gathering info on backup."))
		self.backup_name = self.backup_name_entry.get_text()
		self.backup_desc = self.backup_desc_entry.get_text()
		self.backup_method = self.methods_combo.get_active_text()
		module_logger.debug(_("Name: %s, Description: %s, Source: %s, Destination: %s, Method: %s") %(self.backup_name, self.backup_desc, self.source_dir, self.dest_dir, self.backup_method))
		if self.backup_method == "tarball":
			self.tar_backup_format = self.tarballs_combo.get_active_text()
			module_logger.debug(_("Tar archive format: %s") % self.tar_backup_format)
	
	def calculate_excludes(self):
		# Calculate excludes
		self.excluded_dirs = []
		self.excluded_files = []
		for row in self.excludes_model:
			item = row[2]
			if os.path.exists(item):
				if os.path.isdir(item):
					self.excluded_dirs.append(item)
				else:
					self.excluded_files.append(item)
		module_logger.debug(_("Excluded files list: %s") % self.excluded_files)
		module_logger.debug(_("Excluded folder list: %s") % self.excluded_dirs)
	
	def calculate_includes(self):
		# Calculate includes
		self.included_dirs = []
		self.included_files = []
		for row in self.includes_model:
			item = row[2]
			if os.path.exists(item):
				if os.path.isdir(item):
					self.included_dirs.append(item)
				else:
					self.included_files.append(item)
		module_logger.debug(_("Included files list: %s") % self.included_files)
		module_logger.debug(_("Included folder list: %s") % self.included_dirs)
	
	def backup_data(self):
		if self.source_dir and self.dest_dir and os.access(self.backup_dest, os.W_OK):
			time_now = time.localtime()
			self.timestamp = time.strftime("%Y-%m-%d %H:%M", time_now)
			backuplog = DATA_LOG_DIR + self.backup_name + '.log'
			if self.backup_method == "rsync":
				module_logger.info(_("Starting backup using Rsync method..."))
				show_message(self.window, _("This feature has not been implented yet. Use tarball method."))
				# cmd = "rsync -aAXUH --checksum --compress --partial --progress %s %s" % (self.source_dir, self.dest_dir)
				# cmd = list(cmd.split(" "))
				# module_logger.debug(_("Running command: %s") % cmd)
				# with open(backuplog, "a") as logfile:
				# 	subprocess.Popen(cmd, shell=False, stdout=logfile)
				module_logger.info(_("%s is backed up into %s") % (self.source_dir, self.dest_dir))
			else:
				module_logger.info(_("Starting backup using tarball method..."))
				# show_message(self.window, _("This feature has not been implented yet. Use rsync method."))
			
			self.repeat = ""
			self.db_manager.write_db(self.data_db_list, self.backup_name, self.backup_method,
				 self.source_dir, self.dest_dir, self.timestamp, self.repeat, self.backup_desc)
		else:
			if not self.source_dir:
				module_logger.error(_("No source directory selected."))
			if not self.dest_dir:
				module_logger.error(_("No destination directory selected."))
			if not os.access(self.backup_dest, os.W_OK):
				self.show_message(_("You do not have the permission to write in the selected directory."))
	
	# Page load definition functions
	def load_mainpage(self):
		module_logger.debug(_("Loading main page with available data backups lists."))
		# Clear treeview and selection
		self.data_db_list = self.db_manager.read_db()
		module_logger.debug(_("Existing data backups: %s" % self.data_db_list))
		self.stack.set_visible_child_name("databackup_main")
		self.model.clear()
		for backup in self.data_db_list:
			iter = self.model.insert_before(None, None)
			self.model.set_value(iter, COL_NAME, backup["name"])
			self.model.set_value(iter, COL_METHOD, backup["method"])
			self.model.set_value(iter, COL_SOURCE, backup["source"])
			self.model.set_value(iter, COL_DESTINATION, backup["destination"])
			self.model.set_value(iter, COL_CREATED, backup["created"])
			self.model.set_value(iter, COL_REPEAT, backup["repeat"])
			self.model.set_value(iter, COL_COMMENT, backup["comment"])
		self.button_back.set_sensitive(False)
		self.button_back.hide()
		self.button_forward.hide()
		self.button_apply.hide()
	
	def on_backup_selected(self, selection):
		model, iter = selection.get_selected()
		if iter is not None:
			self.selected_webapp = model.get_value(iter, COL_NAME)
			self.remove_button.set_sensitive(True)
			self.edit_button.set_sensitive(True)
	
	# Action definitions for buttons on the main panel at the top
	def on_backup_data(self, widget):
		module_logger.info(_("Starting Data backup..."))
		self.stack.set_visible_child_name("databackup_page1")
		self.button_back.set_sensitive(True)
		self.button_back.show()
		self.button_forward.show()
	
	def on_restore_data(self, widget):
		module_logger.info(_("Starting Data restore..."))
		self.button_back.set_sensitive(True)
		self.button_back.show()
		self.button_forward.show()
		show_message(self.window, _("This feature has not been implented yet. Please wait for future releases."))
