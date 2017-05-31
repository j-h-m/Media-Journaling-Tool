import csv
import webbrowser
from Tkinter import *
import ttk
import pandas as pd
import os
import collections
import subprocess
import tkFileDialog, tkMessageBox
import json
import requests
from camera_handler import API_Camera_Handler
import data_files

class HP_Device_Form(Toplevel):
    def __init__(self, master, validIDs=None, pathvar=None, token=None, browser=None):
        Toplevel.__init__(self, master)
        self.geometry("%dx%d%+d%+d" % (600, 600, 250, 125))
        self.master = master
        self.pathvar = pathvar # use this to set a tk variable to the path of the output txt file
        self.validIDs = validIDs if validIDs is not None else []
        self.set_list_options()

        self.trello_token = StringVar()
        self.trello_token.set(token) if token is not None else ''
        self.browser_token = StringVar()
        self.browser_token.set(browser) if browser is not None else ''

        self.trello_key = 'dcb97514b94a98223e16af6e18f9f99e'
        self.create_widgets()

    def set_list_options(self):
        df = pd.read_csv(os.path.join(data_files._DB))
        self.manufacturers = [str(x).strip() for x in df['Manufacturer'] if str(x).strip() != 'nan']
        self.lens_mounts = [str(y).strip() for y in df['LensMount'] if str(y).strip() != 'nan']
        self.device_types = [str(z).strip() for z in df['DeviceType'] if str(z).strip() != 'nan']

    def create_widgets(self):
        self.f = VerticalScrolledFrame(self)
        self.f.pack(fill=BOTH, expand=TRUE)

        Label(self.f.interior, text='Add a new HP Device', font=('bold underline', 25)).pack()
        Label(self.f.interior, text='Once complete, the new camera will be added automatically, and a notification card will be posted to trello.', wraplength=400).pack()

        Label(self.f.interior, text='Sample File', font=('bold', 18)).pack()
        Label(self.f.interior, text='This is required. Select an image/video/audio file. Once metadata is loaded from it, you may continue to complete the form.'
                                    ' Some devices can have multiple make/model configurations for images vs. video, or for apps. In this instances, submit this '
                                    'form as normal, and then go to File->Update a Device on the main GUI.', wraplength=400).pack()
        self.imageButton = Button(self.f.interior, text='Select File', command=self.populate_from_image)
        self.imageButton.pack()

        head = [('Media Type*', {'description': 'Select the type of media contained in the sample file (Image, Video, Audio)',
                                 'type': 'readonlylist',
                                 'values': ['image', 'video', 'audio']}),
                ('App', {'description': 'If the sample image was taken with a certain app, specify it here. Otherwise, leave blank.',
                         'type': 'text',
                         'values': None}),
                ('Exif Camera Make',{'description': 'Device make, pulled from device Exif.',
                                     'type': 'list',
                                     'values': self.manufacturers}),
                ('Exif Camera Model',{'description': 'Device model, pulled from device Exif.',
                                      'type': 'text',
                                      'values': None}),
                ('Device Serial Number', {'description': 'Device serial number, pulled from device Exif. If not available, enter the SN marked on the device body.',
                                          'type': 'text',
                                          'values': None}),
                ('Local ID*', {'description': 'This can be a one of a few forms. The most preferable is the cage number. If it is a personal device, you can use INITIALS-MODEL, such as'
                                              ' ES-iPhone4. Please check that the local ID is not already in use.',
                               'type': 'text',
                               'values': None}),
                ('Device Affiliation*', {'description': 'If it is a personal device, please define the affiliation as Other, and write in your organization and your initials, e.g. RIT-TK',
                                         'type': 'radiobutton',
                                         'values': ['RIT', 'PAR', 'Other (please specify):']}),
                ('HP Model',{'description': 'Please write the make/model such as it would be easily identifiable, such as Samsung Galaxy S6.',
                             'type': 'text',
                             'values': None}),
                ('Edition',{'description': 'Specific edition of the device, if applicable and not already in the device\'s name.',
                            'type': 'text',
                            'values': None}),
                ('Device Type*',{'description': 'Select camera type. If none are applicable, select "other".',
                                 'type': 'readonlylist',
                                 'values':self.device_types}),
                ('Sensor Information',{'description': 'Sensor size/dimensions/other sensor info.',
                                       'type': 'text',
                                       'values': None}),
                ('Lens Mount*',{'description': 'Choose \"builtin\" if the device does not have interchangeable lenses.',
                                'type': 'list',
                                'values':self.lens_mounts}),
                ('Firmware/OS',{'description': 'Firmware/OS',
                                'type': 'text',
                                'values': None}),
                ('Firmware/OS Version',{'description': 'Firmware/OS Version',
                                        'type': 'text',
                                        'values': None}),
                ('General Description',{'description': 'Other specifications',
                                        'type': 'text',
                                        'values': None}),
        ]
        self.headers = collections.OrderedDict(head)

        self.questions = {}
        for h in self.headers:
            d = SectionFrame(self.f.interior, title=h, descr=self.headers[h]['description'], type=self.headers[h]['type'], items=self.headers[h]['values'], bd=5)
            d.pack(pady=4)
            self.questions[h] = d

        Label(self.f.interior, text='Trello Login Token*', font=(20)).pack()
        Label(self.f.interior, text='This is required to send a notification of the new device.').pack()
        trello_link = 'https://trello.com/1/authorize?key=' + self.trello_key + '&scope=read%2Cwrite&name=HP_GUI&expiration=never&response_type=token'
        trelloTokenButton = Button(self.f.interior, text='Get Trello Token', command=lambda: self.open_link(trello_link))
        trelloTokenButton.pack()
        tokenEntry = Entry(self.f.interior, textvar=self.trello_token)
        tokenEntry.pack()

        Label(self.f.interior, text='Browser Login Token*', font=(20)).pack()
        Label(self.f.interior, text='This allows for the creation of the new device.').pack()
        browser_link = 'https://medifor.rankone.io/api/login/'
        browserTokenButton = Button(self.f.interior, text='Get Browser Token', command=lambda: self.open_link(browser_link))
        browserTokenButton.pack()
        browserEntry = Entry(self.f.interior, textvar=self.browser_token)
        browserEntry.pack()

        buttonFrame = Frame(self)
        buttonFrame.pack()

        self.okbutton = Button(buttonFrame, text='Complete', command=self.export_results, state='disabled')
        self.okbutton.pack()
        self.cancelbutton = Button(buttonFrame, text='Cancel', command=self.destroy)
        self.cancelbutton.pack()

        for q, a in self.questions.iteritems():
            a.disable()

    def populate_from_image(self):
        self.imfile = tkFileDialog.askopenfilename(title='Select Image File', parent=self)
        if not self.imfile:
            return
        self.imageButton.config(text=os.path.basename(self.imfile))
        args = ['exiftool', '-f', '-j', '-Model', '-Make', '-SerialNumber', self.imfile]
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
            exifData = json.loads(p)[0]
        except:
            self.master.statusBox.println('An error ocurred attempting to pull exif data from image.')
            return

        for q, a in self.questions.iteritems():
            a.enable()
        if exifData['Make'] != '-':
            self.questions['Exif Camera Make'].set(exifData['Make'])
            self.questions['Exif Camera Make'].disable()
        if exifData['Model'] != '-':
            self.questions['Exif Camera Model'].set(exifData['Model'])
            self.questions['Exif Camera Model'].disable()
        if exifData['SerialNumber'] != '-':
            self.questions['Device Serial Number'].set(exifData['SerialNumber'])
        self.okbutton.config(state='normal')

    def export_results(self):
        msg = None
        for h in self.headers:
            if h.endswith('*') and self.questions[h].get() == '':
                msg = 'Field ' + h[:-1] + ' is a required field.'
                break
        if self.trello_token.get() == '':
            msg = 'Trello Token is a required field.'
        if self.browser_token.get() == '':
            msg = 'Browser Token is a required field.'
        check = self.local_id_used()
        msg = msg if check is None else check

        if msg:
            tkMessageBox.showerror(title='Error', message=msg)
            return

        browser_resp = self.post_to_browser()
        if browser_resp.status_code in (requests.codes.ok, requests.codes.created):
            tkMessageBox.showinfo(title='Complete', message='Successfully posted new camera information! Press Okay to continue. You will be prompted to save a file that will be posted to trello.')
        else:
            tkMessageBox.showerror(title='Error', message='An error ocurred posting the new camera information to the MediBrowser. (' + str(browser_resp.status_code)+ ')')
            return

        path = tkFileDialog.asksaveasfilename(initialfile=self.questions['Local ID*'].get()+'.csv')
        if self.pathvar:
            self.pathvar.set(path)
        with open(path, 'wb') as csvFile:
            wtr = csv.writer(csvFile)
            wtr.writerow(['Affiliation', 'HP-LocalDeviceID', 'DeviceSN', 'Manufacturer', 'CameraModel', 'HP-CameraModel', 'Edition',
                          'DeviceType', 'Sensor', 'Description', 'LensMount', 'Firmware', 'version', 'HasPRNUData'])
            wtr.writerow([self.questions['Device Affiliation*'].get(), self.questions['Local ID*'].get(), self.questions['Device Serial Number'].get(),
                          self.questions['Exif Camera Make'].get(), self.questions['Exif Camera Model'].get(),
                          self.questions['HP Model'].get(), self.questions['Edition'].get(), self.questions['Device Type*'].get(),
                          self.questions['Sensor Information'].get(), self.questions['General Description'].get(),
                          self.questions['Lens Mount*'].get(), self.questions['Firmware/OS'].get(), self.questions['Firmware/OS Version'].get(), '0'])

        code = self.post_to_trello(path)
        if code is not None:
            tkMessageBox.showerror('Trello Error', message='An error ocurred connecting to trello (' + str(code) + ').\nIf you\'re not sure what is causing this error, email medifor_manipulators@partech.com.')
        else:
            tkMessageBox.showinfo(title='Information', message='Complete!')

        self.destroy()

    def post_to_browser(self):
        url = 'https://medifor.rankone.io/api/cameras/'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Token ' + self.browser_token.get(),
        }
        data = { 'hp_device_local_id': self.questions['Local ID*'].get(),
                 'affiliation': self.questions['Device Affiliation*'].get(),
                 'hp_camera_model': self.questions['HP Model'].get(),
                 'exif':[{'exif_camera_make': self.questions['Exif Camera Make'].get(),
                          'exif_camera_model': self.questions['Exif Camera Model'].get(),
                          'exif_device_serial_number': self.questions['Device Serial Number'].get(),
                          'hp_app': self.questions['App'].get(),
                          'media_type': self.questions['Media Type*'].get()}],
                 'camera_edition': self.questions['Edition'].get(),
                 'camera_type': self.questions['Device Type*'].get(),
                 'camera_sensor': self.questions['Sensor Information'].get(),
                 'camera_description': self.questions['General Description'].get(),
                 'camera_lens_mount': self.questions['Lens Mount*'].get(),
                 'camera_firmware': self.questions['Firmware/OS'].get(),
                 'camera_version': self.questions['Firmware/OS Version'].get()
        }
        data = self.json_string(data)

        return requests.post(url, headers=headers, data=data)

    def json_string(self, data):
        for key, val in data.iteritems():
            if val == '':
                data[key] = None
        for configuration in data['exif']:
            for key, val in configuration.iteritems():
                if val == '':
                    configuration[key] = None
        return json.dumps(data)

    def local_id_used(self):
        print 'Verifying local ID is not already in use...'
        c = API_Camera_Handler(self, token=self.browser_token.get(), url='https://medifor.rankone.io')
        local_id_reference = c.get_local_ids()
        if not local_id_reference:
            return 'Could not successfully connect to Medifor browser. Please check credentials.'
        elif self.questions['Local ID*'].get().lower() in [i.lower() for i in local_id_reference]:
            return 'Local ID ' + self.questions['Local ID*'].get() + ' already in use.'

    def open_link(self, link):
        webbrowser.open(link)

    def post_to_trello(self, filepath):
        """create a new card in trello and attach a file to it"""

        token = self.trello_token.get()

        # list ID for "New Devices" list
        list_id = '58ecda84d8cfce408d93dd34'

        # post the new card
        new = self.questions['Local ID*'].get()
        resp = requests.post("https://trello.com/1/cards", params=dict(key=self.trello_key, token=token),
                             data=dict(name=new, idList=list_id))

        # attach the file and user, if the card was successfully posted
        if resp.status_code == requests.codes.ok:
            j = json.loads(resp.content)
            files = {'file': open(filepath, 'rb')}
            requests.post("https://trello.com/1/cards/%s/attachments" % (j['id']),
                          params=dict(key=self.trello_key, token=token), files=files)

            me = requests.get("https://trello.com/1/members/me", params=dict(key=self.trello_key, token=token))
            member_id = json.loads(me.content)['id']
            new_card_id = j['id']
            resp2 = requests.post("https://trello.com/1/cards/%s/idMembers" % (new_card_id),
                                  params=dict(key=self.trello_key, token=token),
                                  data=dict(value=member_id))
            return None
        else:
            return resp.status_code

class SectionFrame(Frame):
    def __init__(self, master, title, descr, type, items=None, **kwargs):
        Frame.__init__(self, master, **kwargs)
        self.title = title
        self.descr = descr
        self.type = type
        self.items = items # list items, if combobox type
        self.val = StringVar()
        self.row = 0
        self.create_form_item()

    def create_form_item(self):
        self._title = Label(self, text=self.title, font=(20)).grid(row=self.row)
        self.row+=1
        self._descr = Label(self, text=self.descr, wraplength=350).grid(row=self.row)
        self.row+=1
        if 'list' in self.type:
            self._form = ttk.Combobox(self, textvariable=self.val, values=self.items)
            self._form.bind('<MouseWheel>', self.remove_bind)
        elif 'radiobutton' in self.type:
            for item in self.items:
                if item.lower().startswith('other'):
                    Label(self, text='Other - Please specify: ').grid(row=self.row)
                    self._form = Entry(self, textvar=self.val)
                else:
                    Radiobutton(self, text=item, variable=self.val, value=item).grid(row=self.row)
                self.row+=1
        else:
            self._form = Entry(self, textvar=self.val)

        if 'readonly' in self.type and hasattr(self, '_form'):
            self._form.config(state='readonly')

        if hasattr(self, '_form'):
            self._form.grid(row=self.row)

    def remove_bind(self, event):
        return 'break'

    def get(self):
        return str(self.val.get())

    def set(self, val):
        self.val.set(str(val))

    def disable(self):
        if hasattr(self, '_form'):
            self._form.config(state='disabled')

    def enable(self):
        if hasattr(self, '_form'):
            self._form.config(state='normal')

class Update_Form(Toplevel):
    def __init__(self, master, device_data, trello=None, browser=None):
        Toplevel.__init__(self, master)
        """
        Need to call this class from GUI File Menu, first prompting for device local ID to update. The user must have valid browser creds in settings.
        While you're at it, make that happen for the normal camera form too.
        On start, only valid exif fields should be shown for that device.
        Should be able to add multiple configurations, similar structure to adding arguments in JT's plugin builder.
        """
        self.master = master
        self.device_data = device_data
        self.trello = trello
        self.browser = browser
        self.configurations = {'exif_device_serial_number':[],'exif_camera_make':[], 'exif_camera_model':[], 'hp_app':[], 'media_type':[]}
        self.row = 0
        self.config_count = 0
        self.create_widgets()

    def create_widgets(self):
        self.f = VerticalScrolledFrame(self)
        self.f.pack(fill=BOTH, expand=TRUE)
        self.buttonsFrame = Frame(self)
        self.buttonsFrame.pack(fill=BOTH, expand=True)
        Label(self.f.interior, text='Updating Device:\n' + self.device_data['hp_device_local_id'], font=('bold', 20)).grid(columnspan=6)
        self.row+=1
        Label(self.f.interior, text='Shown below are the current exif configurations for this camera.').grid(row=self.row, columnspan=6)
        self.row+=1
        Button(self.f.interior, text='Show instructions for this form', command=self.show_help).grid(row=self.row, columnspan=6)
        self.row+=1
        col = 1
        for header in ['Serial', 'Make', 'Model', 'Software/App', 'Media Type']:
            Label(self.f.interior, text=header).grid(row=self.row, column=col)
            col+=1
        for configuration in self.device_data['exif']:
            self.add_config(configuration=configuration)

        ok = Button(self.buttonsFrame, text='Ok', command=self.go, width=20, bg='green')
        ok.pack()

        cancel = Button(self.buttonsFrame, text='Cancel', command=self.cancel, width=20)
        cancel.pack()

    def add_config(self, configuration):
        if hasattr(self, 'add_button'):
            self.add_button.grid_forget()
        col = 0
        self.row += 1
        stringvars = collections.OrderedDict([('exif_device_serial_number', StringVar()), ('exif_camera_make', StringVar()), ('exif_camera_model', StringVar()), ('hp_app', StringVar()), ('media_type', StringVar())])
        Label(self.f.interior, text='Config: ' + str(self.config_count + 1)).grid(row=self.row, column=col)
        col += 1
        for k, v in stringvars.iteritems():
            if configuration[k] is None:
                v.set('')
            else:
                v.set(configuration[k])
            if k == 'media_type':
                e = ttk.Combobox(self.f.interior, values=['image', 'video', 'audio', ''], state='readonly', textvariable=v)
            else:
                e = Entry(self.f.interior, textvar=v)
                if k != 'hp_app':
                    e.config(state=DISABLED)
            e.grid(row=self.row, column=col)
            self.configurations[k].append(v)
            col += 1
        self.config_count+=1
        self.row+=1
        self.add_button = Button(self.f.interior, text='Add a new configuration', command=self.get_data)
        self.add_button.grid(row=self.row, columnspan=6)

    def go(self):
        url = 'https://medifor.rankone.io/api/cameras/' + str(self.device_data['id']) + '/'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Token ' + self.browser,
        }
        data = self.prepare_data()

        r = requests.put(url, headers=headers, data=data)
        if r.status_code in (requests.codes.ok, requests.codes.created):
            tkMessageBox.showinfo(title='Done!', message='Camera updated. Press Ok to notify via Trello.', parent=self)
            self.camupdate_notify_trello(url)
        else:
            tkMessageBox.showerror(title='Error', message='An error occurred updating this device. (' + str(r.status_code) + ')', parent=self)

    def prepare_data(self):
        data = {'exif':[]}
        for i in range(len(self.configurations['exif_camera_make'])):
            data['exif'].append({'exif_camera_make':self.configurations['exif_camera_make'][i].get(),
                         'exif_camera_model':self.configurations['exif_camera_model'][i].get(),
                         'hp_app': self.configurations['hp_app'][i].get(),
                         'media_type': self.configurations['media_type'][i].get(),
                         'exif_device_serial_number': self.configurations['exif_device_serial_number'][i].get()})

        for configuration in data['exif']:
            for key, val in configuration.iteritems():
                if val == '':
                    configuration[key] = None
        return json.dumps(data)

    def camupdate_notify_trello(self, link):
        # list ID for "New Devices" list
        trello_key = 'dcb97514b94a98223e16af6e18f9f99e'
        list_id = '58ecda84d8cfce408d93dd34'
        link = 'https://medifor.rankone.io/camera/' + str(self.device_data['id'])

        # post the new card
        title = 'Camera updated: ' + self.device_data['hp_device_local_id']
        resp = requests.post("https://trello.com/1/cards", params=dict(key=trello_key, token=self.trello),
                             data=dict(name=title, idList=list_id, desc=link))

        # attach the user, if successfully posted.
        if resp.status_code == requests.codes.ok:
            j = json.loads(resp.content)
            me = requests.get("https://trello.com/1/members/me", params=dict(key=trello_key, token=self.trello))
            member_id = json.loads(me.content)['id']
            new_card_id = j['id']
            resp2 = requests.post("https://trello.com/1/cards/%s/idMembers" % (new_card_id),
                                  params=dict(key=trello_key, token=self.trello),
                                  data=dict(value=member_id))
            tkMessageBox.showinfo(title='Information', message='Complete!', parent=self)
            self.destroy()
        else:
            tkMessageBox.showerror(title='Error', message='An error occurred connecting to trello (' + str(resp.status_code) + '). The device was still updated.')
            self.destroy()

    def show_help(self):
        tkMessageBox.showinfo(title='Instructions',
                              parent=self,
                              message='Occasionally, cameras can have different metadata for make and model for image vs. video, or for different apps. '
                                    'This usually results in errors in HP data processing, as the tool checks the data on record.\n\n'
                                    'If the device you\'re using has different metadata than what is on the browser for that device, add a new configuration by clicking the "Add a new configuration" button. '
                                    'You will be prompted to choose a file from that camera with the new metadata.\n\n'
                                    'Be sure to enter the media type, and if there was a particular App that was used with this media file, enter that as well in the respective field.'
                                    'Press Ok to push the changes to the browser, or Cancel to cancel the process.')

    def cancel(self):
        self.destroy()

    def get_data(self):
        self.imfile = tkFileDialog.askopenfilename(title='Select Media File')
        args = ['exiftool', '-f', '-j', '-Model', '-Make', '-SerialNumber', self.imfile]
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
            exifData = json.loads(p)[0]
        except:
            self.master.statusBox.println('An error ocurred attempting to pull exif data from image. Check exiftool install.')
            return
        exifData['Make'] = exifData['Make'] if exifData['Make'] != '-' else ''
        exifData['Model'] = exifData['Model'] if exifData['Model'] != '-' else ''
        exifData['SerialNumber'] = exifData['SerialNumber'] if exifData['SerialNumber'] != '-' else ''

        self.add_config({'exif_device_serial_number':exifData['SerialNumber'], 'exif_camera_model':exifData['Model'],
                         'exif_camera_make':exifData['Make'], 'hp_app':None, 'media_type':None})


class VerticalScrolledFrame(Frame):
    """A pure Tkinter scrollable frame that actually works!
    http://stackoverflow.com/questions/16188420/python-tkinter-scrollbar-for-frame
    * Use the 'interior' attribute to place widgets inside the scrollable frame
    * Construct and pack/place/grid normally
    * This frame only allows vertical scrolling

    """
    def __init__(self, parent, *args, **kw):
        Frame.__init__(self, parent, *args, **kw)

        # create a canvas object and a vertical scrollbar for scrolling it
        vscrollbar = Scrollbar(self, orient=VERTICAL)
        vscrollbar.pack(fill=Y, side=RIGHT, expand=FALSE)
        self.canvas = Canvas(self, bd=0, highlightthickness=0,
                        yscrollcommand=vscrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=TRUE)
        vscrollbar.config(command=self.canvas.yview)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        # reset the view
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

        # create a frame inside the canvas which will be scrolled with it
        self.interior = interior = Frame(self.canvas)
        interior_id = self.canvas.create_window(0, 0, window=interior,
                                           anchor=NW)

        # track changes to the canvas and frame width and sync them,
        # also updating the scrollbar
        def _configure_interior(event):
            # update the scrollbars to match the size of the inner frame
            size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
            self.canvas.config(scrollregion="0 0 %s %s" % size)
            if interior.winfo_reqwidth() != self.canvas.winfo_width():
                # update the canvas's width to fit the inner frame
                self.canvas.config(width=interior.winfo_reqwidth())
        interior.bind('<Configure>', _configure_interior)

        def _configure_canvas(event):
            if interior.winfo_reqwidth() != self.canvas.winfo_width():
                # update the inner frame's width to fill the canvas
                self.canvas.itemconfigure(interior_id, width=self.canvas.winfo_width())
        self.canvas.bind('<Configure>', _configure_canvas)

    def on_mousewheel(self, event):
        if sys.platform.startswith('win'):
            self.canvas.yview_scroll(-1*(event.delta/120), "units")
        else:
            self.canvas.yview_scroll(-1*(event.delta), "units")