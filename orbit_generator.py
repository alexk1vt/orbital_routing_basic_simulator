from skyfield.api import EarthSatellite, load, wgs84, N, S, E, W
from sgp4.api import Satrec, WGS72
#from sgp4.conveniences import dump_satrec
#import pandas as pd
import random
from datetime import date, timedelta
from math import pi, floor, sqrt
import math
import time
import os # for cpu_count()
import threading # for multithreading

# for plotting orbits
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import axes3d
from matplotlib.animation import FuncAnimation

# Options
draw_static_orbits = False
draw_distributed_orbits = False
testing = False
plot_dropped_packets = False
do_disruptions = True

# Multi threading
do_multithreading = True
num_threads = max(os.cpu_count()-2, 1) # 4

# Global counters
no_sat_overhead_cnt = 0
num_packets_dropped = 0
num_max_hop_packets_dropped = 0 # this is a subset of num_packets_dropped
num_route_calc_failures = 0
num_packets_sent = 0
num_packets_received = 0

# Global variables
orbit_list = []
sat_object_list = []
cur_time = 0
num_sats = 0
eph = None
packet_schedule = {} # a dictionary with time interval integers as keys and lists of packets as values - the list values are tuples of (src, dest)
disruption_schedule = {} # a dictionary with time interval integers as keys and lists of satellites or regions, along with time intervals, as values
# e.g. {0: [('sat', 443, 3), ('reg', GeographicPosition, 5), ('sat', 843, 1)]}
disrupted_regions_dict = {} # a dictionary with GeographicPosition objects as keys and TTL values as values

# Packet variables
packet_bandwidth_per_sec = 100 # the number of packets a satellite can send in a one sec time interval (so this should be multiplied by the time interval to get the number of packets that can be sent in that time interval)
packet_backlog_size = 1000 # the number of packets that can be stored in a satellite's queue (10 sec worth of data)
packet_start_TTL = 10 # the number of seconds a packet can be stored in a satellite's queue before it is dropped
packets_generated_per_interval = 20 # 100 # the number of packets generated per time interval by the packet scheduler

# Time variables
time_scale = load.timescale()
time_interval = 10 # interval between time increments, measured in seconds
secs_per_km = 0.0000033
num_time_intervals = 5
cur_time_increment = 0

# Orbit characteristics
# Starlink Shell 1:  https://everydayastronaut.com/starlink-group-6-1-falcon-9-block-5-2/
sats_per_orbit = 22
orbit_cnt = 72

# Adjacent satellite characterisitcs
g_lat_range = 1 # satellites to E/W can fall within +- this value
lateral_antenna_range = 30 #30

# Ground Station characteristics
req_elev = 40 # https://www.reddit.com/r/Starlink/comments/i1ua2y/comment/g006krb/?utm_source=share&utm_medium=web2x

# :: Routing Global Variables ::
routing_name = None

# Distributed routing admin values
distributed_max_hop_count = 50

# Link state admin values
interface_correct_range = lateral_antenna_range
interface_lateral_range = 180
interface_bandwidth_low_dist = 1000
interface_bandwidth_low_rate = 1
neigh_recent_down_time_window = time_interval * 2 # a neighbor has been down recently if it's less than two time intervals

# Link state distance metric values
interface_dir_correct = 1
interface_dir_lateral_plus = 2
interface_dir_lateral = 4
interface_dir_lateral_minus = 5
interface_dir_incorrect = 7
interface_bandwidth_high = 1
interface_bandwidth_middle = 2
interface_bandwidth_low = 4
neigh_congested = 4
neigh_neigh_congested = 3
neigh_neigh_link_down = 4
neigh_not_congested = 0
neigh_recently_down = 1
neigh_not_recently_down = 0

class RoutingSat:
    def __init__(self, _sat, _satnum, _orbit_number, _sat_index, _succeeding_orbit_number, _preceeding_orbit_number, _fore_sat_index, _aft_sat_index):
        self.sat = _sat
        self.satnum = _satnum
        self.orbit_number = _orbit_number
        self.sat_index = _sat_index
        self.succeeding_orbit_number = _succeeding_orbit_number
        self.preceeding_orbit_number = _preceeding_orbit_number
        self.fore_sat_satnum = _fore_sat_index
        self.aft_sat_satnum = _aft_sat_index
        self.port_sat_satnum = None
        self.starboard_sat_satnum = None
        #self.xmt_qu = []  # these are the send/receive queues - their contents depend on the routing algorithm being used
        #self.rcv_qu = []
        self.packet_qu = []
        self.packets_sent_cnt = 0 # the number of packets sent in the current time interval
        self.neigh_state_dict = {}  # key: satnum, value is link_state dictionary:
                                                                        # {Interface: ('fore'/'aft'/'port'/'starboard'),    - self setting
                                                                        #  neigh_up (True/False),         - self setting
                                                                        #  last_neigh_status: (time),     - neigh setting
                                                                        #  neigh_last_down:  (time),  - self setting
                                                                        #  link-congested: (True/False)} - neigh setting
        self.fore_int_up = True
        self.aft_int_up = True
        self.port_int_up = True
        self.starboard_int_up = True
        self.heading = None # ensure this is referenced only when you know it has been set for the current time
        self.congestion_cnt = 0
        self.is_disrupted = False
        self.disruption_ttl = 0

    # ::: distributed routing packet structure: [[prev_hop_list], distance_traveled, dest_gs, source_gs] - packet is at destination when satellite is above dest_gs
    def distributed_routing_link_state_process_packet_queue(self):
        if do_disruptions:
            if self.is_disrupted:
                print(f"::distributed_routing_link_state_process_packet_queue: satellite {self.satnum} is disrupted, so not processing packets")
                return -1 # don't process packets if the satellite is disrupted

        if (self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval) or (len(self.packet_qu) == 0):
            return -1
        sent_packet = False

        global num_packets_dropped
        global num_max_hop_packets_dropped
        for packet in self.packet_qu:
            if self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval:
                self.update_neigh_state(congestion = True) # tell neighbors of congestion on-demand (this will be cleared next time interval if packet count is low enough)
                self.congestion_cnt += 1
                break
            if self.is_overhead_of(packet['dest_gs']):
                topo_position = (self.sat - packet['dest_gs']).at(cur_time)
                _, _, dist = topo_position.altaz()
                packet['distance_traveled'] += dist.km
                print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet reached destination in {len(packet['prev_hop_list'])} hops.  Total distance: {int(packet['distance_traveled']):,.0f}km (transit time: {secs_per_km * int(packet['distance_traveled']):.2f} seconds)") # == source: {packet['source_gs']} -- destination: {packet['dest_gs']}")
                global num_packets_received
                num_packets_received += 1
                #if len(packet['prev_hop_list']) > 10:
                #    draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['source_gs'], packet['dest_gs']], title=f"Distributed link-state, {len(packet['prev_hop_list'])} hops, total distance: {int(packet['distance_traveled'])}km", draw_lines = True, draw_sphere = True)
                self.packet_qu.remove(packet)
                sent_packet = True
                self.packets_sent_cnt += 1
            elif len(packet['prev_hop_list']) > distributed_max_hop_count:
                print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet exceeded max hop count.  Dropping packet.")
                num_max_hop_packets_dropped += 1
                num_packets_dropped += 1
                if plot_dropped_packets:
                    draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['source_gs'], packet['dest_gs']], title=f"distributed link-state dropped packet - {len(packet['prev_hop_list'])} hops", draw_lines = True, draw_sphere = True)
                self.packet_qu.remove(packet)
            else:
                target_satnum = self.find_next_link_state_hop(packet['dest_gs'])
                if target_satnum is None:
                    print(f"::distributed_routing_link_state_process_packet_queue:: satellite {self.sat.model.satnum} - could not find next hop for packet.  Dropping packet.")
                    num_packets_dropped += 1
                    if plot_dropped_packets:
                        draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['dest_gs']], title='distributed link-state dropped packet', draw_lines = True, draw_sphere = False)
                    self.packet_qu.remove(packet)
                    continue
                #print(f"::distributed_routing_link_state_process_packet_queue:: satellite {self.sat.model.satnum} setting next hop to satnum: {target_satnum}")
                packet['prev_hop_list'].append(self.sat.model.satnum)
                target_distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, target_satnum)
                packet['distance_traveled'] += target_distance
                add_to_packet_qu_by_satnum(target_satnum, packet)  # add packet to target sat's packet queue
                self.packet_qu.remove(packet)
                sent_packet = True
                self.packets_sent_cnt += 1                
        if sent_packet:
            return 0
        else:
            return -1

    # ::: directed routing packet structure: [dest_satnum, [next_hop_list], [prev_hop_list], distance_traveled, dest_gs] - packet is at destination when dest_satnum matches current_satnum and next_hop_list is empty
    def directed_routing_process_packet_queue(self):
        global no_sat_overhead_cnt
        global num_packets_dropped
        global num_packets_received
        global num_route_calc_failures

        if do_disruptions:
            if self.is_disrupted:
                print(f"::directed_routing_process_packet_queue: satellite {self.satnum} is disrupted, so not processing packets")
                return -1 # don't process packets if satellite is disrupted

        if (self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval) or (len(self.packet_qu) == 0):
            return -1
        sent_packet = False
        # Identify which neighbor sats are available on each interface
        self.port_sat_satnum = None
        self.starboard_sat_satnum = None
        preceeding_orbit_satnum, preceeding_orbit_int = self.check_preceeding_orbit_sat_available()
        succeeding_orbit_satnum, succeeding_orbit_int = self.check_succeeding_orbit_sat_available()
        if not preceeding_orbit_satnum is None:
            if preceeding_orbit_int == 'port':
                self.port_sat_satnum = preceeding_orbit_satnum
            else:
                self.starboard_sat_satnum = preceeding_orbit_satnum
        if not succeeding_orbit_satnum is None:
            if succeeding_orbit_int == 'port':
                self.port_sat_satnum = succeeding_orbit_satnum
            else:
                self.starboard_sat_satnum = succeeding_orbit_satnum
        # process packets in queue
        for packet in self.packet_qu:
            if self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval:
                break
            if self.sat.model.satnum  == packet['dest_satnum']:
                if not self.is_overhead_of(packet['dest_gs']):
                    print(f"Reached final satnum, but not overhead destination terminal!")
                    no_sat_overhead_cnt += 1
                    num_packets_dropped += 1
                    self.packet_qu.remove(packet)
                    continue
                topo_position = (self.sat - packet['dest_gs']).at(cur_time)
                alt, _, dist = topo_position.altaz()
                if alt.degrees < req_elev:
                    print(f"Satellite {self.sat.model.satnum} is not {req_elev}deg overhead destination terminal")
                    no_sat_overhead_cnt += 1
                    num_packets_dropped += 1
                    self.packet_qu.remove(packet)
                    continue
                packet['distance_traveled'] += dist.km
                print(f"{self.sat.model.satnum}: Packet reached destination in {len(packet['prev_hop_list'])} hops.  Total distance: {packet['distance_traveled']:,.0f}km (transit time: {secs_per_km * int(packet['distance_traveled']):.2f} seconds)")
                num_packets_received += 1
                self.packet_qu.remove(packet)
                sent_packet = True
                self.packets_sent_cnt += 1
            else:
                target_satnum = packet['next_hop_list'].pop() #the head of the next_hop_list
                #print(f"::directed_routing_rcv_cycle:: satellite {self.sat.model.satnum}, target_satnum: {target_satnum}, next hop list: {packet['next_hop_list']}")
                if (self.fore_sat_satnum == target_satnum) or (self.aft_sat_satnum == target_satnum) or (self.port_sat_satnum == target_satnum) or (self.starboard_sat_satnum == target_satnum):
                    packet['prev_hop_list'].append(self.sat.model.satnum)
                    target_distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, target_satnum)
                    packet['distance_traveled'] += target_distance
                    add_to_packet_qu_by_satnum(target_satnum, packet)  # add packet to target sat's packet queue
                    self.packet_qu.remove(packet)
                    sent_packet = True
                    self.packets_sent_cnt += 1
                else:
                    print(f"({self.sat.model.satnum})No connection to satnum {target_satnum}")
                    self.packet_qu.remove(packet)
                    num_route_calc_failures += 1
        if sent_packet:
            return 0
        else:
            return -1

    def get_curr_geocentric(self):
        return self.sat.at(cur_time)

    def get_sat_lat_degrees(self):
        lat, _ = wgs84.latlon_of(self.sat.at(cur_time))
        return lat.degrees
        
    def get_sat_lon_degrees(self):
        _, lon = wgs84.latlon_of(self.sat.at(cur_time))
        return lon.degrees
    
    def get_sat_lat_lon_degrees(self):
        lat, lon = wgs84.latlon_of(self.sat.at(cur_time))
        return lat.degrees, lon.degrees
    
    def is_East_of(self, dest):
        sat_geoc = self.sat.at(cur_time)
        _, sat_lon = wgs84.latlon_of(sat_geoc)
        dest_geoc = dest.at(cur_time)
        _, dest_lon = wgs84.latlon_of(dest_geoc)
        return sat_lon.degrees > dest_lon.degrees

    def is_North_of(self, dest):
        sat_geoc = self.sat.at(cur_time)
        sat_lat, _ = wgs84.latlon_of(sat_geoc)
        dest_geoc = dest.at(cur_time)
        dest_lat, _ = wgs84.latlon_of(dest_geoc)
        return sat_lat.degrees > dest_lat.degrees  ### NOTE:  I don't this this is true for things in the Southern Hemisphere!!!??

    def is_overhead_of(self, dest):
        topo_pos = (self.sat - dest).at(cur_time)
        elev, _, _ = topo_pos.altaz()
        if elev.degrees > req_elev:
            return True
        return False
    
    def check_preceeding_orbit_sat_available(self): # returns satnum if sat is within range (None otherwise).  If satnum is other than None, interface will indicate which ('port'/'starboard')
        heading = get_heading_by_satnum_degrees(self.sat.model.satnum)
        port_bearing = 270
        starboard_bearing = 90
        port_range_min = port_bearing-int(lateral_antenna_range/2)
        port_range_max = port_bearing+int(lateral_antenna_range/2)
        starboard_range_min = starboard_bearing-int(lateral_antenna_range/2)
        starboard_range_max = starboard_bearing+int(lateral_antenna_range/2)
        min_satnum = self.preceeding_orbit_number * sats_per_orbit
        max_satnum = min_satnum + sats_per_orbit

        tentative_satnum_list = []
        for test_satnum in range(min_satnum, max_satnum):
            test_sat_bearing = get_rel_bearing_by_satnum_degrees(self.sat.model.satnum, test_satnum, heading)
            distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, test_satnum)
            if distance > 1000:
                continue  # Don't try to connect to lateral satellites with distances > 1000km - seems like an unreasonable ability 
            if (port_range_min < test_sat_bearing) and (test_sat_bearing < port_range_max):
                tentative_satnum_list.append((test_satnum, 'port'))
            elif (starboard_range_min < test_sat_bearing) and (test_sat_bearing < starboard_range_max):
                tentative_satnum_list.append((test_satnum, 'starboard'))
        if len(tentative_satnum_list) == 0:
            satnum = None
            interface = None
        elif len(tentative_satnum_list) == 1:
            satnum = tentative_satnum_list[0][0]
            interface = tentative_satnum_list[0][1]
        else:
            closest_satnum = None
            min_distance = float('inf') # Initialize minimum distance to infinity
            cur_routing_sat = get_routing_sat_obj_by_satnum(self.sat.model.satnum)
            #print(f"Found {len(tentative_satnum_list)} sats in preceeding orbit")
            for test_satnum_int in tentative_satnum_list:
                test_satnum, test_int = test_satnum_int
                test_routing_sat = get_routing_sat_obj_by_satnum(test_satnum)
                # Calculate the straight-line distance between the input satellite and each satellite in the list
                sat_diff = cur_routing_sat.sat.at(cur_time) - test_routing_sat.sat.at(cur_time)
                # Update the closest satellite and minimum distance if a new minimum is found
                if sat_diff.distance().km < min_distance:
                    closest_satnum = test_routing_sat.sat.model.satnum
                    closest_int = test_int
                    min_distance = sat_diff.distance().km
            satnum = closest_satnum
            interface = closest_int
        return satnum, interface

    def check_succeeding_orbit_sat_available(self): # returns satnum if sat is within range (None otherwise).  If satnum is other than None, interface will indicate which ('port'/'starboard')
        heading = get_heading_by_satnum_degrees(self.sat.model.satnum)
        port_bearing = 270
        starboard_bearing = 90
        port_range_min = port_bearing-int(lateral_antenna_range/2)
        port_range_max = port_bearing+int(lateral_antenna_range/2)
        starboard_range_min = starboard_bearing-int(lateral_antenna_range/2)
        starboard_range_max = starboard_bearing+int(lateral_antenna_range/2)
        min_satnum = self.succeeding_orbit_number * sats_per_orbit
        max_satnum = min_satnum + sats_per_orbit

        tentative_satnum_list = []
        for test_satnum in range(min_satnum, max_satnum):
            test_sat_bearing = get_rel_bearing_by_satnum_degrees(self.sat.model.satnum, test_satnum, heading)
            distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, test_satnum)
            if distance > 1000:
                continue  # Don't try to connect to lateral satellites with distances > 1000km - seems like an unreasonable ability
            if (port_range_min < test_sat_bearing) and (test_sat_bearing < port_range_max):
                tentative_satnum_list.append((test_satnum, 'port'))
            elif (starboard_range_min < test_sat_bearing) and (test_sat_bearing < starboard_range_max):
                tentative_satnum_list.append((test_satnum, 'starboard'))
        if len(tentative_satnum_list) == 0:
            satnum = None
            interface = None
        elif len(tentative_satnum_list) == 1:
            satnum = tentative_satnum_list[0][0]
            interface = tentative_satnum_list[0][1]
        else:
            closest_satnum = None
            min_distance = float('inf') # Initialize minimum distance to infinity
            cur_routing_sat = get_routing_sat_obj_by_satnum(self.sat.model.satnum)
            #print(f"Found {len(tentative_satnum_list)} sats in succeeding orbit")
            for test_satnum_int in tentative_satnum_list:
                test_satnum, test_int = test_satnum_int
                test_routing_sat = get_routing_sat_obj_by_satnum(test_satnum)
                # Calculate the straight-line distance between the input satellite and each satellite in the list
                sat_diff = cur_routing_sat.sat.at(cur_time) - test_routing_sat.sat.at(cur_time)
                # Update the closest satellite and minimum distance if a new minimum is found
                if sat_diff.distance().km < min_distance:
                    closest_satnum = test_routing_sat.sat.model.satnum
                    closest_int = test_int
                    min_distance = sat_diff.distance().km
            satnum = closest_satnum
            interface = closest_int
        return satnum, interface

    def check_succeeding_orbit(self):
        pass

    def get_sat_East(self, lat_range = g_lat_range):
        #range of satnums for target orbit
        min_satnum = self.succeeding_orbit_number * sats_per_orbit
        max_satnum = min_satnum + sats_per_orbit
        cur_lat = self.get_sat_lat_degrees()

        routing_sat_list = []
        for routing_sat_obj in sat_object_list[min_satnum:max_satnum]:
            sat_lat = routing_sat_obj.get_sat_lat_degrees()
            if ((cur_lat - lat_range) < sat_lat) and (sat_lat < (cur_lat + lat_range)):
                routing_sat_list.append(routing_sat_obj)
        if len(routing_sat_list) == 0:
            print('No East adjacent satellite found')
            closest_sat_East = None
        elif len(routing_sat_list) > 1:
            ## find closest satellites
            #print(f"{len(routing_sat_list)} satellites found within latitude range, selecting closest")
            closest_sat_East = find_closest_routing_satellite(self, routing_sat_list)
        else:
            #print("Single Eastern satellite found")
            closest_sat_East = routing_sat_list[0]
            
        return closest_sat_East

    def get_sat_West(self, lat_range = g_lat_range):
        #range of satnums for target orbit
        min_satnum = self.preceeding_orbit_number * sats_per_orbit
        max_satnum = min_satnum + sats_per_orbit
        cur_lat = self.get_sat_lat_degrees()

        routing_sat_list = []
        for routing_sat_obj in sat_object_list[min_satnum:max_satnum]:
            sat_lat = routing_sat_obj.get_sat_lat_degrees()
            if ((cur_lat - lat_range) < sat_lat) and (sat_lat < (cur_lat + lat_range)):
                routing_sat_list.append(routing_sat_obj)
        if len(routing_sat_list) == 0:
            print('No West adjacent satellite found')
            closest_sat_West = None
        elif len(routing_sat_list) > 1:
            ## find closest satellites
            #print(f"{len(routing_sat_list)} satellites found within latitude range, selecting closest")
            closest_sat_West = find_closest_routing_satellite(self, routing_sat_list)
        else:
            #print("Single Western satellite found")
            closest_sat_West = routing_sat_list[0]
            
        return closest_sat_West

    def get_sat_North(self):
        first_target_satnum = self.satnum - 1
        second_target_satnum = self.satnum + 1
        first_target_orbit_number = floor(first_target_satnum / sats_per_orbit)
        second_target_orbit_number = floor(second_target_satnum / sats_per_orbit)
        if first_target_orbit_number != self.orbit_number:
            first_target_satnum = (self.orbit_number * sats_per_orbit) + (first_target_satnum % sats_per_orbit)
        if second_target_orbit_number != self.orbit_number:
            second_target_satnum = (self.orbit_number * sats_per_orbit) + (second_target_orbit_number % sats_per_orbit)
        self_lat, _ = wgs84.latlon_of(self.sat.at(cur_time))
        first_target_routing_sat = get_routing_sat_obj_by_satnum(first_target_satnum)
        first_target_lat, _ = wgs84.latlon_of(first_target_routing_sat.sat.at(cur_time))
        second_target_routing_sat = get_routing_sat_obj_by_satnum(second_target_satnum)
        second_target_lat, _ = wgs84.latlon_of(second_target_routing_sat.sat.at(cur_time))
        if first_target_lat.degrees > second_target_lat.degrees:  # test which satellite is Northernmost
            target_satnum = first_target_satnum
            target_lat = first_target_lat
        else:
            target_satnum = second_target_satnum
            target_lat = second_target_lat
        if target_lat.degrees < self_lat.degrees:

            return None
        return sat_object_list[target_satnum]

    def get_fore_sat(self):
        return sat_object_list[self.fore_sat_satnum] # fore satellite never changes
    
    def get_aft_sat(self):
        return sat_object_list[self.aft_sat_satnum] # aft satellite never changes

    def get_sat_South(self):
        first_target_satnum = self.satnum - 1
        second_target_satnum = self.satnum + 1
        first_target_orbit_number = floor(first_target_satnum / sats_per_orbit)
        second_target_orbit_number = floor(second_target_satnum / sats_per_orbit)
        if first_target_orbit_number != self.orbit_number:
            first_target_satnum = (self.orbit_number * sats_per_orbit) + (first_target_satnum % sats_per_orbit)
        if second_target_orbit_number != self.orbit_number:
            second_target_satnum = (self.orbit_number * sats_per_orbit) + (second_target_orbit_number % sats_per_orbit)
        self_lat, _ = wgs84.latlon_of(self.sat.at(cur_time))
        first_target_routing_sat = get_routing_sat_obj_by_satnum(first_target_satnum)
        first_target_lat, _ = wgs84.latlon_of(first_target_routing_sat.sat.at(cur_time))
        second_target_routing_sat = get_routing_sat_obj_by_satnum(second_target_satnum)
        second_target_lat, _ = wgs84.latlon_of(second_target_routing_sat.sat.at(cur_time))
        if first_target_lat.degrees < second_target_lat.degrees:  # test which satellite is Southernmost
            target_satnum = first_target_satnum
            target_lat = first_target_lat
        else:
            target_satnum = second_target_satnum
            target_lat = second_target_lat
        if target_lat.degrees > self_lat.degrees:
            return None
        return sat_object_list[target_satnum]
    
    def find_cur_pos_diff(self, route_sat2):
        sat1_vec = self.sat.at(cur_time)
        sat2_vec = route_sat2.sat.at(cur_time)
        sat_diff_vec = sat2_vec - sat1_vec
        print(f'Satellite difference vector position: {sat_diff_vec.position}; velocity: {sat_diff_vec.velocity}')

    def find_cur_pos_diff_spherical(self, route_sat2):
        global eph
        if eph == None:
            eph = load('de421.bsp')
        earth = eph['earth']
        self_pos = earth.at(cur_time).observe(self.sat)
        sat2_pos = earth.at(cur_time).observe(route_sat2.sat)
        self_ra, self_dec, self_distance = self_pos.radec()
        sat2_ra, sat2_dec, sat2_distance = sat2_pos.radec()
        print(f"Spherical position of self_sat:\n\tright ascension: {self_ra}\n\tdeclination: {self_dec}\n\tdistance: {self_distance}")
        print(f"Spherical position of sat2:\n\tright ascension: {sat2_ra}\n\tdeclination: {sat2_dec}\n\tdistance: {sat2_distance}")
        pos_diff = sat2_pos - self_pos
        diff_ra, diff_dec, diff_distance = pos_diff.radec()
        print(f"\nSpherical position difference of self_sat and sat2:\n\tright ascension: {diff_ra}\n\tdeclination: {diff_dec}\n\tdistance:{diff_distance}")

    # returns satnum of next hop satellite, or None if no next hop satellite is available
    def find_next_link_state_hop(self, dest_gs): 
        # first find which sats, if any, are on each interface
        self.port_sat_satnum = None
        self.starboard_sat_satnum = None
        preceeding_orbit_satnum, preceeding_orbit_int = self.check_preceeding_orbit_sat_available()
        succeeding_orbit_satnum, succeeding_orbit_int = self.check_succeeding_orbit_sat_available()
        if not preceeding_orbit_satnum is None:
            if preceeding_orbit_int == 'port':
                self.port_sat_satnum = preceeding_orbit_satnum
            else:
                self.starboard_sat_satnum = preceeding_orbit_satnum
        if not succeeding_orbit_satnum is None:
            if succeeding_orbit_int == 'port':
                self.port_sat_satnum = succeeding_orbit_satnum
            else:
                self.starboard_sat_satnum = succeeding_orbit_satnum
        avail_neigh_routing_sats = []
        if self.fore_int_up:
            avail_neigh_routing_sats.append(sat_object_list[self.fore_sat_satnum])
        if self.aft_int_up:
            avail_neigh_routing_sats.append(sat_object_list[self.aft_sat_satnum])
        if self.port_int_up and (not self.port_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.port_sat_satnum])
        if self.starboard_int_up and (not self.starboard_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.starboard_sat_satnum])

        # now find which of the available neighbor routing sats is closest to the destination gs
        self.heading = get_heading_by_satnum_degrees(self.sat.model.satnum)
        nearest_dist_metric = float('inf')
        nearest_neigh_routing_sat = None
        for neigh_routing_sat in avail_neigh_routing_sats:
            dist_metric = self.calc_link_state_dist_metric(neigh_routing_sat, dest_gs)
            if dist_metric < nearest_dist_metric:
                nearest_dist_metric = dist_metric
                nearest_neigh_routing_sat = neigh_routing_sat
        if nearest_neigh_routing_sat is None:
            print("find_next_link_state_hop:  No next hop sat could be calculated")
            return None
        return nearest_neigh_routing_sat.sat.model.satnum

    # calculate the distance metric for link state routing protocol    
    # using: destination bearing, satellite bandwidth, whether congested, and whether recently down
    def calc_link_state_dist_metric(self, neigh_routing_sat, dest_gs, bearing_only = False):
        # first check if neighbor routing sat is in neighbor state dict
        if not neigh_routing_sat.sat.model.satnum in self.neigh_state_dict:
            return 0
        # now find bearing of destination gs
        dest_bearing = self.get_rel_bearing_to_dest_gs(dest_gs)
        # assign values to each interface based on dest_bearing
        neigh_sat_interface = self.neigh_state_dict[neigh_routing_sat.sat.model.satnum]['interface_name']
        if neigh_sat_interface == 'fore':
            neigh_sat_interface_bearing = 0
        elif neigh_sat_interface == 'aft':
            neigh_sat_interface_bearing = 180
        elif neigh_sat_interface == 'port':
            neigh_sat_interface_bearing = 270
        elif neigh_sat_interface == 'starboard':
            neigh_sat_interface_bearing = 90
        else:
            print(f"Neighbor sat interface: {neigh_sat_interface} not recognized, aborting")
            exit()
        # calculate distance metric for neighbor satellite bearing
        interface_correct_lower_range = (neigh_sat_interface_bearing - (interface_correct_range/2) + 360) % 360
        interface_correct_upper_range = (neigh_sat_interface_bearing + (interface_correct_range/2) + 360) % 360
        interface_lateral_plus_lower_range = (neigh_sat_interface_bearing - (interface_lateral_range/4) + 360) % 360
        interface_lateral_plus_upper_range = (neigh_sat_interface_bearing + (interface_lateral_range/4) + 360) % 360
        interface_lateral_lower_range = (neigh_sat_interface_bearing - (interface_lateral_range/2) + 360) % 360
        interface_lateral_upper_range = (neigh_sat_interface_bearing + (interface_lateral_range/2) + 360) % 360
        interface_lateral_minus_lower_range = (neigh_sat_interface_bearing - (interface_lateral_range/1.5) + 360) % 360
        interface_lateral_minus_upper_range = (neigh_sat_interface_bearing + (interface_lateral_range/1.5) + 360) % 360
        if (dest_bearing - interface_correct_lower_range) %360 <= (interface_correct_upper_range - interface_correct_lower_range) % 360:
            bearing_metric = interface_dir_correct
        elif (dest_bearing - interface_lateral_plus_lower_range) %360 <= (interface_lateral_plus_upper_range - interface_lateral_plus_lower_range) % 360:
            bearing_metric = interface_dir_lateral_plus
        elif (dest_bearing - interface_lateral_lower_range) %360 <= (interface_lateral_upper_range - interface_lateral_lower_range) % 360:
            bearing_metric = interface_dir_lateral
        elif (dest_bearing - interface_lateral_minus_lower_range) %360 <= (interface_lateral_minus_upper_range - interface_lateral_minus_lower_range) % 360:
            bearing_metric = interface_dir_lateral_minus
        else:
            bearing_metric = interface_dir_incorrect
        
        if bearing_only:
            return bearing_metric
        
        # calculate distance metric for neighbor satellite bandwidth based on which interface it is
        # if neighbor sat is for/aft, it has good bandwidth
        if (neigh_sat_interface == 'fore') or (neigh_sat_interface == 'aft'):
            bandwidth_metric = interface_bandwidth_high 
        else:
            # assign value to neigh based on distance and rate (bandwidth)
            neigh_dist, neigh_rate = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, neigh_routing_sat.sat.model.satnum)
            if (neigh_dist > interface_bandwidth_low_dist) or (neigh_rate > interface_bandwidth_low_rate):
                bandwidth_metric = interface_bandwidth_low
            else:
                bandwidth_metric = interface_bandwidth_middle
        
        # calculate distance metric for neighbor congestion
        if self.neigh_state_dict[neigh_routing_sat.sat.model.satnum]['is_congested']:
            congestion_metric = neigh_congested
        else:
            congestion_metric = neigh_not_congested

        # calculate distance metric for neighbor sat recently down
        neigh_last_down = self.neigh_state_dict[neigh_routing_sat.sat.model.satnum]['connection_last_down']
        if neigh_last_down is None:
            recent_down_metric = neigh_not_recently_down
        else:
            neigh_last_down_datetime = neigh_last_down.utc_datetime()
            cur_time_datetime = cur_time.utc_datetime()
            datetime_delta = cur_time_datetime - neigh_last_down_datetime
            if datetime_delta.total_seconds() < neigh_recent_down_time_window:  # compare number of seconds since coming up against global 'neigh_recent_down_time_window' (calcuated in seconds)
                recent_down_metric = neigh_not_recently_down
            else:
                recent_down_metric = neigh_recently_down
        
        # calculate distance metric for neighbor with a neighbor connection down
        neigh_neigh_connection_down = self.neigh_state_dict[neigh_routing_sat.sat.model.satnum]['has_neigh_connection_down']
        if neigh_neigh_connection_down:
            neigh_neigh_connection_down_metric = neigh_neigh_link_down
        else:
            neigh_neigh_connection_down_metric = 0

        # calculate distance metric for neighbor with a neighbor connection congested
        neigh_neigh_connection_congested = self.neigh_state_dict[neigh_routing_sat.sat.model.satnum]['has_neigh_congested']
        if neigh_neigh_connection_congested:
            neigh_neigh_connection_congested_metric = neigh_neigh_congested
        else:
            neigh_neigh_connection_congested_metric = 0

        # now add up all the values for the overall distance metric and return
        distance_metric = bearing_metric + bandwidth_metric + congestion_metric + recent_down_metric + neigh_neigh_connection_down_metric + neigh_neigh_connection_congested_metric
        return distance_metric

    # find the bearing of the destination ground station relative to the current satellite
    # must have calculated current satellite heading prior to calling this function
    def get_rel_bearing_to_dest_gs(self, dest_gs):
        cur_sat_lat, cur_sat_lon = wgs84.latlon_of(self.sat.at(cur_time))
        dest_lat, dest_lon = wgs84.latlon_of(dest_gs.at(cur_time))
        
        cur_sat_lat_rad = math.radians(cur_sat_lat.degrees)
        cur_sat_lon_rad = math.radians(cur_sat_lon.degrees)
        dest_lat_rad = math.radians(dest_lat.degrees)
        dest_lon_rad = math.radians(dest_lon.degrees)
        bearing = math.atan2(
            math.sin(dest_lon_rad - cur_sat_lon_rad) * math.cos(dest_lat_rad),
            math.cos(cur_sat_lat_rad) * math.sin(dest_lat_rad) - math.sin(cur_sat_lat_rad) * math.cos(dest_lat_rad) * math.cos(dest_lon_rad - cur_sat_lon_rad)
        )
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360

        rel_bearing = bearing - self.heading
        rel_bearing = (rel_bearing + 360) % 360

        return rel_bearing
    
    def find_port_starboard_neighbors(self):
        self.port_sat_satnum = None
        self.starboard_sat_satnum = None
        preceeding_orbit_satnum, preceeding_orbit_int = self.check_preceeding_orbit_sat_available()
        succeeding_orbit_satnum, succeeding_orbit_int = self.check_succeeding_orbit_sat_available()
        if not preceeding_orbit_satnum is None:
            if preceeding_orbit_int == 'port':
                self.port_sat_satnum = preceeding_orbit_satnum
            else:
                self.starboard_sat_satnum = preceeding_orbit_satnum
        if not succeeding_orbit_satnum is None:
            if succeeding_orbit_int == 'port':
                self.port_sat_satnum = succeeding_orbit_satnum
            else:
                self.starboard_sat_satnum = succeeding_orbit_satnum

    # update the state of links to all direct neighbor sats
    def update_state_to_neighbors(self, congestion = None):
        if do_disruptions:
            if self.is_disrupted:  # if this sat is disrupted, don't update state to neighbors
                print(f"::update_state_to_neighbors:: sat {self.sat.model.satnum} is disrupted, not updating state to neighbors")
                return

        # find which, if any, sats are port/starboard neighbors
        self.find_port_starboard_neighbors()
        
        # build list of neighbor sats to update
        neigh_routing_sat_list = []
        if self.fore_int_up:
            neigh_routing_sat_list.append(sat_object_list[self.fore_sat_satnum])
        if self.aft_int_up:
            neigh_routing_sat_list.append(sat_object_list[self.aft_sat_satnum])
        if self.port_int_up and (not self.port_sat_satnum is None):
            neigh_routing_sat_list.append(sat_object_list[self.port_sat_satnum])
        if self.starboard_int_up and (not self.starboard_sat_satnum is None):
            neigh_routing_sat_list.append(sat_object_list[self.starboard_sat_satnum])
        # check if satellite is congested - should this be based on _link congestion_ rather than satellite congestion?
        if congestion is None:
            if len(self.packet_qu) > int((packet_bandwidth_per_sec * time_interval) * .8):  # are we at 80% of our packet queue capacity?
                congestion_status = True
            else:
                congestion_status = False
        else:
            congestion_status = congestion
        # update link state for all available neighbors
        neigh_congested, neigh_connection_down = self.check_internal_link_status()
        for neigh_routing_sat in neigh_routing_sat_list:
            if (neigh_routing_sat.sat.model.satnum == self.fore_sat_satnum):  # designate the interface this satellite is on (note - neighbor satellite interface is the opposite of the current satellite interface [ie, port int talks to starboard int, etc...])
                    interface = 'aft'
            elif (neigh_routing_sat.sat.model.satnum == self.aft_sat_satnum):
                    interface = 'fore'
            elif (neigh_routing_sat.sat.model.satnum == self.port_sat_satnum):
                    interface = 'starboard'
            else:
                    interface = 'port'
            if not self.sat.model.satnum in neigh_routing_sat.neigh_state_dict:  
                # first entry into this neigh_state_dict, so initialize all the link state variables for this sat
                neigh_routing_sat.neigh_state_dict[self.sat.model.satnum] = {'interface_name': interface, 'connection_up': True, 'last_recv_status': cur_time, 'connection_last_down': None, 'is_congested': congestion_status, 'has_neigh_connection_down' : neigh_connection_down, 'has_neigh_congested' : neigh_congested}
            else:  # prev entry exists, so update relavent values
                neigh_routing_sat.neigh_state_dict[self.sat.model.satnum]['interface_name'] = interface # really only needed for port/starboard, but test and check is probably slower than just setting
                neigh_routing_sat.neigh_state_dict[self.sat.model.satnum]['last_recv_status'] = cur_time
                neigh_routing_sat.neigh_state_dict[self.sat.model.satnum]['is_congested'] = congestion_status
                neigh_routing_sat.neigh_state_dict[self.sat.model.satnum]['has_neigh_connection_down'] = neigh_connection_down
                neigh_routing_sat.neigh_state_dict[self.sat.model.satnum]['has_neigh_congested'] = neigh_congested 

    def update_neigh_state_table(self):
        if do_disruptions:
            if self.is_disrupted: # if this sat is disrupted, don't update internal link status
                print(f"::update_neigh_state_table:: sat {self.sat.model.satnum} is disrupted, so not updating internal link status")
                return
        print(f"r_sat.sat.model.satnum: {self.sat.model.satnum}", end="\r")
        for satnum in self.neigh_state_dict:
            last_neigh_status = self.neigh_state_dict[satnum]['last_recv_status']
            if last_neigh_status != cur_time:
                self.neigh_state_dict[satnum]['connection_up'] = False
            else:
                old_link_status = self.neigh_state_dict[satnum]['connection_up']
                self.neigh_state_dict[satnum]['connection_up'] = True
                if old_link_status == False:
                    self.neigh_state_dict[satnum]['connection_last_down'] = cur_time

    # indicates if any connections to current neighbors are either down or congested
    # returns niegh_congested, neigh_connection_down
    def check_internal_link_status(self):
        neigh_congested = False
        neigh_connection_down = False
        for neigh_sat in self.neigh_state_dict:
            if self.neigh_state_dict[neigh_sat]['is_congested']:
                neigh_congested = True
            if self.neigh_state_dict[neigh_sat]['connection_up'] == False:
                neigh_connection_down = True
        return neigh_congested, neigh_connection_down

# End Routing sat class

## :: General Functions ::
# satellite updates it's internal neigh link states and sends updates to own neighbors
# self.neigh_state_dict-  key: satnum, value is link_state dictionary:
                                        # {interface: ('fore'/'aft'/'port'/'starboard'), - self setting
                                        #  neigh_up (True/False),         - self setting
                                        #  last_neigh_status: (time),     - neigh setting
                                        #  neigh_last_down:  (time),  - self setting
                                        #  neigh_congested: (True/False)} - neigh setting

# multi-threaded version of update_state_to_neighbors()
def mt_update_state_to_neighbors(thread_num):
    sat_object_range = floor(len(sat_object_list) / num_threads)
    start = thread_num * sat_object_range
    end = start + sat_object_range
    if thread_num == num_threads - 1:
        end = len(sat_object_list)
    print(f"::mt_update_neigh_state() :: thread {thread_num} : publishing states to neighbors from {start} to {end}", end='\r')
    for r_sat in sat_object_list[start:end]:
        r_sat.update_state_to_neighbors()
    print(f"::mt_update_neigh_state() :: thread {thread_num} : finished publishing states to neighbors", end='\r')

def mt_update_neigh_state_table(thread_num):
    sat_object_range = floor(len(sat_object_list) / num_threads)
    start = thread_num * sat_object_range
    end = start + sat_object_range
    if thread_num == num_threads - 1:
        end = len(sat_object_list)
    print(f"::mt_update_neigh_state_table() :: thread {thread_num} : updating internal states of neighbors from {start} to {end}", end='\r')
    for r_sat in sat_object_list[start:end]:
        r_sat.update_neigh_state_table()
    print(f"::mt_update_neigh_state_table() :: thread {thread_num} : finished updating internal neighbor state table", end='\r')
"""
def mt_update_neigh_state(thread_num):
    sat_object_range = floor(len(sat_object_list) / num_threads)
    start = thread_num * sat_object_range
    end = start + sat_object_range
    if thread_num == num_threads - 1:
        end = len(sat_object_list)
    print(f"::mt_update_neigh_state_table() :: thread {thread_num} : updating internal states of neighbors from {start} to {end}", end='\r')
    for r_sat in sat_object_list[start:end]:
        r_sat.update_neigh_state()
"""
def all_sats_update_neigh_state():
    print("::all_sats_update_neigh_state() :: publishing states to neighbors")
    # publish link state to neighbors first!
    if do_multithreading:
        thread_list = []
        for index in range(num_threads):
            thread = threading.Thread(target=mt_update_state_to_neighbors, args=(index,))
            thread.start()
            thread_list.append(thread)
        for thread in thread_list:
            thread.join()
    else:
        for r_sat in sat_object_list:
            print(f"r_sat.sat.model.satnum: {r_sat.sat.model.satnum}", end="\r")
            r_sat.update_state_to_neighbors() 
    print("\n::all_sats_update_neigh_state() :: updating internal states of neighbors")

    # now update those link states internally
    if do_multithreading:
        thread_list = []
        for index in range(num_threads):
            thread = threading.Thread(target=mt_update_neigh_state_table, args=(index,))
            thread.start()
            thread_list.append(thread)
        for thread in thread_list:
            thread.join()
    else:
        for r_sat in sat_object_list:
            r_sat.update_neigh_state_table()
        print("\n")

def add_to_packet_qu_by_satnum(target_satnum, packet):
    target_routing_sat = sat_object_list[target_satnum]
    if len(target_routing_sat.packet_qu) > packet_backlog_size:
        print(f"Packet queue for satnum {target_satnum} is full. Packet dropped.")
        global num_packets_dropped
        num_packets_dropped += 1
        return
    target_routing_sat.packet_qu.insert(0, packet)

def get_routing_sat_obj_by_satnum(satnum):
    if len(sat_object_list) < 1:
        return None
    for routing_sat_obj in sat_object_list:
        if routing_sat_obj.sat.model.satnum == satnum:
            return routing_sat_obj
    print(f'::get_routing_sat_obj_by_satnum:: ERROR - No satellite found for satnum: {satnum} - number of satellites: {len(sat_object_list)}')
    return None

def find_closest_satnum_to_terminal(GeoPos):
    curr_geocentric = GeoPos.at(cur_time)
    closest_satnum = None
    min_distance = float('inf') # Initialize minimum distance to infinity
    for r_s in sat_object_list:
        sat_diff = curr_geocentric - r_s.sat.at(cur_time)
        if sat_diff.distance().km < min_distance:
            closest_satnum = r_s.sat.model.satnum
            min_distance = sat_diff.distance().km
    return closest_satnum

def find_closest_routing_satellite(cur_routing_sat, routing_sat_list):
    closest_routing_sat = None
    min_distance = float('inf') # Initialize minimum distance to infinity
    
    for r_s in routing_sat_list:
        # Calculate the straight-line distance between the input satellite and each satellite in the list
        sat_diff = cur_routing_sat.sat.at(cur_time) - r_s.sat.at(cur_time)
        
        # Update the closest satellite and minimum distance if a new minimum is found
        if sat_diff.distance().km < min_distance:
            closest_routing_sat = r_s
            min_distance = sat_diff.distance().km
    return closest_routing_sat

def find_closest_satellite(sat, sat_list, t):
    closest_sat = None
    min_distance = float('inf') # Initialize minimum distance to infinity
    
    for s in sat_list:
        # Calculate the straight-line distance between the input satellite and each satellite in the list
        sat_diff = sat.at(t) - s.at(t)
        
        # Update the closest satellite and minimum distance if a new minimum is found
        if sat_diff.distance().km < min_distance:
            closest_sat = s
            min_distance = sat_diff.distance().km
    return closest_sat

def degrees_to_radians(value):
    return value * (3.1416/180)  #https://x-engineer.org/degrees-radians/

def correct_Epoch_days(raw_epoch):
    #print(f'Received object of type: {type(raw_epoch)}')
    print(f'Received timedate: {raw_epoch}')
    _python_utc_epoch = raw_epoch
    _spg4_epoch = date(1949, 12, 31)
    _delta_epoch = _python_utc_epoch - _spg4_epoch
    return _delta_epoch.days

def correct_BSTAR_string(Drag_coef):  # trying to match format listed in: https://rhodesmill.org/skyfield/earth-satellites.html
    _str_drag_coef = str(Drag_coef)
    _split_drag_coef = _str_drag_coef.split('-')
    _h_drag_coef = _split_drag_coef[0]
    _float_drag_coef = float(_h_drag_coef) * 1/pow(10, len(_h_drag_coef)-1)
    _drag_coef_power = int(_split_drag_coef[1])-1
    _drag_coef_power = str(_drag_coef_power).zfill(2) #ensure power is 2 characters long
    Corr_drag_coef = str(_float_drag_coef) + 'e-' + _drag_coef_power
    return Corr_drag_coef
    #Corr_drag_coef = _coeff_drag_coef * pow(10, _drag_coef_power)


def correct_BSTAR_float(Drag_coef):
    _str_drag_coef = str(Drag_coef)
    _split_drag_coef = _str_drag_coef.split('-')
    _h_drag_coef = _split_drag_coef[0]
    _float_drag_coef = float(_h_drag_coef) * 1/pow(10, len(_h_drag_coef)-1)
    _drag_coef_power = int(_split_drag_coef[1])-1
    #_drag_coef_power = str(_drag_coef_power).zfill(2) #ensure power is 2 characters long
    #Corr_drag_coef = str(_float_drag_coef) + 'e-' + _drag_coef_power
    Corr_drag_coef = _float_drag_coef * pow(10, -abs(_drag_coef_power))
    Corr_drag_coef = Corr_drag_coef * (1/100) # adjustment to match source satellite - need to fix math
    return Corr_drag_coef

def get_satellite_height(sat, t):
    geocentric = sat.at(t)
    height = wgs84.height_of(geocentric)
    return height.km

def sat_is_North_of(sat1_geoc, sat2_geoc): # is sat1 more north than sat2
    sat1_lat, _ = wgs84.latlon_of(sat1_geoc)
    sat2_lat, _ = wgs84.latlon_of(sat2_geoc)
    return sat1_lat.degrees > sat2_lat.degrees

def sat_is_East_of(sat1_geoc, sat2_geoc): # is sat1 more east than sat2
    _, sat1_lon = wgs84.latlon_of(sat1_geoc)
    _, sat2_lon = wgs84.latlon_of(sat2_geoc)
    return sat1_lon.degrees > sat2_lon.degrees
    
def get_sat_distance(sat1_geoc, sat2_geoc): # returns distance between satellites in km
    return (sat1_geoc - sat2_geoc).distance().km

def get_sat_distance_and_rate_by_satnum(sat1_satnum, sat2_satnum): # returns distance (in km), rate (in km/s)
    sat1_geoc = sat_object_list[sat1_satnum].sat.at(cur_time)
    sat1_geoc_next = sat_object_list[sat1_satnum].sat.at(cur_time_next)
    sat2_geoc = sat_object_list [sat2_satnum].sat.at(cur_time)
    sat2_geoc_next = sat_object_list[sat2_satnum].sat.at(cur_time_next)
    distance = (sat1_geoc - sat2_geoc).distance().km
    distance_next = (sat1_geoc_next - sat2_geoc_next).distance().km
    return distance, (distance_next-distance)

def apply_disruption_schedule():
    global cur_time_increment, disruption_schedule

    if cur_time_increment not in disruption_schedule: # if no disruptions for this time increment, return
        print(f"No disruptions for time increment {cur_time_increment}")
        return
    disruption_list = disruption_schedule[cur_time_increment] # get list of disruptions for this time increment
    cur_sat_disruption_dict = {} # dictionary of satellites that are disrupted in this time increment

    removed_disruptions = 0
    applied_disruptions = 0
    # check ongoing region disruptions, decrement TTL, and remove if TTL is 0
    if len (disrupted_regions_dict) > 0:
        for region in disrupted_regions_dict:
            disrupted_regions_dict[region] -= 1
            if disrupted_regions_dict[region] == 0:
                del disrupted_regions_dict[region]
                removed_disruptions += 1
    
    # apply new disruptions to region disruption list
    for disruption in disruption_list:
        dis_type, target, TTL = disruption
        if dis_type == 'reg':
            disrupted_regions_dict[target] = TTL
        elif dis_type == 'sat':
            cur_sat_disruption_dict[target] = TTL
        applied_disruptions += 1

    # loop through all satellites and apply disruptions as appropriate
    for r_sat in sat_object_list:
        # check for ongoing disruptions
        if r_sat.is_disrupted and (r_sat.disruption_ttl > 0): # first check for satellite disruptions
            r_sat.disruption_ttl -= 1
            if r_sat.disruption_ttl <= 0:  # disruption is finished, so remove - this includes region disruptions, which are reapplied further down
                r_sat.is_disrupted = False
        elif r_sat.is_disrupted and (r_sat.disruption_ttl == -1): # check for region disruptions
            r_sat.is_disrupted = False
            r_sat.disruption_ttl = 0
        # check for new disruptions
        if r_sat.sat.model.satnum in cur_sat_disruption_dict: # check for new satellite disruptions; overwriting existing disruptions
            r_sat.is_disrupted = True
            r_sat.packet_qu.clear() # satellite is disrupted, so clear packet queue
            r_sat.disruption_ttl = cur_sat_disruption_dict[r_sat.sat.model.satnum]
        if not r_sat.is_disrupted:
            for region in disrupted_regions_dict:
                if r_sat.is_overhead_of(region):
                    r_sat.is_disrupted = True
                    r_sat.packet_qu.clear() # satellite is disrupted, so clear packet queue
                    r_sat.disruption_ttl = -1 # set to -1 to indicate that it is a region disruption
                    break # no need to check other regions if already disrupted
    print(f"::apply_disruption_schedule:: {applied_disruptions} disruptions applied, {removed_disruptions} disruptions removed")

def increment_time():
    global cur_time, cur_time_next, time_scale, cur_time_increment, num_packets_dropped
    python_t = cur_time.utc_datetime()
    new_python_time = python_t + timedelta(seconds = time_interval)
    cur_time = time_scale.utc(new_python_time.year, new_python_time.month, new_python_time.day, new_python_time.hour, new_python_time.minute, new_python_time.second)
    new_python_time = python_t + timedelta(seconds = time_interval+1)
    cur_time_next = time_scale.utc(new_python_time.year, new_python_time.month, new_python_time.day, new_python_time.hour, new_python_time.minute, new_python_time.second)
    # reset packet sent counters for all sats and decrement all packet TTLs, deleting packets as appropriate
    for r_sat in sat_object_list:
        r_sat.packet_sent_cnt = 0
        if len(r_sat.packet_qu) > 0:
            for packet in r_sat.packet_qu:
                packet['TTL'] -= time_interval # decrement by the number of seconds in each time increment
                if packet['TTL'] <= 0:
                    num_packets_dropped += 1
                    print(f"::increment_time:: Packet dropped due to TTL for satnum: {r_sat.sat.model.satnum}")
                    r_sat.packet_qu.remove(packet)
    cur_time_increment += 1
    print(f"::increment_time:: Current time incremented to: {cur_time.utc_jpl()}, time increment: {cur_time_increment}, scheduled time intervals: {num_time_intervals}")
    if do_disruptions: apply_disruption_schedule() # apply any disruptions that are scheduled for this time increment

def set_time_interval(interval_seconds): # sets the time interval (in seconds)
    global time_interval
    time_interval = interval_seconds

def draw_static_plot(satnum_list, terminal_list = [], title='figure', draw_lines = True, draw_sphere = False): # Given a list of satnums, generate a static plot

    # ::: STATIC COLORED ORBITS :::
    # Original version based on: https://stackoverflow.com/questions/51891538/create-a-surface-plot-of-xyz-altitude-data-in-python
    
    color_array = []
    colors = ['red', 'purple', 'blue', 'orange', 'green', 'yellow', 'olive', 'cyan', 'brown']
    x_array = []
    y_array = []
    z_array = []
    
    position_terminals = False
    if len(terminal_list) == 2:
        start_terminal = terminal_list[0]
        end_terminal = terminal_list[1]
        position_terminals = True
    elif len(terminal_list) == 1:
        start_terminal = None
        end_terminal = terminal_list[0]
        position_terminals = True
    else:
        for terminal in terminal_list:
            geocentric = terminal.at(cur_time)
            x, y, z = geocentric.position.km
            x_array.append(x)
            y_array.append(y)
            z_array.append(z)
            color_array.append('orangered')

    if position_terminals and (not start_terminal is None):
        start_geocentric = start_terminal.at(cur_time)
        x, y, z = start_geocentric.position.km
        x_array.append(x)
        y_array.append(y)
        z_array.append(z)
        color_array.append('orangered')
    #for orbit_index in orbit_index_list:
    color_index = 0
    for satnum in satnum_list:
            geocentric = sat_object_list[satnum].get_curr_geocentric()
            x, y, z = geocentric.position.km
            x_array.append(x)
            y_array.append(y)
            z_array.append(z)
            #orbit_color = colors[sat_object_list[satnum].orbit_number%len(colors)]
            #color_array.append(orbit_color)
            color_array.append(colors[color_index])
            color_index = (color_index + 1) % len(colors)
    if position_terminals:
        end_geocentric = end_terminal.at(cur_time)
        x, y, z = end_geocentric.position.km
        x_array.append(x)
        y_array.append(y)
        z_array.append(z)
        color_array.append('orangered')
    
    # configure figure
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.set_title(title)
    # hardcode the xyz limites to keep all satellite plots on same scale
    ax_min = -6000
    ax_max = 6000
    ax.set_xlim3d(ax_min, ax_max)
    ax.set_ylim3d(ax_min, ax_max)
    ax.set_zlim3d(ax_min, ax_max)

    if draw_sphere:
        # referencing: https://www.tutorialspoint.com/plotting-points-on-the-surface-of-a-sphere-in-python-s-matplotlib
        r = 6378.137
        u, v = np.mgrid[0:2*np.pi:20j, 0:np.pi:10j]
        x = np.cos(u) * np.sin(v)
        y = np.sin(u) * np.sin(v)
        z = np.cos(v)
        #ax.plot_wireframe(x*r, y*r, z*r, color="red", zorder=0)
        ax.plot_surface(x*r, y*r, z*r)    
    ax.scatter(x_array, y_array, z_array, c=color_array, zorder = 10)
    if draw_lines:
        ax.plot(x_array, y_array, z_array, color = 'black', zorder = 5)
    
    plt.show()



def plot_NSEW():
        random_satnum = random.randint(0, (orbit_cnt * sats_per_orbit)-1)
        test_list = [random_satnum] # test satellite is first
        random_sat = sat_object_list[random_satnum]
        print(f'Selected sat has satnum: {random_sat.satnum}')
        random_sat_East = random_sat.get_sat_East()
        print(f'Random sat East has satnum: {random_sat_East.satnum}')
        test_list.append(random_sat_East.satnum) # Eastern satellite is second
        random_sat_West = random_sat.get_sat_West()
        print(f'Random sat West has satnum: {random_sat_West.satnum}')
        test_list.append(random_sat_West.satnum) # Western satellite is third

        draw_static_plot(test_list, 'East-West satellites')
        
        test_list = [random_satnum] # test satellite is first
        random_sat = sat_object_list[random_satnum]
        print(f'Selected sat has satnum: {random_sat.satnum}')
        random_sat_North = random_sat.get_sat_North()
        print(f'Random sat North has satnum: {random_sat_North.satnum}')
        test_list.append(random_sat_North.satnum) # Northern satellite is second
        random_sat_South = random_sat.get_sat_South()
        print(f'Random sat South has satnum: {random_sat_South.satnum}')
        test_list.append(random_sat_South.satnum) # Southern satellite is third
        
        draw_static_plot(test_list, 'North-South satellites') 

def get_vector_rad_angle(vec1, vec2):
    cross_prod = np.cross(vec1, vec2)
    cross_pod_len = sqrt((cross_prod[0]*cross_prod[0])+(cross_prod[1]*cross_prod[1])+(cross_prod[2]*cross_prod[2]))
    cross_prod_unit_vec = [cross_prod[0]/cross_pod_len, cross_prod[1]/cross_pod_len, cross_prod[2]/cross_pod_len]
    dot_prod = np.dot(vec1, vec2)
    angle = np.arctan2(cross_prod_unit_vec, dot_prod)
    return angle

def get_bearing_degrees(sat1_geoc, sat2_geoc):
    sat1_lat, sat1_lon = wgs84.latlon_of(sat1_geoc)
    sat2_lat, sat2_lon = wgs84.latlon_of(sat2_geoc)
    sat1_lat_rad = math.radians(sat1_lat.degrees)
    sat1_lon_rad = math.radians(sat1_lon.degrees)
    sat2_lat_rad = math.radians(sat2_lat.degrees)
    sat2_lon_rad = math.radians(sat2_lon.degrees)
    bearing = math.atan2(
        math.sin(sat2_lon_rad - sat1_lon_rad) * math.cos(sat2_lat_rad),
        math.cos(sat1_lat_rad) * math.sin(sat2_lat_rad) - math.sin(sat1_lat_rad) * math.cos(sat2_lat_rad) * math.cos(sat2_lon_rad - sat1_lon_rad)
    )
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360
    return bearing

def get_rel_bearing_by_satnum_degrees(sat1_satnum, sat2_satnum, sat1_heading=None):
    routing_sat1 = sat_object_list[sat1_satnum]
    routing_sat2 = sat_object_list[sat2_satnum]

    sat1_lat, sat1_lon = wgs84.latlon_of(routing_sat1.sat.at(cur_time))
    sat2_lat, sat2_lon = wgs84.latlon_of(routing_sat2.sat.at(cur_time))
    sat1_lat_rad = math.radians(sat1_lat.degrees)
    sat1_lon_rad = math.radians(sat1_lon.degrees)
    sat2_lat_rad = math.radians(sat2_lat.degrees)
    sat2_lon_rad = math.radians(sat2_lon.degrees)
    bearing = math.atan2(
        math.sin(sat2_lon_rad - sat1_lon_rad) * math.cos(sat2_lat_rad),
        math.cos(sat1_lat_rad) * math.sin(sat2_lat_rad) - math.sin(sat1_lat_rad) * math.cos(sat2_lat_rad) * math.cos(sat2_lon_rad - sat1_lon_rad)
    )
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360

    if sat1_heading is None:
        sat1_heading = get_heading_by_satnum_degrees(sat1_satnum)

    rel_bearing = bearing - sat1_heading
    rel_bearing = (rel_bearing + 360) % 360

    return rel_bearing

def get_heading_by_satnum_degrees(satnum):
    global cur_time_next
    routing_sat = sat_object_list[satnum]

    sat1_lat, sat1_lon = wgs84.latlon_of(routing_sat.sat.at(cur_time))
    sat2_lat, sat2_lon = wgs84.latlon_of(routing_sat.sat.at(cur_time_next))
    sat1_lat_rad = math.radians(sat1_lat.degrees)
    sat1_lon_rad = math.radians(sat1_lon.degrees)
    sat2_lat_rad = math.radians(sat2_lat.degrees)
    sat2_lon_rad = math.radians(sat2_lon.degrees)
    heading = math.atan2(
        math.sin(sat2_lon_rad - sat1_lon_rad) * math.cos(sat2_lat_rad),
        math.cos(sat1_lat_rad) * math.sin(sat2_lat_rad) - math.sin(sat1_lat_rad) * math.cos(sat2_lat_rad) * math.cos(sat2_lon_rad - sat1_lon_rad)
    )
    heading = math.degrees(heading)
    heading = (heading + 360) % 360
    return heading

#  Something that goes Up to the North, then over two orbits, then Down to the South
def test_North_South_path():
    print("Going North")
    cur_routing_satnum = random.randint(0, (orbit_cnt * sats_per_orbit)-1)
    print(f"First satellite: {cur_routing_satnum}")
    test_list = [cur_routing_satnum]
    cur_routing_sat = get_routing_sat_obj_by_satnum(cur_routing_satnum)
    next_routing_sat = cur_routing_sat.get_sat_North()
    while (not (next_routing_sat is None)):
        print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
        test_list.append(next_routing_sat.sat.model.satnum)
        cur_routing_sat = next_routing_sat
        next_routing_sat = cur_routing_sat.get_sat_North()
    # Reached the Northnmost satellite in this orbit, so skip two orbits West
    print("Going West")
    next_routing_sat = cur_routing_sat.get_sat_West()
    print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
    test_list.append(next_routing_sat.sat.model.satnum)
    cur_routing_sat = next_routing_sat
    next_routing_sat = cur_routing_sat.get_sat_West()
    print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
    test_list.append(next_routing_sat.sat.model.satnum)
    cur_routing_sat = next_routing_sat
    next_routing_sat = cur_routing_sat.get_sat_West()
    print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
    test_list.append(next_routing_sat.sat.model.satnum)
    cur_routing_sat = next_routing_sat
    next_routing_sat = cur_routing_sat.get_sat_West()
    # Done moving West, now go all the way south
    print("Going South")
    while (not (next_routing_sat is None)):
        print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
        test_list.append(next_routing_sat.sat.model.satnum)
        cur_routing_sat = next_routing_sat
        next_routing_sat = cur_routing_sat.get_sat_South()
    # Reached Southernmost satellite in this orbit

    draw_static_plot(test_list, f'Go North, Westx4, South - {len(test_list)} sats')

def test_circumnavigate():
    # Go East till passing original longitutde, then go North for a bit, and go West 
    print("Going East")
    cur_routing_satnum = random.randint(0, (orbit_cnt * sats_per_orbit)-1)
    print(f"First satellite: {cur_routing_satnum}")
    test_list = [cur_routing_satnum]
    cur_routing_sat = get_routing_sat_obj_by_satnum(cur_routing_satnum)
    next_routing_sat = cur_routing_sat.get_sat_East(1)
    if next_routing_sat is None:
        print(f"Could not find Eastern satellite!")
        exit()
    while (len(test_list) < orbit_cnt):
        print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
        test_list.append(next_routing_sat.sat.model.satnum)
        cur_routing_sat = next_routing_sat
        next_routing_sat = cur_routing_sat.get_sat_East(1)
        if next_routing_sat is None:
            print(f"Could not find Eastern satellite!")
            exit()
    print("Going North")
    next_routing_sat = cur_routing_sat.get_sat_North()
    print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
    test_list.append(next_routing_sat.sat.model.satnum)
    cur_routing_sat = next_routing_sat
    next_routing_sat = cur_routing_sat.get_sat_North()
    print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
    test_list.append(next_routing_sat.sat.model.satnum)
    cur_routing_sat = next_routing_sat
    next_routing_sat = cur_routing_sat.get_sat_North()
    print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
    test_list.append(next_routing_sat.sat.model.satnum)
    cur_routing_sat = next_routing_sat
    next_routing_sat = cur_routing_sat.get_sat_North()
    # Done moving North, now go all the way West
    print("Going West")
    test_orbit_cnt = 0
    while (test_orbit_cnt < orbit_cnt):
        print(f"Next satellite: {next_routing_sat.sat.model.satnum}")
        test_list.append(next_routing_sat.sat.model.satnum)
        cur_routing_sat = next_routing_sat
        next_routing_sat = cur_routing_sat.get_sat_West()
        if next_routing_sat is None:
            print (f"Could not find Western satellite!")
            exit()
        test_orbit_cnt += 1
    

    draw_static_plot(test_list, f"Go East, Northx2, West - {len(test_list)} sats")

def find_route_random(src, dest):
    # Find satellite at least 60 deg above the horizon at source
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(src)):
            topo_position = (r_sat.sat - src).at(cur_time)
            alt, az, dist = topo_position.altaz()    
            print(f'Satellite {r_sat.sat.model.satnum} is at least 30deg off horizon in Blacksburg')
            print(f'\tElevation: {alt.degrees}\n\tAzimuth: {az}\n\tDistance: {dist.km:.1f}km')
            break # Just go with first satellite

    cur_routing_sat = r_sat
    sat_traverse_list = []
    link_distance = 0
    start = time.process_time()
    while True:
        sat_traverse_list.append(cur_routing_sat.sat.model.satnum)
        if cur_routing_sat.is_overhead_of(dest):
            print('Made it to Destination')
            break
        go_North = not cur_routing_sat.is_North_of(dest)     
        go_East = not cur_routing_sat.is_East_of(dest)

        go_lat = random.randint(0,1)

        topo_diff = (cur_routing_sat.sat - dest).at(cur_time)
        _, _, dist = topo_diff.altaz()

        if go_lat:
            go_lat = False
            if go_North:
                next_routing_sat = cur_routing_sat.get_sat_North()
            else:
                next_routing_sat = cur_routing_sat.get_sat_South()
        else:
            go_lat = True
            if go_East:
                next_routing_sat = cur_routing_sat.get_sat_East()
            else:
                next_routing_sat = cur_routing_sat.get_sat_West()
        link_distance += get_sat_distance(cur_routing_sat.sat.at(cur_time), next_routing_sat.sat.at(cur_time))
        cur_routing_sat = next_routing_sat
    compute_time = time.process_time() - start
    print(f'Made {len(sat_traverse_list)} satellite hops to get to destination; distance of {link_distance:.2f}km ({link_distance * secs_per_km:.2f} seconds); compute time: {compute_time}')
    draw_static_plot(sat_traverse_list, [src, dest], title=f'Random: {len(sat_traverse_list)} satellite hops; distance {int(link_distance)}km')

def find_route_dijkstra_dist(src, dest):
    global no_sat_overhead_cnt
    global num_route_calc_failures
    #print("Starting Dijkstra distance routing")
    # Find satellite at least 60 deg above the horizon at source and destination
    # FIX: distances must also include the satnum of which sat put the lowest distance!  Must follow that listing backwards to id path to the source
    sat_found = False
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(src)):
            sat_found = True
            break # Just go with first satellite
    if not sat_found:
        print(f"Unable to find satellite over source!")
        no_sat_overhead_cnt += 1
        return -1
    src_routing_sat = r_sat

    sat_found = False
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(dest)):
            sat_found = True
            break # Just go with first satellite
    if not sat_found:
        print(f"Unable to find satellite over destination!")
        no_sat_overhead_cnt += 1
        return -1
    dest_routing_sat = r_sat

    visited_sat_dict = {} #(satnum, (distance, satnum_who_assigned_distance))

    unvisted_sat_dict = {} # dict of satnums with respective tentative distance values
    for r_sat in sat_object_list:
        unvisted_sat_dict[r_sat.sat.model.satnum] = (float('inf'), -1)

    cur_sat = src_routing_sat
    unvisted_sat_dict[cur_sat.sat.model.satnum] = (0, -1)
    
    cur_sat_dist = 0
    route_found = False

    #start = time.process_time()
    loop_cnt = 0

    #print("Starting Dijsktra Distance Loop")
    while True:
        print(f"Pre-computing Dijsktra Distance - Loop count: {loop_cnt}", end="\r")
        
        neigh_fore = cur_sat.get_fore_sat()
        neigh_aft = cur_sat.get_aft_sat()
        neigh_preceeding_orbit_satnum, _ = cur_sat.check_preceeding_orbit_sat_available()
        neigh_succeeding_orbit_satnum, _ = cur_sat.check_succeeding_orbit_sat_available()
        if neigh_preceeding_orbit_satnum is None: neigh_preceeding_orbit = None
        else: neigh_preceeding_orbit = get_routing_sat_obj_by_satnum(neigh_preceeding_orbit_satnum)
        if neigh_succeeding_orbit_satnum is None: neigh_succeeding_orbit = None
        else: neigh_succeeding_orbit = get_routing_sat_obj_by_satnum(neigh_succeeding_orbit_satnum)

        cur_sat_neigh_list = [neigh_fore, neigh_aft, neigh_preceeding_orbit, neigh_succeeding_orbit]

        # Set distances for adjancent satellites
        for testing_sat in cur_sat_neigh_list:
            if not testing_sat is None:
                if testing_sat.sat.model.satnum in unvisted_sat_dict:
                    testing_sat_dist = get_sat_distance(cur_sat.sat.at(cur_time), testing_sat.sat.at(cur_time))
                    tentative_dist = cur_sat_dist + testing_sat_dist
                    if tentative_dist < unvisted_sat_dict[testing_sat.sat.model.satnum][0]:
                        unvisted_sat_dict[testing_sat.sat.model.satnum] = (tentative_dist, cur_sat.sat.model.satnum)

        # Move current satellite to visited_sat_dict and remove it's entry in unvisted_sat_dict
        visited_sat_dict[cur_sat.sat.model.satnum] = unvisted_sat_dict[cur_sat.sat.model.satnum]
        del unvisted_sat_dict[cur_sat.sat.model.satnum]
        
        # Test to see if we just set the destination node as 'visited'
        if cur_sat.sat.model.satnum == dest_routing_sat.sat.model.satnum:
            #print("Algorithm reached destination node")
            route_found = True  # Indicate the destination has been reached and break out of the loop
            break

        # See if we've run out of unvisited nodes
        if len(unvisted_sat_dict) < 1:
            break

        # Continuing on, so find the next unvisited node with the lowest distance
        next_hop_satnum = None
        next_hop_dist = float('inf')
        for unvisited_satnum in unvisted_sat_dict.keys():
            if unvisted_sat_dict[unvisited_satnum][0] < next_hop_dist:
                next_hop_dist = unvisted_sat_dict[unvisited_satnum][0]
                next_hop_satnum = unvisited_satnum

        # Were there no nodes with distances other than infinity?  Something went wrong
        if next_hop_dist == float('inf'):
            print(f"No more neighbors without infinite distances to explore.  {len(visited_sat_dict)} visited nodes; {len(unvisted_sat_dict)} unvisted nodes remaining")
            num_route_calc_failures += 1
            return -1

        # Get sat routing object for indicated satnum
        cur_sat = get_routing_sat_obj_by_satnum(next_hop_satnum)
        cur_sat_dist = unvisted_sat_dict[cur_sat.sat.model.satnum][0]
        loop_cnt += 1
    # Done with loop; check if a route was found
    if not route_found:
        print(f"Unable to find route using dijkstra's algorithm")
        num_route_calc_failures += 1
        return -1
    
    # Route was found, so retrace steps
    traverse_list = [dest_routing_sat.sat.model.satnum]
    cur_satnum = dest_routing_sat.sat.model.satnum
    link_distance = 0
    while True:
        next_hop = visited_sat_dict[cur_satnum][1]
        if next_hop == -1:
            print(f"::find_route_dijkstra_dist():: ERROR - no next_hop in visted_sat_dict!; cur_satnum: {cur_satnum} / visited_sat_dict: {visited_sat_dict}")
            num_route_calc_failures += 1
            return -1
        link_distance += get_sat_distance(get_routing_sat_obj_by_satnum(cur_satnum).sat.at(cur_time), get_routing_sat_obj_by_satnum(next_hop).sat.at(cur_time))
        traverse_list.insert(0, next_hop)
        if next_hop == src_routing_sat.sat.model.satnum:
            break
        cur_satnum = next_hop
    traverse_list.reverse()
    packet = {'dest_satnum': traverse_list[0], 'next_hop_list' : traverse_list[:-1], 'prev_hop_list' : [], 'distance_traveled' : 0, 'dest_gs' : dest, 'TTL' : packet_start_TTL}
    # route pre-computed, so send packet
    send_directed_routing_packet_from_source(traverse_list[-1], src, packet)
    
def find_route_dijkstra_hop(src, dest):
    #print("Starting Dijkstra hop routing")
    # Find satellite at least 60 deg above the horizon at source and destination
    # FIX: distances must also include the satnum of which sat put the lowest distance!  Must follow that listing backwards to id path to the source
    global num_route_calc_failures, no_sat_overhead_cnt

    sat_found = False
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(src)):
            sat_found = True
            break # Just go with first satellite
    if not sat_found:
        print(f"Unable to find satellite over source!")
        no_sat_overhead_cnt += 1
        return -1
    src_routing_sat = r_sat

    sat_found = False
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(dest)):
            sat_found = True
            break # Just go with first satellite
    if not sat_found:
        print(f"Unable to find satellite over destination!")
        no_sat_overhead_cnt += 1
        return -1
    dest_routing_sat = r_sat

    visited_sat_dict = {} #(satnum, (distance, satnum_who_assigned_distance))

    unvisted_sat_dict = {} # dict of satnums with respective tentative distance values
    for r_sat in sat_object_list:
        unvisted_sat_dict[r_sat.sat.model.satnum] = (float('inf'), -1)

    cur_sat = src_routing_sat
    unvisted_sat_dict[cur_sat.sat.model.satnum] = (0, -1)
    
    cur_sat_dist = 0
    route_found = False

    loop_cnt = 0

    #print("Starting Dijsktra Loop")
    while True:
        print(f"Pre-computing Dijsktra Hop - Loop count: {loop_cnt}", end="\r")
        
        neigh_fore = cur_sat.get_fore_sat()
        neigh_aft = cur_sat.get_aft_sat()
        neigh_preceeding_orbit_satnum, _ = cur_sat.check_preceeding_orbit_sat_available()
        neigh_succeeding_orbit_satnum, _ = cur_sat.check_succeeding_orbit_sat_available()
        if neigh_preceeding_orbit_satnum is None: neigh_preceeding_orbit = None
        else: neigh_preceeding_orbit = get_routing_sat_obj_by_satnum(neigh_preceeding_orbit_satnum)
        if neigh_succeeding_orbit_satnum is None: neigh_succeeding_orbit = None
        else: neigh_succeeding_orbit = get_routing_sat_obj_by_satnum(neigh_succeeding_orbit_satnum)

        cur_sat_neigh_list = [neigh_fore, neigh_aft, neigh_preceeding_orbit, neigh_succeeding_orbit]

        # Set distances for adjancent satellites
        for testing_sat in cur_sat_neigh_list:
            if not testing_sat is None:
                if testing_sat.sat.model.satnum in unvisted_sat_dict:
                    testing_sat_dist = 1 # just a single hop from current satellite to testing satellite
                    tentative_dist = cur_sat_dist + testing_sat_dist
                    if tentative_dist < unvisted_sat_dict[testing_sat.sat.model.satnum][0]:
                        unvisted_sat_dict[testing_sat.sat.model.satnum] = (tentative_dist, cur_sat.sat.model.satnum)

        # Move current satellite to visited_sat_dict and remove it's entry in unvisted_sat_dict
        visited_sat_dict[cur_sat.sat.model.satnum] = unvisted_sat_dict[cur_sat.sat.model.satnum]
        del unvisted_sat_dict[cur_sat.sat.model.satnum]
        
        # Test to see if we just set the destination node as 'visited'
        if cur_sat.sat.model.satnum == dest_routing_sat.sat.model.satnum:
            route_found = True  # Indicate the destination has been reached and break out of the loop
            break

        # See if we've run out of unvisited nodes
        if len(unvisted_sat_dict) < 1:
            break

        # Continuing on, so find the next unvisited node with the lowest distance
        next_hop_satnum = None
        next_hop_dist = float('inf')
        for unvisited_satnum in unvisted_sat_dict.keys():
            if unvisted_sat_dict[unvisited_satnum][0] < next_hop_dist:
                next_hop_dist = unvisted_sat_dict[unvisited_satnum][0]
                next_hop_satnum = unvisited_satnum

        # Were there no nodes with distances other than infinity?  Something went wrong
        if next_hop_dist == float('inf'):
            print(f"No more neighbors without infinite distances to explore.  {len(visited_sat_dict)} visited nodes; {len(unvisted_sat_dict)} unvisted nodes remaining")
            num_route_calc_failures += 1
            return -1 

        # Get sat routing object for indicated satnum
        cur_sat = get_routing_sat_obj_by_satnum(next_hop_satnum)
        cur_sat_dist = unvisted_sat_dict[cur_sat.sat.model.satnum][0]
        loop_cnt += 1
    # Done with loop; check if a route was found
    if not route_found:
        print(f"Unable to find route using dijkstra's algorithm")
        num_route_calc_failures += 1
        return -1
    
    # Route was found, so retrace steps
    traverse_list = [dest_routing_sat.sat.model.satnum]
    cur_satnum = dest_routing_sat.sat.model.satnum
    link_distance = 0
    while True:
        next_hop = visited_sat_dict[cur_satnum][1]
        if next_hop == -1:
            print(f"::find_route_dijkstra_dist():: ERROR - no next_hop in visted_sat_dict!; cur_satnum: {cur_satnum} / visited_sat_dict: {visited_sat_dict}")
            num_route_calc_failures += 1
            return -1
        link_distance += get_sat_distance(get_routing_sat_obj_by_satnum(cur_satnum).sat.at(cur_time), get_routing_sat_obj_by_satnum(next_hop).sat.at(cur_time))
        traverse_list.insert(0, next_hop)
        if next_hop == src_routing_sat.sat.model.satnum:
            break
        cur_satnum = next_hop
    traverse_list.reverse()
    packet = {'dest_satnum': traverse_list[0], 'next_hop_list' : traverse_list[:-1], 'prev_hop_list' : [], 'distance_traveled' : 0, 'dest_gs' : dest, 'TTL' : packet_start_TTL}
    # route pre-computed, now send packet
    send_directed_routing_packet_from_source(traverse_list[-1], src, packet)

# ::: directed routing packet structure: [dest_satnum, [next_hop_list], [prev_hop_list], distance_traveled, dest_terminal] - packet is at destination when dest_satnum matches current_satnum and next_hop_list is empty
def send_directed_routing_packet_from_source(starting_satnum, starting_terminal, packet):  # must have next_hop_list pre_built
    global no_sat_overhead_cnt
    starting_sat = get_routing_sat_obj_by_satnum(starting_satnum)

    topo_position = (starting_sat.sat - starting_terminal).at(cur_time)
    _, _, dist = topo_position.altaz()
    if not starting_sat.is_overhead_of(starting_terminal):
        print(f"Satellite {starting_satnum} is not overhead starting terminal _after routing_ - starting terminal: {starting_terminal}")
        no_sat_overhead_cnt += 1
        return
    packet['distance_traveled'] += dist.km
    add_to_packet_qu_by_satnum(starting_satnum, packet)
    
def send_distributed_routing_packet_from_source(src, dest):
    global num_packets_dropped
    sat_overhead = False
    for routing_sat in sat_object_list:
        if routing_sat.is_overhead_of(src):
            sat_overhead = True
            break
    if not sat_overhead:
        return -1
    distance = get_sat_distance(src.at(cur_time), routing_sat.sat.at(cur_time))
    packet = {'prev_hop_list': [], 'distance_traveled': distance, 'dest_gs': dest, 'source_gs': src, 'TTL' : packet_start_TTL}
    add_to_packet_qu_by_satnum(routing_sat.sat.model.satnum, packet)

def build_constellation(source_sat):

    Epoch =   source_sat.epoch # Maybe just copy the epoch from the loaded TLE?

    # Correct values and convert to radians where needed
    # Epoch - convert to number of days since 1949 December 31 00:00 UT
    Corr_Epoch = correct_Epoch_days(Epoch.utc_datetime().date()) + (source_sat.model.epochdays % 1) #getting the partial days of the epoch
    
    # Drag Coefficient, aka BSTAR  http://www.castor2.ca/03_Mechanics/03_TLE/B_Star.html
    Corr_drag_coef = source_sat.model.bstar

    # Eccentricity
    Corr_Ecc = source_sat.model.ecco

    # Argument of Perigee - convert from degrees to radians
    Rad_Arg_Perig = source_sat.model.argpo
    
    # Inclination - convert from degrees to radians
    Rad_Inclination = source_sat.model.inclo

    # Mean Motion - convert from revolutions/day to radians/minute
    Rad_Mean_motion = source_sat.model.no_kozai

    # Mean anomoly - convert from degrees to radians
    Rad_Starting_mean_anomoly = source_sat.model.mo
    
    # Right Ascension of Ascending Node - convert from degrees to radians
    Rad_Starting_RaaN = source_sat.model.nodeo

    # Mean anomoly Modifier
    MaM = (pi * 2)/sats_per_orbit

    # RaaN Modifier
    RaaNM = (pi * 2)/orbit_cnt

    # ballistic coefficient (ndot) and mean motion 2nd derivative (nddot) - supposedely can just set to 0, but including for completeness
    Ndot = source_sat.model.ndot
    Nddot = source_sat.model.nddot

    #building satellites using instructions from https://rhodesmill.org/skyfield/earth-satellites.html
    
    satnum = 0
    for orbit_index in range(0, orbit_cnt):
        orbit = []
        for sat_index in range(0, sats_per_orbit):  #Going to leave sat_index '0' for progenitor satellite
            fake_sat = Satrec()
            fake_sat.sgp4init(
                WGS72,                                                  # gravity model
                'i',                                                    # improved mode
                satnum,                                                 # satnum: Satellite number
                Corr_Epoch,                                             # epoch: days since 1949 December 31 00:00 UT
                Corr_drag_coef,                                         # bstar: drag coefficient (/earth radii)
                Ndot,                                                   # ndot: ballistic coefficient (radians/minute^2) - can ignore
                Nddot,                                                  # nddot: mean motion 2nd derivative (radians/minute^3) - can ignore
                Corr_Ecc,                                               # ecco: eccentricity
                Rad_Arg_Perig,                                          # argpo: argument of perigee (radians)
                Rad_Inclination,                                        # inclo: inclination (radians)
                #(Rad_Starting_mean_anomoly + (sat_index * MaM))%(2*pi), # mo: mean anomaly (radians) - will need to modify this per satellite ** Need to offset this by appropriate phase!!!
                #((Rad_Starting_mean_anomoly + ((orbit_index%2) * (MaM/2))) + (sat_index * MaM)) % (2*pi),
                ((Rad_Starting_mean_anomoly - (orbit_index*MaM*.7)) + ((sat_index % sats_per_orbit) * (MaM))) % (2 * pi), # unsure why this factor got the satellites to line up, but whatever
                Rad_Mean_motion,                                        # no_kozai: mean motion (radians/minute)
                (Rad_Starting_RaaN + (orbit_index * RaaNM))%(2*pi)      # nodeo: R.A. of ascending node (radians) (greater the value, the more East?)
            )
            fake_sat.classification = source_sat.model.classification
            fake_sat.elnum = source_sat.model.elnum
            fake_sat.revnum = source_sat.model.revnum
            sat = EarthSatellite.from_satrec(fake_sat, time_scale)
            orbit.append(sat)

            new_sat = RoutingSat(sat, satnum, orbit_index, sat_index, (orbit_index + 2) % orbit_cnt, (orbit_index - 2) % orbit_cnt, ((sat_index + 1) % sats_per_orbit) + (orbit_index*sats_per_orbit), ((sat_index - 1) % sats_per_orbit) + (orbit_index*sats_per_orbit))
            sat_object_list.append(new_sat)
            satnum += 1
        
        orbit_list.append(orbit)

    global num_sats
    num_sats = orbit_cnt * sats_per_orbit

def plot_objects_to_sphere(object_list):
    # referencing: https://www.tutorialspoint.com/plotting-points-on-the-surface-of-a-sphere-in-python-s-matplotlib
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    r = 6378.137
    #r = 0.05
    u, v = np.mgrid[0:2*np.pi:20j, 0:np.pi:10j]
    x = np.cos(u) * np.sin(v)
    y = np.sin(u) * np.sin(v)
    z = np.cos(v)
    #ax.plot_wireframe(x*r, y*r, z*r, color="grey")
    ax.plot_surface(x*r, y*r, z*r)
    plt.show()

def directed_dijkstra_hop_routing():
    global no_sat_overhead_cnt, num_packets_dropped, num_packets_sent, cur_time_increment, routing_name
    routing_name = "Directed Dijkstra Hop"

    max_time_inverals = int(num_time_intervals * 1.5) # allow some additional time to process any packets that may have been delayed
    for _ in range(max_time_inverals):
        if cur_time_increment in packet_schedule:
            packet_send_list = packet_schedule[cur_time_increment]  # get list of packets to send for this time interval
            packet_num = 0
            packet_send_list_size = len(packet_send_list)
            for packet in packet_send_list:
                num_packets_sent += 1
                src, dest = packet
                print(f"Sending directed packet {packet_num} of {packet_send_list_size} using Dijkstra Hop")
                packet_num += 1
                if find_route_dijkstra_hop(src, dest) == -1:  # call pre-calculate routing routing
                    #print(f"Unable to find route to {src}", end='\r') # if route from source to destination not found, drop packet
                    num_packets_dropped += 1
            del packet_schedule[cur_time_increment] # remove this time increment from packet scheduler
        # keep sending packets until no more packets are sent (either nothing to sent, or sats have hit their bandwidth limit)
        packets_sent = True
        while (packets_sent):
            packets_sent = False
            for routing_sat in sat_object_list:  # loop through all satellites and send packets
                if routing_sat.directed_routing_process_packet_queue() == 0: # if packets were sent, function returns 0
                    packets_sent = True
        if (len(packet_schedule) == 0) and (num_packets_received + num_packets_dropped == num_packets_sent):
            print("All packets sent and accounted for.  Terminating simulation")
            break
        increment_time() # go to next time increment and start loop over
    # looping simulation is finished
    if len(packet_schedule) > 0:
        print("Failed to send all packets in schedule")
        print(packet_schedule)
    if not (num_packets_received + num_packets_dropped == num_packets_sent):
        print("Some packets unaccounted for!!")

def directed_dijkstra_distance_routing():
    global no_sat_overhead_cnt, num_packets_dropped, num_packets_sent, cur_time_increment, routing_name
    routing_name = "Directed Dijkstra Distance"

    max_time_inverals = int(num_time_intervals * 1.5) # allow some additional time to process any packets that may have been delayed
    for _ in range(max_time_inverals):
        if cur_time_increment in packet_schedule:
            packet_send_list = packet_schedule[cur_time_increment]  # get list of packets to send for this time interval
            packet_num = 0
            packet_send_list_size = len(packet_send_list)
            for packet in packet_send_list:
                num_packets_sent += 1
                src, dest = packet
                print(f"Sending directed packet {packet_num} of {packet_send_list_size} using Dijkstra Hop")
                packet_num += 1
                if find_route_dijkstra_dist(src, dest) == -1:  # call pre-calculate routing routing
                    #print(f"Unable to find route to {src}", end='\r') # if route from source to destination not found, drop packet
                    num_packets_dropped += 1
            del packet_schedule[cur_time_increment] # remove this time increment from packet scheduler
        # keep sending packets until no more packets are sent (either nothing to sent, or sats have hit their bandwidth limit)
        packets_sent = True
        while (packets_sent):
            packets_sent = False
            for routing_sat in sat_object_list:  # loop through all satellites and send packets
                if routing_sat.directed_routing_process_packet_queue() == 0: # if packets were sent, function returns 0
                    packets_sent = True
        if (len(packet_schedule) == 0) and (num_packets_received + num_packets_dropped == num_packets_sent):
            print("All packets sent and accounted for.  Terminating simulation")
            break
        increment_time() # go to next time increment and start loop over
    # looping simulation is finished
    if len(packet_schedule) > 0:
        print("Failed to send all packets in schedule")
        print(packet_schedule)
    if not (num_packets_received + num_packets_dropped == num_packets_sent):
        print("Some packets unaccounted for!!")

def distributed_link_state_routing():
    global no_sat_overhead_cnt, num_packets_dropped, num_packets_sent, cur_time_increment, routing_name
    routing_name = "Distributed Link State"

    max_time_inverals = int(num_time_intervals * 1.5) # allow some additional time to process any packets that may have been delayed
    # Work through packet scheduler at each time interval and send all scheduled packets
    for _ in range(max_time_inverals):
        if cur_time_increment in packet_schedule:
            packet_send_list = packet_schedule[cur_time_increment] # get list of packets to send for this time increment
            for packet in packet_send_list:
                src, dest = packet
                if send_distributed_routing_packet_from_source(src, dest) == -1:  # send packets without any pre-calculation
                    print(f"::distributed_link_state_routing:: No satellite overhead starting terminal {src}, dropping packet")
                    no_sat_overhead_cnt += 1
                    num_packets_dropped += 1
                num_packets_sent += 1
            del packet_schedule[cur_time_increment] # remove time increment from packet scheduler
        
        print("Updating neighbor states")
        start = time.process_time()
        all_sats_update_neigh_state()  # each satellite publishes it's state to it's neighbors and then the satellites process the received data
        compute_time = time.process_time() - start
        print(f"Time to compute neighbor states: {compute_time}")
        
        
        print("Checking for packets to send")
        start = time.process_time()
        packets_sent = True
        while (packets_sent):  # keep sending packets until no more packets are sent (either nothing to sent, or sats have hit their bandwidth limit)
            packets_sent = False
            for routing_sat in sat_object_list:
                if routing_sat.distributed_routing_link_state_process_packet_queue() == 0:  # if packets were sent, function returns 0
                    packets_sent = True
        compute_time = time.process_time() - start
        print(f"Time spent to send packets: {compute_time}")
        if (len(packet_schedule) == 0) and (num_packets_received + num_packets_dropped == num_packets_sent):
            print("All packets sent and accounted for.  Terminating simulation")
            break
        increment_time()
    if len(packet_schedule) > 0:
        print(f"Failed to send all packets in schedule.  {len(packet_schedule)} packets remaining in schedule")
    if not (num_packets_received + num_packets_dropped == num_packets_sent):
        print("Some packets unaccounted for!!")
        
def build_disruption_schedule():
    # select satellites randomly and for random durations (short) to disrupt
    # disruptions are enabled/disabled during time increments
    # satellites can either be set 'disrupted' by scheduler or
    # satellites can be disrupted by 'time intervals' when they are over a geographic region
    # scheduler will need to decide:
    #   1. single satellite or geographic region
    #   2. which satellite or region
    #   3. and how long to disrupt
    #disruption_schedule = {} # a dictionary with time interval integers as keys and lists of satellites or regions, along with time intervals, as values
    # e.g. {0: [('sat', 443, 3), ('reg', GeographicPosition, 5), ('sat', 843, 1)]}
    
    # Disruption likelihood:
    #   50% - No disruption
    #   30% - Single satellite disruption
    #   15% - Single region disruption
    #    5% - Multiple satellite disruption (2 satellites)
    # Disruption duration:
    #   50% - 1 time interval
    #   30% - 2 time intervals
    #   20% - 3 time intervals
    
    global disruption_schedule

    for interval in range(num_time_intervals):
        disruption_schedule[interval] = []
        random_num = random.randint(0, 99)
        if random_num < 50:
            # no disruption
            continue
        elif random_num < 80:
            # single satellite disruption
            sat = random.randint(0, num_sats - 1)
            duration = random.randint(1, 3)
            disruption_schedule[interval].append(('sat', sat, duration))
        elif random_num < 95:
            # single region disruption
            # NOTE: need to figure out how to select a region
            #  maybe just randomly select a lat/lon and build a GeographicPosition object
            region_lat = random.randint(-900000, 900000)
            region_lat = region_lat / 10000
            region_lon = random.randint(-1800000, 1800000)
            region_lon = region_lon / 10000
            region = wgs84.latlon(region_lat, region_lon)
            duration = random.randint(1, 3)
            disruption_schedule[interval].append(('reg', region, duration))
        else:
            # multiple satellite disruption
            sat1 = random.randint(0, num_sats - 1)
            sat2 = random.randint(0, num_sats - 1)
            while sat2 == sat1:
                sat2 = random.randint(0, num_sats - 1)
            duration = random.randint(1, 3)
            disruption_schedule[interval].append(('sat', sat1, duration))
            disruption_schedule[interval].append(('sat', sat2, duration))
        print(f"::build_disruption_schedule:: {len(disruption_schedule[interval])} disruptions scheduled for time interval {interval}")



# generate the list packet_schedule that contains a list of packets to be sent at each time interval
def build_packet_schedule():
    # establish city bandwidth utilization and common routes - using: https://global-internet-map-2021.telegeography.com/
    # Ranked by internation bandwidth capacity
    Frankfurt = wgs84.latlon(50.1109 * N, 8.6821 * E) # 1
    London = wgs84.latlon(51.5072 * N, 0.1276 * W) # 2
    Amsterdam = wgs84.latlon(52.3667 * N, 4.8945 * E) # 3
    Paris = wgs84.latlon(48.8567 * N, 2.3508 * E) # 4
    Singapore = wgs84.latlon(1.3521 * N, 103.8198 * E) # 5
    Hong_Kong = wgs84.latlon(22.3193 * N, 114.1694 * E) # 6
    Stockholm = wgs84.latlon(59.3293 * N, 18.0686 * E) # 7
    Miami = wgs84.latlon(25.7617 * N, 80.1918 * W) # 8
    Marseille = wgs84.latlon(43.2964 * N, 5.3700 * E) # 9
    Los_Angeles = wgs84.latlon(34.0522 * N, 118.2437 * W) # 10
    New_York = wgs84.latlon(40.7128 * N, 74.0060 * W) # 11
    Vienna = wgs84.latlon(48.2082 * N, 16.3738 * E) # 12
    Moscow = wgs84.latlon(55.7558 * N, 37.6173 * E) # 13
    Milan = wgs84.latlon(45.4642 * N, 9.1900 * E) # 14
    Tokyo = wgs84.latlon(35.6762 * N, 139.6503 * E) # 15
    Istanbul = wgs84.latlon(41.0082 * N, 28.9784 * E) # 16
    San_Francisco = wgs84.latlon(37.7749 * N, 122.4194 * W) # 17
    Jakarta = wgs84.latlon(6.2088 * S, 106.8456 * E) # 18
    Sofia = wgs84.latlon(42.6977 * N, 23.3219 * E) # 19
    Madrid = wgs84.latlon(40.4168 * N, 3.7038 * W) # 20
    Copenhagen = wgs84.latlon(55.6761 * N, 12.5683 * E) # 21
    Budapest = wgs84.latlon(47.4979 * N, 19.0402 * E) # 22
    Hamburg = wgs84.latlon(53.5511 * N, 9.9937 * E) # 23
    Hanoi = wgs84.latlon(21.0278 * N, 105.8342 * E) # 24
    Sao_Paulo = wgs84.latlon(23.5505 * S, 46.6333 * W) # 25
    Buenos_Aires = wgs84.latlon(34.6037 * S, 58.3816 * W) # 26
    Warsaw = wgs84.latlon(52.2297 * N, 21.0122 * E) # 27
    Bangkok = wgs84.latlon(13.7563 * N, 100.5018 * E) # 28
    Buchararest = wgs84.latlon(44.4268 * N, 26.1025 * E) # 29
    Helsinki = wgs84.latlon(60.1699 * N, 24.9384 * E) # 30
    Mumbai = wgs84.latlon(19.0760 * N, 72.8777 * E) # 31
    Prague = wgs84.latlon(50.0755 * N, 14.4378 * E) # 32
    Brussels = wgs84.latlon(50.8503 * N, 4.3517 * E) # 33
    St_Petersburg = wgs84.latlon(59.9343 * N, 30.3351 * E) # 34
    Dusseldorf = wgs84.latlon(51.2277 * N, 6.7735 * E) # 35
    Washington = wgs84.latlon(38.9072 * N, 77.0369 * W) # 36
    Chennai = wgs84.latlon(13.0827 * N, 80.2707 * E) # 37
    Kuala_Lumpur = wgs84.latlon(3.1390 * N, 101.6869 * E) # 38
    Rio_de_Janeiro = wgs84.latlon(22.9068 * S, 43.1729 * W) # 39
    Oslo = wgs84.latlon(59.9139 * N, 10.7522 * E) # 40
    Mexico_City = wgs84.latlon(19.4326 * N, 99.1332 * W) # 41
    Beijing = wgs84.latlon(39.9042 * N, 116.4074 * E) # 42    
    Zurich = wgs84.latlon(47.3769 * N, 8.5417 * E) # 43
    Sydney = wgs84.latlon(33.8688 * S, 151.2093 * E) # 44
    Santiago = wgs84.latlon(33.4489 * S, 70.6693 * W) # 45
    Toronto = wgs84.latlon(43.6532 * N, 79.3832 * W) # 46
    Bratislava = wgs84.latlon(48.1486 * N, 17.1077 * E) # 47
    Seoul = wgs84.latlon(37.5665 * N, 126.9780 * E) # 48
    Taipei = wgs84.latlon(25.0330 * N, 121.5654 * E) # 49
    Riyadh = wgs84.latlon(24.7136 * N, 46.6753 * E) # 50

    city_list = [Frankfurt, Paris, Amsterdam, London, Singapore, Jakarta, Marseille, Mumbai, Tokyo, Hong_Kong, Los_Angeles, Hanoi, Miami, Sao_Paulo, Madrid, Washington, Rio_de_Janeiro, Milan, Vienna, Moscow, Istanbul, San_Francisco, Sofia, Copenhagen, Budapest, Hamburg, Buenos_Aires, Warsaw, Bangkok, Buchararest, Helsinki, Prague, Brussels, St_Petersburg, Dusseldorf, Chennai, Kuala_Lumpur, Oslo, Mexico_City, Beijing, Zurich, Sydney, Santiago, Toronto, Bratislava, Seoul, Taipei, Riyadh]

    # Also need to create a range of random locations on the globe (to include oceans)
    # A good percentage of links should come from the random location list!!!

    # Major links between cities - basically eyeballed these using the map from the link above
    # Category 0
    city_links = [
        [(Frankfurt, Paris),
        (Frankfurt, Amsterdam),
        (Frankfurt, London),
        (Frankfurt, Moscow),
        (Frankfurt, Vienna),
        (London, New_York),
        (Singapore, Jakarta)],
    # Category 1
        [(Marseille, Mumbai),
        (Tokyo, Hong_Kong),
        (Tokyo, Los_Angeles),
        (Hong_Kong, Hanoi),
        (Hong_Kong, Singapore),
        (Singapore, Chennai),
        (Singapore, Kuala_Lumpur),
        (Singapore, Bangkok),
        (Miami, Sao_Paulo),
        (Paris, Madrid),
        (Washington, Paris),
        (Miami, Rio_de_Janeiro)],
    # Category 2
        [(Moscow, Stockholm),
        (Sofia, Istanbul),
        (Stockholm, Helsinki),
        (Stockholm, Copenhagen),
        (Stockholm, Oslo),
        (Helsinki, St_Petersburg),
        (Frankfurt, Istanbul),
        (Amsterdam, London),
        (Amsterdam, Paris),
        (Amsterdam, Hamburg),
        (New_York, Toronto),
        (New_York, Sao_Paulo)],
    # Category 3
        [(Hong_Kong, Sydney),
        (Sydney, San_Francisco),
        (Sydney, Los_Angeles),
        (San_Francisco, Hong_Kong),
        (Los_Angeles, Mexico_City)]]

    # Category 4
    # Randomly select cities from the city_list

    # For every time interval, we will generate a certain amount of traffic
    # This traffic is generated randomly between two cities, but higher order
    # link categories are more likely to be chosen
    # Category 0: 40%, Category 1: 25%, Category 2: 15%, Category 3: 10%, Category 4: 10%
    # Variable specifying amount of traffic generated for each time inveral:  packets_generated_per_interval

    global packet_schedule

    for interval in range(num_time_intervals):
        for packet_cnt in range(packets_generated_per_interval):
            if packet_cnt == 0:
                packet_schedule[interval] = []
            random_num = random.randint(0, 99)
            if random_num < 40:
                category = 0
            elif random_num < 65:
                category = 1
            elif random_num < 80:
                category = 2
            elif random_num < 90:
                category = 3
            else:
                category = 4
            if category == 4:
                index1 = random.randint(0, len(city_list) - 1)
                index2 = random.randint(0, len(city_list) - 1)
                city1 = city_list[index1]
                city2 = city_list[index2]
                packet_schedule[interval].append((city1, city2))
            else:
                category_size = len(city_links[category])
                link = random.randint(0, category_size - 1)
                city1, city2 = city_links[category][link]
                order = random.randint(0, 1)
                if order == 0:
                    packet_schedule[interval].append((city1, city2))
                else:
                    packet_schedule[interval].append((city2, city1))


def print_global_counters():
    print(f"::::: GLOBAL COUNTERS :::::")
    print(f"Total packets sent: {num_packets_sent}")
    print(f"Total packets received: {num_packets_received}")
    print(f"Total packets dropped: {num_packets_dropped}")
    print(f"  Number of packets dropped due to exceeding max hops: {num_max_hop_packets_dropped}")
    print(f"  Number of packets dropped due to no satellite overhead source: {no_sat_overhead_cnt}")
    print(f"Number of route calculation failures: {num_route_calc_failures}") # this is essentially max_hop_packets_dropped for directed routing functions
    for r_sat in sat_object_list:
        if r_sat.congestion_cnt > 0:
            print(f"Satellite {r_sat.sat.model.satnum} congestion count: {r_sat.congestion_cnt}")

def main ():
    start_run_time = time.time()
    if do_multithreading:
        print(f"Running with {num_threads} threads")
    if do_disruptions:
        print(f"Running with satellite disruptions")
    
    # ---------- SETUP ------------
    # Load TLEs
    tle_path = './STARLINK-1071.txt'
    #starlink_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'   

    satellites = load.tle_file(tle_path)
    print('Loaded', len(satellites), 'satellites')
    source_sat = satellites[0]
    print(f'Source satellite epoch: {source_sat.epoch.utc_jpl()}')

    # Create a list of satellite objects
    build_constellation(source_sat)

    # Initialize simulation start time
    global cur_time, cur_time_next, routing_name

    cur_time = time_scale.utc(2023, 5, 9, 0, 0, 0)
    cur_time_next = time_scale.utc(2023, 5, 9, 0, 0, 1)
    print(f"Set current time to: {cur_time.utc_jpl()}")
    
    # ---------- ROUTING ------------   

    # build a schedule of packets to send
    build_packet_schedule()
    if do_disruptions:
        build_disruption_schedule() # build a schedule of satellite disruptions

    # call routing algorithm to use to send packets
    #distributed_link_state_routing()
    #directed_dijkstra_distance_routing()
    directed_dijkstra_hop_routing()

    # ---------- RESULTS ------------
    print_global_counters()

    full_run_time = time.time() - start_run_time
    print(f"Full run time for {routing_name}: {floor(full_run_time/60)} minutes and {full_run_time % 60:,.2f} seconds")
    exit ()

    

if __name__ == "__main__":
    main()