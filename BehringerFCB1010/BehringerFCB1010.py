from __future__ import with_statement
from _Framework.ControlSurface import ControlSurface
from _Framework.ButtonElement import ButtonElement
from _Framework.SliderElement import SliderElement
from _Framework.SessionComponent import SessionComponent
from _Framework.DeviceComponent import DeviceComponent
from _Framework.MixerComponent import MixerComponent
from _Framework.Layer import Layer
from _Framework.InputControlElement import MIDI_NOTE_TYPE, MIDI_CC_TYPE
from _Framework.ButtonMatrixElement import ButtonMatrixElement
from functools import partial
import Live


class BehringerFCB1010(ControlSurface):
    NUMBER_OF_CONTROLS = 10 # The number of normal pedal buttons on the board, not including specials like "up"
    NUMBER_OF_EXPRESSION = 2 # The number of expression pedals available
    MIDI_CHANNEL = 0
    # The MIDI note number that each of the 10 pedals transmits (programmed on the board itself,
    # these numbers are what I've set mine to).
    PEDAL_MIDI_NOTES = [1,2,3,4,5,6,7,8,9,10]
    # The MIDI CC number that each of the two expression pedals transmits
    EXPRESSION_MIDI_CC = [27,28]
    
    def __init__(self, *a, **k):
        super(BehringerFCB1010, self).__init__(*a, **k)
        self.log_message("Starting Behringer FCB1010 script __init__")
        # I've already set up the board so that it transmits note C#-2 for pedal 1, D-2 for pedal 3 and so on
        # (increasing each time by one semitone) the MIDI number for note C#-2 is 1 (hence why I chose it for
        # pedal 1). These are hard coded in the PEDAL_MIDI_NOTES array. Note that this is for bank 00. At the
        # moment I'm ignoring the "Up" and "Down" pedals because they change all the other pedals.
        with self.component_guard():
            self._selectButtons=[ ButtonElement( True, MIDI_NOTE_TYPE, self.MIDI_CHANNEL, self.PEDAL_MIDI_NOTES[pedal], name='Pedal_%d' % (pedal+1) ) for pedal in xrange(self.NUMBER_OF_CONTROLS) ]
            self._expressionPedals=[ SliderElement( MIDI_CC_TYPE, self.MIDI_CHANNEL, self.EXPRESSION_MIDI_CC[pedal] ) for pedal in xrange(self.NUMBER_OF_EXPRESSION) ]
            # Need to add buttons for the "up" and "down" pedals. Haven't figured out how I'm goint to implement
            # those however since they change the notes of all the other pedals.

            self._selectButtons[0].add_value_listener( self.begin_recording_handler )
            self._selectButtons[1].add_value_listener( self.begin_recording_new_scene_handler )

            self._selectButtons[5].add_value_listener( partial(self.fire_scene,sceneNumber=0) )
            self._selectButtons[6].add_value_listener( partial(self.fire_scene,sceneNumber=1) )
            self._selectButtons[7].add_value_listener( partial(self.fire_scene,sceneNumber=2) )
            self._selectButtons[8].add_value_listener( partial(self.fire_scene,sceneNumber=3) )
            self._selectButtons[9].add_value_listener( partial(self.fire_scene,sceneNumber=4) )
            
            # Define a function to say where the start of the highlighted region is. When all
            # scripts are loaded I'll try and find another control surface and use that highlighted
            # region. If I can't find one just work relative to the first clip.
            self.scene_offset=lambda : 0

            #self._clipLaunchButtons=[ [self._selectButtons[0],self._selectButtons[1],self._selectButtons[2] ],[self._selectButtons[5],self._selectButtons[6],self._selectButtons[7] ]]            
#             self._matrix_buttons=[ [self._selectButtons[xIndex+yIndex*5] for xIndex in xrange(5) ] for yIndex in xrange(2) ]
#             self._launchMatrix=ButtonMatrixElement( name='Button_Matrix', rows=self._matrix_buttons )
#             self._session = SessionComponent(5, 2, auto_name=True, enable_skinning=False, is_enabled=False, layer=Layer(clip_launch_buttons=self._launchMatrix ) )
#             self._mixer = MixerComponent( 5, auto_name=True, is_enabled=False, invert_mute_feedback=True)
#             self._device=DeviceComponent(name='Device_Component', is_enabled=False)
# 
#             self._session.set_mixer( self._mixer )            
#             self.set_device_component(self._device)
#             self.set_highlighting_session_component(self._session)
#             
#             self._session.set_clip_launch_buttons(self._launchMatrix)
#             self._session.scene(1).clip_slot(1).set_launch_button( self._selectButtons[0] )
#             self._session.set_enabled(True)
#             self._mixer.set_enabled(True)
#             self._device.set_enabled(True)

        self.log_message("Finished Behringer FCB1010 script __init__")

    def connect_script_instances(self,instanciated_scripts) :
        """
        Gets called by the application whenever a new script is loaded or unloaded.
        Used here to get a control surface to piggy back on so that the scene launch
        buttons match the scenes highlighted by the other control surface. 
        """
        self.log_message("Behringer connect_script_instances with "+str(instanciated_scripts))
        
        self.scene_offset=None
        for script in instanciated_scripts:
            if script==self : continue
            # See if I can find a SessionComponent and get a reference to
            # its scene_offset method.
            try :
                # This assumes the scene has the attribute name "_session" which may
                # not be true, but it is for the control surface I'm using.
                self.scene_offset=script._session.scene_offset
                self.log_message("Behringer appears to have succesful piggy backed onto "+str(script))
                break
            except Exception, error:
                self.log_message("Behringer couldn't piggy back on "+str(script)+" because:"+str(error))

        if self.scene_offset==None :
            self.log_message("Behringer couldn't find another control surface to piggy back onto. Scene control will only control the first scenes.")
            self.scene_offset=lambda : 0

    def get_matrix_button(self, column, row):
        return self._matrix_buttons[row][column]
    
    def handle_sysex(self, midi_bytes):
        pass

    def begin_recording_handler(self,value):
        """
        Starts recording a clip on any tracks that are armed. If the track is already
        recording then it starts playing that clip.
        Tracks that already have clips are skipped.
        """
        # Some controllers send 127 when the button is pressed, my FCB1010 sends 100.
        # I'll just check to see if it's over 90.
        if value>90 : # Only do this when the button is pressed (not released)
            scene_slots=self.song().view.selected_scene.clip_slots
            tracks=self.song().tracks
            # I assume the clip slots in a scene always match 1-to-1 with the number of tracks.
            # Start recording in the current scene for every track that is armed. If there is
            # a clip there already ignore that track. If anything is recording already, stop recording.
            for index in xrange( max( len(scene_slots), len(tracks) ) ) :
                if tracks[index].arm or tracks[index].implicit_arm :
                    if (not scene_slots[index].has_clip) or scene_slots[index].is_recording :
                        scene_slots[index].fire()

    def begin_recording_new_scene_handler(self,value):
        """
        Creates a new scene at the end and begins recording
        a clip on all armed tracks.
        """
        # Some controllers send 127 when the button is pressed, my FCB1010 sends 100.
        # I'll just check to see if it's over 90.
        if value>90 : # Only do this when the button is pressed (not released)
            scene_slots=self.song().view.selected_scene.clip_slots
            tracks=self.song().tracks
            # Make sure there are at least some tracks armed for recording before creating
            # the new scene
            armedTrackIndices=[]
            clipIndicesToCopy=[]
            clipIndicesToPlay=[]
            for index in xrange( max( len(scene_slots), len(tracks) ) ) :
                if tracks[index].arm or tracks[index].implicit_arm :
                    armedTrackIndices.append(index)
                elif scene_slots[index].has_clip : # See if there is a clip that needs to be copied
                    clipIndicesToCopy.append(index)
                    if scene_slots[index].is_playing : clipIndicesToPlay.append(index)

            # If there are no armed tracks then there's no point doing anything
            if len(armedTrackIndices)==0 : return

            # I need to know the index of the current scene. The only way I know to do this is
            # to loop through all the scenes and see which one matches the current one
            for sceneIndex in xrange( len(self.song().scenes) ) :
                if self.song().scenes[sceneIndex]==self.song().view.selected_scene :
                    break
            newScene=self.song().create_scene(sceneIndex+1)
            scene_slots=newScene.clip_slots
            for index in clipIndicesToCopy :
                tracks[index].duplicate_clip_slot(sceneIndex)
            for index in clipIndicesToPlay :
                scene_slots[index].fire()
            for index in armedTrackIndices :
                scene_slots[index].fire()

    def fire_scene(self, value, sceneNumber):
        """
        Fires the scene at the given index. If piggy backing on another control
        surface then the index is relative to the highlighted region, otherwise
        it's relative to the first scene.
        """
        if value>90 : # Only do this when the button is pressed (not released)
            scenes=self.song().scenes
            index=self.scene_offset()+sceneNumber
            if index<len(scenes) :
                scenes[index].fire()
