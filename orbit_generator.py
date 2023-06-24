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
#from multiprocessing import Process, Queue
import multiprocessing as mp
import multiprocessing.shared_memory

import sys # for recursive get_size() function
import gc # for actualsize() function
import getopt # for command line arguments

# for plotting orbits
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import axes3d
from matplotlib.animation import FuncAnimation

# custom modules
import tri_coordinates

# :: Simulation Options::
do_multithreading = True
do_multiprocessing = False # Doesn't work -- multiprocessing takes precedence over multithreading where appropriate
draw_static_orbits = False
draw_distributed_orbits = False
testing = False
plot_dropped_packets = False
do_disruptions = False
packet_schedule_method = "static" # "random", "alt_random", "static"
packet_schedule_method_options = ["random", "alt_random", "static"]
test_point_to_point = True # routes repeatedly between two static locations over specified time intervals -- MUST BE SET FOR 'STATIC' PACKET SCHEDULE METHOD
routing_name = "Distributed Link State TriCoord" # options: "Directed Dijkstra Hop", "Directed Dijkstra Distance", "Distributed Link State Bearing", "Distributed Link State TriCoord"
routing_name_options = ["Directed Dijkstra Hop", "Directed Dijkstra Distance", "Distributed Link State Bearing", "Distributed Link State TriCoord"]
time_interval = 10 # interval between time increments, measured in seconds
num_time_intervals = 5

# Orbit characteristics
# Starlink Shell 1:  https://everydayastronaut.com/starlink-group-6-1-falcon-9-block-5-2/
sats_per_orbit = 22
orbit_cnt = 72

# Packet variables
packet_bandwidth_per_sec = 100 # the number of packets a satellite can send in a one sec time interval (so this should be multiplied by the time interval to get the number of packets that can be sent in that time interval)
packet_backlog_size = 1000 # the number of packets that can be stored in a satellite's queue (10 sec worth of data)
packet_start_TTL = 10 # the number of seconds a packet can be stored in a satellite's queue before it is dropped
packets_generated_per_interval = 20 # 100 # the number of packets generated per time interval by the packet scheduler

# multiprocessing variables
shm = None

# Multi threading
num_threads = max(os.cpu_count()-2, 1) # 4

# Global counters
no_sat_overhead_cnt = 0
num_packets_dropped = 0
num_max_hop_packets_dropped = 0 # this is a subset of num_packets_dropped
num_route_calc_failures = 0
num_packets_sent = 0
num_packets_received = 0
total_distance_traveled = 0
total_hop_count = 0

# Global variables / trackers
orbit_list = []
sat_object_list = []
cur_time = 0
num_sats = 0
eph = None
packet_schedule = {} # a dictionary with time interval integers as keys and lists of packets as values - the list values are tuples of (src, dest)
disruption_schedule = {} # a dictionary with time interval integers as keys and lists of satellites or regions, along with time intervals, as values
# e.g. {0: [('sat', 443, 3), ('reg', GeographicPosition, 5), ('sat', 843, 1)]}
disrupted_regions_dict = {} # a dictionary with GeographicPosition objects as keys and TTL values as values

# Time variables
time_scale = load.timescale()
secs_per_km = 0.0000033
cur_time_increment = 0

# Adjacent satellite characterisitcs
g_lat_range = 1 # satellites to E/W can fall within +- this value
lateral_antenna_range = 30 #30  # in degrees.  Lateral satellite bearings can fall +- lateral_antenna_range / 2
# lateral antenna interface bearings
port_interface_bearing = 70 #90
starboard_interface_bearing = 250 #270
fore_port_interface_bearing = 25 # 45
fore_starboard_interface_bearing = 335 #315
aft_port_interface_bearing = 155 #135
aft_starboard_interface_bearing = 205 #225
# maximum antenna range in km
max_lateral_antenna_range = 1500 # 1500 km

# Ground Station characteristics
req_elev = 40 # https://www.reddit.com/r/Starlink/comments/i1ua2y/comment/g006krb/?utm_source=share&utm_medium=web2x

# :: Routing Global Variables ::

# Distributed routing admin values
distributed_max_hop_count = 100

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
        self.aft_port_sat_satnum = None
        self.fore_port_sat_satnum = None
        self.aft_starboard_sat_satnum = None
        self.fore_starboard_sat_satnum = None
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
        self.fore_port_int_up = True
        self.aft_port_int_up = True
        self.port_int_up = True
        self.starboard_int_up = True
        self.fore_starboard_int_up = True
        self.aft_starboard_int_up = True
        self.heading = None # ensure this is referenced only when you know it has been set for the current time
        self.congestion_cnt = 0
        self.is_disrupted = False
        self.disruption_ttl = 0

    # ::: distributed routing packet structure: {'prev_hop_list': [prev_hop_list], 'distance_traveled': dist, 'dest_gs': dest_gs, 'TTL': packet_TTL, 'dest_satnum': dest_satnum} - packet is at destination when satellite is above dest_gs
    def distributed_routing_link_state_process_packet_queue(self):
        if do_disruptions:
            if self.is_disrupted:
                print(f"::distributed_routing_link_state_process_packet_queue: satellite {self.satnum} is disrupted - not processing packets")
                return -1 # don't process packets if the satellite is disrupted

        if (self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval) or (len(self.packet_qu) == 0):
            return -1
        sent_packet = False

        global num_packets_dropped, num_max_hop_packets_dropped, num_packets_received, total_distance_traveled, total_hop_count, no_sat_overhead_cnt
        for packet in self.packet_qu:
            if self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval:  # First, check if satellite exceeded packet bandwidth; notify neighbors of congestion if so
                print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet bandwidth exceeded.  Congestion on-demand sent to neighbors")
                self.update_neigh_state(congestion = True) # tell neighbors of congestion on-demand (this will be cleared next time interval if packet count is low enough)
                self.congestion_cnt += 1
                break
            if 'dest_satnum' in packet:
                if packet['dest_satnum'] == self.sat.model.satnum:
                    #print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet received by destination satellite")
                    topo_position = (self.sat - packet['dest_gs']).at(cur_time)
                    _, _, dist = topo_position.altaz()
                    packet['distance_traveled'] += dist.km
                    distance_traveled = packet['distance_traveled']
                    hop_count = len(packet['prev_hop_list'])
                    print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet reached destination satellite in {hop_count} hops.  Total distance: {int(distance_traveled):,.0f}km (transit time: {secs_per_km * int(distance_traveled):.2f} seconds)")
                    #print(f"Packet traveled through sats: {packet['prev_hop_list']}")
                    num_packets_received += 1
                    total_distance_traveled += distance_traveled
                    total_hop_count += hop_count
                    if draw_static_orbits:
                        if len(packet['prev_hop_list']) > 30:
                            draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['source_gs'], packet['dest_gs']], title=f"Distributed link-state {routing_name}, {len(packet['prev_hop_list'])} hops, total distance: {int(packet['distance_traveled'])}km", draw_lines = True, draw_sphere = True)
                    self.packet_qu.remove(packet)
                    sent_packet = True
                    self.packets_sent_cnt += 1
                    continue
            else:
                if self.is_overhead_of(packet['dest_gs']): # Second, check if satellite is overhead destination ground station / terminal; deliver packet if so
                    print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet delivered to destination ground station / terminal")
                    topo_position = (self.sat - packet['dest_gs']).at(cur_time)
                    _, _, dist = topo_position.altaz()
                    packet['distance_traveled'] += dist.km
                    distance_traveled = packet['distance_traveled']
                    hop_count = len(packet['prev_hop_list'])
                    print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet reached destination in {hop_count} hops.  Total distance: {int(distance_traveled):,.0f}km (transit time: {secs_per_km * int(distance_traveled):.2f} seconds)") # == source: {packet['source_gs']} -- destination: {packet['dest_gs']}")
                    print(f"Packet traveled through sats: {packet['prev_hop_list']}")
                    num_packets_received += 1
                    total_distance_traveled += distance_traveled
                    total_hop_count += hop_count
                    if draw_static_orbits:
                        if len(packet['prev_hop_list']) > 30:
                            draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['source_gs'], packet['dest_gs']], title=f"Distributed link-state {routing_name}, {len(packet['prev_hop_list'])} hops, total distance: {int(packet['distance_traveled'])}km", draw_lines = True, draw_sphere = True)
                    self.packet_qu.remove(packet)
                    sent_packet = True
                    self.packets_sent_cnt += 1
                    continue
            if len(packet['prev_hop_list']) > distributed_max_hop_count: # Third, check if packet has taken too many hops; drop if so
                print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet exceeded max hop count.  Dropping packet.")
                print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Packet exceeded max hop count.  Dropping packet.")
                num_max_hop_packets_dropped += 1
                num_packets_dropped += 1
                if plot_dropped_packets:
                    draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['source_gs'], packet['dest_gs']], title=f"distributed link-state dropped packet - {len(packet['prev_hop_list'])} hops", draw_lines = True, draw_sphere = True)
                self.packet_qu.remove(packet)
            else: # Fourth, find next hop for packet; add distance of hop to counter; and add to next hop's packet queue
                #print(f"::distributed_routing_link_state_process_packet_queue:: {self.sat.model.satnum}: Finding next hop.")
                if len(packet['prev_hop_list']) == 0:
                    prev_hop = None
                else:
                    prev_hop = packet['prev_hop_list'][-1]
                target_satnum = self.find_next_link_state_hop(packet['dest_gs'], packet['dest_satnum'], prev_hop) # find_next_link_state_hop() is function that performs routing selection
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
        global no_sat_overhead_cnt, num_packets_dropped, num_packets_received, num_route_calc_failures, total_distance_traveled, total_hop_count

        if do_disruptions:
            if self.is_disrupted:
                print(f"::directed_routing_process_packet_queue: satellite {self.satnum} is disrupted, so not processing packets")
                return -1 # don't process packets if satellite is disrupted

        if (self.packets_sent_cnt >= packet_bandwidth_per_sec * time_interval) or (len(self.packet_qu) == 0):
            return -1
        sent_packet = False
        # Identify which neighbor sats are available on each interface
        neigh_satnum_list = self.get_list_of_cur_neighbor_satnums()

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
                _, _, dist = (self.sat - packet['dest_gs']).at(cur_time).altaz()
                packet['distance_traveled'] += dist.km
                distance_traveled = packet['distance_traveled']
                hop_count = len(packet['prev_hop_list'])
                print(f"{self.sat.model.satnum}: Packet reached destination in {hop_count} hops.  Total distance: {distance_traveled:,.0f}km (transit time: {secs_per_km * int(distance_traveled):.2f} seconds)")
                if draw_static_orbits:
                    if len(packet['prev_hop_list']) > 30:
                        draw_static_plot(packet['prev_hop_list'], terminal_list = [packet['dest_gs']], title=f"Directed_routing: {routing_name}, {hop_count} hops, total distance: {distance_traveled:,.0f}km", draw_lines = True, draw_sphere = True)
                num_packets_received += 1
                total_distance_traveled += distance_traveled
                total_hop_count += hop_count
                self.packet_qu.remove(packet)
                sent_packet = True
                self.packets_sent_cnt += 1
            else:
                target_satnum = packet['next_hop_list'].pop() #the head of the next_hop_list
                if target_satnum in neigh_satnum_list: # see if target_satnum is available on any interface
                    packet['prev_hop_list'].append(self.sat.model.satnum)
                    target_distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, target_satnum)
                    packet['distance_traveled'] += target_distance
                    add_to_packet_qu_by_satnum(target_satnum, packet) # add packet to target sat's packet queue
                    
                    # packet has been given to next satellite, so remove from current satellite's packet queue
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
    
    def check_neighboring_orbit_sat_available(self, neighboring_orbit_num): # returns satnum if sat is within range (None otherwise).  If satnum is other than None, interface will indicate which ('port'/'starboard')
        interfaces = ['port', 'starboard', 'fore_port', 'fore_starboard', 'aft_port', 'aft_starboard']
        neighboring_satnum_list = []
        # get our bearings
        heading = get_heading_by_satnum_degrees(self.sat.model.satnum)
        #fore_port_bearing = 45  # moving these to global variables
        #fore_starboard_bearing = 315
        #aft_port_bearing = 135
        #aft_starboard_bearing = 225
        # find min/max for each interface
        port_range_min = port_interface_bearing-int(lateral_antenna_range/2)
        port_range_max = port_interface_bearing+int(lateral_antenna_range/2)
        starboard_range_min = starboard_interface_bearing-int(lateral_antenna_range/2)
        starboard_range_max = starboard_interface_bearing+int(lateral_antenna_range/2)
        fore_port_range_min = fore_port_interface_bearing-int(lateral_antenna_range/2)
        fore_port_range_max = fore_port_interface_bearing+int(lateral_antenna_range/2)
        fore_starboard_range_min = fore_starboard_interface_bearing-int(lateral_antenna_range/2)
        fore_starboard_range_max = fore_starboard_interface_bearing+int(lateral_antenna_range/2)
        aft_port_range_min = aft_port_interface_bearing-int(lateral_antenna_range/2)
        aft_port_range_max = aft_port_interface_bearing+int(lateral_antenna_range/2)
        aft_starboard_range_min = aft_starboard_interface_bearing-int(lateral_antenna_range/2)
        aft_starboard_range_max = aft_starboard_interface_bearing+int(lateral_antenna_range/2)
        #print(f"::check_neighboring_orbit_sat_available:: Interface intervals: fore_port: {fore_port_range_min}-{fore_port_range_max}, fore_starboard: {fore_starboard_range_min}-{fore_starboard_range_max}, aft_port: {aft_port_range_min}-{aft_port_range_max}, aft_starboard: {aft_starboard_range_min}-{aft_starboard_range_max}")

        # find min/max satnums for target orbit
        min_satnum = neighboring_orbit_num * sats_per_orbit
        max_satnum = min_satnum + sats_per_orbit

        # loop through neighboring orbit satellites and find which are within range of each interface
        tentative_satnum_list = []
        for test_satnum in range(min_satnum, max_satnum):
            test_sat_bearing = get_rel_bearing_by_satnum_degrees(self.sat.model.satnum, test_satnum, heading)
            distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, test_satnum)
            if distance > max_lateral_antenna_range:
                continue  # Don't try to connect to lateral satellites with distances > 1000km - seems like an unreasonable ability 
            #print(f"::check_neighboring_orbit_sat_available:: Testing satnum {test_satnum} at bearing {test_sat_bearing:.0f} with distance {distance:,.0f}")
            if (test_sat_bearing - port_range_min) % 360 <= (port_range_max - port_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'port'))
            elif (test_sat_bearing - starboard_range_min) % 360 <= (starboard_range_max - starboard_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'starboard'))
            elif (test_sat_bearing - fore_port_range_min) % 360 <= (fore_port_range_max - fore_port_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'fore_port'))
            elif (test_sat_bearing - fore_starboard_range_min) % 360 <= (fore_starboard_range_max - fore_starboard_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'fore_starboard'))
            elif (test_sat_bearing - aft_port_range_min) % 360 <= (aft_port_range_max - aft_port_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'aft_port'))
            elif (test_sat_bearing - aft_starboard_range_min) % 360 <= (aft_starboard_range_max - aft_starboard_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'aft_starboard'))
        
        if len(tentative_satnum_list) == 0:
            return []
        # find closest satellite for each interface and append to neighboring_satnum_list
        for interface in interfaces:
            interface_list = []
            for tentative_tuple in tentative_satnum_list:
                if interface in tentative_tuple:
                    if tentative_tuple[1] == interface:
                        interface_list.append(tentative_tuple[0])
            if len(interface_list) == 0:
                continue
            elif len(interface_list) == 1:
                neighboring_satnum_list.append((interface_list[0], interface))
            else:
                closest_satnum = None
                min_distance = float('inf')
                for test_satnum in interface_list:
                    distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, test_satnum)
                    if distance < min_distance:
                        closest_satnum = test_satnum
                        min_distance = distance
                neighboring_satnum_list.append((closest_satnum, interface))
        
        return neighboring_satnum_list

    """
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
    """
    """
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
    """
    """
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
    """
    def get_fore_sat(self):
        return sat_object_list[self.fore_sat_satnum] # fore satellite never changes
    
    def get_aft_sat(self):
        return sat_object_list[self.aft_sat_satnum] # aft satellite never changes
    """
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
    """

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

    # calculates satnum of next hop or None if no next hop satellite is available
    def find_next_link_state_hop(self, dest_gs, dest_satnum, prev_hop_satnum):
        global routing_name
        # update current neighboring satellites on each interface
        self.update_current_neighbor_sats()
        
        avail_neigh_routing_sats = []
        if self.fore_int_up:
            avail_neigh_routing_sats.append(sat_object_list[self.fore_sat_satnum])
        if self.aft_int_up:
            avail_neigh_routing_sats.append(sat_object_list[self.aft_sat_satnum])
        if self.port_int_up and (not self.port_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.port_sat_satnum])
        if self.starboard_int_up and (not self.starboard_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.starboard_sat_satnum])
        if self.fore_port_int_up and (not self.fore_port_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.fore_port_sat_satnum])
        if self.fore_starboard_int_up and (not self.fore_starboard_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.fore_starboard_sat_satnum])
        if self.aft_port_int_up and (not self.aft_port_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.aft_port_sat_satnum])
        if self.aft_starboard_int_up and (not self.aft_starboard_sat_satnum is None):
            avail_neigh_routing_sats.append(sat_object_list[self.aft_starboard_sat_satnum])
            
        if routing_name == "Distributed Link State TriCoord":
            return self.link_state_routing_method_triCoord(avail_neigh_routing_sats, dest_satnum, prev_hop_satnum)
        elif routing_name == "Distributed Link State Bearing":
            return self.link_state_routing_method_neigh_bearing(avail_neigh_routing_sats, dest_gs) # the actual routing algorithm to find the next hop
        else:
            print(f"::find_next_link_state_hop:: No known routing name specified.  routing_name: {routing_name}")
            return None
        
    # Requires use of tri_coordinates.py module
    # An implementation of Routing Method 2 using the connectivity simulator
    # Uses list of avail neighbor satellites, the destination satellite satnum, and the previous hop satellite satnum
    # Returns satnum of next hop or None if next hop could not be found
    # Must have neighbor stats updated prior to calling!
    def link_state_routing_method_triCoord(self, available_neigh_routing_sats, dest_satnum, prev_hop_satnum):
        name = "Distributed Link State TriCoord"
        next_hop_satnum = None
        # get triCoordinates of current and destination satellites, then calculate the difference for each axis
        curr_A, curr_B, curr_C = tri_coordinates.get_sat_ABC(self.sat.model.satnum)
        dest_A, dest_B, dest_C = tri_coordinates.get_sat_ABC(dest_satnum)
        
            
        A_diff, B_diff, C_diff = tri_coordinates.calc_triCoord_dist(curr_A, curr_B, curr_C, dest_A, dest_B, dest_C)

        
        if not prev_hop_satnum is None: # See if we can just send packet along previous axis and direction
            prev_hop_A, prev_hop_B, prev_hop_C = tri_coordinates.get_sat_ABC(prev_hop_satnum)
            prev_hop_diff_A, prev_hop_diff_B, _ = tri_coordinates.calc_triCoord_dist(curr_A, curr_B, curr_C, prev_hop_A, prev_hop_B, prev_hop_C)
            # Find axis with no change from last hop - that's the axis the packet came in on and is the inferior axis
        
            axis_change_needed = False
            if prev_hop_diff_A == 0:
                #inferior_axis = 'A'
                if B_diff == 0 or C_diff == 0:
                    axis_change_needed = True
            elif prev_hop_diff_B == 0:
                #inferior_axis = 'B'
                if A_diff == 0 or C_diff == 0: 
                    axis_change_needed = True
            else:
                if A_diff == 0 or B_diff == 0: 
                    axis_change_needed = True
                #inferior_axis = 'C' 
        
            if not axis_change_needed: # continue sending packet along current axis
                if (prev_hop_satnum == self.fore_sat_satnum) and (not self.aft_sat_satnum is None):
                    next_hop_satnum = self.aft_sat_satnum
                elif (prev_hop_satnum == self.aft_sat_satnum) and (not self.fore_sat_satnum is None):
                    next_hop_satnum = self.fore_sat_satnum
                elif (prev_hop_satnum == self.port_sat_satnum) and (not self.starboard_sat_satnum is None):
                    next_hop_satnum = self.starboard_sat_satnum
                elif (prev_hop_satnum == self.starboard_sat_satnum) and (not self.port_sat_satnum is None):
                    next_hop_satnum = self.port_sat_satnum
                elif (prev_hop_satnum == self.fore_port_sat_satnum) and (not self.aft_starboard_sat_satnum is None):
                    next_hop_satnum = self.aft_starboard_sat_satnum
                elif (prev_hop_satnum == self.fore_starboard_sat_satnum) and (not self.aft_port_sat_satnum is None):
                    next_hop_satnum = self.aft_port_sat_satnum
                elif (prev_hop_satnum == self.aft_port_sat_satnum) and (not self.fore_starboard_sat_satnum is None):
                    next_hop_satnum = self.fore_starboard_sat_satnum
                elif (prev_hop_satnum == self.aft_starboard_sat_satnum) and (not self.fore_port_sat_satnum is None):
                    next_hop_satnum = self.fore_port_sat_satnum
                if not next_hop_satnum is None:
                    return next_hop_satnum
        
        # Need to identify new axis to send packet
        diff_list = [abs(A_diff), abs(B_diff), abs(C_diff)]
        axis_list = ['A', 'B', 'C']
        print("::link_state_routing_method_triCoord:: Axis direction updated needed!")
        max_diff = max(diff_list)
        if (max_diff == abs(A_diff)):
            major_axis = 'A'
            axis_list.remove('A')
            if (A_diff < 0): # A_diff already accounted for shortest direction
                major_direction = 'neg'
            else:
                major_direction = 'pos'
        elif (max_diff == abs(B_diff)):
            major_axis = 'B'
            axis_list.remove('B')
            if (B_diff < 0): # B_diff already accounted for shortest direction
                major_direction = 'neg'
            else:
                major_direction = 'pos'
        else:
            major_axis = 'C'
            axis_list.remove('C')
            if (C_diff < 0): # C_diff already accounted for shortest direction
                major_direction = 'neg'
            else:
                major_direction = 'pos'

        # Identify Inferior Axis (the axis with the smallest difference)
        min_diff = min(diff_list)
        if (min_diff == abs(A_diff)) and ('A' in axis_list):
            inferior_axis = 'A'
            if A_diff < 0:
                inferior_direction = 'neg'
            else:
                inferior_direction = 'pos'
            axis_list.remove('A')
        elif (min_diff == abs(B_diff)) and ('B' in axis_list):
            inferior_axis = 'B'
            if B_diff < 0:
                inferior_direction = 'neg'
            else:
                inferior_direction = 'pos'
            axis_list.remove('B')
        else:
            inferior_axis = 'C'
            if C_diff < 0:
                inferior_direction = 'neg'
            else:
                inferior_direction = 'pos'
            axis_list.remove('C')
        
        # Minor axis is the remaining coordinate value
        minor_axis = axis_list[0]
        if minor_axis == 'A':
            if A_diff < 0:
                minor_direction = 'neg'
            else:
                minor_direction = 'pos'
        elif minor_axis == 'B':
            if B_diff < 0:
                minor_direction = 'neg'
            else:
                minor_direction = 'pos'
        else:
            if C_diff < 0:
                minor_direction = 'neg'
            else:
                minor_direction = 'pos'

        # Identify which axes are available and the satnum of satellite along that axis

        # How about I calculate triCoords for each neighbor sat, then have cases of axis
        # value tests to identify the logical direction of each neighbor
        # Will use compass directions of logical map for reference names
        neigh_axes_dict = {}
        for neigh_routing_sat in available_neigh_routing_sats:
            neigh_A, neigh_B, neigh_C = tri_coordinates.get_sat_ABC(neigh_routing_sat.sat.model.satnum)
            A_diff, B_diff, C_diff = tri_coordinates.calc_triCoord_dist(curr_A, curr_B, curr_C, neigh_A, neigh_B, neigh_C)
            if (A_diff == 0) and (B_diff == -1) and (C_diff == 1):
                neigh_axes_dict['logical_N'] = neigh_routing_sat.sat.model.satnum
            elif (A_diff == 0) and (B_diff == 1) and (C_diff == -1):
                neigh_axes_dict['logical_S'] = neigh_routing_sat.sat.model.satnum
            elif (A_diff == 1) and (B_diff == 0) and (C_diff == 1):
                neigh_axes_dict['logical_NE'] = neigh_routing_sat.sat.model.satnum
            elif (A_diff == 1) and (B_diff == 1) and (C_diff == 0):
                neigh_axes_dict['logical_SE'] = neigh_routing_sat.sat.model.satnum
            elif (A_diff == -1) and (B_diff == 0) and (C_diff == -1):
                neigh_axes_dict['logical_SW'] = neigh_routing_sat.sat.model.satnum
            elif (A_diff == -1) and (B_diff == -1) and (C_diff == 0):
                neigh_axes_dict['logical_NW'] = neigh_routing_sat.sat.model.satnum
            else:
                print(f"::link_state_routing_method_triCoord:: Unexpected neighbor coordinates!\n\tCurrent satnum: {self.sat.model.satnum} ({curr_A},{curr_B},{curr_C}), Neighbor satnum: {neigh_routing_sat.sat.model.satnum} ({neigh_A},{neigh_B},{neigh_C})\n\tdiff: ({A_diff},{B_diff},{C_diff})")

        # Major, Minor, and Inferior axes identified, along with direction
        # Available logical directions identified, along with associated satnums
        # Select highest available priority route that does not return packet to previous hop
        
        # Priority 1: Reduce major_axis along inferior_axis
        priority_direction = tri_coordinates.calc_triCoord_next_hop_logical_direction(major_axis, major_direction, inferior_axis)
        if priority_direction in neigh_axes_dict:
            next_hop_satnum = neigh_axes_dict[priority_direction]
            if next_hop_satnum != prev_hop_satnum:
                print(f"Priority 1 direction: {priority_direction}, next hop satnum: {next_hop_satnum}")
                return next_hop_satnum
        print(f"Priority 1 direction: {priority_direction} NOT AVAILABLE")

        # Priority 2: Reduce major_axis along minor_axis
        priority_direction = tri_coordinates.calc_triCoord_next_hop_logical_direction(major_axis, major_direction, minor_axis)
        if priority_direction in neigh_axes_dict:
            next_hop_satnum = neigh_axes_dict[priority_direction]
            if next_hop_satnum != prev_hop_satnum:
                print(f"Priority 2 direction: {priority_direction}, next hop satnum: {next_hop_satnum}")
                return next_hop_satnum
        print(f"Priority 2 direction: {priority_direction} NOT AVAILABLE")
        
        # Priority 3: Reduce minor_axis along inferior_axis    
        priority_direction = tri_coordinates.calc_triCoord_next_hop_logical_direction(minor_axis, minor_direction, inferior_axis)
        if priority_direction in neigh_axes_dict:
            next_hop_satnum = neigh_axes_dict[priority_direction]
            if next_hop_satnum != prev_hop_satnum:
                print(f"Priority 3 direction: {priority_direction}, next hop satnum: {next_hop_satnum}")
                return next_hop_satnum
        print(f"Priority 3 direction: {priority_direction} NOT AVAILABLE")

        # Priority 4: Reduce inferior_axis along minor_axis
        priority_direction = tri_coordinates.calc_triCoord_next_hop_logical_direction(inferior_axis, inferior_direction, minor_axis)
        if priority_direction in neigh_axes_dict:
            next_hop_satnum = neigh_axes_dict[priority_direction]
            if next_hop_satnum != prev_hop_satnum:
                print(f"Priority 4 direction: {priority_direction}, next hop satnum: {next_hop_satnum}")
                return next_hop_satnum
        print(f"Priority 4 direction: {priority_direction} NOT AVAILABLE")

        # Priority 5: Reduce minor_axis along major_axis
        priority_direction = tri_coordinates.calc_triCoord_next_hop_logical_direction(minor_axis, minor_direction, major_axis)
        if priority_direction in neigh_axes_dict:
            next_hop_satnum = neigh_axes_dict[priority_direction]
            if next_hop_satnum != prev_hop_satnum:
                print(f"Priority 5 direction: {priority_direction}, next hop satnum: {next_hop_satnum}")
                return next_hop_satnum
        print(f"Priority 5 direction: {priority_direction} NOT AVAILABLE")

        # Priority 6: Reduce inferior_axis along major_axis
        priority_direction = tri_coordinates.calc_triCoord_next_hop_logical_direction(inferior_axis, inferior_direction, major_axis)
        if priority_direction in neigh_axes_dict:
            next_hop_satnum = neigh_axes_dict[priority_direction]
            if next_hop_satnum != prev_hop_satnum:
                print(f"Priority 6 direction: {priority_direction}, next hop satnum: {next_hop_satnum}")
                return next_hop_satnum
        print(f"Priority 6 direction: {priority_direction} NOT AVAILABLE")
        print("::link_state_routing_method_triCoord:: Unable to find next hop!")
        print(f"neigh_axes_dict: {neigh_axes_dict}\navailable_neigh_routing_sats: {available_neigh_routing_sats}")
        return None

    # Calculates next hop based on bearing of destination and neighboring satellites
    # Receives a list of available neighbor satnums
    # Returns satnum of next hop or None if no next hop could be calculated
    # Must have neighbor stats updated prior to calling!
    def link_state_routing_method_neigh_bearing(self, avail_neigh_routing_sats, dest_gs):
        name = "Distributed Link State Bearing"
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
            print("::link_state_routing_method_neigh_bearing::  No next hop sat could be calculated")
            return None
        return nearest_neigh_routing_sat.sat.model.satnum

    def calc_bearing_dist_metric(self, neigh_routing_sat, dest_gs):
        # find bearing of destination gs
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
        elif neigh_sat_interface == 'fore_port':
            neigh_sat_interface_bearing = fore_port_interface_bearing 
        elif neigh_sat_interface == 'fore_starboard':
            neigh_sat_interface_bearing = fore_starboard_interface_bearing 
        elif neigh_sat_interface == 'aft_port':
            neigh_sat_interface_bearing = aft_port_interface_bearing 
        elif neigh_sat_interface == 'aft_starboard':
            neigh_sat_interface_bearing = aft_starboard_interface_bearing 
        else:
            print(f"Neighbor sat interface: {neigh_sat_interface} not recognized, aborting")
            exit()

        # calculate max/min for each interface metric (correct, lateral_plus, lateral, lateral_minus, incorrect)
        interface_correct_lower_range = (neigh_sat_interface_bearing - (interface_correct_range/2) + 360) % 360
        interface_correct_upper_range = (neigh_sat_interface_bearing + (interface_correct_range/2) + 360) % 360
        interface_lateral_plus_lower_range = (neigh_sat_interface_bearing - (interface_lateral_range/4) + 360) % 360
        interface_lateral_plus_upper_range = (neigh_sat_interface_bearing + (interface_lateral_range/4) + 360) % 360
        interface_lateral_lower_range = (neigh_sat_interface_bearing - (interface_lateral_range/2) + 360) % 360
        interface_lateral_upper_range = (neigh_sat_interface_bearing + (interface_lateral_range/2) + 360) % 360
        interface_lateral_minus_lower_range = (neigh_sat_interface_bearing - (interface_lateral_range/1.5) + 360) % 360
        interface_lateral_minus_upper_range = (neigh_sat_interface_bearing + (interface_lateral_range/1.5) + 360) % 360
        # test dest_bearing against each interface range and assign value to each interface metric (correct, lateral_plus, lateral, lateral_minus, incorrect)
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
        
        return bearing_metric


    # calculate the distance metric for link state routing protocol    
    # using: destination bearing, satellite bandwidth, whether congested, and whether recently down
    def calc_link_state_dist_metric(self, neigh_routing_sat, dest_gs, bearing_only = False):
        # first check if neighbor routing sat is in neighbor state dict
        if not neigh_routing_sat.sat.model.satnum in self.neigh_state_dict:
            return 0
        
        bearing_metric = self.calc_bearing_dist_metric(neigh_routing_sat, dest_gs)
        
        if bearing_only:
            return bearing_metric
        
        # calculate distance metric for neighbor satellite bandwidth based on which interface it is
        # if neighbor sat is for/aft, it has good bandwidth
        neigh_sat_interface = self.neigh_state_dict[neigh_routing_sat.sat.model.satnum]['interface_name']
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

    def update_current_neighbor_sats(self):
        # first find which sats, if any, are on each interface
        self.port_sat_satnum = None
        self.starboard_sat_satnum = None
        self.fore_port_sat_satnum = None
        self.fore_starboard_sat_satnum = None 
        self.aft_port_sat_satnum = None
        self.aft_starboard_sat_satnum = None
        preceeding_orbit_satnum_list = self.check_neighboring_orbit_sat_available(self.preceeding_orbit_number)
        succeeding_orbit_satnum_list = self.check_neighboring_orbit_sat_available(self.succeeding_orbit_number)
        # _orbit_satnum_list has format [(satnum, interface), ...]
        # possible interfaces: 'fore_port', 'fore_starboard', 'aft_port', 'aft_starboard'
        if len(preceeding_orbit_satnum_list) > 0:
            for satnum_tuple in preceeding_orbit_satnum_list:
                if satnum_tuple[1] == 'port':
                    self.port_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'starboard':
                    self.starboard_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'fore_port':
                    self.fore_port_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'fore_starboard':
                    self.fore_starboard_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'aft_port':
                    self.aft_port_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'aft_starboard':
                    self.aft_starboard_sat_satnum = satnum_tuple[0]
        if len(succeeding_orbit_satnum_list) > 0:
            for satnum_tuple in succeeding_orbit_satnum_list:
                if satnum_tuple[1] == 'port':
                    self.port_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'starboard':
                    self.starboard_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'fore_port':
                    self.fore_port_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'fore_starboard':
                    self.fore_starboard_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'aft_port':
                    self.aft_port_sat_satnum = satnum_tuple[0]
                elif satnum_tuple[1] == 'aft_starboard':
                    self.aft_starboard_sat_satnum = satnum_tuple[0]

    # update the state of links to all direct neighbor sats
    def publish_state_to_neighbors(self, congestion = None):
        if do_disruptions:
            if self.is_disrupted:  # if this sat is disrupted, don't update state to neighbors
                print(f"::update_state_to_neighbors:: sat {self.sat.model.satnum} is disrupted, not updating state to neighbors")
                return
            
        # update current neighboring satellites on each interface
        self.update_current_neighbor_sats()

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
        # check if current satellite is congested - should this be based on _link congestion_ rather than satellite congestion?
        if congestion is None:
            if len(self.packet_qu) > int((packet_bandwidth_per_sec * time_interval) * .8):  # are we at 80% of our packet queue capacity?
                congestion_status = True
            else:
                congestion_status = False
        else:
            congestion_status = congestion
            
        # update link state for all available neighbors
        neigh_congested, neigh_connection_down = self.check_internal_link_status()
        interface = None
        for neigh_routing_sat in neigh_routing_sat_list:
            if (neigh_routing_sat.sat.model.satnum == self.fore_sat_satnum):  # designate the interface this satellite is on (note - neighbor satellite interface is the opposite of the current satellite interface [ie, port int talks to starboard int, etc...])
                interface = 'aft'
            elif (neigh_routing_sat.sat.model.satnum == self.aft_sat_satnum):
                interface = 'fore'
            elif (neigh_routing_sat.sat.model.satnum == self.starboard_sat_satnum):
                interface = 'starboard'
            elif (neigh_routing_sat.sat.model.satnum == self.port_sat_satnum):
                interface = 'port'
            elif (neigh_routing_sat.sat.model.satnum == self.fore_port_sat_satnum):
                interface = 'fore_port'
            elif (neigh_routing_sat.sat.model.satnum == self.fore_starboard_sat_satnum):
                interface = 'fore_starboard'
            elif (neigh_routing_sat.sat.model.satnum == self.aft_port_sat_satnum):
                interface = 'aft_port'
            elif (neigh_routing_sat.sat.model.satnum == self.aft_starboard_sat_satnum):
                interface = 'aft_starboard'
            if interface is None:
                print(f"publish_state_to_neighbors: interface is None, aborting")
                exit()
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

    def get_list_of_cur_neighbor_satnums(self):
        self.update_current_neighbor_sats()
        cur_neigh_satnum_list = []
        if self.fore_int_up:
            cur_neigh_satnum_list.append(self.fore_sat_satnum)
        if self.aft_int_up:
            cur_neigh_satnum_list.append(self.aft_sat_satnum)
        if self.port_int_up and self.port_sat_satnum is not None:
            cur_neigh_satnum_list.append(self.port_sat_satnum)
        if self.starboard_int_up and self.starboard_sat_satnum is not None:
            cur_neigh_satnum_list.append(self.starboard_sat_satnum)
        if self.fore_port_int_up and self.fore_port_sat_satnum is not None:
            cur_neigh_satnum_list.append(self.fore_port_sat_satnum)
        if self.fore_starboard_int_up and self.fore_starboard_sat_satnum is not None:
            cur_neigh_satnum_list.append(self.fore_starboard_sat_satnum)
        if self.aft_port_int_up and self.aft_port_sat_satnum is not None:
            cur_neigh_satnum_list.append(self.aft_port_sat_satnum)
        if self.aft_starboard_int_up and self.aft_starboard_sat_satnum is not None:
            cur_neigh_satnum_list.append(self.aft_starboard_sat_satnum)
        return cur_neigh_satnum_list

    def get_list_of_cur_sat_neighbors(self):
        self.update_current_neighbor_sats()
        cur_sat_neigh_list = []
        if self.fore_int_up:
            cur_sat_neigh_list.append(sat_object_list[self.fore_sat_satnum])
        if self.aft_int_up:
            cur_sat_neigh_list.append(sat_object_list[self.aft_sat_satnum])
        if self.port_int_up and self.port_sat_satnum is not None:
            cur_sat_neigh_list.append(sat_object_list[self.port_sat_satnum])
        if self.starboard_int_up and self.starboard_sat_satnum is not None:
            cur_sat_neigh_list.append(sat_object_list[self.starboard_sat_satnum])
        if self.fore_port_int_up and self.fore_port_sat_satnum is not None:
            cur_sat_neigh_list.append(sat_object_list[self.fore_port_sat_satnum])
        if self.aft_port_int_up and self.aft_port_sat_satnum is not None:
            cur_sat_neigh_list.append(sat_object_list[self.aft_port_sat_satnum])
        if self.fore_starboard_int_up and self.fore_starboard_sat_satnum is not None:
            cur_sat_neigh_list.append(sat_object_list[self.fore_starboard_sat_satnum])
        if self.aft_starboard_int_up and self.aft_starboard_sat_satnum is not None:
            cur_sat_neigh_list.append(sat_object_list[self.aft_starboard_sat_satnum])
        return cur_sat_neigh_list

# End Routing sat class
# From https://towardsdatascience.com/the-strange-size-of-python-objects-in-memory-ce87bdfbb97f
def actualsize(input_obj):
    memory_size = 0
    ids = set()
    objects = [input_obj]
    while objects:
        new = []
        for obj in objects:
            if id(obj) not in ids:
                ids.add(id(obj))
                memory_size += sys.getsizeof(obj)
                new.append(obj)
        objects = gc.get_referents(*new)
    return memory_size

# From https://goshippo.com/blog/measure-real-size-any-python-object/
def get_size(obj, seen=None):
    """Recursively finds size of objects"""
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    # Important mark as seen *before* entering recursion to gracefully handle
    # self-referential objects
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_size(v, seen) for v in obj.values()])
        size += sum([get_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__dict__'):
        size += get_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_size(i, seen) for i in obj])
    return size


## :: General Functions ::
# satellite updates it's internal neigh link states and sends updates to own neighbors
# self.neigh_state_dict-  key: satnum, value is link_state dictionary:
                                        # {interface: ('fore'/'aft'/'port'/'starboard'), - self setting
                                        #  neigh_up (True/False),         - self setting
                                        #  last_neigh_status: (time),     - neigh setting
                                        #  neigh_last_down:  (time),  - self setting
                                        #  neigh_congested: (True/False)} - neigh setting

# multi-threaded version of publish_state_to_neighbors()
def mt_publish_state_to_neighbors(thread_num):
    sat_object_range = floor(len(sat_object_list) / num_threads)
    start = thread_num * sat_object_range
    end = start + sat_object_range
    if thread_num == num_threads - 1:
        end = len(sat_object_list)
    print(f"::mt_update_neigh_state():: thread {thread_num} : publishing states to neighbors from {start} to {end}", end='\r')
    for r_sat in sat_object_list[start:end]:
        r_sat.publish_state_to_neighbors()
    print(f"::mt_update_neigh_state():: thread {thread_num} : finished publishing states to neighbors", end='\r')

def mt_update_neigh_state_table(thread_num):
    sat_object_range = floor(len(sat_object_list) / num_threads)
    start = thread_num * sat_object_range
    end = start + sat_object_range
    if thread_num == num_threads - 1:
        end = len(sat_object_list)
    print(f"::mt_update_neigh_state_table():: thread {thread_num} : updating internal states of neighbors from {start} to {end}", end='\r')
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
            thread = threading.Thread(target=mt_publish_state_to_neighbors, args=(index,), daemon=True)
            thread.start()
            thread_list.append(thread)
        for thread in thread_list:
            thread.join()
    else:
        for r_sat in sat_object_list:
            print(f"r_sat.sat.model.satnum: {r_sat.sat.model.satnum}", end="\r")
            r_sat.publish_state_to_neighbors() 
    print("\n::all_sats_update_neigh_state() :: updating internal states of neighbors")

    # now update those link states internally
    if do_multithreading:
        thread_list = []
        for index in range(num_threads):
            thread = threading.Thread(target=mt_update_neigh_state_table, args=(index,), daemon=True)
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
    #print(f"::increment_time:: Current time incremented to: {cur_time.utc_jpl()}, time increment: {cur_time_increment}, scheduled time intervals: {num_time_intervals}")
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

def find_route_random(src, dest): # NOTE: Currently non-functional - need to update !!!
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
        
        # Get neighbors of current satellite
        cur_sat_neigh_list = cur_sat.get_list_of_cur_sat_neighbors()

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
    packet = {'dest_satnum': traverse_list[0], 'next_hop_list' : traverse_list[:-1], 'prev_hop_list' : [], 'distance_traveled' : 0, 'dest_gs' : dest}
    if send_directed_routing_packet_from_source(traverse_list[-1], src, packet) == -1:
        num_packets_dropped += 1
    
def find_route_dijkstra_hop(src, dest, send_packet = True, local_sat_object_list = None):
    #print("Starting Dijkstra hop routing")
    # Find satellite at least 60 deg above the horizon at source and destination
    # FIX: distances must also include the satnum of which sat put the lowest distance!  Must follow that listing backwards to id path to the source
    if not do_multiprocessing:
        global sat_object_list
    else:
      sat_object_list = local_sat_object_list

    #print(f"::find_route_dijkstra_hop:: Using sat_object_list; size: {len(sat_object_list)}")
    #if len(sat_object_list) == 0:
    #    sat_object_list = local_sat_object_list

    src_routing_sat = None
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(src)):
            src_routing_sat = r_sat
            break # Just go with first satellite
    if src_routing_sat is None:
        print(f"Unable to find satellite over source!")
        return -1, None, 'no_sat_overhead'

    dest_routing_sat = None
    for r_sat in sat_object_list:
        if (r_sat.is_overhead_of(dest)):
            dest_routing_sat = r_sat
            break # Just go with first satellite
    if dest_routing_sat is None:
        print(f"Unable to find satellite over destination!")
        return -1, None, 'no_sat_overhead'
    

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
        print(f"Loop count: {loop_cnt}", end="\r")
        cur_sat_neigh_list = cur_sat.get_list_of_cur_sat_neighbors()

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
            return -1, None, 'route_calc_failure'

        # Get sat routing object for indicated satnum
        cur_sat = get_routing_sat_obj_by_satnum(next_hop_satnum)
        cur_sat_dist = unvisted_sat_dict[cur_sat.sat.model.satnum][0]
        loop_cnt += 1
    # Done with loop; check if a route was found
    if not route_found:
        print(f"Unable to find route using dijkstra's algorithm")
        return -1, None, 'route_calc_failure'
    
    # Route was found, so retrace steps
    traverse_list = [dest_routing_sat.sat.model.satnum]
    cur_satnum = dest_routing_sat.sat.model.satnum
    link_distance = 0
    while True:
        next_hop = visited_sat_dict[cur_satnum][1]
        if next_hop == -1:
            print(f"::find_route_dijkstra_dist():: ERROR - no next_hop in visted_sat_dict!; cur_satnum: {cur_satnum} / visited_sat_dict: {visited_sat_dict}")
            return -1, None, 'route_calc_failure'
        link_distance += get_sat_distance(get_routing_sat_obj_by_satnum(cur_satnum).sat.at(cur_time), get_routing_sat_obj_by_satnum(next_hop).sat.at(cur_time))
        traverse_list.insert(0, next_hop)
        if next_hop == src_routing_sat.sat.model.satnum:
            break
        cur_satnum = next_hop
    traverse_list.reverse()
    packet = {'dest_satnum': traverse_list[0], 'next_hop_list' : traverse_list[:-1], 'prev_hop_list' : [], 'distance_traveled' : 0, 'dest_gs' : dest, 'TTL' : packet_start_TTL}
    # route pre-computed, now send packet
    if send_packet:
        send_directed_routing_packet_from_source(traverse_list[-1], src, packet)
        return None, None, ''
    else:
        return traverse_list[-1], packet, ''

# ::: directed routing packet structure: [dest_satnum, [next_hop_list], [prev_hop_list], distance_traveled, dest_terminal] - packet is at destination when dest_satnum matches current_satnum and next_hop_list is empty
def send_directed_routing_packet_from_source(starting_satnum, starting_terminal, packet):  # must have next_hop_list pre_built
    global no_sat_overhead_cnt
    starting_sat = get_routing_sat_obj_by_satnum(starting_satnum)

    #topo_position = (starting_sat.sat - starting_terminal).at(cur_time)
    #_, _, dist = topo_position.altaz()
    _, _, dist = (starting_sat.sat - starting_terminal).at(cur_time).altaz()
    if not starting_sat.is_overhead_of(starting_terminal):
        print(f"Satellite {starting_satnum} is not overhead starting terminal _after routing_ - starting terminal: {starting_terminal}")
        no_sat_overhead_cnt += 1
        return -1
    packet['distance_traveled'] += dist.km
    add_to_packet_qu_by_satnum(starting_satnum, packet)
    
# ::: distributed routing packet structure: {'prev_hop_list': [prev_hop_list], 'distance_traveled': dist, 'dest_gs': dest_gs, 'TTL': packet_TTL, 'dest_satnum': dest_satnum}
def send_distributed_routing_packet_from_source(src_gs, dest_gs):
    global no_sat_overhead_cnt
    sat_overhead_src = False
    sat_overhead_dest = False
    dest_satnum = -1
    for routing_sat in sat_object_list:
        if routing_sat.is_overhead_of(src_gs):
            sat_overhead_src = True
            src_routing_sat = routing_sat
        if routing_sat.is_overhead_of(dest_gs):
            sat_overhead_dest = True
            dest_satnum = routing_sat.sat.model.satnum
        if sat_overhead_src and sat_overhead_dest:
            break
    if not sat_overhead_src:
        print(f"No satellite overhead starting terminal {src_gs}", end='\r')
        no_sat_overhead_cnt += 1
        return -1
    elif not sat_overhead_dest:
        print(f"No satellite overhead destination terminal {dest_gs}", end='\r')
        no_sat_overhead_cnt += 1
        return -1
    distance = get_sat_distance(src_gs.at(cur_time), src_routing_sat.sat.at(cur_time))
    #print(f"::send_distributed_routing_packet_from_source():: Sending packet from {src_routing_sat.sat.model.satnum} to {dest_satnum}")
    packet = {'prev_hop_list': [], 'distance_traveled': distance, 'dest_gs': dest_gs, 'source_gs': src_gs, 'TTL' : packet_start_TTL, 'dest_satnum': dest_satnum}
    add_to_packet_qu_by_satnum(src_routing_sat.sat.model.satnum, packet)

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
                (Rad_Starting_mean_anomoly + (sat_index * MaM) + ((orbit_index%2) * (MaM/2) )) % (2*pi), # == MODIFIED PHASE OFFSET TO MATCH TRIANGLE GRID
                #((Rad_Starting_mean_anomoly - (orbit_index*MaM*.7)) + ((sat_index % sats_per_orbit) * (MaM))) % (2 * pi), # unsure why this factor got the satellites to line up, but whatever == ORIGINAL PHASE OFFSET
                Rad_Mean_motion,                                        # no_kozai: mean motion (radians/minute)
                (Rad_Starting_RaaN + (orbit_index * RaaNM))%(2*pi)      # nodeo: R.A. of ascending node (radians) (greater the value, the more East?)
            )
            fake_sat.classification = source_sat.model.classification
            fake_sat.elnum = source_sat.model.elnum
            fake_sat.revnum = source_sat.model.revnum
            sat = EarthSatellite.from_satrec(fake_sat, time_scale)
            orbit.append(sat)

            new_sat = RoutingSat(sat, satnum, orbit_index, sat_index, (orbit_index + 1) % orbit_cnt, (orbit_index - 1) % orbit_cnt, ((sat_index + 1) % sats_per_orbit) + (orbit_index*sats_per_orbit), ((sat_index - 1) % sats_per_orbit) + (orbit_index*sats_per_orbit))
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

def init_worker_processes(_sat_object_list):
    global local_sat_object_list
    local_sat_object_list = _sat_object_list

def mp_find_route_dijkstra_hop(raw_packet):
    src, dest = raw_packet
    local_sat_object_list = mp.shared_memory.SharedMemory(name='sat_object_list')
    #print(f"::mt_find_route_dijkstra_hop:: received src: {src}, dest {dest}, sat_object_list size: {len(local_sat_object_list)}")
    src_satnum, packet, error_str = find_route_dijkstra_hop(src, dest, False, local_sat_object_list)
    print(f"::mp_find_route_dijkstra_hop:: calculated src_satnum: {src_satnum}", end='\r')
    #packets_to_send.put((src_satnum, src, packet))
    return (src_satnum, src, packet, error_str)

def mt_find_route_dijkstra_hop(thread_index, raw_packet):
    global no_sat_overhead_cnt, num_route_calc_failures, num_packets_dropped
    src, dest = raw_packet
    #print(f"::mt_find_route_dijkstra_hop:: received src: {src}, dest {dest}, sat_object_list size: {len(local_sat_object_list)}")
    print(f"::mt_find_route_dijkstra_hop:: starting thread {thread_index}")
    satnum, _, error_str = find_route_dijkstra_hop(src, dest)
    if satnum == -1:
        num_packets_dropped += 1
        if error_str == 'no_sat_overhead':
            no_sat_overhead_cnt += 1
        elif error_str == 'route_calc_failure':
            num_route_calc_failures += 1
    

def directed_dijkstra_hop_routing():
    global no_sat_overhead_cnt, num_packets_dropped, num_packets_sent, cur_time_increment, routing_name, num_route_calc_failures, sat_object_list, shm
    name = "Directed Dijkstra Hop"

    #if do_multithreading:
    #    def my_callback(result):
    #        src_satnum, src, packet = result
    #        if src_satnum == -1:
    #            num_packets_dropped += 1
    #        else:
    #            send_directed_routing_packet_from_source(src_satnum, src, packet)

    max_time_inverals = int(num_time_intervals * 1.5) # allow some additional time to process any packets that may have been delayed
    for _ in range(max_time_inverals):
        if cur_time_increment in packet_schedule:
            packet_send_list = packet_schedule[cur_time_increment]  # get list of packets to send for this time interval
            packet_num = 0
            packet_send_list_size = len(packet_send_list)
            print(f"::directed_dijkstra_hop_routing:: Sending packets for time interval {cur_time_increment}; {len(packet_schedule)-1} remaining")
            if do_multiprocessing:
                buff_size = actualsize(sat_object_list)
                shm = mp.shared_memory.SharedMemory(create=True, size=buff_size, name='sat_object_list')
                shm.buf[:] = bytearray(sat_object_list)
                with mp.Pool(num_threads) as pool:
                    results = pool.map(mp_find_route_dijkstra_hop, packet_send_list)
                
                for result in results:
                    src_satnum, src, packet, error_str = result
                    if src_satnum == -1:
                        num_packets_dropped += 1
                        if error_str == 'no_sat_overhead':
                            no_sat_overhead_cnt += 1
                        elif error_str == 'route_calc_failure':
                            num_route_calc_failures += 1
                    else:
                        send_directed_routing_packet_from_source(src_satnum, src, packet)        
                
                """
                process_list = []
                results = mp.Queue()
                packet_index = 0
                while(packet_index < packet_send_list_size):
                    for proc_index in range(num_threads):
                        if packet_index == packet_send_list_size:
                            break
                        p = mp.Process(target=mp_find_route_dijkstra_hop, args=(proc_index, packet_send_list[packet_index], sat_object_list, results))
                        process_list.append(p)
                        p.start()
                        num_packets_sent += 1
                        packet_index += 1

                    for p in process_list:
                        p.join()
                
                while not results.empty():
                    result = results.get()
                    src_satnum, src, packet, error_str = result
                    if src_satnum == -1:
                        num_packets_dropped += 1
                        if error_str == 'no_sat_overhead':
                            no_sat_overhead_cnt += 1
                        elif error_str == 'route_calc_failure':
                            num_route_calc_failures += 1
                    else:
                        send_directed_routing_packet_from_source(src_satnum, src, packet)
                """
            elif (do_multithreading):
                thread_list = []
                packet_index = 0
                while(packet_index < packet_send_list_size):
                    for thread_index in range (num_threads):
                        if packet_index == packet_send_list_size:
                            break
                        thread = threading.Thread(target=mt_find_route_dijkstra_hop, args=(thread_index, packet_send_list[packet_index]), daemon=True)
                        thread_list.append(thread)
                        thread.start()
                        num_packets_sent += 1
                        packet_index += 1
                    for thread in thread_list:
                        thread.join()
            else:
                for packet in packet_send_list:
                    num_packets_sent += 1
                    src, dest = packet
                    print(f"Sending directed packet {packet_num} of {packet_send_list_size} using Dijkstra Hop")
                    packet_num += 1
                    src_satnum, packet, error_str = find_route_dijkstra_hop(src, dest)
                    if  src_satnum == -1:  # call pre-calculate routing routing
                        #print(f"Unable to find route to {src}", end='\r') # if route from source to destination not found, drop packet
                        num_packets_dropped += 1
                        if error_str == 'no_sat_overhead':
                            no_sat_overhead_cnt += 1
                        elif error_str == 'route_calc_failure':
                            num_route_calc_failures += 1
            print(f"::directed_dijkstra_hop_routing:: Completed sending packets for time interval {cur_time_increment}")
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
    name = "Directed Dijkstra Distance"

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
    global num_packets_dropped, num_packets_sent
    name = "Distributed Link State"
    print(f"Routing method: {routing_name}")
    max_time_inverals = int(num_time_intervals * 1.5) # allow some additional time to process any packets that may have been delayed
    # Loop through all time interverals and perform the following operations:
    #   1. Send all packets scheduled by packet scheduler
    #   2. All satellites update neighbor states (first publish their state to their neighbors, then update internal neighbor state table)
    #   3. All satellites send all packets that can be sent
    #   4. Increment time interval
    
    for _ in range(max_time_inverals):
        print(f"::distributed_link_state_routing::  Time interval: {time_interval}")
        # 1. Work through packet scheduler at each time interval and send all scheduled packets
        if cur_time_increment in packet_schedule:
            packet_send_list = packet_schedule[cur_time_increment]
            for packet in packet_send_list:
                src, dest = packet
                if send_distributed_routing_packet_from_source(src, dest) == -1:
                    num_packets_dropped += 1
                num_packets_sent += 1
            del packet_schedule[cur_time_increment]
        
        # 2. Update all neighbor states for current time interval        
        print("Updating neighbor states")
        start = time.process_time()
        all_sats_update_neigh_state()  # each satellite publishes it's state to it's neighbors and then the satellites process the received data
        compute_time = time.process_time() - start
        print(f"Time to compute neighbor states: {compute_time}")
        
        # 3. Keep sending packets until no more packets are sent (either nothing to sent, or sats have hit their bandwidth limit)
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
        
        # 4. Increment time interval
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

# generate the list packet_schedule that contains a list of packets to be sent at each time interval
def alt_build_packet_schedule():
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

    # For every time interval, we will generate a certain amount of traffic
    # This traffic is generated randomly between three categories:
    #  1. One city from city_list and one random location
    #  2. Two cities from city_list
    #  3. Two random locations
    # Category 1: 50%, Category 2: 25%, Category 3: 25%
    # Variable specifying amount of traffic generated for each time inveral:  packets_generated_per_interval

    global packet_schedule

    for interval in range(num_time_intervals):
        for packet_cnt in range(packets_generated_per_interval):
            if packet_cnt == 0:
                packet_schedule[interval] = []
            # determine which traffic category it will be
            random_num = random.randint(0, 99)
            if random_num < 50:
                category = 1
            elif random_num < 75:
                category = 2
            else:
                category = 3
            # generate the packet
            if category == 1:
                radom_lat = random.randint(-520000, 520000) / 10000
                random_lon = random.randint(-1800000, 1800000) / 10000
                random_location = wgs84.latlon(radom_lat, random_lon)
                city_index = random.randint(0, len(city_list) - 1)
                city = city_list[city_index]
                order = random.randint(0, 1)
                if order == 0:
                    packet_schedule[interval].append((city, random_location))
                else:
                    packet_schedule[interval].append((random_location, city))
            elif category == 2:
                index1 = random.randint(0, len(city_list) - 1)
                index2 = random.randint(0, len(city_list) - 1)
                city1 = city_list[index1]
                city2 = city_list[index2]
                packet_schedule[interval].append((city1, city2))
            else:
                radom_lat1 = random.randint(-520000, 520000) / 10000
                random_lon1 = random.randint(-1800000, 1800000) / 10000
                random_location1 = wgs84.latlon(radom_lat1, random_lon1)
                radom_lat2 = random.randint(-520000, 520000) / 10000
                random_lon2 = random.randint(-1800000, 1800000) / 10000
                random_location2 = wgs84.latlon(radom_lat2, random_lon2)
                packet_schedule[interval].append((random_location1, random_location2))

def static_build_packet_schedule():
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

    city_list = [Stockholm, New_York, Frankfurt, Paris, Amsterdam, London, Singapore, Jakarta, Marseille, Mumbai, Tokyo, Hong_Kong, Los_Angeles, Hanoi, Miami, Sao_Paulo, Madrid, Washington, Rio_de_Janeiro, Milan, Vienna, Moscow, Istanbul, San_Francisco, Sofia, Copenhagen, Budapest, Hamburg, Buenos_Aires, Warsaw, Bangkok, Buchararest, Helsinki, Prague, Brussels, St_Petersburg, Dusseldorf, Chennai, Kuala_Lumpur, Oslo, Mexico_City, Beijing, Zurich, Sydney, Santiago, Toronto, Bratislava, Seoul, Taipei, Riyadh]

    # Also need to create a range of random locations on the globe (to include oceans)
    # A good percentage of links should come from the random location list!!!


    global packet_schedule

    for interval in range(num_time_intervals):
        for packet_cnt in range(packets_generated_per_interval):
            if packet_cnt == 0:
                packet_schedule[interval] = []
            # determine which traffic category it will be
            if test_point_to_point:
                city1 = New_York
                city2 = Sydney
                packet_schedule[interval].append((city1, city2))
            else:
                index1 = (num_time_intervals + packets_generated_per_interval + (3*packet_cnt)) % len(city_list)
                index2 = (num_time_intervals + interval + packets_generated_per_interval + (2*packet_cnt) + 3) % len(city_list)
                if packet_cnt % 2 == 0:
                        packet_schedule[interval].append((city_list[index1], city_list[index2]))
                else:
                        packet_schedule[interval].append((city_list[index2], city_list[index1]))
            

def print_global_counters():
    print(f"::::: GLOBAL COUNTERS :::::")
    print(f"Routing Method: {routing_name}")
    print(f"Total packets sent: {num_packets_sent}")
    print(f"Total packets received: {num_packets_received}")
    print(f"Total packets dropped: {num_packets_dropped}")
    print(f"  Number of packets dropped due to exceeding max hops: {num_max_hop_packets_dropped}")
    print(f"  Number of packets dropped due to no satellite overhead source: {no_sat_overhead_cnt}")
    print(f"  Number of route calculation failures: {num_route_calc_failures}") # this is essentially max_hop_packets_dropped for directed routing functions
    for r_sat in sat_object_list:
        if r_sat.congestion_cnt > 0:
            print(f"Satellite {r_sat.sat.model.satnum} congestion count: {r_sat.congestion_cnt}")
    if num_packets_received != 0:
        print(f"Average packet distance: {total_distance_traveled//num_packets_received:,.0f}")
        print(f"Average packet hop count: {total_hop_count//num_packets_received}")
    else:
        print(f"No packets received!")
    

# ::::::: TESTING FUNCTIONS :::::::
def print_all_satellite_neighbors():
    for r_sat in sat_object_list:
        r_sat.update_current_neighbor_sats()
        print(f"Satellite {r_sat.sat.model.satnum} neighbors= fore: {r_sat.fore_sat_satnum}, aft: {r_sat.aft_sat_satnum}, port: {r_sat.port_sat_satnum}, starboard: {r_sat.starboard_sat_satnum}, fore_port: {r_sat.fore_port_sat_satnum}, fore_starboard: {r_sat.fore_starboard_sat_satnum}, aft_port: {r_sat.aft_port_sat_satnum}, aft_starboard: {r_sat.aft_starboard_sat_satnum}")

def print_satellite_neighbors_over_time(r_sat, num_time_increments):
    for _ in range(num_time_increments):
        r_sat.update_current_neighbor_sats()
        lat = r_sat.get_sat_lat_degrees()
        print(f"Satellite {r_sat.sat.model.satnum} neighbors at lat {lat:.2f}= fore: {r_sat.fore_sat_satnum}, aft: {r_sat.aft_sat_satnum}, port: {r_sat.port_sat_satnum}, starboard: {r_sat.starboard_sat_satnum}, fore_port: {r_sat.fore_port_sat_satnum}, fore_starboard: {r_sat.fore_starboard_sat_satnum}, aft_port: {r_sat.aft_port_sat_satnum}, aft_starboard: {r_sat.aft_starboard_sat_satnum}")
        increment_time()

def print_configured_options():
    print("::Configured Options::")
    print(f"  Multithreaded: {do_multithreading}")
    print(f"  Multiprocessing: {do_multiprocessing}")
    if do_multithreading or do_multiprocessing:
        print(f"    Running with {num_threads} threads")
    print(f"  Draw static orbits: {draw_static_orbits}")
    print(f"  Draw distributed orbits: {draw_distributed_orbits}")
    print(f"  Do test_point_to_point: {test_point_to_point}")
    print(f"  Testing: {testing}")
    print(f"  Plot dropped packets: {plot_dropped_packets}")
    print(f"  Doing satellite disruptions: {do_disruptions}")
    print(f"  Packet scheduling method: {packet_schedule_method}")
    print(f"  Routing method: {routing_name}")
    print(f"  Interval between time increments: {time_interval} seconds")
    print(f"  Number of time intervals: {num_time_intervals}")

def print_help(options, long_options, option_explanation):
    pruned_options = []
    for option in options:
        if option != ":":
            pruned_options.append(option)
    print("::Help::")
    print(f"  Usage: python3 {sys.argv[0]} [options]")
    print(f"  Options:")
    for i in range(len(pruned_options)):
        print(f"    -{pruned_options[i]}; --{long_options[i]}")
        print(f"      {option_explanation[i]}")
        if pruned_options[i] == 'r':
            print(f"      Routing methods: {routing_name_options}")
        elif pruned_options[i] == 'c':
            print(f"      Packet scheduling methods: {packet_schedule_method_options}")
    print("Default options:")
    print_configured_options()

# ::::::: MAIN :::::::

def main ():
    start_run_time = time.time()
    
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

    # Accept Command Line Arguments
    argumentList = sys.argv[1:]
    options = "hmutpr:i:n:odasc:"
    long_options = ["help", "multithreaded", "multiprocessing", "test", "point_to_point", "routing=", "interval=", "num_intervals=", "plot_dropped_packets", "disruptions", "draw_static_orbits", "draw_distributed_orbits", "packet_schedule_method"]
    option_explanation = ["this help message", "run with multithreading", "run with multiprocessing", "run testing functions", "run point to point test", "specify routing method", "specify time interval between time increments", "specify number of time increments", "plot dropped packets", "do satellite disruptions", "draw static orbits", "draw distributed orbits", "specify packet scheduling method"]
    try:
        arguments, values = getopt.getopt(argumentList, options, long_options)
    except getopt.error as err:
        print(str(err))
        sys.exit(2)
    for currentArgument, currentValue in arguments:
        if currentArgument in ("-h", "--help"):
            print_help(options, long_options, option_explanation)
            sys.exit()
        elif currentArgument in ("-m", "--multithreaded"):
            global do_multithreading
            do_multithreading = True
        elif currentArgument in ("-u", "--multiprocessing"):
            global do_multiprocessing
            do_multiprocessing = True
        elif currentArgument in ("-t", "--test"):
            global testing
            testing = True
        elif currentArgument in ("-p", "--point_to_point"):
            global test_point_to_point
            test_point_to_point = True
        elif currentArgument in ("-r", "--routing"):
            routing_name = currentValue
        elif currentArgument in ("-i", "--interval"):
            global time_interval
            time_interval = int(currentValue)
        elif currentArgument in ("-n", "--num_intervals"):
            global num_time_intervals
            num_time_intervals = int(currentValue)
        elif currentArgument in ("-o", "--plot_dropped_packets"):
            global plot_dropped_packets
            plot_dropped_packets = True
        elif currentArgument in ("-d", "--disruptions"):
            global do_disruptions
            do_disruptions = True
        elif currentArgument in ("-a", "--draw_static_orbits"):
            global draw_static_orbits
            draw_static_orbits = True
        elif currentArgument in ("-s", "--draw_distributed_orbits"):
            global draw_distributed_orbits
            draw_distributed_orbits = True
        elif currentArgument in ("-c", "--packet_schedule_method"):
            global packet_schedule_method
            packet_schedule_method = currentValue

    # Print out the configured options
    print_configured_options()

    

    # ---------- TESTING ------------
    """
    target_satnum = 1003
    set_time_interval(120) # set time interval to 60 seconds
    num_time_increments = 90
    print_satellite_neighbors_over_time(sat_object_list[target_satnum], num_time_increments)
    exit ()
    """
    # ---------- ROUTING ------------   

    # build a schedule of packets to send
    if packet_schedule_method == 'static':
        static_build_packet_schedule()
    elif packet_schedule_method == 'random':
        build_packet_schedule()
    elif packet_schedule_method == 'alt_random':
        alt_build_packet_schedule()
    else:
        print(f"Unkown packet schedule method specified: {packet_schedule_method}")
        exit()
    

    if do_disruptions:
        build_disruption_schedule() # build a schedule of satellite disruptions

    # call routing algorithm to use to send packets

    if routing_name == "Directed Dijkstra Hop":
        directed_dijkstra_hop_routing()
    elif routing_name == "Directed Dijkstra Distance":
        directed_dijkstra_distance_routing()
    elif routing_name == "Distributed Link State Bearing" or routing_name == "Distributed Link State TriCoord":
        distributed_link_state_routing()
    else:
        print(f"::main:: No known routing name specified.  routing_name: {routing_name}")

    
    

    # ---------- RESULTS ------------
    print_configured_options()
    print_global_counters()

    full_run_time = time.time() - start_run_time
    print(f"Full run time for {routing_name}: {floor(full_run_time/60)} minutes and {full_run_time % 60:,.2f} seconds")
    exit ()

    

if __name__ == "__main__":
    main()