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
import threading, Queue
import datetime


class CallOnceListener(object):
    """
    Listener object that disconnects itself as soon as it has
    been called once.
    """
    def __init__(self, functor, disconnectFunction ):
        self.functor=functor
        self.disconnectFunction=disconnectFunction
    def __call__(self, *a, **k) :
        self.functor( *a, **k )
        self.disconnectFunction(self)
        

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
        
        self.tracksToDisarm=[]
        # I can't figure out why, but I can't use clip slots as the key in a dict, I always get
        # a key error when trying to retrieve. I'll store as a (key,value) tuple in a list and
        # search manually. 
        self.clipSlotTimers=[] # deletes the clip if it isn't cancelled before finishing. Key is the clip slot
        self.buttonHoldTime=datetime.timedelta(0,2)
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
            self._selectButtons[2].add_value_listener( self.playCurrentRecordingAndArmNext )
            self._selectButtons[3].add_value_listener( self.stopSong )
            self._selectButtons[4].add_value_listener( self.toggleMetronome )
            

#             self._selectButtons[5].add_value_listener( partial(self.fire_scene,sceneNumber=0) )
#             self._selectButtons[6].add_value_listener( partial(self.fire_scene,sceneNumber=1) )
#             self._selectButtons[7].add_value_listener( partial(self.fire_scene,sceneNumber=2) )
#             self._selectButtons[8].add_value_listener( partial(self.fire_scene,sceneNumber=3) )
#             self._selectButtons[9].add_value_listener( partial(self.fire_scene,sceneNumber=4) )
            self._selectButtons[5].add_value_listener( partial(self.fire_clip,clipNumber=0) )
            self._selectButtons[6].add_value_listener( partial(self.fire_clip,clipNumber=1) )
            self._selectButtons[7].add_value_listener( partial(self.fire_clip,clipNumber=2) )
            self._selectButtons[8].add_value_listener( partial(self.fire_clip,clipNumber=3) )
            self._selectButtons[9].add_value_listener( partial(self.fire_clip,clipNumber=4) )
            
            # Define a function to say where the start of the highlighted region is. When all
            # scripts are loaded I'll try and find another control surface and use that highlighted
            # region. If I can't find one just work relative to the first clip.
            self.scene_offset=lambda : 0
            self.track_offset=lambda : 0

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
                self.track_offset=script._session.track_offset
                self.log_message("Behringer appears to have succesful piggy backed onto "+str(script))
                break
            except Exception, error:
                self.log_message("Behringer couldn't piggy back on "+str(script)+" because:"+str(error))

        if self.scene_offset==None :
            self.log_message("Behringer couldn't find another control surface to piggy back onto. Scene control will only control the first scenes.")
            self.scene_offset=lambda : 0
            self.track_offset=lambda : 0

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
            # This isn't quite the same as firing the scene, because any clips that aren't playing
            # are left alone.
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

    def fire_clip(self, value, clipNumber ):
        """
        If the button is pressed, starts a timer and deletes the clip when the
        timer finishes. If the button is released before the timer finishes then
        it is cancelled and the clip fired.
        I.e. press button once to fire clip, hold to delete current contents.
        """
        clipSlots=self.song().view.selected_scene.clip_slots
        index=self.track_offset()+clipNumber
        if index>=len(clipSlots) : return

        if value>90 : # button has been pressed
            self.log_message("index "+str(index))
            if index<len(clipSlots) : self.log_message("clipSlots[index].has_clip= "+str(clipSlots[index].has_clip))
            
            if clipSlots[index].has_clip :
                self.clipSlotTimers.append( (clipSlots[index],datetime.datetime.now()) )
        else : # button has been released
            timerWasRunning=False
            # Manually search for the clip slot in the list of clipSlotTimers
            self.log_message("Looking for timer in "+str(self.clipSlotTimers))
            for (storedClipSlot,storedTimer) in self.clipSlotTimers :
                if storedClipSlot==clipSlots[index] :
                    self.log_message("Timer found")
                    timerWasRunning=True#storedTimer.isAlive()
                    self.log_message("Tomer was found="+str(timerWasRunning))
                    self.clipSlotTimers.remove((storedClipSlot,storedTimer))
                    break

            if timerWasRunning or (not clipSlots[index].has_clip) : # button was released before clip deleted, so fire clip
                with self.component_guard():
                    if clipSlots[index].is_recording :
                        # If recording just play the clip
                        clipSlots[index].fire() # doesn't seem to be included in "else" for some reason. Maybe is_recording and is_triggered can both be true
                    elif clipSlots[index].is_playing or clipSlots[index].is_triggered :
                        clipSlots[index].stop()
                    else :
                        clipSlots[index].fire()

    def deleteClip( self, clipSlot ) :
        self.log_message("Deleting clip number "+str(clipSlot))
        with self.component_guard():
            clipSlot.delete_clip()
                

    def stopSong(self,value) :
        if value<=90 : return # Only do this when the button is pressed (not released)
        self.song().stop_playing()

    def toggleMetronome( self, value ):
        if value<=90 : return # Only do this when the button is pressed (not released)
        self.song().metronome=not self.song().metronome

    def playCurrentRecordingAndArmNext(self,value) :
        """
        Finds tracks that have the same input and output routing.
        """
        if value<=90 : return # Only do this when the button is pressed (not released)
        # I need to know the index of the current scene. The only way I know to do this is
        # to loop through all the scenes and see which one matches the current one
        for sceneIndex in xrange( len(self.song().scenes) ) :
            if self.song().scenes[sceneIndex]==self.song().view.selected_scene :
                break

        
        allTracks=self.song().tracks
        allClipSlots=self.song().view.selected_scene.clip_slots
        tracksToDuplicate=[] # List of indices of tracks that where there wasn't a match found
        for trackIndex in xrange( len(allClipSlots) ) :
            if allTracks[trackIndex].arm==True or allTracks[trackIndex].implicit_arm==True :
                # Make sure I don't do anything with any tracks that are in the process of
                # finishing their recording.
                if self.tracksToDisarm.count( allTracks[trackIndex] )!=0 : continue
                # If it's currently recording then I want it to fire and start playing. If it's
                # empty then I want it to fire and start recording.
                if not allClipSlots[trackIndex].has_clip :
                    allClipSlots[trackIndex].fire()
                    continue # Can just record into here, so no need to find another track
                if allClipSlots[trackIndex].is_recording :
                    allClipSlots[trackIndex].fire()
                if allClipSlots[trackIndex].has_clip :
                    # If it previously had a clip, I want to find another track that has the same
                    # input but an empty slot and start recording on that instead. I want it to use
                    # the next available slot to the right; if there isn't one then loop around.
                    foundMatchingTrack=False
                    for secondTrackIndex in xrange( trackIndex+1, len(allClipSlots)+trackIndex ) : # start one to the right
                        if secondTrackIndex>=len(allClipSlots) : secondTrackIndex-=len(allClipSlots) # loop around
                        
                        if not allClipSlots[secondTrackIndex].has_clip :
                            # Check to see if the input is the same
                            if allTracks[secondTrackIndex].current_input_routing==allTracks[trackIndex].current_input_routing \
                            and allTracks[secondTrackIndex].current_input_sub_routing==allTracks[trackIndex].current_input_sub_routing :
                                allTracks[secondTrackIndex].arm=True
                                allClipSlots[secondTrackIndex].fire()
                                # Can't unarm this track yet because recording stops immediately.
                                # Need to add a listener to unarm once the playing status has changed.
                                self.tracksToDisarm.append( allTracks[trackIndex] )
                                foundMatchingTrack=True
                                break
                    if not foundMatchingTrack :
                        # A suitable track wasn't found, so need to create a new one. Can't do this now
                        # though because it would mess up this loop. Record the track index and do it
                        # in a second loop.
                        tracksToDuplicate.append(trackIndex)
        
        # Now I've looped over the pre-existing tracks, I can create any new ones that are
        # required.
        offsetFromNewTracks=0 # When I insert a track, the next items in the array will be wrong. Use this to keep track.
        for sourceIndex in tracksToDuplicate :
            sourceIndex+=offsetFromNewTracks # Note in python this doesn't affect the next iteration
            # Can't use duplicate because it doesn't work if the current track is
            # currently recording. Insert it immediately to the right
            if allTracks[sourceIndex].has_audio_input :
                self.song().create_audio_track(sourceIndex+1)
            else :
                self.song().create_midi_track(sourceIndex+1)
            offsetFromNewTracks+=1 # Make sure the next iteration doesn't accidentally address the new track
            # allTracks and allClipSlots don't appear to update with the new track, so get it again.
            allTracks=self.song().tracks
            allClipSlots=self.song().view.selected_scene.clip_slots

            allTracks[sourceIndex+1].current_input_routing=allTracks[sourceIndex].current_input_routing
            allTracks[sourceIndex+1].current_input_sub_routing=allTracks[sourceIndex].current_input_sub_routing
            allTracks[sourceIndex+1].arm=True
            allClipSlots[sourceIndex+1].fire() # Fire the new track
            # Can't unarm this track yet because recording stops immediately.
            # Need to delay until the recording has acually stopped. Can't use a listener
            # because Live complains about making changes during notification. I'll just
            # add it to a list of things that will be cleared up in a periodically function.
            self.tracksToDisarm.append( allTracks[sourceIndex] )

    def update_display(self,*a, **k):
        super(BehringerFCB1010, self).update_display(*a, **k)
        
        # I can't disarm tracks in listeners so I have to check here to see if anything has
        # been queued up to be disarmed. 
        if len(self.tracksToDisarm)>0 :
            # I need to know the index of the current scene. The only way I know to do this is
            # to loop through all the scenes and see which one matches the current one
            for sceneIndex in xrange( len(self.song().scenes) ) :
                if self.song().scenes[sceneIndex]==self.song().view.selected_scene : break

            for track in self.tracksToDisarm :
                if not track.clip_slots[sceneIndex].is_recording :
                    track.arm=False
                    track.implicit_arm=False
                    self.tracksToDisarm.remove(track)

        if len(self.clipSlotTimers)>0 :
            timeNow=datetime.datetime.now()
            for (clipSlot,timeStarted) in self.clipSlotTimers[:] :
                if timeNow-timeStarted > self.buttonHoldTime :
                    clipSlot.delete_clip()
                    self.clipSlotTimers.remove( (clipSlot,timeStarted) )
