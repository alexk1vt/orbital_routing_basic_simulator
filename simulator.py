from skyfield.api import EarthSatellite, load, wgs84
from numpy import array2string
from numpy.linalg import norm
from math import sqrt
import csv
import pandas as pd

import time

import random

#import matplotlib.pyplot as plt
#import numpy
#import scipy.cluster.hierarchy as shc

#import numpy as np
#from scipy.cluster.vq import kmeans, vq

#from sklearn.cluster import KMeans
#import numpy as np

# From ChatGPT
def straight_line_below_altitude(sat1, sat2, altitude, t):
    # Calculate the positions of each satellite
    #t = ts.utc(2022,9,14,17)
    #t = sat1.epoch
    p1, p2 = sat1.at(t).position.km, sat2.at(t).position.km
    
    # Calculate the altitude of the intersection point between the line and the Earth's surface
    cos_theta = p1.dot(p2) / (norm(p1) * norm(p2))
    sin_theta = (1 - cos_theta**2)**0.5
    altitude_intersection = norm(p1) * sin_theta - 6378.137  # Earth's radius
    
    # Check whether the altitude of the intersection point is below the given threshold
    return altitude_intersection < altitude

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
    #line1 = '1 25544U 98067A   14020.93268519  .00009878  00000-0  18200-3 0  5082'
    #line2 = '2 25544  51.6498 109.4756 0003572  55.9686 274.8005 15.49815350868473'
    #satellite = EarthSatellite(line1, line2, 'ISS (ZARYA)', ts)
    #print(satellite)

    #tle_path = '/home/alexk1/Documents/satellite_data/starlink.txt'
    tle_path = '/home/alexk1/Documents/satellite_data/starlink_9MAY23.txt'
    #starlink_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'

    #reader = csv.reader(open(tle_path), delimiter=' ')
    #i = 0
    #for row in reader:
    #    print (row)
    #    i += 1
    #    if i == 3:
    #        break
    col_headers = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    data_frame = pd.read_csv(tle_path, header=None, delim_whitespace=True, names=col_headers, engine='python')
    #print(data_frame)
    #print(data_frame.dtypes)

    """
    tolerance = 2
    Inc_tolerance = 0.5
    AoP_tolerance = 15
    Ecc_tolerance = 5000
    RaaN_tolerance = 30
    orbit_list = []
    initial_orbit = []
    initial_sat_orbit = [data_frame.iat[0,0], float(data_frame.iat[2,2]), data_frame.iat[2,3], data_frame.iat[2,4], float(data_frame.iat[2,5])] # Sat_name, inclination, RaaN, eccentricity
    #initial_sat_orbit = [data_frame.iat[0,0], float(data_frame.iat[2,2]), data_frame.iat[2,3]] # Sat_name, inclination, RaaN
    initial_orbit.append(initial_sat_orbit)
    orbit_list.append(initial_orbit)
    for i in range(3, len(data_frame), 3):  #start at next satellite entry and count by 3's
        name = data_frame.iloc[i,0]
        if not 'STARLINK' in name:
            continue
        Inclination = float(data_frame.iloc[i+2,2])
        RaaN = data_frame.iloc[i+2,3]
        Ecc = data_frame.iloc[i+2,4]
        Arg_Perig = float(data_frame.iloc[i+2,5])
        orbit = [name, Inclination, RaaN, Ecc, Arg_Perig]
        match = False
        Inc_match = False
        RaaN_match = False
        Ecc_match = False
        AoP_match = False
        for o in orbit_list:
            #print(f'Satellite orbit:\n{orbit}')
            #print(f'Testing against:\n{o[0]}')
            # need following TLE values:  inclination, RaaN, Ecc, Arg of Perig
            #if (((o[0][1] - Inc_tolerance < Inclination) and (o[0][1] + Inc_tolerance > Inclination)) and ((o[0][2] - tolerance < RaaN) and (o[0][2] + tolerance > RaaN)) and ((o[0][3] - Ecc_tolerance < Ecc) and (o[0][3] + Ecc_tolerance > Ecc)) and ((o[0][4] - AoP_tolerance < Arg_Perig) and (o[0][4] + AoP_tolerance > Arg_Perig))):
            if ((o[0][1] - Inc_tolerance < Inclination) and (o[0][1] + Inc_tolerance > Inclination)):
                Inc_match = True
            #else: print(f"Inclination mismatch.  Test val: {Inclination}, Ref val: {o[0][1]} +/- {Inc_tolerance}")
            if ((o[0][2] - RaaN_tolerance < RaaN) and (o[0][2] + RaaN_tolerance > RaaN)):
                RaaN_match = True
            #else: print(f"RaaN mismatch.  Test val: {RaaN}, Ref val: {o[0][2]} +/- {RaaN_tolerance}")
            if ((o[0][3] - Ecc_tolerance < Ecc) and (o[0][3] + Ecc_tolerance > Ecc)):
                Ecc_match = True
            #else: print(f"Eccentricity mismatch.  Test val: {Ecc}, Ref val: {o[0][3]} +/- {Ecc_tolerance}")
            if ((o[0][4] - AoP_tolerance < Arg_Perig) and (o[0][4] + AoP_tolerance > Arg_Perig)):
                AoP_match = True
            #else: print(f"AoP mismatch.  Test val: {Arg_Perig}, Ref val: {o[0][4]} +/- {AoP_tolerance}")
            
            if Inc_match and RaaN_match and Ecc_match and AoP_match:
                match = True
                #print ('Matching orbit found!')
                o.append(orbit)
                break
        if not match:
            new_orbit = []
            new_orbit.append(orbit)
            orbit_list.append(new_orbit)
    """
    tolerance = 2
    Inc_tolerance = 0.5
    #AoP_tolerance = 15
    Ecc_tolerance = 5000
    RaaN_tolerance = 30
    
    """
    AoP_list = []
    for i in range(0, len(data_frame), 3):
        AoP_list.append(float(data_frame.iloc[i+2,5]))
    with open ('AoPs.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(AoP_list)
    print(AoP_list[:10])
    exit ()
    """

    """
    inclination_list = []
    for i in range(0, len(data_frame), 3):
        inclination_list.append(float(data_frame.iloc[i+2,2]))

    with open ('inclinations.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(inclination_list)

    print(inclination_list[:10])

    exit ()

    twoD_inclination_list = np.reshape(inclination_list, (-1, 1))
    km = KMeans()
    #km.fit(twoD_inclination_list)
    labels = km.fit_predict(twoD_inclination_list)
    print (labels)

    exit ()

    """
    #plot
    #plt.plot(km)
    #plt.axis('equal')
    #title = "title"
    #plt.title(title)
    #plt.show()


    #inclination_clusters = hcluster.fclusterdata(inclination_list, Inc_tolerance, criterion="distance")
    
    #inclination_clusters = shc.linkage(inclination_list, method='ward', metric='euclidean')
    #shc.dendrogram(Z=inclination_clusters)
    
    #plotting
    #plt.figure(figsize=(10,7))
    #plt.title("title")
    #plt.show

    #plt.scatter(*numpy.transpose(inclination_list), c=inclination_clusters)
    #plt.axis('equal')
    #title = "threshold: %f, number of clusters: %d" % (Inc_tolerance, len(set(inclination_clusters)))
    #plt.title(title)
    #plt.show()

    orbit_list = []
    #orbit_list.append(initial_orbit)
    done = False
    print(f'Number of satellites in data_frame: {int(len(data_frame)/3)}')
    while (not done):
        remove_list = [0,1,2]
        orbit = []
        initial_sat = [data_frame.iat[0,0], float(data_frame.iat[2,2]), data_frame.iat[2,3], data_frame.iat[2,4]] # Sat_name, inclination, RaaN, eccentricity
        orbit.append(initial_sat)
        for i in range(3, len(data_frame), 3):  #start at next satellite entry and count by 3's
            name = data_frame.iloc[i,0]
            if not 'STARLINK' in name:
                remove_list.append(i)
                remove_list.append(i+1)
                remove_list.append(i+2)
                continue
            try:
                Inclination = float(data_frame.iloc[i+2,2])
            except:
                print(f'Bad inclination read on data_frame index {i}.\nData_frame row {i}: {data_frame.iloc[i]}\nData_frame row {i+2}: {data_frame.iloc[i+2]}\nInclination: {data_frame.iloc[i+2,2]}\nNumber of satellites remaining in data_frame: {len(data_frame)/3}.\nInitial_sat: {initial_sat}')
                exit()
            if ((initial_sat[1] - Inc_tolerance < Inclination) and (initial_sat[1] + Inc_tolerance > Inclination)):
                RaaN = data_frame.iloc[i+2,3]
                if ((initial_sat[2] - RaaN_tolerance < RaaN) and (initial_sat[2] + RaaN_tolerance > RaaN)):
                    Ecc = data_frame.iloc[i+2,4]
                    if ((initial_sat[3] - Ecc_tolerance < Ecc) and (initial_sat[3] + Ecc_tolerance > Ecc)):
                        sat = [name, Inclination, RaaN, Ecc]
                        orbit.append(sat)
                        remove_list.append(i)
                        remove_list.append(i+1)
                        remove_list.append(i+2)
                        continue
        orbit_list.append(orbit)

        #print(f'Removing {len(remove_list)} entries from data frame')
        #print(f'Size of data_frame: {len(data_frame)}')
        #print(data_frame)
        #remove_list.sort(reverse=True)
        data_frame.drop(remove_list, inplace = True)
        data_frame.reset_index(drop=True, inplace=True)
        #for i in remove_list:
            #data_frame.drop(data_frame.index[i:i+2], inplace=True)
            #data_frame = data_frame.drop(data_frame.index[i:i+2])
        #print(f'Remaining number of satellites in data_frame: {int(len(data_frame)/3)}')
        if (len(data_frame)%3 != 0):
            print('Irregular number of remaining rows!  Exitting')
            exit()
        if len(data_frame) < 6:
            print('Done parsing data_frame!')
            done = True
            if len(data_frame) == 3:
                orbit = []
                initial_sat = [data_frame.iat[0,0], float(data_frame.iat[2,2]), data_frame.iat[2,3], data_frame.iat[2,4]]
                orbit.append(initial_sat)
                orbit_list.append(orbit)




    print(f"\nOrbital slotting using following tolerances:"
          f"\n\tInclination +/- {Inc_tolerance}"
          f"\n\tRaaN +/- {RaaN_tolerance}"
          f"\n\tEccentricity +/- {Ecc_tolerance}")
          #f"\n\tArgument of Perigee +/ {AoP_tolerance}")
    print(f'\nNumber of seperate orbits: {len(orbit_list)}')
    print(f'Number of satellites in first orbit: {len(orbit_list[0])}')
    print(f'Minimum number of satellites in an orbit: {min(len(o) for o in orbit_list)}')
    print(f'Maximum number of satellites in an orbit: {max(len(o) for o in orbit_list)}')
    print('Expecting 72 planes with 22 satellites in each plane\n')
    #https://everydayastronaut.com/starlink-group-4-13-falcon-9-block-5-2/

    """
    print('\n')
    i = 1
    for o in orbit_list:
        print(f'Number of satellites in orbit {i}: {len(o)}')
        i += 1
    """

    t = 1
    for o in orbit_list:
        inc_list = []
        RaaN_list = []
        Ecc_list = []
        inc_list.append(o[0][1])
        RaaN_list.append(o[0][2])
        Ecc_list.append(o[0][3])
        for s in o:
            no_match = True
            for i in inc_list:
                if not ((i - Inc_tolerance < s[1]) and (i + Inc_tolerance > s[1])):
                    inc_list.append(s[1])
                    break
            for r in RaaN_list:
                if not ((r - RaaN_tolerance < s[2]) and (r + RaaN_tolerance > s[2])):
                    RaaN_list.append(s[2])
            for e in Ecc_list:
                if not ((e - Ecc_tolerance < s[3]) and (e + Ecc_tolerance > s[3])):
                    Ecc_list.append(s[3])
        inc_list.sort()
        RaaN_list.sort()
        Ecc_list.sort()
        print(f"Orbit {t} features:")
        print(f"\tUnique Inclinations in orbit {t}: {inc_list}")
        print(f"\tUnique RaaNs in orbit {t}: {RaaN_list}")
        print(f"\tUnique Eccentricities in orbit {t}: {Ecc_list}")
        t += 1


    

    """
    inc_list = []
    inc_list.append(orbit_list[0][0][1])
    for o in orbit_list:
        no_match = True
        for i in inc_list:
            if ((i - Inc_tolerance < o[0][1]) and (i + Inc_tolerance > o[0][1])):
                no_match = False
                break
        if no_match:
            inc_list.append(o[0][1])
    inc_list.sort()
    print(f"Unique Inclinations of recorded orbits:\n{inc_list}")
    """

    """
    RaaN_list = []
    RaaN_list.append(orbit_list[0][0][2])
    for o in orbit_list:
        no_match = True
        for r in RaaN_list:
            if ((r - RaaN_tolerance < o[0][2]) and (r + RaaN_tolerance > o[0][2])):
                no_match = False
                break
        if no_match:
            RaaN_list.append(o[0][2])
    RaaN_list.sort()
    print(f"Unique RaaNs of recorded orbits:\n{RaaN_list}")

    Ecc_list = []
    Ecc_list.append(orbit_list[0][0][3])
    for o in orbit_list:
        no_match = True
        for e in Ecc_list:
            if ((e - Ecc_tolerance < o[0][3]) and (e + Ecc_tolerance > o[0][3])):
                no_match = False
                break
        if no_match:
            Ecc_list.append(o[0][3])
    Ecc_list.sort()
    print(f"Unique Eccentricities of recorded orbits:\n{Ecc_list}")
    """

    """
    AoP_list = []
    AoP_list.append(orbit_list[0][0][4])
    for o in orbit_list:
        no_match = True
        for a in AoP_list:
            if ((a - AoP_tolerance < o[0][4]) and (a + AoP_tolerance > o[0][4])):
                no_match = False
                break
        if no_match:
            AoP_list.append(o[0][4])
    AoP_list.sort()
    print(f"Unique Arguments of Perigee of recorded orbits:\n{AoP_list}")
    """
    satellites = load.tle_file(tle_path)
    print('Loaded', len(satellites), 'satellites')

    remove_ctr = 0
    for s in satellites:
        if 'STARLINK' not in s.name:
            satellites.remove(s)
            remove_ctr += 1
    print(f'Removed {remove_ctr} non-Starlink satellites; size of satellites: {len(satellites)}')
    
    loaded_orbit_list = []
    for o in orbit_list:
        loaded_orbit = []
        for i in o:
            for s in satellites:
                if s.name == i[0]:
                    loaded_orbit.append(s)
        loaded_orbit_list.append(loaded_orbit)
    print(f'\nNumber of seperate loaded orbits: {len(loaded_orbit_list)}')
    print(f'Number of satellites in first loaded orbit: {len(loaded_orbit_list[0])}')
    print(f'Minimum number of satellites in a loaded orbit: {min(len(o) for o in loaded_orbit_list)}')
    print(f'Maximum number of satellites in a loaded orbit: {max(len(o) for o in loaded_orbit_list)}')

    print(f'\nTLE epoch: {satellites[0].epoch.utc_jpl()}')
    t = ts.utc(2023, 5, 9, 11, 18, 7)
    print(f'Using epoch: {t.utc_jpl()}\n')
    
    t_span = ts.utc(2023, 5, 9, range(0, 24))
    i = 1
    for o in loaded_orbit_list:
        print(f'Orbit: {i}:')
        print(f'\tNumber of satellites in orbit {i}: {len(o)}')
        print(f'\tMinimum height for satellites in orbit {i}: {min(get_satellite_height(s, t) for s in o)}')
        print(f'\tMaximum height for satellites in orbit {i}: {max(get_satellite_height(s, t) for s in o)}')
        min_height = min(get_satellite_height(o[0], t_i) for t_i in t_span)
        max_height = max(get_satellite_height(o[0], t_i) for t_i in t_span)
        height_diff = int(max_height - min_height)
        print(f'\tHeight difference for satellite[0] in orbit {i}: {height_diff}')
        i += 1


    print(f"Testing orbital distances of orbital element calculations")

    while True:
        i = random.randint(0, len(loaded_orbit_list))
        if len(loaded_orbit_list[i]) > 20:
            break # find first orbit with more than 20 satellites

    print(f"Orbit {i} has {len(loaded_orbit_list[i])} satellites")
    #for x in range(20):
    #    print(f'Orbit {i} | Satellite {x}: {loaded_orbit_list[i][x]}')
    t = ts.utc(2023, 5, 9, 14)
    
    sat_index = random.randint(0, len(loaded_orbit_list[i]))

    closest_sat_list = loaded_orbit_list[i][:sat_index] + loaded_orbit_list[i][sat_index+1:]
    closest_sat = find_closest_satellite(loaded_orbit_list[i][sat_index], closest_sat_list, t)
    for x in range(len(loaded_orbit_list[i])):
        if closest_sat.name == loaded_orbit_list[i][x].name:
            print(f'Closest satellite to Orbit {i} | Satellite {sat_index}: {x}')
            break
    print(f"Calculating distance between satellites {sat_index} and {x} in this orbit over 10 hour interval")
    
    sat1 = loaded_orbit_list[i][sat_index]
    sat2 = loaded_orbit_list[i][x]
    
    t_span = ts.utc(2023, 5, 9, range(10, 20)) # calculate max/min distance over time interval
    
    dist_list = []
    for t_i in t_span:
        dist_diff = (sat1.at(t_i) - sat2.at(t_i)).distance().km
        dist_list.append(int(abs(dist_diff)))

    print(f'\tMinimum distance: {min(dist_list)}km')
    print(f'\tMaximum distance: {max(dist_list)}km')
    print(f'\tDistance difference: {max(dist_list)-min(dist_list)}km')



    
    start_time = time.time()
    distance_orbit_list = []
    t_range = range(0,2)
    t_span = ts.utc(2023, 5, 9, t_range) # calculate max/min distance over two hour interval
    print(f'\nComputing distance orbits over {len(t_range)} hours\n')
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
        print(f"\nOrbit {ctr} has {len(remove_list)} satellites (Has been running for {int(elapsed_time/60)} minutes)")
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
        
        sat_index = random.randint(0, len(distance_orbit_list[i]))

        closest_sat_list = distance_orbit_list[i][:sat_index] + distance_orbit_list[i][sat_index+1:]
        closest_sat = find_closest_satellite(distance_orbit_list[i][sat_index], closest_sat_list, t)
        for x in range(len(distance_orbit_list[i])):
            if closest_sat.name == distance_orbit_list[i][x].name:
                print(f'Closest satellite to Orbit {i} | Satellite {sat_index}: {closest_sat.name} [index: {x}]')
                break
        next_closest_sat_list = closest_sat_list[:x] + closest_sat_list[x+1:]
        closest_sat = find_closest_satellite(distance_orbit_list[i][sat_index], next_closest_sat_list, t)
        for y in range(len(distance_orbit_list[i])):
            if closest_sat.name == distance_orbit_list[i][y].name:
                print(f'Next closest satellite to Orbit {i} | Satellite {sat_index}: {closest_sat.name} [index: {y}]')
                break

        sat1 = distance_orbit_list[i][sat_index]
        sat2 = distance_orbit_list[i][x]
        sat3 = distance_orbit_list[i][y]
        
        t_range = range(0,20)
        t_span = ts.utc(2023, 5, 9, t_range) # calculate max/min distance over time interval
        print(f"Calculating distance between satellites {sat_index} and {x} in this orbit over {len(t_range)} hour interval")
        dist_list = []
        for t_i in t_span:
            dist_diff = (sat1.at(t_i) - sat2.at(t_i)).distance().km
            dist_list.append(int(abs(dist_diff)))

        print(f'\tMinimum distance: {min(dist_list)}km')
        print(f'\tMaximum distance: {max(dist_list)}km')
        print(f'\tAmount of distance change: {max(dist_list)-min(dist_list)}km')

        print(f"Calculating distance between satellites {sat_index} and {y} in this orbit over {len(t_range)} hour interval")
        dist_list = []
        for t_i in t_span:
            dist_diff = (sat1.at(t_i) - sat3.at(t_i)).distance().km
            dist_list.append(int(abs(dist_diff)))

        print(f'\tMinimum distance: {min(dist_list)}km')
        print(f'\tMaximum distance: {max(dist_list)}km')
        print(f'\tAmount of distance change: {max(dist_list)-min(dist_list)}km')

    """
    satellites = load.tle_file(tle_path)
    print('Loaded', len(satellites), 'satellites')
    satellite = satellites[0]
    print(satellite)
    print('Satellite TLE epoch:\t\t', satellite.epoch.utc_jpl())
    
    t = ts.utc(2022,9,14,1,0,0)
    print('Current configured epoch:\t', t.utc_jpl())
    days = t - satellite.epoch
    print('{:.3f} days away from epoch'.format(days))

    geocentric = satellite.at(t)
    lat, lon = wgs84.latlon_of(geocentric)
    print('Satellite current position:')
    print('\tLatitude: ', lat)
    print('\tLongitude: ', lon)

    blacksburg = wgs84.latlon(+37.2296, -80.4139)
    #print('Blacksburgs position: ', blacksburg)

    t0 = ts.utc(2022, 9, 14)
    t1 = ts.utc(2022, 9, 15)
    print(f'Satellites viewable from Blacksburg between times {t0} and {t1}:')
    t, events = satellite.find_events(blacksburg, t0, t1, altitude_degrees=30.0)
    event_names = 'rise above 30°', 'culminate', 'set below 30°'
    for ti, event, in zip(t, events):
        name = event_names[event]
        print('\t',ti.utc_strftime('%Y %b %d %H:%M:%S'), name)


    t = ts.utc(2022,9,14,17,range(32,38))
    print('Current configured epoch:\n\t', t.utc_jpl())
    pos = (satellite - blacksburg).at(t)
    _, _, the_range, _, _, range_rate = pos.frame_latlon_and_rates(blacksburg)
    print ('Distances and rates of change during events listed above:')
    print ('\t',array2string(the_range.km, precision=1), 'km' )
    print ('\t',array2string(range_rate.km_per_s, precision=2), 'km/s')

    t = ts.utc(2022,9,14,17)
    closest_sat = find_closest_satellite(satellites[0], satellites[1:], t)
    print (f'Closest satellite to satellite[0] at time {t} is: {closest_sat}')

    #t = ts.utc(2022,9,14,17,range(32,38))
    satellite_diff = (satellites[0].at(t) - closest_sat.at(t))
    print ('The satellites are ', satellite_diff.distance().km, ' km away at time ', t.utc_jpl())
    geocentric = satellites[0].at(t)
    height = wgs84.height_of(geocentric)
    #subpoint = wgs84.latlon(lat.degrees, lon.degrees, 0)
    print (f'Satellite 0 has altitude of {height.km}km')
    
    #if straight_line_below_altitude(satellites[0], closest_sat, 80.0, t):
    #    print("Straight line will pass below 80km")
    #else:
    #    print("Straight line will not pass below 80km")
    
    if connecting_line_below_altitude(satellites[0], closest_sat, 80.0, t):
        print("Straight line will pass below 80km")
    else:
        print("Straight line will not pass below 80km")

    sat_neighbor_list = []
    for s in satellites[1:]:
        satellite_diff = satellites[0].at(t) - s.at(t)
        if satellite_diff.distance().km < 300: # estimated range of satellite laser comms (wikipedia estimates 2000km max)
            sat_neighbor_list.append(s)
    for s in sat_neighbor_list:
        if (connecting_line_below_altitude(satellites[0], s, 80.0, t)):
            sat_neighbor_list.remove(s)
    
    print(f'Sat[0] has {len(sat_neighbor_list)} reachable neighbors at time {t.utc_jpl()}')
    if len(sat_neighbor_list) > 0:
        i = 1
        for s in sat_neighbor_list:
            satellite_diff = satellites[0].at(t) - s.at(t)
            print(f'Distance from neighbor {i}: {satellite_diff.distance().km} [{s}]')
            i += 1
    
    
    #for i, dist in enumerate(satellite_diff):
    #    print (f"{t[i]}: {dist.km:10.3f} km")

    #eph = load('de421.bsp')
    #earth = eph['earth']
    #two_hours = ts.utc(2022, 9, 14, 0, range(0, 120, 20))
    #p = (earth + satellite).at(two_hours).observe(satellites[1]).apparent()
    #print (p)
    
    #print(satellite.epoch.utc_jpl())
    
    #t = ts.utc(2014, 1, 23, 11, 18, 7)
    #days = t - satellite.epoch
    #print('{:.3f} days away from epoch'.format(days))
    
    #bluffton = wgs84.latlon(+40.8939, -83.8917)
    #t0 = ts.utc(2014, 1, 23)
    #t1 = ts.utc(2014, 1, 24)
    #t, events = satellite.find_events(bluffton, t0, t1, altitude_degrees=30.0)
    #event_names = 'rise above 30°', 'culminate', 'set below 30°'
    #for ti, event in zip(t, events):
        #name = event_names[event]
        #print(ti.utc_strftime('%Y %b %d %H:%M:%S'), name)
    """
    exit()

if __name__ == "__main__":
    main()