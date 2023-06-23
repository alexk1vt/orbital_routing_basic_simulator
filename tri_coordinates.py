# tri_coordinates.py

from orbit_generator import sats_per_orbit
from orbit_generator import orbit_cnt as num_orbits
import baseS # import the baseS class - use as baseS.baseS(decimalValue, num_orbits, sats_per_orbit)

def x_transform(x):
    global num_orbits
    return ((x+(num_orbits/2)) % num_orbits) - (num_orbits/2)
    # (x+36) % 72 - 36

def y_transform(y):
    global sats_per_orbit
    return ((y+sats_per_orbit) % (sats_per_orbit*2)) - sats_per_orbit

def rotate_list(list, num_rotations):
    if num_rotations >= 0:
        for _ in range(num_rotations):
            list.append(list.pop(0))
    else:
        for _ in range(abs(num_rotations)):
            list.insert(0, list.pop())    
    return list

# Get a satellites ABC coordinates - ALT 3
def get_sat_ABC(satnum):
    orbit_num = satnum//sats_per_orbit
    A = orbit_num

    orbit_index = int(satnum % sats_per_orbit)
    B_val = int(((orbit_num - (orbit_num%2)) / 2) - orbit_index) % sats_per_orbit
    B = baseS.baseS(B_val, num_orbits, sats_per_orbit)
            
    C_val = (int(((orbit_num + (orbit_num % 2)) % num_orbits) / 2)  + orbit_index) % sats_per_orbit
    C = baseS.baseS(C_val, num_orbits, sats_per_orbit)

    return A, B, C

# method for finding the distance between two coordinates on a ring
# Given triCoordinates for both current satellite and destination satellite,
# returns the difference for each triCoordinate: A_diff, B_diff, C_diff
def calc_triCoord_dist(curr_A, curr_B, curr_C, dest_A, dest_B, dest_C): # This includes detection of Prime Meridian traversals and offsets B/C values to account for it
    global num_orbits, sats_per_orbit
    # A axis
    A_diff = (dest_A + num_orbits) - (curr_A + num_orbits)
    if abs(A_diff) >= (num_orbits//2):  # check if shorter going the other way
        rev_curr_A = curr_A
        rev_dest_A = dest_A
        if dest_A < curr_A:
            rev_dest_A += num_orbits
        else:
            rev_curr_A += num_orbits
        A_diff = rev_dest_A - rev_curr_A

    # Detect if crossing prime meridian
    crossing_B_PM = False # axis B prime meridian is A = 0
    crossing_C_PM = False # axis C prime meridian is A = 71 (the math just works out that way)


    if (0 <= curr_A <= num_orbits//2): # may cross prime meridian going negative
        if A_diff < 0:
            if curr_A + A_diff < 0:
                crossing_B_PM = True
            if curr_A + A_diff < -1:
                crossing_C_PM = True
    else:  # may cross prime meridian going positive
        if A_diff > 0:
            if (curr_A + A_diff) >= num_orbits:
                crossing_B_PM = True
            if (curr_A + A_diff) >= num_orbits-1:
                crossing_C_PM = True

    # align B and C values to account for prime meridian crossings
    if crossing_B_PM:
        orig_dest_B = dest_B
        if A_diff > 0:
            dest_B = (dest_B - 8) % sats_per_orbit
        else:
            dest_B = (dest_B + 8) % sats_per_orbit
        print(f"\t\t::calc_dist_to_dst:: Crossing B prime meridian! {orig_dest_B} -> {dest_B}")
    if crossing_C_PM:
        orig_dest_C = dest_C
        if A_diff > 0:
            dest_C = (dest_C - 8) % sats_per_orbit
        else:
            dest_C = (dest_C + 8) % sats_per_orbit
        print(f"\t\t::calc_dist_to_dst:: Crossing C prime meridian! {orig_dest_C} -> {dest_C}")

    # modulo B and C values by sats_per_orbit to account for equivelant positions (ie, B0 and B10 are same axis line)
    curr_B = curr_B % sats_per_orbit
    curr_C = curr_C % sats_per_orbit
    dest_B = dest_B % sats_per_orbit
    dest_C = dest_C % sats_per_orbit

    # B axis
    B_diff = (dest_B + sats_per_orbit) - (curr_B + sats_per_orbit)
    if abs(B_diff) >= (sats_per_orbit//2):  # check if shorter going the other way
        if dest_B < curr_B:
            dest_B += sats_per_orbit
        else:
            curr_B += sats_per_orbit
        B_diff = dest_B - curr_B
   
    # C axis
    C_diff = (dest_C + sats_per_orbit) - (curr_C + sats_per_orbit)
    if abs(C_diff) >= (sats_per_orbit//2):  # check if shorter going the other way
        if dest_C < curr_C:
            dest_C += sats_per_orbit
        else:
            curr_C += sats_per_orbit
        C_diff = dest_C - curr_C

    return A_diff, B_diff, C_diff

def calc_triCoord_next_hop_logical_direction(reduction_axis, reduction_dir, along_axis):
        if along_axis == 'A':
            if reduction_axis == 'B':
                if reduction_dir == 'pos':
                    logical_direction = 'logical_S'
                else:
                    logical_direction = 'logical_N'
            else: # major_axis == 'C'
                if reduction_dir == 'pos':
                    logical_direction = 'logical_N'
                else:
                    logical_direction = 'logical_S'
        elif along_axis == 'B':
            if reduction_axis == 'A':
                if reduction_dir == 'pos':
                    logical_direction = 'logical_NE'
                else:
                    logical_direction = 'logical_SW'
            else: # major_axis == 'C'
                if reduction_dir == 'pos':
                    logical_direction = 'logical_NE'
                else:
                    logical_direction = 'logical_SW'
        else: # along_axis is C
            if reduction_axis == 'A':
                if reduction_dir == 'pos':
                    logical_direction = 'logical_SE'
                else:
                    logical_direction = 'logical_NW'
            else: # major_axis == 'B'
                if reduction_dir == 'pos':
                    logical_direction = 'logical_SE'
                else:
                    logical_direction = 'logical_NW'
        return logical_direction