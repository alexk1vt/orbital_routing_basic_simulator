import subprocess
from datetime import datetime

# Available arguments
specify_routing_method_arg = "-r"
specify_packet_schedule_arg = "-c"
specify_interval_arg = "-i"
specify_update_interval_arg = "-e"
specify_num_increments_arg = "-n"
specify_num_packets_per_interval_arg = "-k"
specify_disruption_schedule_arg = "-l"
specify_disruption_option_arg = "-z"
specify_csv_output_arg = "-v"
do_disruptions_arg = "-d"

# Empty arguments
routing_method_arg = ""
packet_schedule_arg = ""
disruption_schedule_arg = ""

# Packet schedule method arguments
EW_equator_packet = "EW_equator"
# Routing method arguments
TriCoord_routing_method = "Distributed Link State TriCoord"
DistDijkstarHop_routing_method = "Distributed Dijkstar Hop"
DistMotif_routing_method = "Distributed Motif"

# disruption schedule arguments
type_I_disruption_schedule = "type_I"

# WHICH RUNS TO DO
run_list = [4,5,6]#[1,2,3]
# 1: TriCoord, no disruptions
# 2: TriCoord, disruptions, Reims, 25
# 3: TriCoord, disruptions, Reims, 75
# 4: DistDijkstarHop, no disruptions
# 5: DistDijkstarHop, disruptions, Reims, 25
# 6: DistDijkstarHop, disruptions, Reims, 75

# FIRST RUN
#  TriCoord
#  EW_equator
#  No Disruptions

# Script arguments
routing_method_arg = TriCoord_routing_method
packet_schedule_arg = EW_equator_packet
interval_arg = "1" # Simulator updates every 1 second
update_interval_arg = "3" # Satellites update each other every 3 seconds
num_increments_arg = "1800" # 30 minutes
num_packets_per_interval_arg = "100"

# Output path
output_path = "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\outputs\\"

# CSV output argument
csv_path = output_path
csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
# no disruptions
csv_output_name = csv_friendly_routing_method_arg + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + ".csv"
csv_output_arg = csv_path + csv_output_name

# Std output file path
std_output_path = output_path + csv_output_name + "_std_output.txt"

# Notify the user
print("FIRST RUN")
if 1 not in run_list:
    print("  Skipping this run")
else:
    print("  Running the simulator with the following arguments:")
    print(f"  python orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {specify_csv_output_arg} {csv_output_arg}")
    print(f"  Std output will be saved to {std_output_path}")
    print(f"  Start time is: {datetime.now().time()}")
    # Run the simulator
    # no disruptions
    with open (std_output_path, "w") as f:
        subprocess.run(["python", "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
                        specify_routing_method_arg, routing_method_arg, 
                        specify_packet_schedule_arg, packet_schedule_arg,
                        specify_interval_arg, interval_arg,
                        specify_update_interval_arg, update_interval_arg,
                        specify_num_increments_arg, num_increments_arg,
                        specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                        specify_csv_output_arg, csv_output_arg], 
                        stdout=f, stderr=subprocess.STDOUT)

# SECOND RUN
# (change only what needs changing)
#  TriCoord
#  EW_equator
#  Disruptions
#    type_I
#      300, Reims, 25, 30, 1500

# Script arguments
disruption_schedule_arg = type_I_disruption_schedule
disruption_option_start = "300" # 5 min #"15"
disruption_option_end = "1500" # 25 min #"60"
disruption_option_location = "Reims"
disruption_option_intensity = "25"
disruption_option_overhead_angle = "30"
disruption_option_arg = f"{disruption_option_start},{disruption_option_location},{disruption_option_intensity},{disruption_option_overhead_angle},{disruption_option_end}" #"15,Pontianak,25,30,60"

# CSV output argument
csv_friendly_disruption_option_arg = disruption_option_arg.replace(",", "_")
csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
csv_output_name = csv_friendly_routing_method_arg + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + "_d_l_" + disruption_schedule_arg + "_z_" + csv_friendly_disruption_option_arg + ".csv"
csv_output_arg = csv_path + csv_output_name

# Std output file path
std_output_path = output_path + csv_output_name + "_std_output.txt"

# Notify the user
print("SECOND RUN")
if 2 not in run_list:
    print("  Skipping this run")
else:
    print("  Running the simulator with the following arguments:")
    print(f"  python orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {do_disruptions_arg} {specify_disruption_schedule_arg} {disruption_schedule_arg} {specify_disruption_option_arg} {disruption_option_arg} {specify_csv_output_arg} {csv_output_arg}")
    print(f"  Std output will be saved to {std_output_path}")
    print(f"  Start time is: {datetime.now().time()}")
    # Run the simulator (with disruptions)
    with open (std_output_path, "w") as f:
        subprocess.run(["python", "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
                        specify_routing_method_arg, routing_method_arg, 
                        specify_packet_schedule_arg, packet_schedule_arg,
                        specify_interval_arg, interval_arg,
                        specify_update_interval_arg, update_interval_arg,
                        specify_num_increments_arg, num_increments_arg,
                        specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                        do_disruptions_arg, specify_disruption_schedule_arg, disruption_schedule_arg,
                        specify_disruption_option_arg, disruption_option_arg,
                        specify_csv_output_arg, csv_output_arg], 
                        stdout=f, stderr=subprocess.STDOUT)

# THIRD RUN
# (change only what needs changing)
#  TriCoord
#  EW_equator
#  Disruptions
#    type_I
#      300, Reims, 75, 30, 1500

# Script arguments

disruption_option_intensity = "75"
disruption_option_arg = f"{disruption_option_start},{disruption_option_location},{disruption_option_intensity},{disruption_option_overhead_angle},{disruption_option_end}" #"15,Pontianak,25,30,60"

# CSV output argument

csv_friendly_disruption_option_arg = disruption_option_arg.replace(",", "_")
csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
csv_output_name = csv_friendly_routing_method_arg + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + "_d_l_" + disruption_schedule_arg + "_z_" + csv_friendly_disruption_option_arg + ".csv"
csv_output_arg = csv_path + csv_output_name

# Std output file path
std_output_path = output_path + csv_output_name + "_std_output.txt"

# Notify the user
print("THIRD RUN")
if 3 not in run_list:
    print("  Skipping this run")
else:
    print("  Running the simulator with the following arguments:")
    print(f"  python orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {do_disruptions_arg} {specify_disruption_schedule_arg} {disruption_schedule_arg} {specify_disruption_option_arg} {disruption_option_arg} {specify_csv_output_arg} {csv_output_arg}")
    print(f"  Std output will be saved to {std_output_path}")
    print(f"  Start time is: {datetime.now().time()}")
    # Run the simulator (with disruptions)
    with open (std_output_path, "w") as f:
        subprocess.run(["python", "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
                        specify_routing_method_arg, routing_method_arg, 
                        specify_packet_schedule_arg, packet_schedule_arg,
                        specify_interval_arg, interval_arg,
                        specify_update_interval_arg, update_interval_arg,
                        specify_num_increments_arg, num_increments_arg,
                        specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                        do_disruptions_arg, specify_disruption_schedule_arg, disruption_schedule_arg,
                        specify_disruption_option_arg, disruption_option_arg,
                        specify_csv_output_arg, csv_output_arg], 
                        stdout=f, stderr=subprocess.STDOUT)

# FOURTH RUN
#  DistDijkstarHop
#  EW_equator
#  No Disruptions

# Script arguments
routing_method_arg = DistDijkstarHop_routing_method

# CSV output argument
csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
# no disruptions
csv_output_name = csv_friendly_routing_method_arg + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + ".csv"
csv_output_arg = csv_path + csv_output_name

# Std output file path
std_output_path = output_path + csv_output_name + "_std_output.txt"

# Notify the user
print("FOURTH RUN")
if 4 not in run_list:
    print("  Skipping this run")
else:
    print("  Running the simulator with the following arguments:")
    print(f"  python orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {specify_csv_output_arg} {csv_output_arg}")
    print(f"  Std output will be saved to {std_output_path}")
    print(f"  Start time is: {datetime.now().time()}")
    # Run the simulator
    # no disruptions
    with open (std_output_path, "w") as f:
        subprocess.run(["python", "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
                        specify_routing_method_arg, routing_method_arg, 
                        specify_packet_schedule_arg, packet_schedule_arg,
                        specify_interval_arg, interval_arg,
                        specify_update_interval_arg, update_interval_arg,
                        specify_num_increments_arg, num_increments_arg,
                        specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                        specify_csv_output_arg, csv_output_arg], 
                        stdout=f, stderr=subprocess.STDOUT)
        
# FIFTH RUN
# (change only what needs changing)
#  DistDijkstarHop
#  EW_equator
#  Disruptions
#    type_I
#      300, Reims, 25, 30, 1500

# Script arguments
disruption_schedule_arg = type_I_disruption_schedule
disruption_option_start = "300" # 5 min #"15"
disruption_option_end = "1500" # 25 min #"60"
disruption_option_location = "Reims"
disruption_option_intensity = "25"
disruption_option_overhead_angle = "30"
disruption_option_arg = f"{disruption_option_start},{disruption_option_location},{disruption_option_intensity},{disruption_option_overhead_angle},{disruption_option_end}" #"15,Pontianak,25,30,60"

# CSV output argument
csv_friendly_disruption_option_arg = disruption_option_arg.replace(",", "_")
csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
csv_output_name = csv_friendly_routing_method_arg + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + "_d_l_" + disruption_schedule_arg + "_z_" + csv_friendly_disruption_option_arg + ".csv"
csv_output_arg = csv_path + csv_output_name

# Std output file path
std_output_path = output_path + csv_output_name + "_std_output.txt"

# Notify the user
print("FIFTH RUN")
if 2 not in run_list:
    print("  Skipping this run")
else:
    print("  Running the simulator with the following arguments:")
    print(f"  python orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {do_disruptions_arg} {specify_disruption_schedule_arg} {disruption_schedule_arg} {specify_disruption_option_arg} {disruption_option_arg} {specify_csv_output_arg} {csv_output_arg}")
    print(f"  Std output will be saved to {std_output_path}")
    print(f"  Start time is: {datetime.now().time()}")
    # Run the simulator (with disruptions)
    with open (std_output_path, "w") as f:
        subprocess.run(["python", "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
                        specify_routing_method_arg, routing_method_arg, 
                        specify_packet_schedule_arg, packet_schedule_arg,
                        specify_interval_arg, interval_arg,
                        specify_update_interval_arg, update_interval_arg,
                        specify_num_increments_arg, num_increments_arg,
                        specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                        do_disruptions_arg, specify_disruption_schedule_arg, disruption_schedule_arg,
                        specify_disruption_option_arg, disruption_option_arg,
                        specify_csv_output_arg, csv_output_arg], 
                        stdout=f, stderr=subprocess.STDOUT)
        

# SIXTH RUN
# (change only what needs changing)
#  DistDijkstarHop
#  EW_equator
#  Disruptions
#    type_I
#      300, Reims, 75, 30, 1500

# Script arguments

disruption_option_intensity = "75"
disruption_option_arg = f"{disruption_option_start},{disruption_option_location},{disruption_option_intensity},{disruption_option_overhead_angle},{disruption_option_end}" #"15,Pontianak,25,30,60"

# CSV output argument

csv_friendly_disruption_option_arg = disruption_option_arg.replace(",", "_")
csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
csv_output_name = csv_friendly_routing_method_arg + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + "_d_l_" + disruption_schedule_arg + "_z_" + csv_friendly_disruption_option_arg + ".csv"
csv_output_arg = csv_path + csv_output_name

# Std output file path
std_output_path = output_path + csv_output_name + "_std_output.txt"

# Notify the user
print("SIXTH RUN")
if 3 not in run_list:
    print("  Skipping this run")
else:
    print("  Running the simulator with the following arguments:")
    print(f"  python orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {do_disruptions_arg} {specify_disruption_schedule_arg} {disruption_schedule_arg} {specify_disruption_option_arg} {disruption_option_arg} {specify_csv_output_arg} {csv_output_arg}")
    print(f"  Std output will be saved to {std_output_path}")
    print(f"  Start time is: {datetime.now().time()}")
    # Run the simulator (with disruptions)
    with open (std_output_path, "w") as f:
        subprocess.run(["python", "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
                        specify_routing_method_arg, routing_method_arg, 
                        specify_packet_schedule_arg, packet_schedule_arg,
                        specify_interval_arg, interval_arg,
                        specify_update_interval_arg, update_interval_arg,
                        specify_num_increments_arg, num_increments_arg,
                        specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                        do_disruptions_arg, specify_disruption_schedule_arg, disruption_schedule_arg,
                        specify_disruption_option_arg, disruption_option_arg,
                        specify_csv_output_arg, csv_output_arg], 
                        stdout=f, stderr=subprocess.STDOUT)