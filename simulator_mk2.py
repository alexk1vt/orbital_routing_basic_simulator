from skyfield.api import EarthSatellite, load, wgs84
from numpy import array2string
from numpy.linalg import norm
from math import sqrt
import csv
import pandas as pd

import time

import random



# My own
def connecting_line_below_altitude(sat1, sat2, altitude, t):
    sat_diff = (sat1.at(t) - sat2.at(t))
    sat1_distance = sat1.at(t).distance().km
    sat2_distance = sat2.at(t).distance().km
    sat_diff_distance = sat_diff.distance().km

    sat_diff_mean = sqrt(2 * sat1_distance * sat1_distance + 2 * sat2_distance * sat2_distance - sat_diff_distance * sat_diff_distance) / 2
    sat_diff_altitude = sat_diff_mean - 6378 # Radius of Earth is 6378km
    #print (f'The triangle median altitude is {sat_diff_altitude}km')

    return sat_diff_altitude < altitude

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

def get_satellite_height(sat, t):
    geocentric = sat.at(t)
    height = wgs84.height_of(geocentric)
    return height.km
    #subpoint = wgs84.latlon(lat.degrees, lon.degrees, 0)
    #print (f'Satellite 0 has altitude of {height.km}km')

def main():
    ts = load.timescale()
    tle_path = '/home/alexk1/Documents/satellite_data/starlink_9MAY23.txt'
    #starlink_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'   

    satellites = load.tle_file(tle_path)
    print('Loaded', len(satellites), 'satellites')

    remove_ctr = 0
    for s in satellites:
        if 'STARLINK' not in s.name:
            satellites.remove(s)
            remove_ctr += 1
    print(f'Removed {remove_ctr} non-Starlink satellites; size of satellites: {len(satellites)}')
    

    # Computing Distance Orbits
    start_time = time.time()
    distance_orbit_list = []
    t_range = range(0,10)
    t_span = ts.utc(2023, 5, 9, t_range) # calculate max/min distance over two hour interval
    print(f'\nComputing distance orbits over a {len(t_range)} hour range\n')
    ctr = 0
    while True:
        print(f'Number of satellites considered for orbit {ctr}: {len(satellites)}')
        if len(satellites) < 1:
            break
        if len(satellites) == 1:
            distance_orbit.append(satellites[0])
            distance_orbit_list.append(distance_orbit)
            break
        distance_orbit = []
        remove_list = [0]
        distance_orbit.append(satellites[0])
        min_height = min(get_satellite_height(satellites[0], t_i) for t_i in t_span)
        max_height = max(get_satellite_height(satellites[0], t_i) for t_i in t_span)
        height_diff = int(max_height - min_height)
        for i in range(1, len(satellites)):
            dist_min = min(((satellites[0].at(t_i) - satellites[i].at(t_i)).distance().km) for t_i in t_span)
            dist_max = max(((satellites[0].at(t_i) - satellites[i].at(t_i)).distance().km) for t_i in t_span)
            dist_diff = dist_max-dist_min
            if (dist_diff < (height_diff * 3)):  # the seperation between the two satellites is less than 3x the altitude difference of first satellite, so they stay fixed within a range
                distance_orbit.append(satellites[i])
                remove_list.append(i)
                print(f'\r>> Adding satellite to orbit {ctr}. Orbit has {len(remove_list)} satellites', end='')
        #print(f'\nOrbit {ctr} has {len(remove_list)} satellites')
        distance_orbit_list.append(distance_orbit)
        remove_list.sort(reverse=True)
        for i in remove_list:
            satellites.pop(i)
        #ctr += 1
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"\nOrbit {ctr} has {len(remove_list)} satellites (Has been running for {int(elapsed_time/60)} minutes)\n")
        ctr += 1
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f'Computed {len(distance_orbit_list)} distance orbits')
    print(f"Took {int(elapsed_time/60)} minutes to compute")

    print(f"Testing orbital distances of satellite distance calculations")

    for a in range(10):
        while True:
            i = random.randint(0, len(distance_orbit_list)-1)
            if len(distance_orbit_list[i]) > 20:
                break # find first orbit with more than 20 satellites

        print(f"Orbit {i} has {len(distance_orbit_list[i])} satellites")

        t = ts.utc(2023, 5, 9, 14)
        
        sat1_index = random.randint(0, len(distance_orbit_list[i])-1)
        sat2_index = random.randint(0, len(distance_orbit_list[i])-1)
        while (sat1_index == sat2_index):
            sat2_index = random.randint(0, len(distance_orbit_list[i])-1) # ensure we're not looking at the same satellite accidentally

        #closest_sat_list = distance_orbit_list[i][:sat_index] + distance_orbit_list[i][sat_index+1:]
        #closest_sat = find_closest_satellite(distance_orbit_list[i][sat_index], closest_sat_list, t)
        #for x in range(len(distance_orbit_list[i])):
        #    if closest_sat.name == distance_orbit_list[i][x].name:
        #        print(f'Closest satellite to Orbit {i} | Satellite {sat_index}: {x}')
        #        break
        
        sat1 = distance_orbit_list[i][sat1_index]
        sat2 = distance_orbit_list[i][sat2_index]
        
        t_range = range(0,20)
        t_span = ts.utc(2023, 5, 9, t_range) # calculate max/min distance over time interval
        print(f"Calculating distance between satellites {sat1_index} and {sat2_index} in this orbit over {len(t_range)} hour interval")

        dist_list = []
        for t_i in t_span:
            dist_diff = (sat1.at(t_i) - sat2.at(t_i)).distance().km
            dist_list.append(int(abs(dist_diff)))

        print(f'\tMinimum distance: {min(dist_list)}km')
        print(f'\tMaximum distance: {max(dist_list)}km')
        print(f'\tAmount of distance change: {max(dist_list)-min(dist_list)}km')

    exit()

if __name__ == "__main__":
    main()