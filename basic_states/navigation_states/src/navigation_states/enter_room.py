#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author: Cristina De Saint Germain
@email: crsaintc8@gmail.com
@author: Roger Boldu
@email: roger.boldu@gmail.com

22 Feb 2014

"""

import rospy
import smach
import math

from navigation_states.nav_to_coord import nav_to_coord
from navigation_states.nav_to_poi import nav_to_poi
from manipulation_states.play_motion_sm import play_motion_sm
from util_states.sleeper import Sleeper
from sensor_msgs.msg import LaserScan
from speech_states.say import text_to_say
from speed_limit.msg import DisableActionGoal
from odom_moving.srv import Straight, StraightRequest

 
class prepareData(smach.State):
    
    def __init__(self, poi_name):
        
        smach.State.__init__(self, outcomes=['succeeded','aborted', 'preempted'], 
                            input_keys=['nav_to_poi_name'], output_keys=['nav_to_poi_name'])
        self.poi_name = poi_name
        
    def execute(self, userdata):
           
        if not self.poi_name and not userdata.nav_to_poi_name:
            rospy.logerr("Poi_name isn't set")
            return 'aborted'
        
        #Priority in init
        userdata.nav_to_poi_name = self.poi_name if self.poi_name else userdata.nav_to_poi_name   
        
        return 'succeeded'

class pass_door(smach.State):
    
    def __init__(self):
        
        smach.State.__init__(self, outcomes=['succeeded','aborted', 'preempted'], 
                            input_keys=[], output_keys=[])
        self.publisher = rospy.Publisher('/speed_limit/disable/goal', DisableActionGoal)
        self.straight = rospy.ServiceProxy('/straight_nav', Straight)
        
    def execute(self, userdata):
                     
        # Deactivate the speed limit

        g = DisableActionGoal()
        g.goal.duration = 15.0
        self.publisher.publish(g)
        # Send goal to odom_nav

        self.straight.wait_for_service()
        sr = StraightRequest()
        sr.enable = True
        sr.meters = 2.0
        self.straight.call(sr)
        
        return 'succeeded'


class check_door_status(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'aborted', 'preempted', 'door_too_far'],
         output_keys=['standard_error','nav_to_coord_goal'])
        self.door_position = -1

    def execute(self, userdata):

        distance = 1.5
        
        WIDTH = 0.10  # Width in meters to look forward.
        READ_TIMEOUT = 15
        MAX_DIST_TO_DOOR = 3.0

        message = rospy.wait_for_message('/scan_filtered', LaserScan, 60)
        
        # Check the distance between the robot and the door
        length_ranges = len(message.ranges)
        alpha = math.atan((WIDTH/2)/distance)
        n_elem = int(math.ceil(length_ranges*alpha/(2*message.angle_max)))  # Num elements from the 0 angle to the left or right
        middle = length_ranges/2
        cut = [x for x in message.ranges[middle-n_elem:middle+n_elem] if x > 0.01]
        minimum = min(cut)
        if self.door_position == -1:
            if message.ranges[middle] <= MAX_DIST_TO_DOOR:
                self.door_position = message.ranges[middle]
            else:
                # We approach one meter to the door
                userdata.nav_to_coord_goal = [0.5, 0.0, 0.0]    
                return 'door_too_far'

        if (minimum >= distance+self.door_position):
            return 'succeeded'
        
        rospy.loginfo("Distance in front of the robot is too small: " + str(distance+self.door_position) + ". Minimum distance: " + str(minimum))
        userdata.standard_error = "get_current_robot_pose : Time_out getting /scan_filtered"
        return 'aborted'
                        

class EnterRoomSM(smach.StateMachine):
    """
    Executes a SM that enter a room. 
    Wait if the door isn't open and enter the room.

    Required parameters:
    No parameters.

    Optional parameters:
    No optional parameters

    Input keys:
        nav_to_poi_name: indicates the point we need to reach after detect that the door is open
    Output keys:
        standard_error: String that show what kind of error could be happened
    No io_keys.

    Nothing must be taken into account to use this SM.
    """

    def __init__(self, poi_name = None):
        smach.StateMachine.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                    input_keys=['nav_to_poi_name'],
                    output_keys=['standard_error'])

        with self:
            
            self.userdata.tts_text = None
            self.userdata.tts_wait_before_speaking = None
            self.userdata.tts_lang = None
            self.userdata.manip_motion_to_play = None
            self.userdata.manip_time_to_play = None
            self.userdata.skip_planning = False
        
            smach.StateMachine.add('PrepareData',
               prepareData(poi_name),
               transitions={'succeeded':'check_can_pass', 'aborted':'aborted'})
            
            # Check door state
            smach.StateMachine.add('check_can_pass',
                   check_door_status(),
                   transitions={'succeeded': 'home_position',
                                'aborted': 'say_open_door',
                                'door_too_far': 'say_too_far_from_door'})

            # Robot is too far from door
            smach.StateMachine.add(
                'say_too_far_from_door',
                text_to_say("I'm too far from the door."),
                transitions={'succeeded': 'approach_to_door', 'aborted': 'approach_to_door'})
                        
            # Approach to the door
            smach.StateMachine.add(
                'approach_to_door',
                nav_to_coord("/base_link"),
                transitions={'succeeded': 'check_can_pass', 'aborted': 'check_can_pass'})
                         
            # Robot ask to open the door
            smach.StateMachine.add(
                'say_open_door',
                text_to_say("Can anyone open the door please?"),
                transitions={'succeeded': 'sleep_state', 'aborted': 'sleep_state'})
            
            # Sleep time before speak
            smach.StateMachine.add(
                'sleep_state',
                Sleeper(5),
                transitions={'succeeded': 'check_can_pass', 'aborted': 'check_can_pass'})
            
            # Home position
            smach.StateMachine.add(
                'home_position',
                play_motion_sm('home'),
                transitions={'succeeded': 'say_enter_room', 'aborted': 'say_enter_room', 'preempted': 'succeeded'})
            
            # We don't need to prepare the state, it takes the input_key directly
            
            # Robot announces it is going through the door
            smach.StateMachine.add(
                'say_enter_room',
                text_to_say("I am going to enter the room"),
                transitions={'succeeded': 'pass_door', 'aborted': 'pass_door'})

            #We pass the door
            smach.StateMachine.add(
                'pass_door',
                pass_door(),
                transitions={'succeeded': 'enter_room', 'aborted': 'pass_door', 'preempted': 'preempted'})
            
            # Go to the poi in the other site of the door
            smach.StateMachine.add(
                'enter_room',
                nav_to_poi(),
                transitions={'succeeded': 'succeeded', 'aborted': 'enter_room', 'preempted': 'preempted'})

  

