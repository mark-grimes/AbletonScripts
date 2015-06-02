#Embedded file name: /Users/versonator/Jenkins/live/Binary/Core_Release_64_static/midi-remote-scripts/APC_mini/APC_mini.py
from __future__ import with_statement
from _Framework.Layer import Layer, SimpleLayerOwner
from _Framework.Skin import Skin
from _Framework.ButtonElement import Color,ButtonElement,DummyUndoStepHandler
from _Framework.InputControlElement import MIDI_NOTE_TYPE, MIDI_CC_TYPE
from _APC.ControlElementUtils import make_slider, make_button
from APC_Key_25.APC_Key_25 import APC_Key_25
from functools import partial
import Live


class CustomColourButtonElement(ButtonElement):
    """
    A subclass of _Framework.ButtonElement.ButtonElement but allows setting the
    colour value for on/off buttons. Skins don't seem to have any effect on on/off
    buttons as far as I can see.
    """
    OFF = Color(0)
    GREEN = Color(1)
    GREEN_BLINK = Color(2)
    RED = Color(3)
    RED_BLINK = Color(4)
    AMBER = Color(5)
    AMBER_BLINK = Color(6)

    def __init__(self, is_momentary, msg_type, channel, identifier, skin = Skin(), undo_step_handler = DummyUndoStepHandler(), custom_on_value=127, custom_off_value=0, *a, **k):
        super(CustomColourButtonElement, self).__init__(is_momentary, msg_type, channel, identifier, skin, undo_step_handler, *a, **k)
        self.custom_on_value=custom_on_value
        self.custom_off_value=custom_off_value

    def turn_on(self):
        self.send_value(self.custom_on_value)

    def turn_off(self):
        self.send_value(self.custom_off_value)


class CustomAPC_mini(APC_Key_25):
    """
    A customisation of the APC Mini control surface that sacrifices part of the clip launch grid
    to have track arm, mute and select always available. 
    """
    SESSION_HEIGHT = 5
    HAS_TRANSPORT = False

    def __init__(self, *a, **k):
        super(CustomAPC_mini, self).__init__(*a, **k)
        with self.component_guard():
            self.register_disconnectable(SimpleLayerOwner(layer=Layer(_unused_buttons=self.wrap_matrix(self._unused_buttons))))
        self._mixer.set_track_select_buttons( self._custom_matrix_buttons_row1 )
        self._mixer.set_mute_buttons( self._custom_matrix_buttons_row2 )
        self._mixer.set_arm_buttons( self._custom_matrix_buttons_row3 )
        #self.song().exclusive_arm(True) # gives TypeError 'bool' object is not callable

    def _make_stop_all_button(self):
        #return self.make_shifted_button(self._scene_launch_buttons[7])
        return make_button(0, 89, name='Scene_Launch_8', skin=self._color_skin )

    def _create_controls(self):
        super(CustomAPC_mini, self)._create_controls()
        # Need to shift the active part of the matrix up 3 rows
        for row in self._matrix_buttons :
            for button in row :
                button._msg_identifier+=24
                button._original_identifier+=24
        # Now set my custom buttons to something
        self._custom_session_buttons = [ make_button(0, index + 87, name='Custom_session_button_%d' % (index + 1), skin=self._color_skin) for index in xrange(3) ]
        #self._custom_matrix_buttons = [[ make_button(0,xIndex+self.SESSION_WIDTH*(self.SESSION_HEIGHT-yIndex-1), name='Custom_matrix_button_%d_%d' % (xindex+1,yIndex+1), skin=self._color_skin) for yIndex in xrange(self.SESSION_WIDTH) ] for xIndex in xrange(3)]

        #self._custom_matrix_buttons_row1 = [ make_button(0,xIndex+self.SESSION_WIDTH*2, name='Custom_matrix_button_%d_%d' % (xIndex+1,1), skin=self._custom_select_colors) for xIndex in xrange(self.SESSION_WIDTH) ]
        self._custom_matrix_buttons_row1 = [ CustomColourButtonElement(True,MIDI_NOTE_TYPE,0,xIndex+self.SESSION_WIDTH*2, name='Custom_matrix_button_%d_%d' % (xIndex+1,1), custom_on_value=CustomColourButtonElement.AMBER) for xIndex in xrange(self.SESSION_WIDTH) ]
        self._custom_matrix_buttons_row2 = [ CustomColourButtonElement(True,MIDI_NOTE_TYPE,0,xIndex+self.SESSION_WIDTH*1, name='Custom_matrix_button_%d_%d' % (xIndex+1,2), custom_off_value=CustomColourButtonElement.RED, custom_on_value=CustomColourButtonElement.OFF) for xIndex in xrange(self.SESSION_WIDTH) ]
        self._custom_matrix_buttons_row3 = [ CustomColourButtonElement(True,MIDI_NOTE_TYPE,0,xIndex+self.SESSION_WIDTH*0, name='Custom_matrix_button_%d_%d' % (xIndex+1,3), custom_on_value=CustomColourButtonElement.RED) for xIndex in xrange(self.SESSION_WIDTH) ]
        
        self.custom_arms = Layer(arm_buttons=self.wrap_matrix(self._custom_matrix_buttons_row1))
        #self._unused_buttons = map(self.make_shifted_button, self._scene_launch_buttons[5:7])
        self._unused_buttons = self._custom_session_buttons
        self._master_volume_control = make_slider(0, 56, name='Master_Volume')

    def _create_mixer(self):
        mixer = super(CustomAPC_mini, self)._create_mixer()
        mixer.master_strip().layer = Layer(volume_control=self._master_volume_control)
        return mixer

    def _product_model_id_byte(self):
        return 40
    
