import kivy
kivy.require('1.0.8-dev')

import random
from glob import glob
from os.path import join, dirname, exists, basename
from os import mkdir
from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.logger import Logger
from kivy.resources import resource_add_path
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation

import museolib
from museolib.utils import format_date
from museolib.widgets.circularslider import CircularSlider
from museolib.widgets.imagemap import ImageMap
from museolib.widgets.imageitem import ImageItem
from museolib.widgets.exposelector import ExpoSelector
#from museolib.backend.backendxml import BackendXML
from museolib.backend.backendjson import BackendJSON
from museolib.backend.backendweb import BackendWeb
from math import cos, sin, radians
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.animation import Animation
from kivy.utils import format_bytes_to_human
import json

try:
    mode = 'mobile'
    import android
except ImportError:
    mode = 'table'

class MuseotouchApp(App):

    imgtype = 'dds'

    @property
    def mode(self):
        return mode

    def do_panic(self, *largs):
        children = self.root_images.children
        cx, cy = self.root_images.center

        # seperate the table in 2
        imgs = 512 * 0.3
        width = self.root_images.width - 300
        height = self.root_images.height - 300
        x = 50
        y = self.root_images.top - imgs - 50
        dx = 1
        dy = -1

        mx = 1 + width // imgs
        my = 1 + height // imgs

        for i, item in enumerate(reversed(children)):
            mi = i % (mx * my)
            ix = x + (mi % mx) * imgs * dx
            iy = y + (mi // mx) * imgs * dy
            item.flip_front=True
            (Animation(d=0.1 + i / 30.) + Animation(scale=0.30, pos=(ix, iy),
                    rotation=0., t='out_quad',
                    d=.25)).start(item)

        return
        # angle disposition test
        step = 360. / len(children)
        dist = 100
        for i, item in enumerate(children):
            r = radians(step * i)
            ix = cx + dist * cos(r)
            iy = cy + dist * sin(r)
            item.flip_front = True
            '''
            item.scale = 0.25
            item.center = ix, iy
            item.rotation = step * i
            '''

            Animation(scale=0.30, center=(ix, iy),
                    rotation=step*i, t='out_quad', d=.25).start(item)

    def show_objects(self, objects):
        images_displayed = [x.source for x in self.root_images.children]
        root = self.root
        add = self.root_images.add_widget
        randint = random.randint

        print 'show_objects()', objects

        for item in objects:
            # is the current filename is already showed ?
            filename = item.filename
            if filename in images_displayed:
                images_displayed.remove(filename)
                continue

            x = randint(root.x + 200, root.right - 200)
            y = randint(root.y + 300, root.top - 100)
            angle = randint(0, 360)

            image = ImageItem(source=filename, rotation=angle + 90,
                    center=(x, y), item=item, app=self)
            add(image)

        # remove all the previous images
        for child in self.root_images.children[:]:
            for filename in images_displayed:
                if filename == child.source:
                    self.root_images.remove_widget(child)

    def update_objects_from_filter(self, *largs):
        '''Update the objects displayed from filters (date range, origin...)
        '''
        # update date range from slider value
        ma, mb = self.slider.value_range
        count = self.db.length
        item_min = int(ma * count)
        item_max = max(item_min + 1, int(mb * count))

        # adjust item selection
        items = self.db.items[item_min:item_max]
        if len(items) == 0:
            self.show_objects(items)
            return
        item1 = items[0]
        item2 = items[-1]

        # set the text inside the slider
        self.slider.text_min = format_date(item1.date)
        self.slider.text_max = format_date(item2.date)

        # filter from origin
        origin_ids = self.imagemap.active_ids
        items = [x for x in items if x.origin_key in origin_ids]

        # show only the first 10 objects
        self.show_objects(items)

    def build_config(self, config):
        config.setdefaults('museotouch', {
            'expo': '',
        })

    def build(self):
        # add data directory as a resource path
        self.data_dir = data_dir = join(dirname(museolib.__file__), 'data')
        resource_add_path(data_dir)

        # add kv file
        Builder.load_file(join(data_dir, 'global.kv'))

        # create trigger for updating objects
        self.trigger_objects_filtering = Clock.create_trigger(
            self.update_objects_from_filter, 0)

        # web backend
        self.backend = BackendWeb(
                url='http://museotouch.erasme.org/prive/api/',
                data_url='http://museotouch.erasme.org/prive/uploads/')

        # if we are on android, always start on selector
        # otherwise, check configuration
        if mode == 'table':
            self.build_for_table()
        else:
            self.build_selector()


    def build_for_table(self):
        # check which exposition we must use from the configuration
        expo = self.config.get('museotouch', 'expo')
        if expo == '':
            # no exposition set in the configuration file.
            # show the selector
            return self.build_selector()
        self.show_expo(expo)
        return FloatLayout()

    def build_selector(self):
        return ExpoSelector(app=self)

    def build_app(self):
        # link with the db. later, we need to change it to real one.
        Builder.load_file(join(self.expo_data_dir, 'museotouch.kv'))
        self.db = db = BackendJSON(filename=join(
            self.expo_dir, 'objects.json'))
        Logger.info('Museotouch: loaded %d items' % len(db.items))

        # resolving filename for all item
        items = db.items[:]
        imgtype = self.imgtype
        for item in items[:]:
            if imgtype == 'raw':
                directory, ext = imgtype, 'png'
            else:
                directory, ext = imgtype, imgtype
            filename = join(self.expo_img_dir,  directory, '%d.%s' % (item.id, ext))
            if not exists(filename):
                Logger.error('Museolib: Unable to found image %s' % filename)
                items.remove(item)
                continue
            item.filename = filename

        db.items = items
        Logger.info('Museotouch: %d items usable' % len(db.items))

        # construct the app.
        # at one moment, this could be moved to a "generic" app.xml file
        # that can be used to load another scenario
        self.root = root = FloatLayout()
        self.slider = slider = CircularSlider(
                pos_hint={'right': 1, 'center_y': 0.5},
                size_hint=(None, None),
                size=(250, 500))
        root.add_widget(slider)

        # search image for map (exclude _active) files
        sources = glob(join(self.expo_data_dir, 'widgets', 'map', '*.png'))
        sources = [x for x in sources if '_active' not in x]
        self.imagemap = imagemap = ImageMap(
                pos_hint={'center_x': 0.5, 'y': 0},
                size_hint=(None, None),
                size=(500, 268),
                sources=sources,
                suffix='_active')
        root.add_widget(imagemap)

        # add root layer for putting image
        self.root_images = FloatLayout()
        self.root.add_widget(self.root_images)

        # panic button
        self.panic_button = Button(text='Panic!', size_hint=(None, None),
                size=(50, 50))
        self.panic_button.bind(on_release=self.do_panic)
        self.root.add_widget(self.panic_button)

        # update the initial slider values to show date.
        slider.bind(value_range=self.trigger_objects_filtering)
        imagemap.bind(active_ids=self.trigger_objects_filtering)
        self.trigger_objects_filtering()

        parent = self.root.parent
        if parent:
            parent.remove_widget(self.root)
        else:
            from kivy.core.window import Window
            parent = Window
        self.root = root
        parent.add_widget(self.root)
        return root

    def show_expo(self, expo_id, popup=None):
        # check if expo is available on the disk
        self.expo_dir = self.get_expo_dir(expo_id)
        self.expo_data_dir = join(self.expo_dir, 'data')
        self.expo_img_dir = join(self.expo_dir, 'images')
        resource_add_path(self.expo_data_dir)

        # be able to run offline too.
        force_sync = True
        if force_sync:
            # create popup
            if popup is None:
                from kivy.uix.popup import Popup
                popup = Popup(title='Chargement...', size_hint=(None, None),
                        size=(300, 300))
                popup.open()
            # synchronize it !
            self.sync_expo(expo_id, popup)
        else:
            self.build_app()


    #
    # Synchronisation of an exhibition
    # this part is seperated in multiple step:
    # 1. create directory layout for an exhibition if not exists
    # 2. update the objects list of an exhibition
    # 3. fetch missing objects
    #

    def get_expo_dir(self, expo_id):
        return join(dirname(__file__), 'expos', expo_id)

    def sync_expo(self, expo_id, popup=None):
        # adjust the popup 
        popup.title = 'Synchronisation en cours...'
        popup.content = Label(text='Synchronisation de la base...',
                halign='center')
        Animation(size=(300, 200), d=.2, t='out_quad').start(popup)
        self._sync_popup = popup

        # create layout for exhibition
        for directory in (
                self.expo_dir,
                self.expo_data_dir,
                self.expo_img_dir,
                join(self.expo_img_dir, self.imgtype)):
            try:
                mkdir(directory)
            except OSError:
                pass

        # get the initial json
        self.backend.set_expo(expo_id)
        self.backend.get_objects(on_success=self._sync_expo_2, on_error=self._sync_error)

    def _sync_expo_2(self, req, result):
        filename = join(self.expo_dir, 'objects.json')
        with open(filename, 'wb') as fd:
            json.dump(result, fd)

        # on the result, remove all the object already synced
        items = result['items'][:]
        for item in result['items']:
            fichier = item['fichier']
            if not fichier:
                items.remove(item)
                continue
            filename, ext = self._sync_convert_filename(item['fichier'])
            local_filename = self._sync_get_local_filename(filename)
            if not exists(local_filename):
                continue
            items.remove(item)

        self._sync_result = items
        self._sync_index = 0
        self._sync_missing = []

        if len(items):

            # prepare for synchronization
            layout = BoxLayout(orientation='vertical')
            layout.add_widget(Label(halign='center'))
            layout.add_widget(Label(halign='center'))
            layout.add_widget(ProgressBar())
            self._sync_popup.content = layout

            self._sync_download()

        else:
            # no item to synchronize, all done !
            self._sync_popup.dismiss()
            self.build_app()

    def _sync_get_local_filename(self, fn):
        return join(self.expo_img_dir, self.imgtype, fn)

    def _sync_convert_filename(self, filename):
        # from the original filename given by json
        # convert to the filename we want.
        print 'filename', filename, basename(filename)
        filename = basename(filename)
        if self.imgtype != 'raw':
            filename = filename.rsplit('.', 1)[0] + '.' + self.imgtype
        # get ext
        ext = filename.rsplit('.', 1)[-1]
        return filename, ext

    def _sync_download(self):
        uid = self._sync_result[self._sync_index]['id']
        filename, ext = self._sync_convert_filename(
            self._sync_result[self._sync_index]['fichier'])
        print 'SYNCHRO', filename, '|', ext

        text = 'Synchronisation de %d/%d' % (
                self._sync_index + 1, len(self._sync_result))
        if len(self._sync_missing):
            text += '\n(%d non disponible)' % len(self._sync_missing)
        self._sync_popup.content.children[-1].text = text
        self._sync_popup.content.children[-2].text = filename

        # check if the file already exist on the disk
        filename = self._sync_get_local_filename(filename)
        if exists(filename):
            # speedup a little bit. but we can't use always -1.
            Clock.schedule_once(self._sync_download_next,
                    -1 if self._sync_index % 10 < 8 else 0)
        else:
            self.backend.download_object(uid, ext, self.imgtype == 'raw',
                self._sync_download_ok, self._sync_error, self._sync_progress)

    def _sync_download_ok(self, req, result):
        if req.resp_status < 200 or req.resp_status >= 300:
            # look like invalid ? ok.
            self._sync_missing.append(self._sync_index)
        else:
            # save on disk
            filename = self._sync_convert_filename(req.url)
            filename = self._sync_get_local_filename(filename)
            with open(filename, 'wb') as fd:
                fd.write(result)
        Clock.schedule_once(self._sync_download_next)

    def _sync_download_next(self, *largs):
        self._sync_index += 1
        if self._sync_index >= len(self._sync_result):
            self._sync_end()
            return
        self._sync_download()

    def _sync_end(self):
        self._sync_popup.dismiss()
        self.build_app()

    def _sync_progress(self, req, current, total):
        self._sync_popup.content.children[0].max = total
        self._sync_popup.content.children[0].value = current
        text = self._sync_popup.content.children[-2].text
        filename = text.split(' ')[0]
        text = '%s - %s/%s' % (filename,
                format_bytes_to_human(current),
                format_bytes_to_human(total))
        self._sync_popup.content.children[-2].text = text

    def _sync_error(self, req, result):
        self._sync_popup.content.children[-2].text = 'Erreur lors de la synchro'
        

if __name__ in ('__main__', '__android__'):
    MuseotouchApp().run()
