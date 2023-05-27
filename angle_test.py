# Path: angle_test.py

fore = 0
aft = 180
starboard = 90
port = 270

interface_correct_range = 30
interface_lateral_range = 180

# (neigh_sat_interface_bearing - int(interface_lateral_range / 1.5) < dest_bearing) and (dest_bearing < neigh_sat_interface_bearing + int(interface_lateral_range / 1.5))
neigh_sat_interface_bearing = port
test_val = 220


lower_range = (neigh_sat_interface_bearing - int(interface_lateral_range / 1.5) + 360) % 360
upper_range = (neigh_sat_interface_bearing + int(interface_lateral_range / 1.5) + 360) % 360
in_range = (test_val - lower_range) % 360 <= (upper_range - lower_range) % 360

print(f"Interace bearing: {neigh_sat_interface_bearing}, +- {int(interface_lateral_range / 1.5)}: Lower range: {lower_range}, Upper range: {upper_range} - test_val: {test_val}")
if in_range:
    print(f"Test_val: {test_val} is in range: {lower_range} - {upper_range}")
else:
    print(f"Test_val: {test_val} is not in range: {lower_range} - {upper_range}")


"""
lower_range = 180 - abs(abs(neigh_sat_interface_bearing - int(interface_lateral_range / 1.5)) - 180)
upper_range = 180 - abs(abs(neigh_sat_interface_bearing + int(interface_lateral_range / 1.5)) - 180)
print(f"Interace bearing: {neigh_sat_interface_bearing}, +- {int(interface_lateral_range / 1.5)}: Lower range: {lower_range}, Upper range: {upper_range} - test_val: {test_val}")
lower_range = lower_range if (neigh_sat_interface_bearing + lower_range == int(interface_lateral_range / 1.5)) else -lower_range
upper_range = upper_range if (neigh_sat_interface_bearing + upper_range == int(interface_lateral_range / 1.5)) else -upper_range
print(f"Interace bearing: {neigh_sat_interface_bearing}, +- {int(interface_lateral_range / 1.5)}: Lower range: {lower_range}, Upper range: {upper_range} - test_val: {test_val}")
"""

"""
print("Alternative: ")
lower_range = 180 - abs(abs(neigh_sat_interface_bearing - int(interface_lateral_range / 1.5)) - 180)
upper_range = 180 - abs(abs(neigh_sat_interface_bearing + int(interface_lateral_range / 1.5)) - 180)
print(f"Interace bearing: {neigh_sat_interface_bearing}, +- {int(interface_lateral_range / 1.5)}: Lower range: {lower_range}, Upper range: {upper_range} - test_val: {test_val}")
lower_range = (lower_range + 360) % 360
upper_range = (upper_range + 360) % 360
test_val = (test_val + 360) % 360
print(f"Interace bearing: {neigh_sat_interface_bearing}, +- {int(interface_lateral_range / 1.5)}: Lower range: {lower_range}, Upper range: {upper_range} - test_val: {test_val}")
# (neigh_sat_interface_bearing + upper_range == int(interface_lateral_range / 1.5)) ? upper_range : -upper_range
# (condition) ? Expression1 : Expression2
# if condition is true, the entire expression evaluates to Expression1, and otherwise it evaluates to Expression2
"""

"""
print("Alternative 2: ")
lower_range = neigh_sat_interface_bearing - int(interface_lateral_range / 1.5)
lower_range = lower_range if lower_range >= 0 else 360 + lower_range
upper_range = neigh_sat_interface_bearing + int(interface_lateral_range / 1.5)
upper_range = upper_range if upper_range >= 0 else 360 + upper_range
print(f"Interace bearing: {neigh_sat_interface_bearing}, +- {int(interface_lateral_range / 1.5)}: Lower range: {lower_range}, Upper range: {upper_range} - test_val: {test_val}")
print("Testing if test_val is in range: ")
lower_range_test = lower_range < test_val
upper_range_test = test_val < upper_range
if (lower_range < test_val) and (test_val < upper_range):
    print(f"Test_val: {test_val} is in range: {lower_range} - {upper_range}")
else:
    print(f"Test_val: {test_val} is not in range: {lower_range} - {upper_range}")
lower_result = 180 - abs(abs(test_val - lower_range) - 180)
lower_result = lower_result if test_val + lower_result == lower_range else -lower_result
upper_result = 180 - abs(abs(test_val - upper_range) - 180)
upper_result = upper_result if test_val + upper_result == upper_range else -upper_result
print(f"Lower result: {lower_result}, Upper result: {upper_result}")
"""
