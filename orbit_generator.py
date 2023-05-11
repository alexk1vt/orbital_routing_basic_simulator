from skyfield.api import EarthSatellite, load, wgs84
from sgp4.api import Satrec, WGS72
from sgp4.conveniences import dump_satrec
import pandas as pd
import random
from datetime import date
from math import pi

from sys import stdout

# for plotting orbits
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import axes3d
from matplotlib.animation import FuncAnimation

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

def main ():
    ts = load.timescale()
    #tle_path = '/home/alexk1/Documents/satellite_data/starlink_9MAY23.txt'
    tle_path = '/home/alexk1/Documents/satellite_data/STARLINK-1071.txt'
    #starlink_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'   

    satellites = load.tle_file(tle_path)
    print('Loaded', len(satellites), 'satellites')
    source_sat = satellites[0]

    print(f'Source satellite epoch: {source_sat.epoch.utc_jpl()}')

    sats_per_orbit = 22
    orbit_cnt = 72

    # load tle into pandas data_frame to pull data
    #col_headers = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    #data_frame = pd.read_csv(tle_path, header=None, delim_whitespace=True, names=col_headers, engine='python')
   
    #print(data_frame)

    #data_frame_index = 0 # we're only reading in a single TLE
    #Name = data_frame.iloc[data_frame_index,0]
    #Inclination = float(data_frame.iloc[data_frame_index+2,2])
    #RaaN = data_frame.iloc[data_frame_index+2,3]
    #Ecc = data_frame.iloc[data_frame_index+2,4]
    #Arg_Perig = float(data_frame.iloc[data_frame_index+2,5])
    Epoch =   source_sat.epoch # Maybe just copy the epoch from the loaded TLE?
    #Drag_coef = data_frame.iloc[data_frame_index+1,6]
    #Mean_motion = data_frame.iloc[data_frame_index+2,7]
    #Starting_mean_anomoly = float(data_frame.iloc[data_frame_index+2,6])

    # Correct values and convert to radians where needed

    # Epoch - convert to number of days since 1949 December 31 00:00 UT
    Corr_Epoch = correct_Epoch_days(Epoch.utc_datetime().date()) + (source_sat.model.epochdays % 1) #getting the partial days of the epoch
    
    # Drag Coefficient, aka BSTAR  http://www.castor2.ca/03_Mechanics/03_TLE/B_Star.html
    #Corr_drag_coef = correct_BSTAR_float(Drag_coef)
    Corr_drag_coef = source_sat.model.bstar

    # Eccentricity
    #Corr_Ecc = Ecc * (1/pow(10, 7))
    Corr_Ecc = source_sat.model.ecco

    # Argument of Perigee - convert from degrees to radians
    #Rad_Arg_Perig = degrees_to_radians(Arg_Perig)
    Rad_Arg_Perig = source_sat.model.argpo
    
    # Inclination - convert from degrees to radians
    #Rad_Inclination = degrees_to_radians(Inclination)
    Rad_Inclination = source_sat.model.inclo

    # Mean Motion - convert from revolutions/day to radians/minute
    #_revs_per_minute = Mean_motion / 24 / 60
    #Rad_Mean_motion = _revs_per_minute * 2 * 3.1416
    Rad_Mean_motion = source_sat.model.no_kozai

    # Mean anomoly - convert from degrees to radians
    #Rad_Starting_mean_anomoly = degrees_to_radians(Starting_mean_anomoly)
    #while (Rad_Starting_mean_anomoly > (2*3.1416)):
    #    Rad_Starting_mean_anomoly -= (2*3.1416)
    Rad_Starting_mean_anomoly = source_sat.model.mo
    
    # Right Ascension of Ascending Node - convert from degrees to radians
    #Rad_RaaN = degrees_to_radians(RaaN)
    Rad_Starting_RaaN = source_sat.model.nodeo

    # Mean anomoly Modifier
    MaM = (pi * 2)/sats_per_orbit

    # RaaN Modifier
    RaaNM = (pi * 2)/orbit_cnt

    # ballistic coefficient (ndot) and mean motion 2nd derivative (nddot) - supposedely can just set to 0, but including for completeness
    Ndot = source_sat.model.ndot
    Nddot = source_sat.model.nddot

    """
    print(f'Using values:\n'
          f'\tCorr_Epoch: {Corr_Epoch}\n'
          f'\tCorr_drag_coef: {Corr_drag_coef}\n'
          f'\tCorr_Ecc: {Corr_Ecc}\n'
          f'\tRad_Arg_Perig: {Rad_Arg_Perig}\n'
          f'\tRad_Inclination: {Rad_Inclination}\n'
          f'\tMean_anomoly: {Rad_Starting_mean_anomoly + (1 * MaM)} (Rad_Starting_mean_anomoly + (sat_index[1] * MaM))\n'
          f'\tRad_Mean_motion: {Rad_Mean_motion}\n'
          f'\Rad_Starting_RaaN: {Rad_Starting_RaaN}\n\n')
    """

    #building satellites using instructions from https://rhodesmill.org/skyfield/earth-satellites.html
    orbit_list = []
    satnum = 0
    for orbit_index in range(0, orbit_cnt):
        orbit = []
        for sat_index in range(0, sats_per_orbit):  #Going to leave sat_index '0' for progenitor satellite
            fake_sat = Satrec()
            fake_sat.sgp4init(
                WGS72,                                          # gravity model
                'i',                                            # improved mode
                satnum,                                      # satnum: Satellite number
                Corr_Epoch,                                     # epoch: days since 1949 December 31 00:00 UT
                Corr_drag_coef,                                 # bstar: drag coefficient (/earth radii)
                Ndot,                                           # ndot: ballistic coefficient (radians/minute^2) - can ignore
                Nddot,                                          # nddot: mean motion 2nd derivative (radians/minute^3) - can ignore
                Corr_Ecc,                                       # ecco: eccentricity
                Rad_Arg_Perig,                                  # argpo: argument of perigee (radians)
                Rad_Inclination,                                # inclo: inclination (radians)
                (Rad_Starting_mean_anomoly + (sat_index * MaM))%(2*pi),  # mo: mean anomaly (radians) - will need to modify this per satellite
                Rad_Mean_motion,                                # no_kozai: mean motion (radians/minute)
                (Rad_Starting_RaaN + (orbit_index * RaaNM))%(2*pi)       # nodeo: R.A. of ascending node (radians)
            )
            fake_sat.classification = source_sat.model.classification
            fake_sat.elnum = source_sat.model.elnum
            fake_sat.revnum = source_sat.model.revnum
            sat = EarthSatellite.from_satrec(fake_sat, ts)
            orbit.append(sat)
            satnum += 1
        
        orbit_list.append(orbit)

    print(f'Orbit list has {len(orbit_list)} orbits')

    """
    print(f'\n~~~~~~~~~~ Comparing fake_sat 0 against source satellite ~~~~~~~~~~')
    print(f'   fake_sat 0                           {source_sat.name}')
    stdout.writelines(dump_satrec(orbit_list[0][0].model, source_sat.model))
    print('\n')
    """

    # ---------- DRAWING ORBITS ----------
    # Original version based on: https://stackoverflow.com/questions/51891538/create-a-surface-plot-of-xyz-altitude-data-in-python
    
    # Number of orbits to draw
    max_num_orbits_to_draw = 12

    # time interval covered
    m_range = range(0, 60)
    h_range = range(0, 24)
    t_span = []
    for h in h_range:
        for m in m_range:
            t_span.append(ts.utc(2023, 5, 9, h, m))
    #t_span = ts.utc(2023, 5, 9, h_range)

    # calculating which orbits to draw
    orbit_index_list = []
    """
    # if spacing orbits out equally
    draw_orbit_index = int(orbit_cnt/max_num_orbits_to_draw)
    for orbit_index in range(len(orbit_list)):
        if (orbit_index%draw_orbit_index == 0):
           orbit_index_list.append(orbit_index) 
    """
    # if drawing sequential orbits
    for orbit_index in range((min(max_num_orbits_to_draw, len(orbit_list)))):
        orbit_index_list.append(orbit_index)


    """
    # ::: STATIC COLORED ORBITS :::
    # Original version based on: https://stackoverflow.com/questions/51891538/create-a-surface-plot-of-xyz-altitude-data-in-python
    color_array = []
    colors = ['red', 'purple', 'blue', 'orange', 'green', 'yellow', 'olive', 'cyan', 'brown']
    x_array = []
    y_array = []
    z_array = []
    t = t_span[0]
    
    for orbit_index in orbit_index_list:
            orbit = orbit_list[orbit_index]
            for s in orbit:
                geocentric = s.at(t)
                x, y, z = geocentric.position.km
                x_array.append(x)
                y_array.append(y)
                z_array.append(z)
                orbit_color = colors[orbit_index%len(colors)]
                color_array.append(orbit_color)
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(x_array, y_array, z_array, c=color_array)
    plt.show()
    """
    
    """
    # ::: ANIMATED ORBITS :::
    # Updating plot over time:  https://www.geeksforgeeks.org/how-to-update-a-plot-on-same-figure-during-the-loop/
    plt.ion() # used to run GUI event loop
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    empty_array = []
    #sp = ax.scatter(X, Y, Z, c=color_array)
    #sp = ax.scatter(empty_array, empty_array, empty_array, c='red')
    ax_min = -6000
    ax_max = 6000

    ax.set_xlim3d(ax_min, ax_max)
    ax.set_ylim3d(ax_min, ax_max)
    ax.set_zlim3d(ax_min, ax_max)

    # assuming equal number of satellites in each orbit
    colors = ['red', 'blue', 'green', 'yellow', 'orange', 'purple', 'olive', 'cyan', 'brown']
    color_array = []
    #for orbit_index in range(len(orbit_list[0])):
    #    orbit_color = colors[orbit_index%len(colors)]
    #    color_array.append(orbit_color)


    #sp = ax.scatter(empty_array, empty_array, empty_array, c=color_array)
    sp = ax.scatter(empty_array, empty_array, empty_array)
    fig.show()
  
    for t_i in t_span:  # t_span defined at start of plotting section
        x_array = []
        y_array = []
        z_array = []
        for orbit_index in orbit_index_list:
            orbit = orbit_list[orbit_index]
            for s in orbit:
                geocentric = s.at(t_i)
                x, y, z = geocentric.position.km
                x_array.append(x)
                y_array.append(y)
                z_array.append(z)
                #orbit_color = colors[orbit_index%len(colors)]
                #color_array.append(orbit_color)

        X = np.array(x_array)
        Y = np.array(y_array)
        Z = np.array(z_array)
        sp._offsets3d = (X, Y, Z)
        #sp.set_segments(X, Y, Z)
        #sp.set(color=color_array)
        plt.draw()
        plt.pause(.1)
    plt.waitforbuttonpress()
    """

    # ---------- TESTING ------------

    # :: Testing N/S/E/W ::

    h_range = range(0, 24)
    t_span = ts.utc(2023, 5, 9, h_range)

    test_orbit_b_index = random.randint(0, len(orbit_list)-1)
    test_orbit_a_index = (test_orbit_b_index - 1) % len(orbit_list)
    test_orbit_c_index = (test_orbit_b_index + 1) % len(orbit_list)

    test_orbit_a = orbit_list[test_orbit_a_index]
    test_orbit_b = orbit_list[test_orbit_b_index]
    test_orbit_c = orbit_list[test_orbit_c_index]

    test_sat_2_index = random.randint(0, len(test_orbit_a)-1)
    test_sat_1_index = (test_sat_2_index - 1) % len(test_orbit_a)
    test_sat_3_index = (test_sat_2_index + 1) % len(test_orbit_a)

    test_sat_a1 = test_orbit_a[test_sat_1_index]
    test_sat_a2 = test_orbit_a[test_sat_2_index]
    test_sat_a3 = test_orbit_a[test_sat_3_index]

    test_sat_b1 = test_orbit_b[test_sat_1_index]
    test_sat_b2 = test_orbit_b[test_sat_2_index]
    test_sat_b3 = test_orbit_b[test_sat_3_index]

    test_sat_c1 = test_orbit_c[test_sat_1_index]
    test_sat_c2 = test_orbit_c[test_sat_2_index]
    test_sat_c3 = test_orbit_c[test_sat_3_index]

    for t_i in t_span:
        print(t_i.utc_jpl())
        geocentric_a1 = test_sat_a1.at(t_i)
        geocentric_a2 = test_sat_a2.at(t_i)
        geocentric_a3 = test_sat_a3.at(t_i)

        a1_lat, a1_lon = wgs84.latlon_of(geocentric_a1)
        a2_lat, a2_lon = wgs84.latlon_of(geocentric_a2)
        a3_lat, a3_lon = wgs84.latlon_of(geocentric_a3)
        print(f"Type of lat: {type(a3_lat)}")
        print(f"Compare test: {a3_lat.degrees < a2_lat.degrees}")
        print(f"Sat_a1 lat: {a1_lat}, long: {a1_lon}")
        print(f"Sat_a2 lat: {a2_lat}, long: {a2_lon}")
        print(f"Sat_a3 lat: {a3_lat}, long: {a3_lon}")
        print("\n")
        print(f"Sat_a1 is North of Sat_a3: {sat_is_North_of (geocentric_a1, geocentric_a3)}")
        print(f"Sat_a1 is East of Sat_a3: {sat_is_East_of (geocentric_a1, geocentric_a3)}")
        print("\n")

        """
        pos_a1 = geocentric_a1.position.km
        pos_a2 = geocentric_a2.position.km
        pos_a3 = geocentric_a3.position.km
        print(f"Sat_a1 position: {pos_a1}")
        print(f"Sat_a2 position: {pos_a2}")
        print(f"Sat_a3 position: {pos_a3}")
        print("\n")
        """
        
        geocentric_b1 = test_sat_b1.at(t_i)
        #geocentric_b2 = test_sat_b2.at(t_i)
        #geocentric_b3 = test_sat_b3.at(t_i)

        pos_b1 = geocentric_b1.position.km
        #pos_b2 = geocentric_b2.position.km
        #pos_b3 = geocentric_b3.position.km

        geocentric_c1 = test_sat_c1.at(t_i)
        #geocentric_c2 = test_sat_c2.at(t_i)
        #geocentric_c3 = test_sat_c3.at(t_i)

        b1_lat, b1_lon = wgs84.latlon_of(geocentric_b1)
        c1_lat, c1_lon = wgs84.latlon_of(geocentric_c1)
        print(f"Sat_a1 lat: {a1_lat}, long: {a1_lon}")
        print(f"Sat_b1 lat: {b1_lat}, long: {b1_lon}")
        print(f"Sat_c1 lat: {c1_lat}, long: {c1_lon}")
        print("\n")
        print(f"Sat_a1 is North of Sat_c1: {sat_is_North_of (geocentric_a1, geocentric_c1)}")
        print(f"Sat_a1 is East of Sat_c1: {sat_is_East_of (geocentric_a1, geocentric_c1)}")
        print("\n")

        """
        pos_c1 = geocentric_c1.position.km
        pos_c2 = geocentric_c2.position.km
        pos_c3 = geocentric_c3.position.km
        print(f"Sat_a1 position: {pos_a1}")
        print(f"Sat_b1 position: {pos_b1}")
        print(f"Sat_c1 position: {pos_c1}")
        print("\n")
        """

    """
    # :: Testing Satellite Distances ::
    t = ts.utc(2023, 5, 9, 14)
    i = 0
    test_orbit_index = random.randint(0, len(orbit_list)-1)
    test_orbit = orbit_list[test_orbit_index]
    test_sat_index = random.randint(0, len(test_orbit)-1)
    test_sat = test_orbit[test_sat_index]
    print(f"Testing satellite satnum: {test_sat.model.satnum} in orbit {test_orbit_index}")
    closest_sat_list = test_orbit[:test_sat_index] + test_orbit[test_sat_index+1:]  # make a satellite list that doesn't contain the test sat
    closest_sat = find_closest_satellite(test_sat, closest_sat_list, t)

    closest_sat_list.remove(closest_sat)
    next_closest_sat = find_closest_satellite(test_sat, closest_sat_list, t)
    print(f"Satellites closest to satellite: {test_sat.model.satnum} are {closest_sat.model.satnum} and {next_closest_sat.model.satnum}")

    sat1 = test_sat 
    sat2 = closest_sat
    sat3 = next_closest_sat
    
    t_range = range(0,20)
    t_span = ts.utc(2023, 5, 9, t_range) # calculate max/min distance over time interval
    print(f"Calculating distance between satellites {sat1.model.satnum} and {sat2.model.satnum} in this orbit over {len(t_range)} hour interval")
    dist_list = []
    for t_i in t_span:
        dist_diff = (sat1.at(t_i) - sat2.at(t_i)).distance().km
        dist_list.append(int(abs(dist_diff)))

    print(f'\tMinimum distance: {min(dist_list)}km')
    print(f'\tMaximum distance: {max(dist_list)}km')
    print(f'\tAmount of distance change: {max(dist_list)-min(dist_list)}km')

    print(f"Calculating distance between satellites {sat1.model.satnum} and {sat3.model.satnum} in this orbit over {len(t_range)} hour interval")
    dist_list = []
    for t_i in t_span:
        dist_diff = (sat1.at(t_i) - sat3.at(t_i)).distance().km
        dist_list.append(int(abs(dist_diff)))

    print(f'\tMinimum distance: {min(dist_list)}km')
    print(f'\tMaximum distance: {max(dist_list)}km')
    print(f'\tAmount of distance change: {max(dist_list)-min(dist_list)}km')

    print(f"\nChecking height variability of satellite {test_sat.model.satnum} over same time span")
    min_height = min(get_satellite_height(test_sat, t_i) for t_i in t_span)
    max_height = max(get_satellite_height(test_sat, t_i) for t_i in t_span)
    height_diff = int(max_height - min_height)
    print(f'\tHeight difference for satellite {test_sat.model.satnum} over {len(t_range)} hours: {height_diff}km')
    """

    exit()

if __name__ == "__main__":
    main()