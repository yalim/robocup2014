#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Sat March 16 11:30:00 2013

@author: Chang Long Zhu
@email: changlongzj@gmail.com
"""


import rospy
import smach
from navigation_states.nav_to_coord import nav_to_coord
from navigation_states.nav_to_poi import nav_to_poi
from navigation_states.enter_room import EnterRoomSM
from speech_states.say import text_to_say
from speech_states.ask_question import AskQuestionSM
from manipulation_states.play_motion_sm import play_motion_sm
from manipulation_states.move_hands_form import move_hands_form 
from manipulation_states.ask_give_object_grasping import ask_give_object_grasping
from util_states.topic_reader import topic_reader
from geometry_msgs.msg import PoseStamped


# Some color codes for prints, from http://stackoverflow.com/questions/287871/print-in-terminal-with-colors-using-python
ENDC = '\033[0m'
FAIL = '\033[91m'
OKGREEN = '\033[92m'

import random

class DummyStateMachine(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded','aborted', 'preempted'], 
            input_keys=[]) 

    def execute(self, userdata):
        print "Dummy state just to change to other state"  # Don't use prints, use rospy.logXXXX

        rospy.sleep(3)
        return 'succeeded'

# Class that prepare the value need for nav_to_poi
class prepare_poi_person_emergency(smach.State):
    def __init__(self, poi_type='arena_door_out'):
        smach.State.__init__(self, outcomes=['succeeded','aborted', 'preempted'], 
            input_keys=['person_location'], 
            output_keys=['nav_to_poi_name']) 
        self.poi_type_in = poi_type
    def execute(self,userdata):
        userdata.nav_to_poi_name = userdata.person_location

        return 'succeeded'

class prepare_tts(smach.State):
    def __init__(self,tts_text_phrase=''):
        smach.State.__init__(self, 
            outcomes=['succeeded','aborted', 'preempted'], 
            output_keys=['tts_text']) 
        self.tts_text_phrase_in = tts_text_phrase
    def execute(self, userdata):
        userdata.tts_text = self.tts_text_phrase_in

        return 'succeeded'


class Get_Person_Desired_Object(smach.StateMachine):
    """
    Executes a SM that does the Emergency Situation's Save People SM.
    It is a SuperStateMachine (contains submachines) with these functionalities (draft):
    # The functionalities of this SuperSM are:
    # 1. Ask the person what to fetch
    # 2. Go and grab the object  --> Similar with Pick-and-Place
    #   2.1. Go to room
    #   2.2. Find Object 
    #   2.3. Go to Object
    #   2.4. Grab Object
    #   2.5. Go to person
    #   2.6. Give object --> Ungrab
    #                    --> Database of objects and their location
    #                    --> Manip/Grab 

    Required parameters:
    No parameters.

    Optional parameters:
    No optional parameters

    Input_keys:
    @key: emergency_person_location: person's location (Geometry or PoseStamped)

    Output Keys:
        none
    No io_keys.

    Nothing must be taken into account to use this SM.
    """
    def __init__(self):
        smach.StateMachine.__init__(self, ['succeeded', 'preempted', 'aborted'],
                                    input_keys=['person_location'])

        with self:           
            self.userdata.emergency_location = []
            self.userdata.tts_lang = 'en_US'
            self.userdata.tts_wait_before_speaking = 0
            # Ask for the object to bring to the person
            # Output: 
            #   - string 'userSaid'
            #   - actiontag[] 'asr_userSaid_tags'
            # TODO: grammar for the Emergency Situation -- Get_Person_Desired_Object
            smach.StateMachine.add(
                'Ask_Question',
                AskQuestionSM(text='What would you like me to bring?', grammar='emergency_drinks'),
                transitions={'succeeded':'Process_Tags', 'aborted':'Ask_Question', 'preempted':'Ask_Question'})
#            smach.StateMachine.add(
#                'Prepare_Ask_Object',
#                prepare_tts('What would you like me to bring?'),
#                transitions={'succeeded':'Say_Ask_Object', 'aborted':'Say_Ask_Object', 'preempted':'Say_Ask_Object'})

#            smach.StateMachine.add(
#                'Say_Ask_Object',
#                text_to_say(),
#                transitions={'succeeded':'Listen_to_Desire', 'aborted':'Listen_to_Desire', 'preempted':'Listen_to_Desire'})

            # TODO: ASR : Automatic Speech Recognition: Whay_say/Listen_to
            # TODO: Activate_ASR + Read_ASR + DeActivate_ASR
#            smach.StateMachine.add(
#                'Listen_to_Desire',
#                DummyStateMachine(),
#                #Listen_to(),
#                transitions={'succeeded':'Go_Grab_Object', 'aborted':'Say_Ask_Object', 'preempted':'Say_Ask_Object'})

            # Get the output from AskQuestionSM, process it, and search in the yaml file for the location of the object asked 
            # Input keys: actiontag[] 'asr_userSaid_tags'
            # Output keys: object
            smach.StateMachine.add(
                'Process_Tags',
                DummyStateMachine(),
                #Process_Tags(),
                transitions={'succeeded':'Go_To_Object_Place', 'aborted':'Go_To_Object_Place', 'aborted':'Go_To_Object_Place'})

            smach.StateMachine.add(
                'Go_To_Object_Place',
                DummyStateMachine(),
                transitions={'succeeded':'Find_and_grab_object', 'aborted':'Go_To_Object_Place', 'preempted':'Go_To_Object_Place'})

            #Find Object + Grab Object SM
            smach.StateMachine.add(
                'Find_and_grab_object',
                #Find_and_grab_object(),
                DummyStateMachine(),
                transitions={'succeeded':'Prepare_Go_To_Person', 'aborted':'Grasp_fail_Ask_Person', 'preempted':'Grasp_fail_Ask_Person'})
            smach.StateMachine.add(
                'Grasp_fail_Ask_Person',
                ask_give_object_grasping(),
                transitions={'succeeded':'Prepare_Go_To_Person', 'aborted':'Prepare_Go_To_Person', 'preempted':'Prepare_Go_To_Person'})
            #Go to person
            smach.StateMachine.add(
                'Prepare_Go_To_Person',
                prepare_poi_person_emergency(),
                transitions={'succeeded':'Go_To_Person', 'aborted':'Go_To_Person', 'preempted':'Go_To_Person'})
            #TODO: POI For Person in Emergency
            smach.StateMachine.add(
                'Go_To_Person',
                DummyStateMachine(),
                #nav_to_poi(),
                transitions={'succeeded':'Give_Object', 'aborted':'Give_Object', 'preempted':'Give_Object'})

            #Give the grabbed object to the person
            smach.StateMachine.add(
                'Give_Object',
                #DummyStateMachine(),
                move_hands_form(hand_pose_name='full_open', hand_side='right'),
                transitions={'succeeded':'succeeded', 'aborted':'aborted', 'preempted':'preempted'})













