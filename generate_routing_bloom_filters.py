# generate_routing_bloom_filters.py

from skyfield.api import EarthSatellite, load, wgs84, N, S, E, W
from sgp4.api import Satrec, WGS72
from datetime import date, timedelta
from math import pi, floor, sqrt
import math

import csv

# :: GLOBAL VARIABLES ::
# Orbit characteristics
# Starlink Shell 1:  https://everydayastronaut.com/starlink-group-6-1-falcon-9-block-5-2/
sats_per_orbit = 22
orbit_cnt = 72

# Adjacent satellite characterisitcs
g_lat_range = 1 # satellites to E/W can fall within +- this value
lateral_antenna_range = 40 #30

# Ground Station characteristics
req_elev = 40 # https://www.reddit.com/r/Starlink/comments/i1ua2y/comment/g006krb/?utm_source=share&utm_medium=web2x

# Simulator variables
orbit_list = []
sat_object_list = []
sat_routing_node_list = []
cur_time = 0
num_sats = 0
eph = None

# Time variables
time_scale = load.timescale()
time_interval = 10 # interval between time increments, measured in seconds
secs_per_km = 0.0000033
num_time_intervals = 5
cur_time_increment = 0

# End of global variables



# :: SATELLITE NODE CLASS ::
class SatRoutingNode:
    def __init__(self, _routing_sat, _index):
        self.routing_sat = _routing_sat
        self.fore_neigh = None
        self.aft_neigh = None
        self.succ_orbit_neigh = None
        self.prec_orbit_neigh = None
        self.all_neighs_found = False
        self.shortest_past_dict = {} # key: satnum, value: list of satnums in shortest path to satnum
        self.index = _index

    def find_fore_aft_neighbors(self):
        self.fore_neigh = sat_routing_node_list[self.routing_sat.fore_sat_satnum]
        self.aft_neigh = sat_routing_node_list[self.routing_sat.aft_sat_satnum] 

    def find_prec_succ_neighbors(self, print_result = False):
        preceeding_orbit_satnum, _ = self.routing_sat.check_preceeding_orbit_sat_available()
        succeeding_orbit_satnum, _ = self.routing_sat.check_succeeding_orbit_sat_available()
        if not preceeding_orbit_satnum is None:
            self.prec_orbit_neigh = sat_routing_node_list[preceeding_orbit_satnum]    
        if not succeeding_orbit_satnum is None:
            self.succ_orbit_neigh = sat_routing_node_list[succeeding_orbit_satnum]
        if not preceeding_orbit_satnum is None and not succeeding_orbit_satnum is None:
            self.all_neighs_found = True
        if print_result:
            print(f":: find_prec_succ_neighbors :: satnum: {self.index} :: prec_orbit_neigh: {preceeding_orbit_satnum} :: succ_orbit_neigh: {succeeding_orbit_satnum}")

    def find_shortest_path_to_all_sats(self):
        print(f":: find_shortest_path_to_all_sats :: satnum: {self.index}")
        for r_sat in sat_object_list:
            if r_sat.sat.model.satnum == self.index:
                continue
            path_list = self.find_shortest_path_to_sat(r_sat.sat.model.satnum)
            if path_list == None:
                print(f"Could not find path to satnum: {r_sat.sat.model.satnum} from satnum: {self.index}")
                continue
            self.shortest_past_dict[r_sat.sat.model.satnum] = path_list

    def find_shortest_path_to_sat(self, satnum):
        print(f":: find_shortest_path_to_sat :: satnum: {satnum} from satnum: {self.index}")
        if satnum in self.shortest_past_dict:
            return None
        src_node_index = self.index
        dest_node = sat_routing_node_list[satnum]
        cur_node = self
        cur_node_dist = 0

        unvisted_node_dict = {} # dict of satnums with respective tentative distance values
        for s_node in sat_routing_node_list:
            unvisted_node_dict[s_node.index] = (float('inf'), -1) # initialize each node with a tentative distance of infinity and no predecessor
        visited_node_dict = {} # (sat_node_index, (distance, sat_node_index_who_assigned_distance))
        
        unvisted_node_dict[cur_node.index] = (0, -1) # set current node's distance to 0
        
        route_found = False
        loop_cnt = 0
        while True:
            print(f"Pre-computing Dijsktra Hop - Loop count: {loop_cnt}", end="\r")
            cur_node_neigh_list = [cur_node.fore_neigh, cur_node.aft_neigh]
            if not (cur_node.prec_orbit_neigh is None):
                cur_node_neigh_list.append(cur_node.prec_orbit_neigh)
            if not (cur_node.succ_orbit_neigh is None):
                cur_node_neigh_list.append(cur_node.succ_orbit_neigh)

            # Set distances for adjancent satellite nodes
            for testing_node in cur_node_neigh_list:
                if not testing_node is None:
                    if testing_node.index in unvisted_node_dict:
                        testing_node_dist = 1 # just a single hop from current satellite to testing satellite
                        tentative_dist = cur_node_dist + testing_node_dist
                        if tentative_dist < unvisted_node_dict[testing_node.index][0]:
                            unvisted_node_dict[testing_node.index] = (tentative_dist, cur_node.index)

            # Move current satellite to visited_sat_dict and remove it's entry in unvisted_sat_dict
            visited_node_dict[cur_node.index] = unvisted_node_dict[cur_node.index]
            del unvisted_node_dict[cur_node.index]
            
            # Test to see if we just set the destination node as 'visited'
            if cur_node.index == dest_node.index:
                route_found = True  # Indicate the destination has been reached and break out of the loop
                break

            # See if we've run out of unvisited nodes
            if len(unvisted_node_dict) < 1:
                break

            # Continuing on, so find the next unvisited node with the lowest distance
            next_hop_index = None
            next_hop_dist = float('inf')
            for unvisited_node_index in unvisted_node_dict.keys():
                if unvisted_node_dict[unvisited_node_index][0] < next_hop_dist:
                    next_hop_dist = unvisted_node_dict[unvisited_node_index][0]
                    next_hop_index = unvisited_node_index

            # Were there no nodes with distances other than infinity?  Something went wrong
            if next_hop_dist == float('inf'):
                print(f"No more neighbors without infinite distances to explore.  {len(visited_node_dict)} visited nodes; {len(unvisted_node_dict)} unvisted nodes remaining")
                return None 

            # Get sat routing object for indicated satnum
            cur_node = sat_routing_node_list[next_hop_index]
            cur_node_dist = unvisted_node_dict[cur_node.index][0]
            loop_cnt += 1

        # Done with loop; check if a route was found
        if not route_found:
            print(f"Unable to find route using dijkstra's algorithm")
            return None
        
        # Route was found, so retrace steps
        traverse_list = [dest_node.index]
        cur_node_index = dest_node.index
#       link_distance = 0
        while True:
            next_hop_index = visited_node_dict[cur_node_index][1]
            if next_hop_index == -1:
                print(f"::find_route_dijkstra_dist():: ERROR - no next_hop in visted_sat_dict!; cur_node_index: {cur_node_index} / visited_sat_dict: {visited_node_dict}")
                return None
#            link_distance += get_sat_distance(get_routing_sat_obj_by_satnum(cur_satnum).sat.at(cur_time), get_routing_sat_obj_by_satnum(next_hop).sat.at(cur_time))
            traverse_list.insert(0, next_hop_index)
            if next_hop_index == src_node_index:
                break
            cur_node_index = next_hop_index
        traverse_list.reverse()
        return traverse_list

# :: ROUTING SATELLITE CLASS ::
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
        port_range_min = (port_bearing-int(lateral_antenna_range/2)+360)%360
        port_range_max = (port_bearing+int(lateral_antenna_range/2)+360)%360
        starboard_range_min = (starboard_bearing-int(lateral_antenna_range/2)+360)%360
        starboard_range_max = (starboard_bearing+int(lateral_antenna_range/2)+360)%360
        min_satnum = self.preceeding_orbit_number * sats_per_orbit
        max_satnum = min_satnum + sats_per_orbit

        tentative_satnum_list = []
        for test_satnum in range(min_satnum, max_satnum):
            test_sat_bearing = get_rel_bearing_by_satnum_degrees(self.sat.model.satnum, test_satnum, heading)
            distance, _ = get_sat_distance_and_rate_by_satnum(self.sat.model.satnum, test_satnum)
            if distance > 1000:
                continue  # Don't try to connect to lateral satellites with distances > 1000km - seems like an unreasonable ability 
            #if (port_range_min < test_sat_bearing) and (test_sat_bearing < port_range_max):
            if (test_sat_bearing - port_range_min) %360 <= (port_range_max - port_range_min) % 360:
                tentative_satnum_list.append((test_satnum, 'port'))
            #elif (starboard_range_min < test_sat_bearing) and (test_sat_bearing < starboard_range_max):
            elif (test_sat_bearing - starboard_range_min) %360 <= (starboard_range_max - starboard_range_min) % 360:
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
            cur_routing_sat = sat_object_list[self.sat.model.satnum]
            for test_satnum_int in tentative_satnum_list:
                test_satnum, test_int = test_satnum_int
                test_routing_sat = sat_object_list[test_satnum]
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
            cur_routing_sat = sat_object_list[self.sat.model.satnum]
            #print(f"Found {len(tentative_satnum_list)} sats in succeeding orbit")
            for test_satnum_int in tentative_satnum_list:
                test_satnum, test_int = test_satnum_int
                test_routing_sat = sat_object_list[test_satnum]
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
        first_target_routing_sat = sat_object_list[first_target_satnum]
        first_target_lat, _ = wgs84.latlon_of(first_target_routing_sat.sat.at(cur_time))
        second_target_routing_sat = sat_object_list[second_target_satnum]
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
        first_target_routing_sat = sat_object_list[first_target_satnum]
        first_target_lat, _ = wgs84.latlon_of(first_target_routing_sat.sat.at(cur_time))
        second_target_routing_sat = sat_object_list[second_target_satnum]
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

# End Routing sat class

# :: Other Functions ::
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

# Satellite direction functions
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

def get_sat_distance_and_rate_by_satnum(sat1_satnum, sat2_satnum): # returns distance (in km), rate (in km/s)
    sat1_geoc = sat_object_list[sat1_satnum].sat.at(cur_time)
    sat1_geoc_next = sat_object_list[sat1_satnum].sat.at(cur_time_next)
    sat2_geoc = sat_object_list [sat2_satnum].sat.at(cur_time)
    sat2_geoc_next = sat_object_list[sat2_satnum].sat.at(cur_time_next)
    distance = (sat1_geoc - sat2_geoc).distance().km
    distance_next = (sat1_geoc_next - sat2_geoc_next).distance().km
    return distance, (distance_next-distance)

# Distance functions
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

# :: FUNCTIONS USED TO GENERATE CONSTELLATION ::
def correct_Epoch_days(raw_epoch):
    #print(f'Received object of type: {type(raw_epoch)}')
    print(f'Received timedate: {raw_epoch}')
    _python_utc_epoch = raw_epoch
    _spg4_epoch = date(1949, 12, 31)
    _delta_epoch = _python_utc_epoch - _spg4_epoch
    return _delta_epoch.days

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

def increment_time():
    global cur_time, cur_time_next, time_scale, cur_time_increment, num_packets_dropped
    python_t = cur_time.utc_datetime()
    new_python_time = python_t + timedelta(seconds = time_interval)
    cur_time = time_scale.utc(new_python_time.year, new_python_time.month, new_python_time.day, new_python_time.hour, new_python_time.minute, new_python_time.second)
    new_python_time = python_t + timedelta(seconds = time_interval+1)
    cur_time_next = time_scale.utc(new_python_time.year, new_python_time.month, new_python_time.day, new_python_time.hour, new_python_time.minute, new_python_time.second)
    print(f"::increment_time:: Time incremented to: {cur_time.utc_jpl()}")

def set_time_interval(interval_seconds): # sets the time interval (in seconds)
    global time_interval
    time_interval = interval_seconds

def find_all_sat_routing_node_neighbors():
    print(f"::find_all_sat_routing_node_neighbors:: Finding fore/aft neigbors")
    for routing_node in sat_routing_node_list: # quickly generate the fore/aft node neighbors
        routing_node.find_fore_aft_neighbors()

    print(f"::find_all_sat_routing_node_neighbors:: Finding succeeding/preceeding orbit neighbors")
    num_nodes = len(sat_routing_node_list)
    all_neighs_found = False
    print_result = False
    max_attempts = floor(180 / (time_interval/60)) # 3 hours worth of attempts - two LEO orbits worth of time
    attempts = 0
    while all_neighs_found == False:
        missing_neighs_cnt = 0
        all_neighs_found = True
        for routing_node in sat_routing_node_list:  # I can probably parallelize this...
            if routing_node.all_neighs_found == False:
                routing_node.find_prec_succ_neighbors(print_result)
                if routing_node.all_neighs_found == False:
                    all_neighs_found = False
                    missing_neighs_cnt += 1
        if not all_neighs_found:
            print(f"::find_all_sat_routing_node_neighbors:: Could not find all neighbors for {missing_neighs_cnt} of {num_nodes} nodes.  {attempts} out of {max_attempts} Trying again...")
            increment_time()
            #if missing_neighs_cnt < 100:
            #    print_result = True
            attempts += 1
        if attempts > max_attempts:
            print(f"::find_all_sat_routing_node_neighbors:: Could not find all neighbors for {missing_neighs_cnt} of {num_nodes} nodes after {max_attempts} attempts.  Exiting...")
            return False
    return True

def build_sat_routing_node_list():
    for satnum in range(len(sat_object_list)):
        sat_routing_node_list.append(SatRoutingNode(sat_object_list[satnum], satnum))

def write_all_shortest_paths_to_file():
    filename = "shortest_paths.csv"
    fields = ['src_satnum', 'dest_satnum', 'path_list']
    with open(filename, 'w') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(fields)
        for node in sat_routing_node_list:
            print(f"::write_all_shortest_paths_to_file:: Writing shortest paths for node {node.index}", end="\r")
            for dest_satnum in range(len(sat_object_list)):
                path_list = node.shortest_path_dict[dest_satnum]
                if path_list == None:
                    continue
                row = [node.index, dest_satnum] + path_list
                csvwriter.writerow(row)

def main ():
    # ---------- SETUP ------------
    # Load TLEs
    tle_path = './STARLINK-1071.txt'
    #starlink_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'   

    satellites = load.tle_file(tle_path)
    print('Loaded', len(satellites), 'satellites')
    source_sat = satellites[0]
    print(f'Source satellite epoch: {source_sat.epoch.utc_jpl()}')

    # Initialize simulation start time
    global cur_time, cur_time_next, routing_name

    cur_time = time_scale.utc(2023, 5, 9, 0, 0, 0)
    cur_time_next = time_scale.utc(2023, 5, 9, 0, 0, 1)
    print(f"Set current time to: {cur_time.utc_jpl()}")
    set_time_interval(600) # setting time interval to 10 minutes

    # Create a list of satellite objects
    print(f"Building constellation...")
    build_constellation(source_sat)

    # Create a list of routing nodes
    print(f"Building routing nodes...")
    build_sat_routing_node_list()

    # Find all neighbors for each routing node
    print(f"Finding all neighbors...")
    find_all_sat_routing_node_neighbors()

    # Find shortest paths between all pairs of routing nodes
    print(f"Finding shortest paths...")
    for node in sat_routing_node_list:  # I think I should parellelize this...
        node.find_shortest_path_to_all_sats()

    # Write all shortest paths to file
    print(f"Writing shortest paths to file...")
    write_all_shortest_paths_to_file()

if __name__ == "__main__":
    main()