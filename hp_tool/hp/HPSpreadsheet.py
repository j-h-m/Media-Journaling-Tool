import json
import subprocess
import tarfile
import ttk
from Tkinter import *
import tkFileDialog
import os
import sys
from operator import add

import boto3
from boto3.s3.transfer import S3Transfer
import collections
import pandas as pd
import tkMessageBox
import tkSimpleDialog
import pandastable
import csv
import webbrowser
import requests
import tempfile
import shutil
from PIL import Image, ImageTk
from ErrorWindow import ErrorWindow
import hp_data
import datetime
import threading
import data_files
from camera_handler import ValidResolutions, API_Camera_Handler
from FormHandler import FormSelector

RVERSION = hp_data.RVERSION

class HPSpreadsheet(Toplevel):
    """
    Allows for data entry in spreadsheet format for all HP data. Provides functions for validation, uploading,
    and UI management.
    """
    def __init__(self, settings, dir=None, ritCSV=None, master=None, devices=None):
        Toplevel.__init__(self, master=master)
        self.settings = settings
        self.dir = dir
        if self.dir:
            self.imageDir = os.path.join(self.dir, 'image')
            self.videoDir = os.path.join(self.dir, 'video')
            self.audioDir = os.path.join(self.dir, 'audio')
            self.modelDir = os.path.join(self.dir, 'model')
            self.thumbnailDir = os.path.join(self.dir, 'thumbnails')
            self.csvDir = os.path.join(self.dir, 'csv')
            self.formDir = os.path.join(self.dir, "release_forms")
            self.release_forms = os.listdir(self.formDir) if os.path.isdir(self.formDir) else []
        self.master = master
        self.ritCSV=ritCSV
        self.trello_key = data_files._TRELLO['app_key']
        self.saveState = True
        self.highlighted_cells = []
        self.error_cells = []
        self.temps_created = False
        self.device_type = None
        self.create_widgets()
        self.kinematics = self.load_kinematics()
        self.collections = sorted(hp_data.load_json_dictionary(data_files._COLLECTIONS).keys())
        self.collections.remove('None')
        self.devices = devices
        self.apps = self.load_apps()
        self.lensFilters = self.load_lens_filters()
        self.protocol('WM_DELETE_WINDOW', self.check_save)
        w, h = self.winfo_screenwidth()-100, self.winfo_screenheight()-100
        self.geometry("%dx%d+0+0" % (w, h))
        #self.attributes('-fullscreen', True)
        self.set_bindings()

    def create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.topFrame = Frame(self)
        self.topFrame.pack(side=TOP, fill=X)
        self.rightFrame = Frame(self, width=480)
        self.rightFrame.pack(side=RIGHT, fill=Y)
        self.leftFrame = Frame(self)
        self.leftFrame.pack(side=LEFT, fill=BOTH, expand=1)
        self.nb = ttk.Notebook(self.leftFrame)
        self.nb.pack(fill=BOTH, expand=1)
        self.nbtabs = {'main': ttk.Frame(self.nb)}
        self.nb.add(self.nbtabs['main'], text='All Items')
        self.pt = CustomTable(self.nbtabs['main'], scrollregion=None, width=1024, height=720,
                              color_cb=self.color_code_cells)
        self.pt.show()
        self.pt.bind_columns()
        self.on_main_tab = True
        self.add_tabs()
        self.nb.bind('<<NotebookTabChanged>>', self.switch_tabs)

        self.currentImageNameVar = StringVar()
        self.currentImageNameVar.set('Current Image: ')
        l = Label(self.topFrame, height=1, textvariable=self.currentImageNameVar)
        l.pack(fill=BOTH, expand=1)

        image = Image.open(data_files._REDX)
        image.thumbnail((250,250))
        self.photo = ImageTk.PhotoImage(image)
        self.l2 = Button(self.rightFrame, image=self.photo, command=self.open_image)
        self.l2.image = self.photo  # keep a reference!
        self.l2.pack(side=TOP)

        self.validateFrame = Frame(self.rightFrame, width=480)
        self.validateFrame.pack(side=BOTTOM)
        self.currentColumnLabel = Label(self.validateFrame, text='Current column:')
        self.currentColumnLabel.grid(row=0, column=0, columnspan=2)
        lbl = Label(self.validateFrame, text='Valid values for cells in this column:').grid(row=1, column=0, columnspan=2)
        self.vbVertScroll = Scrollbar(self.validateFrame)
        self.vbVertScroll.grid(row=2, column=1, sticky='NS')
        self.vbHorizScroll = Scrollbar(self.validateFrame, orient=HORIZONTAL)
        self.vbHorizScroll.grid(row=3, sticky='WE')
        self.validateBox = Listbox(self.validateFrame, xscrollcommand=self.vbHorizScroll.set, yscrollcommand=self.vbVertScroll.set, selectmode=SINGLE, width=50, height=14)
        self.validateBox.grid(row=2, column=0)
        self.vbVertScroll.config(command=self.validateBox.yview)
        self.vbHorizScroll.config(command=self.validateBox.xview)

        self.menubar = Menu(self)
        self.fileMenu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=self.fileMenu)
        self.fileMenu.add_command(label='Save', command=self.exportCSV, accelerator='ctrl-s')
        self.fileMenu.add_command(label='Validate', command=self.validate)
        self.fileMenu.add_command(label='Export to S3', command=self.s3export)
        self.fileMenu.add_command(label='Organize Columns', command=self.sort_columns)
        self.fileMenu.add_command(label="Edit Release Forms", command=lambda: FormSelector(self.formDir,
                                  self.release_forms, self.get_current_tab(), self))

        self.editMenu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label='Edit', menu=self.editMenu)
        self.editMenu.add_command(label='Copy', command=self.pt.copy_value, accelerator='ctrl-c')
        self.editMenu.add_command(label='Paste', command=self.pt.paste_value, accelerator='ctrl-v')
        self.editMenu.add_command(label='Fill Selection', command=self.pt.fill_selection, accelerator='ctrl-d')
        self.editMenu.add_command(label='Fill Column', command=self.pt.fill_column, accelerator='ctrl-g')
        self.editMenu.add_command(label='Fill True', command=self.pt.enter_true, accelerator='ctrl-t')
        self.editMenu.add_command(label='Fill False', command=self.pt.enter_false, accelerator='ctr-f')
        self.editMenu.add_command(label='Undo', command=self.undo, accelerator='ctrl-z')
        self.editMenu.add_command(label='Redo', command=self.redo, accelerator='ctrl-y')
        self.config(menu=self.menubar)

    def set_bindings(self):
        self.bind('<Key>', self.keypress)
        self.validateBox.bind('<Button-1>', self.keypress)
        self.bind('<Button-1>', self.update_current_image)
        self.bind('<Left>', self.update_current_image)
        self.bind('<Right>', self.update_current_image)
        self.bind('<Return>', self.update_current_image)
        self.bind('<Up>', self.update_current_image)
        self.bind('<Down>', self.update_current_image)
        self.bind('<Tab>', self.update_current_image)
        self.bind('<Control-s>', self.exportCSV)
        self.bind('<Control-z>', self.undo)
        self.bind('<Control-y>', self.redo)

    def get_current_tab(self):
        if self.on_main_tab:
            currentTable = self.pt
        else:
            currentTable = self.tabpt
        return currentTable

    def undo(self, event=None):
        """
        Will undo the most recent fill action. Does not undo regular single text entry.
        :param event: event trigger
        :return: None
        """
        currentTable = self.get_current_tab()
        if hasattr(currentTable, 'undo') and currentTable.undo and isinstance(currentTable.undo, list):
            currentTable.redo = []
            # cell: tuple (value, row, column)
            for cell in currentTable.undo:
                currentTable.redo.append((currentTable.model.getValueAt(cell[1], cell[2]), cell[1], cell[2]))
                currentTable.model.setValueAt(*cell)
            currentTable.redraw()

    def redo(self, event=None):
        """
        Will redo the most recent fill action, after undone with undo().
        :param event: event trigger
        :return: None
        """
        currentTable = self.get_current_tab()
        if hasattr(currentTable, 'redo') and currentTable.redo and isinstance(currentTable.redo, list):
            currentTable.undo = []
            for cell in currentTable.redo:
                currentTable.undo.append((currentTable.model.getValueAt(cell[1], cell[2]), cell[1], cell[2]))
                currentTable.model.setValueAt(cell[0], cell[1], cell[2])
            currentTable.redraw()

    def keypress(self, event):
        # any time a key is pressed in spreadsheet, assume the sheet needs to be saved
        self.saveState = False

    def open_image(self):
        """
        Open clicked image in system default viewer. Primarily for video and raw files.
        :return: None
        """
        image = os.path.join(self.imageDir, self.imName)
        if not os.path.exists(image):
            image = os.path.join(self.videoDir, self.imName)
            if not os.path.exists(image):
                image = os.path.join(self.audioDir, self.imName)
                if not os.path.exists(image):
                    image = os.path.join(self.modelDir, self.imName[:-6], self.imName)
                    if not os.path.exists(image):
                        image = os.path.join(self.thumbnailDir, self.imName)
        if sys.platform.startswith('linux'):
            os.system('xdg-open "' + image + '"')
        elif sys.platform.startswith('win'):
            try:
                os.startfile(image)
            except WindowsError:
                print("Image could not be opened")

        else:
            os.system('open "' + image + '"')

    def update_current_image(self, event=None):
        """
        Open image in preview pane on right side based on current cell. Open default Red X image if fails.
        :param event: event trigger
        :return: None
        """
        import hp.hp_data
        row = self.get_current_tab().getSelectedRow()
        type = self.pt.model.getValueAt(row, 32)
        current_file = str(self.pt.model.getValueAt(row, self.pt.get_col_by_name("ImageFilename")))

        self.imName = str(self.pt.model.getValueAt(row, 0) if (type == "image" and "." + self.pt.model.getValueAt(row, 13).lower() not in hp_data.exts['nonstandard']) else self.pt.model.getValueAt(row, 61).split(";")[0])

        self.currentImageNameVar.set('Current Image: ' + current_file)
        maxSize = 480
        try:
            type_col = self.pt.get_col_by_name("FileType")

            if type == "image":
                im = Image.open(os.path.join(self.imageDir, self.imName))
            elif type == "model":
                im = Image.open(os.path.join(self.modelDir, current_file.split(".")[0], self.imName))
            else:
                im = Image.open(os.path.join(self.thumbnailDir, self.imName))
        except (IOError, AttributeError):
            im = Image.open(data_files._REDX)
        if im.size[0] > maxSize or im.size[1] > maxSize:
            im.thumbnail((maxSize,maxSize), Image.ANTIALIAS)
        newimg=ImageTk.PhotoImage(im)
        self.l2.configure(image=newimg)
        self.l2.image = newimg
        self.update_valid_values()

    def add_tabs(self):
        """
        Add tabs to the spreadsheet. More tabs can be added in data/hptabs.json
        :return: None
        """
        with open(data_files._HPTABS) as j:
            tabs = json.load(j, object_pairs_hook=collections.OrderedDict)
        for tab in tabs:
            self.nbtabs[tab] = ttk.Frame(self.nb)
            self.nb.add(self.nbtabs[tab], text=tab)

    def switch_tabs(self, event=None):
        """
        Logic handling for spreadsheet tabs. Main tab still acts as control. When a different tab is selected, ensures
        main tab is updated, and then pulls data from main tab.
        :param event: event trigger
        :return: None
        """
        with open(data_files._HPTABS) as j:
            tabs = json.load(j)
        clickedTab = self.nb.tab(event.widget.select(), 'text')
        if clickedTab == 'All Items':
            self.update_main()
            self.on_main_tab = True
            self.pt.bind_columns()
        else:
            self.update_main()
            headers = tabs[clickedTab]
            self.tabpt = CustomTable(self.nbtabs[clickedTab], scrollregion=None, width=1024, height=720, rows=0, cols=0,
                                     color_cb=self.color_code_cells)
            for h in headers:
                self.tabpt.model.df[h] = self.pt.model.df[h]
            self.tabpt.show()
            self.tabpt.bind_columns(self.tabpt)
            self.tabpt.redraw()
            self.on_main_tab = False
            self.color_code_cells(self.tabpt)

    def update_main(self):
        if self.on_main_tab:
            # switching from main tab to another. don't need to do any extra prep
            pass
        else:
            # switching from an alt tab, to any other tab. need to save headers back into pt, and then del tabpt
            for h in self.tabpt.model.df:
                self.pt.model.df[h] = self.tabpt.model.df[h]
            del self.tabpt

    def update_valid_values(self):
        """
        Cheap function to handle instructions/value selection for cells. Started small, but has grown considerably.
        Should be refactored when time allows.
        :return: None
        """
        col = self.get_current_tab().getSelectedColumn()
        cols = list(self.get_current_tab().model.df)
        currentCol = cols[col]
        self.currentColumnLabel.config(text='Current column: ' + currentCol)
        if currentCol in self.booleanColNames:
            validValues = ['True', 'False']
        elif currentCol == 'HP-CameraKinematics':
            validValues = self.kinematics
        elif currentCol == 'HP-JpgQuality':
            validValues = ['High', 'Medium', 'Low']
        elif currentCol == 'Type':
            validValues = ['image', 'video', 'audio']
        elif currentCol == 'CameraMake':
            validValues = self.load_device_exif('exif_camera_make')
        elif currentCol == 'CameraModel':
            validValues = self.load_device_exif('exif_camera_model')
        elif currentCol == 'HP-CameraModel':
            validValues = sorted(set([self.devices[data]['hp_camera_model'] for data in self.devices if self.devices[data]['hp_camera_model'] is not None]), key=lambda s: s.lower())
        elif currentCol == 'DeviceSN':
            validValues = self.load_device_exif('exif_device_serial_number')
        elif currentCol == 'HP-App':
            validValues = self.apps
        elif currentCol == 'HP-LensFilter':
            validValues = self.lensFilters
        elif currentCol == 'HP-DeviceLocalID':
            validValues = sorted(self.devices.keys())
        elif currentCol == 'HP-ProximitytoSource':
            validValues = ['close', 'medium', 'far']
        elif currentCol == 'HP-AudioChannels':
            validValues = ['stereo', 'mono']
        elif currentCol ==  "HP-BackgroundNoise":
            validValues = ["constant", "intermittant", "none"]
        elif currentCol == "HP-Description":
            validValues = ["voice", "man-made object", "weather", "environment"]
        elif currentCol == "HP-MicLocation":
            validValues = ["built in", "attached to recorder", "attached to subject", "boom pole"]
        elif currentCol == "HP-AngleofRecording":
            validValues = ["12:00", "1:00", "2:00", "3:00", "4:00", "5:00", "6:00", "7:00", "8:00", "9:00", "10:00", "11:00"]
        elif currentCol == 'HP-PrimarySecondary':
            validValues = ['primary', 'secondary']
        elif currentCol == 'HP-ZoomLevel':
            validValues = ['max optical zoom', 'max digital zoom', 'no zoom']
        elif currentCol == 'HP-Recapture':
            validValues = ['Screenshot', 'scan', 're-photograph']
        elif currentCol == 'HP-LightSource':
            validValues = ['overhead fluorescent', 'daylight', 'cloudy', 'two surrounding fluorescent lights', 'Two Impact Fluorescent Ready Cool 22 lights on each side']
        elif currentCol == 'HP-Orientation':
            validValues = ['landscape', 'portrait']
        elif currentCol == 'HP-DynamicStatic':
            validValues = ['dynamic', 'static']
        elif currentCol == 'HP-Collection':
            validValues = self.collections
        elif currentCol == 'HP-License':
            validValues = ['CC-0']
        elif currentCol in ['ImageWidth', 'ImageHeight', 'BitDepth', 'HP-PolyCount']:
            validValues = {'instructions':'Any integer value'}
        elif currentCol in ['GPSLongitude', 'GPSLatitude']:
            validValues = {'instructions':'Coodinates, specified in decimal degree format'}
        elif currentCol == 'CreationDate':
            validValues = {'instructions':'Date/Time, specified as \"YYYY:MM:DD HH:mm:SS\"'}
        elif currentCol == 'FileType':
            validValues = {'instructions':'Any file extension, without the dot (.) (e.g. jpg, png)'}
        elif currentCol == 'HP-LensLocalID':
            validValues = {'instructions':'Local ID number (PAR, RIT) of lens'}
        elif currentCol == 'HP-NumberOfSpeakers':
            validValues = {'instructions':'Number of people speaking in recording. Do not count background noise.'}
        elif currentCol == 'HP-ReleaseForms':
            validValues = {'values': self.release_forms, 'type': 'multiselect'}

        else:
            validValues = {'instructions':'Any string of text'}

        self.validateBox.delete(0, END)
        if type(validValues) == dict:
            types = {"multiselect": self.multi_select_insert,
                     "additionalaction": lambda *args: self.check_additional(currentCol, *args)}
            self.validateBox.unbind('<<ListboxSelect>>')
            if 'instructions' in validValues:
                self.validateBox.insert(END, validValues['instructions'])
            if 'values' in validValues:
                for v in validValues['values']:
                    self.validateBox.insert(END, v)
            if 'type' in validValues:
                self.validateBox.bind('<<ListboxSelect>>', types[validValues['type']])
        else:
            for v in validValues:
                self.validateBox.insert(END, v)
            self.validateBox.bind('<<ListboxSelect>>', self.insert_item)

    def multi_select_insert(self, event):
        selection = event.widget.curselection()

        try:
            val = event.widget.get(selection[0])
        except IndexError:
            return

        if self.on_main_tab:
            currentTable = self.pt
        else:
            currentTable = self.tabpt

        row = currentTable.getSelectedRow()
        col = currentTable.getSelectedColumn()

        try:
            if ((row, col) in currentTable.disabled_cells) and not ((row, col) in currentTable.special_cells):
                return
        except AttributeError:
            pass

        current_values = currentTable.model.getValueAt(row, col).split(", ")
        if "" in current_values:
            current_values.pop(current_values.index(""))

        if val in current_values:
            current_values.pop(current_values.index(val))
        else:
            current_values.append(val)

        currentTable.undo = [(currentTable.model.getValueAt(row, col), row, col)]
        currentTable.model.setValueAt(", ".join(sorted(current_values)), row, col)
        currentTable.redraw()

        if hasattr(currentTable, 'cellentry'):
            currentTable.cellentry.destroy()

        currentTable.parentframe.focus_set()


    def check_additional(self, column_name):
        if self.on_main_tab:
            currentTable = self.pt
        else:
            currentTable = self.tabpt

        ops = {}

        try:
            ops[column_name]
        except KeyError:
            pass
        return

    def load_device_exif(self, field):
        """
        Load all valid values for a particular exif field, based on known camera configurations.
        :param field: string, field to search for
        :return: sorted, lowercase list of valid values for that field
        """
        output = []
        for cameraID, data in self.master.cameras.iteritems():
            for configuration in data['exif']:
                output.append(configuration[field])
        return sorted(set([x for x in output if x is not None]), key = lambda s: s.lower())

    def insert_item(self, event=None):
        """
        Inserts a value in the current cell from valid values box when value is clicked.
        :param event: event trigger
        :return: None
        """
        selection = event.widget.curselection()
        val = event.widget.get(selection[0])
        if self.on_main_tab:
            currentTable = self.pt
        else:
            currentTable = self.tabpt

        row = currentTable.getSelectedRow()
        col = currentTable.getSelectedColumn()

        if hasattr(currentTable, 'disabled_cells') and (row, col) in currentTable.disabled_cells:
            return

        currentTable.undo = [(currentTable.model.getValueAt(row, col), row, col)]
        currentTable.model.setValueAt(val, row, col)
        currentTable.redraw()
        if hasattr(currentTable, 'cellentry'):
            currentTable.cellentry.destroy()
        currentTable.parentframe.focus_set()

    def open_spreadsheet(self):
        """
        Call this function to load the CSV file and set the table defaults/settings
        :return: None
        """
        if self.dir and not self.ritCSV:
            for f in os.listdir(self.csvDir):
                if f.endswith('.csv') and 'rit' in f:
                    self.ritCSV = os.path.join(self.csvDir, f)
        self.title(self.ritCSV)
        self.pt.importCSV(self.ritCSV)

        self.booleanColNums = []
        self.booleanColNames = ['HP-OnboardFilter', 'HP-WeakReflection', 'HP-StrongReflection', 'HP-TransparentReflection',
                        'HP-ReflectedObject', 'HP-Shadows', 'HP-HDR', 'HP-Inside', 'HP-Outside', 'HP-MultiInput', 'HP-Echo', 'HP-Modifier', 'HP-MultipleLightSources']
        for b in self.booleanColNames:
            if b in self.pt.model.df:
                self.booleanColNums.append(self.pt.model.df.columns.get_loc(b))

        self.mandatoryImage = []
        self.mandatoryImageNames = ['HP-OnboardFilter', 'HP-HDR', 'HP-DeviceLocalID', 'HP-Inside', 'HP-Outside', 'HP-PrimarySecondary']
        for i in self.mandatoryImageNames:
            self.mandatoryImage.append(self.pt.model.df.columns.get_loc(i))

        self.mandatoryVideo = []
        self.mandatoryVideoNames = self.mandatoryImageNames + ['HP-CameraKinematics']
        for v in self.mandatoryVideoNames:
            self.mandatoryVideo.append(self.pt.model.df.columns.get_loc(v))

        self.mandatoryAudioNames = ['HP-DeviceLocalID', 'HP-OnboardFilter', 'HP-ProximitytoSource', 'HP-MultiInput', 'HP-AudioChannels',
                 'HP-Echo', 'HP-BackgroundNoise', 'HP-Description', 'HP-Modifier','HP-AngleofRecording', 'HP-MicLocation',
                 'HP-Inside', 'HP-Outside', 'HP-NumberOfSpeakers']
        self.mandatoryAudio = []
        for c in self.mandatoryAudioNames:
            self.mandatoryAudio.append(self.pt.model.df.columns.get_loc(c))

        self.mandatoryModels = []
        self.mandatoryModelNames = ['HP-Keywords', 'HP-PolyCount', 'HP-License']
        for m in self.mandatoryModelNames:
            self.mandatoryModels.append(self.pt.model.df. columns.get_loc(m))

        self.disabledColNames = ['HP-DeviceLocalID', 'HP-CameraModel', 'CameraModel', 'DeviceSN', 'CameraMake',
                                 'HP-Thumbnails', 'HP-Username', 'HP-seed', 'HP-HDLocation']
        self.disabledCols = []
        for d in self.disabledColNames:
            self.disabledCols.append(self.pt.model.df.columns.get_loc(d))

        #self.mandatory = {'image':self.mandatoryImage, 'video':self.mandatoryVideo, 'audio':self.mandatoryAudio}

        self.processErrors = self.check_process_errors()
        self.exportCSV(False, True)
        self.update_current_image()
        self.master.statusBox.println('Loaded data from ' + self.ritCSV)

    def get_old_name(self, newname):
        old_col = self.pt.get_col_by_name('OriginalImageName')
        image_row = self.pt.get_row_by_image_name(newname)
        if not image_row:
            return newname

        return self.pt.model.getValueAt(image_row, old_col)

    def color_code_cells(self, tab=None):
        """
        Go through all cells and check color coding. Called when spreadsheet is first opened, and after each validation.
        GRAY (#c1c1c1) indicates cell is DISABLED
        YELLOW (#f3f315) indicates cell is MANDATORY
        RED (#ff5b5b) indicates an ERROR in that cell
        BLUE (#66edff) indicates a special entry (No Manual Entry)
        WHITE (#ffffff) is NORMAL
        :param tab: (optional), specify current tab (self.tabpt)
        :return: None
        """
        if tab is None:
            tab = self.pt
            track_highlights = True
        else:
            track_highlights = False
        tab.disabled_cells = []
        tab.special_cells = []

        local_id = self.pt.model.getValueAt(0, 9)

        if not self.device_type and local_id:
            cam_handler = API_Camera_Handler(self, self.settings.get_key("apiurl"), self.settings.get_key("apitoken"),
                                             local_id)
            self.device_type = cam_handler.get_types()[0] if cam_handler.get_types() else "model"

        props = {"disabled": {"color": "#c1c1c1", "disabled": True},
                 "mandatory": {"color": "#f3f315", "disabled": False},
                 "specialentry": {"color": "#66edff", "disabled": True},
                 "enable": {"color": "#fff", "disabled": False}}

        notnans = tab.model.df.notnull()
        tab.delete("all")
        for row in range(0, tab.rows):
            for col in range(0, tab.cols):
                colName = list(tab.model.df)[col]
                fname = self.pt.model.getValueAt(row, 0)
                currentExt = os.path.splitext(fname)[1].lower()
                x1, y1, x2, y2 = tab.getCellCoords(row, col)

                celltype = \
                    "disabled" if (notnans.iloc[row, col] and not colName.startswith("HP")) or (colName in
                               self.disabledColNames or (colName == "HP-PrimarySecondary" and self.device_type !=
                               "CellPhone") or (colName == "HP-Keywords" and self.device_type != "model")) else\
                    "mandatory" if (colName in self.mandatoryImageNames and currentExt in hp_data.exts['IMAGE']) or \
                              (colName in self.mandatoryVideoNames and ((currentExt in hp_data.exts['VIDEO']) or
                              fname.lower().endswith(".dng.zip"))) or (colName in self.mandatoryAudioNames and
                              currentExt in hp_data.exts['AUDIO']) or (colName in self.mandatoryModelNames and
                              hp_data.is_model(self.pt.model.getValueAt(row, 0))) else\
                    "specialentry" if colName in ["HP-ReleaseForms"] else\
                    "enable"

                rect = tab.create_rectangle(x1, y1, x2, y2, fill=props[celltype]["color"], outline="#084B8A",
                                            tag="cellrect")

                if props[celltype]["disabled"]:
                    tab.disabled_cells.append((row, col))
                if celltype == "specialentry":
                    tab.special_cells.append((row, col))

            image = self.pt.model.df['OriginalImageName'][row]
            if self.processErrors is not None and image in self.processErrors and self.processErrors[image]:
                for errors in self.processErrors[image]:
                    for errCol in errors[0]:
                        try:
                            col = tab.model.df.columns.get_loc(errCol)
                            x1, y1, x2, y2 = tab.getCellCoords(row, col)
                            rect = tab.create_rectangle(x1, y1, x2, y2,
                                                        fill='#ff5b5b',
                                                        outline='#084B8A',
                                                        tag='cellrect')
                            self.error_cells.append((row, col))
                        except KeyError:
                            continue

        tab.lift('cellrect')
        tab.redraw()

    def sort_columns(self):
        if not self.on_main_tab:
            self.nb.select(self.nbtabs['main'])
            self.update_main()
            self.on_main_tab = True
        with open(data_files._HEADERS, "r") as f:
            headers = json.load(f)["rit"]
        valid = [x for x in headers if x in self.pt.model.df]
        self.pt.model.df = self.pt.model.df[valid]
        self.pt.redraw()
        self.color_code_cells()
        return

    def exportCSV(self, showErrors=True, quiet=False):
        """
        Export the spreadsheet to CSV. DOES NOT EXPORT TO S3 (see s3export).
        :param showErrors: boolean, set False to skip validation
        :param quiet: boolean, set True to skip message dialog pop-ups
        :return: True if cancelled, None otherwise
        """
        self.sort_columns()
        self.pt.doExport(self.ritCSV)
        tmp = self.ritCSV + '-tmp.csv'
        with open(self.ritCSV, 'r') as source:
            rdr = csv.reader(source)
            with open(tmp, 'wb') as result:
                wtr = csv.writer(result, lineterminator='\n', quoting=csv.QUOTE_ALL)
                for r in rdr:
                    wtr.writerow((r[1:]))
        os.remove(self.ritCSV)
        shutil.move(tmp, self.ritCSV)
        self.export_rankOne()
        self.saveState = True
        self.color_code_cells()
        if not quiet and showErrors:
            msg = tkMessageBox.showinfo('Status', 'Saved! The spreadsheet will now be validated.', parent=self)
        if showErrors:
            try:
                (errors, cancelled) = self.validate()
                if cancelled == True:
                    return cancelled
            except (AttributeError, IOError):
                print 'Spreadsheet could not be validated, but will still be saved. Ensure all fields have proper data.'
        return None

    def export_rankOne(self):
        """
        Export the rankOne csv. This file is the one that is actually processed on ingest.
        :return: None
        """
        global RVERSION
        self.rankOnecsv = self.ritCSV.replace('-rit.csv', '-rankone.csv')
        with open(data_files._HEADERS) as j:
            headers = json.load(j)['rankone']

        # extract keyword data
        old_rankone_data = pd.read_csv(self.rankOnecsv, header=1)
        try:
            keywords = old_rankone_data['HP-Keywords'].tolist()
        except KeyError:
            pass

        with open(self.rankOnecsv, 'w') as ro:
            wtr = csv.writer(ro, lineterminator='\n', quoting=csv.QUOTE_ALL)
            wtr.writerow([RVERSION])
            now = datetime.datetime.today().strftime('%m/%d/%Y %I:%M:%S %p')
            subset = self.pt.model.df.filter(items=headers)
            importDates = []
            for row in range(0, len(subset.index)):
                importDates.append(now)
            subset['ImportDate'] = importDates
            try:
                # insert keyword data into csv
                subset['HP-Keywords'] = keywords
            except:
                pass
            subset.to_csv(ro, columns=headers, index=False, quoting=csv.QUOTE_ALL)

    def s3export(self):
        """
        Process control for HP Data S3 uploading
        :return: None
        """
        cancelled = self.exportCSV(quiet=True)
        if cancelled:
            return

        initial = self.settings.get_key('aws-hp')
        val = tkSimpleDialog.askstring(title='Export to S3', prompt='S3 bucket/folder to upload to.', initialvalue=initial, parent=self)

        if val is not None and len(val) > 0:
            self.settings.save('aws-hp', val)

            BUCKET = val.split('/')[0].strip()
            DIR = val[val.find('/') + 1:].strip()
            DIR = DIR if DIR.endswith('/') else DIR + '/'

            archives_in_dir = [x for x in os.listdir(self.dir) if os.path.splitext(x)[1] == ".tar" and
                               self.is_hp_archive(x)]
            encryptions_in_dir = [x for x in os.listdir(self.dir) if os.path.splitext(x)[1] == ".gpg"]
            # item -1 is going to be the most recent since files are named <name>-<device>-<date><time>.tar

            if not (archives_in_dir or encryptions_in_dir):
                print('Archiving and encrypting data...'),
                archive = self.create_hp_archive()
                print('done.')
            else:
                reuse_archive = tkMessageBox.askyesno("Archive Found", "A preexisting archive has been found.  Would"
                                                                       " you like to reuse it?\n\nWARNING: If you reuse"
                                                                       " the archive, none of the changes made since "
                                                                       "the archive was made will be uploaded.",
                                                      parent=self)
                if reuse_archive:
                    if encryptions_in_dir and archives_in_dir:
                        if tkMessageBox.askyesno("Use Encrypted Archive", "An encrypted archive has been found.  Would "
                                                                          "you like to use that to skip the encryption "
                                                                          "process? (Select no to re-encrypt archive)",
                                                 parent=self):
                            archive = os.path.join(self.dir, encryptions_in_dir[-1])
                        else:
                            for e in encryptions_in_dir:
                                os.remove(os.path.join(self.dir, e))
                            print("Encrypting data..."),
                            archive = self.encrypt(os.path.join(self.dir, archives_in_dir[-1]))
                            print("done.")
                    elif encryptions_in_dir:
                        archive = os.path.join(self.dir, encryptions_in_dir[-1])
                    else:  # only archive exists
                        print("Encrypting data..."),
                        archive = self.encrypt(os.path.join(self.dir, archives_in_dir[-1]))
                        print("done.")

                else:
                    print('Archiving and encrypting data...'),
                    archive = self.create_hp_archive()
                    print('done.')

            print('Uploading...')
            try:
                from maskgen.external.exporter import S3ExportTool
                endpoint = self.settings.get_key('s3-endpoint', '')
                profile = self.settings.get_key('s3-profile', 'default')
                region = self.settings.get_key('s3-region', 'us-east-1')
                S3ExportTool().export(archive, BUCKET, DIR, None, profile=profile, endpoint=endpoint, region=region)
            except Exception as e:
                tkMessageBox.showerror(title='Error', message='Could not complete upload.\n\n\n' + str(e), parent=self)
                print e
                return

            try:
                os.remove(archive)
            except Exception as e:
                tkMessageBox.showerror(title='Error', message='Could not remove file.\n\n\n' + str(e), parent=self)

            #self.verify_upload(all_files, os.path.join(BUCKET, DIR))
            if tkMessageBox.askyesno(title='Complete', message='Successfully uploaded HP data to S3://' + val + '. Would you like to notify via Trello?', parent=self):
                comment = self.check_trello_login()
                err = self.notify_trello('s3://' + os.path.join(BUCKET, DIR, os.path.basename(archive)), archive, comment)
                if err:
                    tkMessageBox.showerror(title='Error', message='Failed to notify Trello (' + str(err) + ')', parent=self)
                else:
                    tkMessageBox.showinfo(title='Status', message='Complete!', parent=self)

        else:
            tkMessageBox.showinfo(title='Information', message='Upload canceled.', parent=self)

    def check_trello_login(self):
        """
        Prompt for Trello comment, while also checking that trello credential exists
        :return: string, comment to be posted to trello with upload information
        """
        if self.settings.get_key('trello') == '':
            token = self.get_trello_token()
            if token == '':
                return None
            self.settings.save('trello', token)
        comment = tkSimpleDialog.askstring(title='Trello Notification', prompt='(Optional) Enter any trello comments for this upload.', parent=self)
        return comment

    def is_hp_archive(self, archive):
        from tarfile import TarFile, ReadError
        test_file = TarFile(os.path.join(self.dir, archive))
        # the only directory we can guarantee is parent/csv
        try:
            # path must use '/' separator, os.path.join doesn't work
            test_file.getmember(os.path.basename(self.dir) + "/csv")
            test_file.close()
            return True
        except KeyError:
            # Didn't exist
            test_file.close()
            return False
        except ReadError:
            print("WARNING: {0} could not be read, and therefore can not be reused for uploading.".format(archive))
            return False


    def notify_trello(self, filestr, archive, comment):
        """
        Handles trello card posting notifier
        :param filestr: string, S3 path, used for description only
        :param archive: string, archive filepath
        :param comment: string, user comment
        :return: status code if error occurs, else None
        """

        if self.settings.get_key('trello') is None:
            token = self.get_trello_token()
            self.settings.save('trello', token)
        else:
            token = self.settings.get_key('trello')

        # list ID for "New Devices" list
        list_id = data_files._TRELLO['hp_list']

        # post the new card
        new = os.path.splitext(os.path.splitext(os.path.basename(archive))[0])[0]  # one split for tar, one for gpg
        stats = filestr + '\n' + self.collect_stats() + '\n' + 'User comment: ' + comment
        stats = stats
        resp = requests.post("https://trello.com/1/cards", params=dict(key=self.trello_key, token=token),
                             data=dict(name=new, idList=list_id, desc=stats))

        # attach the file, if the card was successfully posted
        if resp.status_code == requests.codes.ok:
            me = requests.get("https://trello.com/1/members/me", params=dict(key=self.trello_key, token=token))
            member_id = json.loads(me.content)['id']
            new_card_id = json.loads(resp.content)['id']
            resp2 = requests.post("https://trello.com/1/cards/%s/idMembers" % (new_card_id),
                                  params=dict(key=self.trello_key, token=token),
                                  data=dict(value=member_id))
            return None
        else:
            return resp.status_code

    def get_trello_token(self):
        # open prompt for Trello token
        t = TrelloSignInPrompt(self)
        return t.token.get()

    def collect_stats(self):
        """
        Count images/video/audio files in upload
        :return: string, count of each file category in CSV
        """
        images = 0
        videos = 0
        audio = 0
        for data in self.pt.model.df['Type']:
            if data == 'video':
                videos+=1
            elif data == 'audio':
                audio+=1
            else:
                images+=1

        return 'Image Files: ' + str(images) + '\nVideo Files: ' + str(videos) + '\nAudio Files: ' + str(audio)

    def create_hp_archive(self):
        """
        Archive output folder into a .tar file.
        :return: string, archive filename formatted as "USR-LocalID-YYmmddHHMMSS.tar"
        """

        ignore_dirs = ["temp"]
        val = self.pt.model.df['HP-DeviceLocalID'][0] if type(self.pt.model.df['HP-DeviceLocalID'][0]) is str else ''
        dt = datetime.datetime.now().strftime('%Y%m%d%H%M%S')[2:]
        fd, tname = tempfile.mkstemp(suffix='.tar')
        archive = tarfile.open(tname, "w", errorlevel=2)
        for d in os.listdir(self.dir):
            fp = os.path.join(self.dir, d)
            if os.path.isdir(fp) and d not in ignore_dirs:
                archive.add(fp, arcname=os.path.join(os.path.split(self.dir)[1], d))
        archive.close()
        os.close(fd)
        final_name = os.path.join(self.dir, '-'.join((self.settings.get_key('username'), val, dt)) + '.tar')
        tar_path = os.path.join(self.dir, final_name)
        shutil.move(tname, tar_path)
        gpg = self.encrypt(tar_path)
        return gpg

    def encrypt(self, tar_path):
        import subprocess

        recipient = self.settings.get_key("archive_recipient") if self.settings.get_key("archive_recipient") else None
        if recipient:
            subprocess.Popen(['gpg', '--recipient', recipient, '--trust-model', 'always', '--encrypt', "--yes",
                              tar_path]).communicate()
            final_name = tar_path + ".gpg"
            return final_name

        tkMessageBox.showerror("No Recipient", "The HP Tool cannot upload archives unless they are encrypted to a "
                                               "recipient.  Enter your recipient in the settings menu.")
        return None

    def validate(self):
        """
        Run validation routines, and re-color code cells after check is complete
        :return: None. Opens ErrorWindow if errors exist.
        """
        resolutions = []
        errors = []
        types = self.pt.model.df['Type']
        uniqueIDs = []
        self.processErrors = self.check_process_errors()

        w_col = self.pt.get_col_by_name("ImageWidth")
        h_col = self.pt.get_col_by_name("ImageHeight")
        ps_col = self.pt.get_col_by_name("HP-PrimarySecondary")

        files_in_dir = []
        files_in_csv = []

        for row in range(0, self.pt.rows):
            for col in range(0, self.pt.cols):
                currentColName = self.pt.model.df.columns[col]
                type = types[row]
                val = str(self.pt.model.getValueAt(row, col))
                if currentColName in self.booleanColNames:
                    if val.title() == 'True' or val.title() == 'False':
                        self.pt.model.setValueAt(val.title(), row, col)
                    elif type == 'image' and col in self.mandatoryImage:
                        errors.append('Invalid entry at column ' + currentColName + ', row ' + str(
                            row + 1) + '. Value must be True or False')
                    elif type == 'video' and col in self.mandatoryVideo:
                        errors.append('Invalid entry at column ' + currentColName + ', row ' + str(
                            row + 1) + '. Value must be True or False')
                    elif type == 'audio' and col in self.mandatoryAudio:
                        errors.append('Invalid entry at column ' + currentColName + ', row ' + str(
                            row + 1) + '. Value must be True or False')
                elif currentColName == "HP-PrimarySecondary" and val not in ['primary', 'secondary']:
                    errors.append('Invalid entry at column HP-PrimarySecondary, row {0}.  Value must be "primary" or'
                                  ' "secondary".'.format(row + 1))
            try:
                width = int(self.pt.model.getValueAt(row, w_col))
                height = int(self.pt.model.getValueAt(row, h_col))
            except ValueError:
                width = height = ""
            ps = self.pt.model.getValueAt(row, ps_col)
            res = (width, height)
            if (res, ps) not in resolutions and res[0] != "" and res[1] != "":
                resolutions.append((res, ps))

            errors.extend(self.parse_process_errors(row))
            errors.extend(self.check_model(row))
            errors.extend(self.check_kinematics(row))
            errors.extend(self.check_localID(row))
            errors.extend(self.check_collections(row))
            if self.pt.model.df['HP-DeviceLocalID'][row] not in uniqueIDs:
                uniqueIDs.append(self.pt.model.df['HP-DeviceLocalID'][row])
            name = self.pt.model.df['ImageFilename'][row] if self.pt.model.df["Type"][row] != "model" else \
                os.path.normpath(os.path.join(self.dir, "model", self.pt.model.df['ImageFilename'][row].split(".")[0]))
            files_in_csv.append(name)

        local_id = self.pt.model.getValueAt(0, 9)
        tkerrs = [[], []]
        if self.device_type == "CellPhone":
            browser_res_list = ValidResolutions(self, self.settings.get_key("apiurl"),
                                                self.settings.get_key("apitoken"),
                                                local_id=local_id).get_resolutions()

            for r in resolutions:
                opp = "secondary" if r[1] == 'primary' else 'primary'
                if r[1] != "":
                    if r[0] not in browser_res_list[r[1]]:
                        tkerrs[0].append("{0}x{1} - {2}.".format(r[0][0], r[0][1], r[1]))
                    if r[0] in browser_res_list[opp] and not r[0] in browser_res_list[r[1]]:
                        tkerrs[1].append("{0}x{1} - Tagged:{2} Found:{3}".format(r[0][0], r[0][1], r[1], opp))
                else:
                    tkMessageBox.showerror("Error", "The HP-PrimarySecondary field MUST be filled in prior to uploading.")
                    return None, True

        if tkerrs[0] or tkerrs[1]:
            tkMessageBox.showwarning("New Resolutions", "\nThe following resolutions do not exist under the camera "
                                     "indicated\n" * (len(tkerrs[0]) > 0) + "\n".join(tkerrs[0]) + "\nThe following "
                                     "resolutions were found online tagged as the opposite.\n" *(len(tkerrs[1]) > 0) +
                                     "\n".join(tkerrs[1]) + "\n\nPlease check your HP-PrimarySecondary selections.")

        for coord in self.highlighted_cells:
            val = str(self.pt.model.getValueAt(coord[0], coord[1]))
            if val == '':
                currentColName = list(self.pt.model.df.columns.values)[coord[1]]
                err = 'Invalid entry at column ' + currentColName + ', row ' + str(
                            coord[0] + 1) + '. This cell is mandatory.'
                if err not in errors:
                    errors.append(err)

        for root, dirs, files in os.walk(self.dir):
            for f in files:
                if os.path.splitext(f)[1] not in ['.csv', '.tar']:
                    if any(x in os.path.normpath(root).split("\\") for x in ['image', 'video', 'audio']):
                        files_in_dir.append(f)
                    elif 'model' in os.path.normpath(root).split('\\'):
                            files_in_dir.append(os.path.normpath(root))
                    else:
                        continue

        dif_list = [x for x in files_in_dir if (x not in files_in_csv and "_" not in x and os.path.splitext(x)[1]
                                                not in ["tar", "gpg"])]

        if dif_list:
            ans = tkMessageBox.askyesno("Missing Data", "There have been files found in the output directory that are"
                                                        " not in the csv.  Would you like to delete them?")
            if ans:
                for root, dirs, files in os.walk(self.dir):
                    for f in files:
                        if f in dif_list:
                            os.remove(os.path.join(root, f))
                    if os.path.normpath(root) in dif_list:
                        shutil.rmtree(root, ignore_errors=True)
            else:
                dif_errs = []
                for dif in dif_list:
                    dif_errs.append("Addition file ({0}) found in directory, and not in CSV.".format(dif))
                errors.extend(dif_errs)

        if len(uniqueIDs) > 1:
            errors.append('Multiple cameras identified. Each processed dataset should contain data from only one camera.')

        cancelPressed = None
        if errors:
            d = ErrorWindow(self, errors)
            cancelPressed = d.cancelPressed
        else:
            d = tkMessageBox.showinfo(title='Information', message='No validation errors found!', parent=self)

        self.color_code_cells()

        return errors, cancelPressed

    def parse_process_errors(self, row):
        """
        Parse dictionary-formatted process errors into workable list for ErrorWindow
        :param row: int, current row in spreadsheet
        :return: list of process errors
        """
        errors = []
        invalid_errors = []
        imageName = self.pt.model.df['OriginalImageName'][row]
        localID = self.pt.model.df['HP-DeviceLocalID'][row]
        if hasattr(self, 'processErrors') and imageName in self.processErrors:
            for err in self.processErrors[imageName]:
                errors.append(err[1])
        return errors

    def check_process_errors(self):
        """
        Check sheet for process errors. These are exif mismatches, where a file's exif data does not match the record
        for that device ID. These fields will be highlighted red once color-coded.
        :return: dictionary containing an entry for each row, with what columns to highlight, and an error messages.
        """
        errors = {}
        for row in range(0, self.pt.rows):
            db_configs = []
            image = self.pt.model.df['OriginalImageName'][row]
            errors[image] = []
            try:
                dbData = self.master.cameras[self.pt.model.df['HP-DeviceLocalID'][row]]
            except KeyError:
                try:
                    errors[image].append(('HP-DeviceLocalID', 'Invalid Device Local ID ' + self.pt.model.df['HP-DeviceLocalID'][row]))
                except TypeError:
                    pass
                continue
            for item in dbData:
                if dbData[item] is None or dbData[item] == 'nan':
                    dbData[item] = ''
            for configuration in range(len(dbData['exif'])):
                for field, val in dbData['exif'][configuration].iteritems():
                    if val is None or val == 'nan':
                        dbData['exif'][configuration][field] = ''
                dbData['exif'][configuration].pop('hp_app', 0)
                dbData['exif'][configuration].pop('created', 0)
                dbData['exif'][configuration].pop('username', 0)
                db_configs.append(dbData['exif'][configuration])

            data_config = {'exif_camera_make': self.get_val(self.pt.model.df['CameraMake'][row]),
                           'exif_camera_model': self.get_val(self.pt.model.df['CameraModel'][row]),
                           'exif_device_serial_number': self.get_val(self.pt.model.df['DeviceSN'][row]),
                           'media_type': self.get_val(self.pt.model.df['Type'][row])}

            if data_config not in db_configs:
                errors[image].append((['CameraMake', 'CameraModel', 'DeviceSN', 'Type'],
                                      'Invalid exif metadata configuration (row ' + str(row+1) +
                                      '). Add a new configuration for this device via \"File->Update a Device\" on the main UI\'s menu.'))

        return errors

    def get_val(self, item):
        """
        Handles NaN results from pandas df indexing.
        :param item: pandas df index result
        :return: string representation of item - empty string if NaN
        """
        if pd.isnull(item):
            return ''
        else:
            return item

    def check_save(self):
        """
        Prompts user to save sheet if edits have been made
        :return: None. Closes spreadsheet.
        """
        if self.saveState == False:
            message = 'Would you like to save before closing this sheet?'
            confirm = tkMessageBox.askyesnocancel(title='Save On Close', message=message, default=tkMessageBox.YES, parent=self)
            if confirm:
                errs = self.exportCSV(showErrors=False)
                if not errs:
                    self.destroy()
            elif confirm is None:
                pass
            else:
                self.destroy()
        else:
            self.destroy()

    def load_kinematics(self):
        """
        Load kinematics from file
        :return: list of kinematics
        """
        try:
            df = pd.read_csv(data_files._KINEMATICS)
        except IOError:
            tkMessageBox.showwarning('Warning', 'Camera kinematics reference not found!', parent=self)
            return []
        return [x.strip() for x in df['Camera Kinematics']]

    def check_collections(self, row):
        """
        Checks for valid Collection column entry
        :param row: row to check
        :return: list containing error message, if available
        """
        errors = []
        collection = self.pt.model.df['HP-Collection'][row]
        if collection not in self.collections and pd.notnull(collection):
            errors.append('Invalid Collection name: ' + collection + ' (row ' + str(row + 1) + ')')
        return errors

    def check_kinematics(self, row):
        """
        Checks for valid Kinematics column entry
        :param row: row to check
        :return: list containing error message, if available
        """
        errors = []
        kinematic = self.pt.model.df['HP-CameraKinematics'][row]
        type = self.pt.model.df['Type'][row]
        if type.lower() == 'video':
            if str(kinematic).lower() == 'nan' or str(kinematic) == '':
                imageName = self.pt.model.df['ImageFilename'][row]
                errors.append('No camera kinematic entered for ' + imageName + ' (row ' + str(row + 1) + ')')
            elif kinematic.lower() not in [x.lower() for x in self.kinematics]:
                errors.append('Invalid camera kinematic ' + kinematic + ' (row ' + str(row + 1) + ')')
        return errors

    def load_apps(self):
        """
        Load camera apps from file
        :return: alphabetically sorted list of apps
        """
        try:
            df = pd.read_csv(data_files._APPS)
        except IOError:
            tkMessageBox.showwarning('Warning', 'HP-App reference not found!', parent=self)
            return
        apps = [w.strip() for w in df['AppName']]
        return sorted(list(set(apps)))

    def load_lens_filters(self):
        """
        Load lens filter list from file
        :return: alphabetically sorted list of lens filters
        """
        try:
            df = pd.read_csv(data_files._LENSFILTERS)
        except IOError:
            tkMessageBox.showwarning('Warning', 'LensFilter reference not found!', parent=self)
            return
        filters = [w.lower().strip() for w in df['LensFilter']]
        return sorted(list(set(filters)))

    def check_model(self, row):
        """
        Checks for valid HP camera model column entry
        :param row: row to check
        :return: list containing error message, if available
        """
        errors = []
        model = self.pt.model.df['HP-CameraModel'][row]
        if pd.isnull(model) or model.lower() == 'nan' or model == '':
            if self.pt.model.df['Type'][row] != "model":
                imageName = self.pt.model.getValueAt(row, 0)
                errors.append('No camera model entered for ' + imageName + ' (row ' + str(row + 1) + ')')
            else:
                pass
        elif model not in [self.devices[data]['hp_camera_model'] for data in self.devices if
                         self.devices[data]['hp_camera_model'] is not None]:
            errors.append('Invalid camera model ' + model + ' (row ' + str(row + 1) + ')')
        return errors

    def check_localID(self, row):
        """
        Checks for valid Local ID column entry
        :param row: row to check
        :return: list containing error message, if available
        """
        errors = []
        localID = self.pt.model.df['HP-DeviceLocalID'][row]
        try:
            if localID.lower() == 'nan' or localID == '':
                imageName = self.pt.model.getValueAt(row, 0)
                errors.append('No Device Local ID entered for ' + imageName + ' (row' + str(row + 1) + ')')
            elif localID not in [self.devices[data]['hp_device_local_id'] for data in self.devices if
                             self.devices[data]['hp_device_local_id'] is not None]:
                errors.append('Invalid localID ' + localID + ' (row ' + str(row + 1) + ')')
        except AttributeError:
            pass
        return errors


class TrelloSignInPrompt(tkSimpleDialog.Dialog):
    """
    Prompt user for their trello credentials, showing button to get trello token.
    """
    def __init__(self, master):
        self.master=master
        self.token = StringVar()
        self.trello_key = data_files._TRELLO['app_key']
        tkSimpleDialog.Dialog.__init__(self, master)

    def body(self, master):
        Label(self, text='Please enter your Trello API token. If you do not know it, access it here: ').pack()
        b = Button(self, text='Get Token', command=self.open_trello_token)
        b.pack()
        e = Entry(self, textvar=self.token)
        e.pack()

    def open_trello_token(self):
        webbrowser.open('https://trello.com/1/authorize?key=' + self.trello_key + '&scope=read%2Cwrite&name=HP_GUI&expiration=never&response_type=token')


class ProgressPercentage(object):
    """
    http://boto3.readthedocs.io/en/latest/_modules/boto3/s3/transfer.html
    """
    def __init__(self, filename, total_files=None, count=None, *args, **kwargs):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()
        if total_files and count:
            self.percent_of_total = (count / total_files) * 100

    def __call__(self, bytes_amount):
        # To simplify we'll assume this is hooked up
        # to a single filename.
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            p = '[%.2f%% of total files uploaded.]' % self.percent_of_total if hasattr(self, 'percent_of_total') else ''
            sys.stdout.write(
                "\r%s  %s / %s  (%.2f%%) " % (
                    self._filename, self._seen_so_far, self._size,
                    percentage) + p)
            sys.stdout.flush()


class CustomTable(pandastable.Table):
    """
    Backend for pandastable. Modify this to change shortcuts, right-click menus, cell movement, etc.
    """
    def __init__(self, master, color_cb=None, **kwargs):
        pandastable.Table.__init__(self, parent=master, **kwargs)
        self.color_cb = color_cb
        self.copied_val = None, None

    def doBindings(self):
        """Bind keys and mouse clicks, this can be overriden"""

        self.bind("<Button-1>", self.handle_left_click)
        self.bind("<Double-Button-1>", self.handle_double_click)
        self.bind("<Control-Button-1>", self.handle_left_ctrl_click)
        self.bind("<Shift-Button-1>", self.handle_left_shift_click)

        self.bind("<ButtonRelease-1>", self.handle_left_release)
        if self.ostyp == 'mac':
            # For mac we bind Shift, left-click to right click
            self.bind("<Button-2>", self.handle_right_click)
            self.bind('<Shift-Button-1>', self.handle_right_click)
        else:
            self.bind("<Button-3>", self.handle_right_click)

        self.bind('<B1-Motion>', self.handle_mouse_drag)
        # self.bind('<Motion>', self.handle_motion)

        self.bind("<Control-c>", self.copy)
        # self.bind("<Control-x>", self.deleteRow)
        # self.bind_all("<Control-n>", self.addRow)
        self.bind("<Delete>", self.clearData)
        self.bind("<Control-v>", self.paste)
        self.bind("<Control-a>", self.selectAll)

        self.bind("<Right>", self.handle_arrow_keys)
        self.bind("<Left>", self.handle_arrow_keys)
        self.bind("<Up>", self.handle_arrow_keys)
        self.bind("<Down>", self.handle_arrow_keys)
        self.bind("<Tab>", self.handle_tab)
        self.parentframe.master.bind_all("<Return>", self.handle_arrow_keys)
        self.parentframe.master.bind_all("<KP_8>", self.handle_arrow_keys)
        # if 'windows' in self.platform:
        self.bind("<MouseWheel>", self.mouse_wheel)
        self.bind('<Button-4>', self.mouse_wheel)
        self.bind('<Button-5>', self.mouse_wheel)

        #######################################
        self.bind('<Control-Key-t>', self.enter_true)
        self.bind('<Control-Key-f>', self.enter_false)
        self.bind('<Control-Key-d>', self.fill_selection)
        self.bind('<Control-Key-g>', self.fill_column)
        self.bind('<Control-Key-c>', self.copy_value)
        self.bind('<Control-Key-v>', self.paste_value)
        #self.bind('<Return>', self.handle_double_click)
        ########################################

        self.focus_set()
        return

    def get_col_by_name(self, name):
        for i in range(0, self.cols):
            if self.model.getColumnName(i).lower() == name.lower():
                return i
        return None

    def get_row_by_image_name(self, name):
        col_num = self.get_col_by_name("ImageFilename")
        for row in range(0, self.rows):
            if self.model.getValueAt(row, col_num) == name:
                return row
        return None

    def enter_true(self, event=None):
        current = self.getSelectedColumn()
        ps_col = self.get_col_by_name("HP-PrimarySecondary")
        if current == ps_col:
            self.fill_selection(val='primary')
        else:
            self.fill_selection(val='True')

    def enter_false(self, event=None):
        current = self.getSelectedColumn()
        ps_col = self.get_col_by_name("HP-PrimarySecondary")
        if current == ps_col:
            self.fill_selection(val='secondary')
        else:
            self.fill_selection(val='False')

    def fill_selection(self, event=None, val=None):
        if hasattr(self, 'disabled_cells'):
            if not self.check_disabled_cells(range(self.startrow,self.endrow+1),
                                             range(self.startcol, self.endcol+1)):
                return
        self.undo = []
        self.focus_set()
        col = self.getSelectedColumn()
        row = self.getSelectedRow()
        val = val if val is not None else self.model.getValueAt(row, col)
        max_row = max(self.startrow, self.endrow)
        min_row = min(self.startrow, self.endrow)
        max_col = max(self.startcol, self.endcol)
        min_col = min(self.startcol, self.endcol)
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                if hasattr(self, 'disabled_cells') and (row, col) in self.disabled_cells:
                    continue
                self.undo.append((self.model.getValueAt(row, col), row, col))
                self.model.setValueAt(val, row, col)
        self.redraw()
        if hasattr(self, 'cellentry'):
            self.cellentry.destroy()

    def fill_column(self, event=None):
        col = self.getSelectedColumn()
        col_name = self.model.getColumnName(col)
        rowList = range(0, self.rows)
        if hasattr(self, 'disabled_cells') and not col_name == "HP-ReleaseForms":
            if not self.check_disabled_cells(rowList, [col]):
                return
        self.focus_set()
        self.undo = []
        row = self.getSelectedRow()
        val = self.model.getValueAt(row, col)
        for row in rowList:
            if hasattr(self, 'disabled_cells') and (row, col) in self.disabled_cells and not \
                    col_name == "HP-ReleaseForms":
                continue
            self.undo.append((self.model.getValueAt(row, col), row, col))
            self.model.setValueAt(val, row, col)
        self.redraw()
        if hasattr(self, 'cellentry'):
            self.cellentry.destroy()

    def check_disabled_cells(self, rows, columns):
        for row in rows:
            for col in columns:
                if (row, col) in self.disabled_cells:
                    return tkMessageBox.askyesno(title='Error',
                                          message='Some cells in column are disabled. Would you like to fill the valid ones?', parent=self)
        return True

    def copy_value(self, event=None):
        self.focus_set()
        col = self.getSelectedColumn()
        row = self.getSelectedRow()
        self.copied_val = (self.model.getValueAt(row, col), self.model.getColumnName(col))
        self.redraw()

    def paste_value(self, event=None):
        self.focus_set()
        col = self.getSelectedColumn()
        col_name = self.model.getColumnName(col)
        row = self.getSelectedRow()
        if hasattr(self, 'disabled_cells') and (row, col) in self.disabled_cells and col_name != "HP-ReleaseForms":
            return
        # xnor between copied value and current column being HP-ReleaseForms
        if (self.copied_val[1] == "HP-ReleaseForms") != (col_name == "HP-ReleaseForms"):
            tkMessageBox.showerror("Paste Error", "HP-ReleaseForms cell values cannot be mixed with other columns.",
                                   master=self.master)
            return
        if self.copied_val[0] is not None:
            self.undo = [(self.model.getValueAt(row, col), row, col)]
            self.model.setValueAt(self.copied_val[0], row, col)
        self.redraw()

    def deleteCells(self, rows, cols, answer=None):
        from itertools import product
        from numpy import nan
        # Remove possibility of deleting disabled data (You can select negative index values by dragging too high up)
        rows = [r for r in rows if r >= 0]
        cols = [c for c in cols if c >= 0]

        disabled = [(row, col) for (row, col) in product(rows, cols) if (row, col) in self.disabled_cells and
                    self.model.getColumnName(col) != "HP-ReleaseForms"] if hasattr(self, "disabled_cells") else []
        self.storeCurrent()
        if disabled:
            self.undo = []
            for row, col in product(rows, cols):
                if (row, col) in disabled:
                    continue
                else:
                    self.undo.append([self.model.getValueAt(row, col), row, col])
                    self.model.setValueAt(nan, row, col)
        else:
            self.undo = [[self.model.getValueAt(row, col), row, col] for (row, col) in product(rows, cols)]
            self.model.deleteCells(rows, cols)
        self.redraw()

    def move_selection(self, event, direction='down', entry=False):
        row = self.getSelectedRow()
        col = self.getSelectedColumn()
        if direction == 'down':
            self.currentrow += 1
        elif direction == 'up':
            self.currentrow -= 1
        elif direction == 'left':
            self.currentcol -= 1
        else:
            self.currentcol += 1

        if entry:
            self.drawCellEntry(self.currentrow, self.currentcol)

    def handle_tab(self, event=None):
        self.handle_arrow_keys(direction='Right')

    def handle_arrow_keys(self, event=None, direction=None):
        """Handle arrow keys press"""
        # print event.keysym

        # row = self.get_row_clicked(event)
        # col = self.get_col_clicked(event)
        x, y = self.getCanvasPos(self.currentrow, 0)
        if x == None:
            return
        if event is not None:
            direction = event.keysym

        if direction == 'Up':
            if self.currentrow == 0:
                return
            else:
                # self.yview('moveto', y)
                # self.rowheader.yview('moveto', y)
                self.currentrow = self.currentrow - 1
        elif direction == 'Down':
            if self.currentrow >= self.rows - 1:
                return
            else:
                # self.yview('moveto', y)
                # self.rowheader.yview('moveto', y)
                self.currentrow = self.currentrow + 1
        elif direction == 'Right' or direction == 'Tab':
            if self.currentcol >= self.cols - 1:
                if self.currentrow < self.rows - 1:
                    self.currentcol = 0
                    self.currentrow = self.currentrow + 1
                else:
                    return
            else:
                self.currentcol = self.currentcol + 1
        elif direction == 'Left':
            if self.currentcol == 0:
                if self.currentrow > 0:
                    self.currentcol = self.cols - 1
                    self.currentrow = self.currentrow - 1
                else:
                    return
            else:
                self.currentcol = self.currentcol - 1
        self.drawSelectedRect(self.currentrow, self.currentcol)
        self.startrow = self.currentrow
        self.endrow = self.currentrow
        self.startcol = self.currentcol
        self.endcol = self.currentcol
        self.handle_left_click()
        self.handle_double_click()
        return

    def drawCellEntry(self, row, col, text=None):
        """When the user single/double clicks on a text/number cell,
          bring up entry window and allow edits."""

        if self.editable == False:
            return
        if hasattr(self, 'disabled_cells') and (row, col) in self.disabled_cells:
            return

        h = self.rowheight
        model = self.model
        text = self.model.getValueAt(row, col)
        x1,y1,x2,y2 = self.getCellCoords(row,col)
        w=x2-x1
        self.cellentryvar = txtvar = StringVar()
        txtvar.set(text)

        self.cellentry = Entry(self.parentframe,width=20,
                        textvariable=txtvar,
                        takefocus=1,
                        font=self.thefont)
        self.cellentry.icursor(END)
        self.cellentry.bind('<Return>', lambda x: self.cellentryCallback(row,col, direction='Down'))
        self.cellentry.bind("<Right>", lambda x: self.cellentryCallback(row,col, direction='Right'))
        self.cellentry.bind("<Left>", lambda x: self.cellentryCallback(row,col, direction='Left'))
        self.cellentry.bind("<Up>", lambda x: self.cellentryCallback(row,col, direction='Up'))
        self.cellentry.bind("<Down>", lambda x: self.cellentryCallback(row,col, direction='Down'))
        self.cellentry.bind("<Tab>", lambda x: self.cellentryCallback(row,col, direction='Right'))

        self.cellentry.bind('<Control-Key-t>', self.enter_true)
        self.cellentry.bind('<Control-Key-f>', self.enter_false)
        self.cellentry.bind('<Control-Key-d>', self.fill_selection)
        self.cellentry.bind('<Control-Key-g>', self.fill_column)
        self.cellentry.bind('<Control-Key-c>', self.copy_value)
        self.cellentry.bind('<Control-Key-v>', self.paste_value)
        self.cellentry.focus_set()
        self.entrywin = self.create_window(x1,y1,
                                width=w,height=h,
                                window=self.cellentry,anchor='nw',
                                tag='entry')
        return

    def cellentryCallback(self, row, col, direction=None):
        """Callback for cell entry"""

        value = self.cellentryvar.get()
        self.model.setValueAt(value,row,col)
        self.redraw()
        #self.drawText(row, col, value, align=self.align)
        #self.delete('entry')
        self.gotonextCell(direction)
        return

    def handle_left_click(self, event=None):
        """Respond to a single press"""

        self.clearSelected()
        self.allrows = False
        #which row and column is the click inside?
        if event is not None:
            rowclicked = self.get_row_clicked(event)
            colclicked = self.get_col_clicked(event)
        else:
            rowclicked = self.startrow
            colclicked = self.startcol
        if colclicked == None:
            return
        try:
            self.focus_set()
        except:
            pass

        if hasattr(self, 'cellentry'):
            #self.cellentryCallback()
            self.cellentry.destroy()
        #ensure popup menus are removed if present
        if hasattr(self, 'rightmenu'):
            self.rightmenu.destroy()
        if hasattr(self.tablecolheader, 'rightmenu'):
            self.tablecolheader.rightmenu.destroy()

        self.startrow = rowclicked
        self.endrow = rowclicked
        self.startcol = colclicked
        self.endcol = colclicked
        #reset multiple selection list
        self.multiplerowlist=[]
        self.multiplerowlist.append(rowclicked)
        if 0 <= rowclicked < self.rows and 0 <= colclicked < self.cols:
            self.setSelectedRow(rowclicked)
            self.setSelectedCol(colclicked)
            self.drawSelectedRect(self.currentrow, self.currentcol)
            self.drawSelectedRow()
            self.rowheader.drawSelectedRows(rowclicked)
            self.tablecolheader.delete('rect')
        if hasattr(self, 'cellentry'):
            self.cellentry.destroy()
        return

    def handle_double_click(self, event=None):
        """Do double click stuff. Selected row/cols will already have
           been set with single click binding"""

        if event is not None:
            rowclicked = self.get_row_clicked(event)
            colclicked = self.get_col_clicked(event)
        else:
            rowclicked = self.startrow
            colclicked = self.startcol
        self.drawCellEntry(self.currentrow, self.currentcol)
        return

    def gotonextCell(self, direction=None):
        """Move highlighted cell to next cell in row or a new col"""
        if direction is None:
            direction = 'right'
        if hasattr(self, 'cellentry'):
            self.cellentry.destroy()

        self.handle_arrow_keys(direction=direction)
        # self.currentrow = self.currentrow+1
        # if self.currentcol >= self.cols-1:
        #     self.currentcol = self.currentcol+1
        #self.drawSelectedRect(self.currentrow, self.currentcol)
        # self.handle_left_click()
        # self.handle_double_click()
        return

    def clearSelected(self):
        """Clear selections"""
        try:
            self.delete('rect')
            self.delete('entry')
            self.delete('tooltip')
            self.delete('searchrect')
            self.delete('colrect')
            self.delete('multicellrect')
        except TclError:
            pass
        return

    def importCSV(self, filename=None, dialog=False):
        """Import from csv file"""

        if self.importpath == None:
            self.importpath = os.getcwd()
        if filename == None:
            filename = tkFileDialog.askopenfilename(parent=self.master,
                                                          defaultextension='.csv',
                                                          initialdir=self.importpath,
                                                          filetypes=[("csv","*.csv"),
                                                                     ("tsv","*.tsv"),
                                                                     ("txt","*.txt"),
                                                            ("All files","*.*")])
        if not filename:
            return
        if dialog == True:
            df = None
        else:
            df = pd.read_csv(filename, dtype=str, quoting=1)
        model = pandastable.TableModel(dataframe=df)
        self.updateModel(model)
        self.redraw()
        self.importpath = os.path.dirname(filename)
        return

    def bind_columns(self, tab=None):
        self.tab = tab
        self.tablecolheader.bind("<B1-Motion>", self.mouse_drag_with_color_cb)

    def mouse_drag_with_color_cb(self, event):
        self.tablecolheader.handle_mouse_drag(event)
        self.tablecolheader.bind("<ButtonRelease-1>", self.release)
        return

    def deleteRow(self):
        pandastable.Table.deleteRow(self)
        self.resetIndex()
        self.color_cb()

    def release(self, event):
        self.tablecolheader.handle_left_release(event)
        if self.color_cb:
            self.color_cb(tab=self.tab)
        self.tablecolheader.bind("<ButtonRelease-1>", self.handle_left_release)
        return

    # right click menu!
    def popupMenu(self, event, rows=None, cols=None, outside=None):
        """Add left and right click behaviour for canvas, should not have to override
            this function, it will take its values from defined dicts in constructor"""

        defaultactions = {
                        "Copy" : self.copy_value,
                        "Paste" : self.paste_value,
                        "Fill Selection" : self.fill_selection,
                        "Fill True" : self.enter_true,
                        "Fill False" : self.enter_false,
                        #"Fill Down" : lambda: self.fillDown(rows, cols),
                        #"Fill Right" : lambda: self.fillAcross(cols, rows),
                        #"Add Row(s)" : lambda: self.addRows(),
                        #"Delete Row(s)" : lambda: self.deleteRow(),
                        #"Add Column(s)" : lambda: self.addColumn(),
                        #"Delete Column(s)" : lambda: self.deleteColumn(),
                        "Clear Data" : lambda: self.deleteCells(rows, cols),
                        "Select All" : self.selectAll,
                        #"Auto Fit Columns" : self.autoResizeColumns,
                        #"Table Info" : self.showInfo,
                        #"Show as Text" : self.showasText,
                        #"Filter Rows" : self.queryBar,
                        #"New": self.new,
                        #"Load": self.load,
                        # "Save": self.save,
                        # "Save as": self.saveAs,
                        # "Import csv": lambda: self.importCSV(dialog=True),
                        # "Export": self.doExport,
                        # "Plot Selected" : self.plotSelected,
                        # "Hide plot" : self.hidePlot,
                        # "Show plot" : self.showPlot,
                        # "Preferences" : self.showPrefs
            }

        main = ["Copy", "Paste", "Fill Selection", "Fill True", "Fill False", "Clear Data", "Select All"]
        general = []

        filecommands = []
        plotcommands = []

        def createSubMenu(parent, label, commands):
            menu = Menu(parent, tearoff = 0)
            popupmenu.add_cascade(label=label,menu=menu)
            for action in commands:
                menu.add_command(label=action, command=defaultactions[action])
            return menu

        def add_commands(fieldtype):
            """Add commands to popup menu for column type and specific cell"""
            functions = self.columnactions[fieldtype]
            for f in list(functions.keys()):
                func = getattr(self, functions[f])
                popupmenu.add_command(label=f, command= lambda : func(row,col))
            return

        popupmenu = Menu(self, tearoff = 0)
        def popupFocusOut(event):
            popupmenu.unpost()

        if outside == None:
            #if outside table, just show general items
            row = self.get_row_clicked(event)
            col = self.get_col_clicked(event)
            coltype = self.model.getColumnType(col)
            def add_defaultcommands():
                """now add general actions for all cells"""
                for action in main:
                    if action == 'Fill Down' and (rows == None or len(rows) <= 1):
                        continue
                    if action == 'Fill Right' and (cols == None or len(cols) <= 1):
                        continue
                    else:
                        popupmenu.add_command(label=action, command=defaultactions[action])
                return

            if coltype in self.columnactions:
                add_commands(coltype)
            add_defaultcommands()

        for action in general:
            popupmenu.add_command(label=action, command=defaultactions[action])

        #popupmenu.add_separator()
        # createSubMenu(popupmenu, 'File', filecommands)
        # createSubMenu(popupmenu, 'Plot', plotcommands)
        popupmenu.bind("<FocusOut>", popupFocusOut)
        popupmenu.focus_set()
        popupmenu.post(event.x_root, event.y_root)
        return popupmenu
