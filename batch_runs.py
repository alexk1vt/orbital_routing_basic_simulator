import os
import subprocess
import platform
from datetime import datetime

systemOS = platform.system()
if systemOS == 'Linux':
    python = "python3"
elif systemOS == 'Windows':
    python = "python"
print(f"System OS is {systemOS}; using python command: {python}")

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
EW_high_latitude_packet = "EW_high_latitude"
NS_old_world_packet = "NS_old_world"
NS_new_world_packet = "NS_new_world"

# Routing method arguments
TriCoord_routing_method = "Distributed Link State TriCoord"
DistDijkstarHop_routing_method = "Distributed Dijkstar Hop"
DistMotif_routing_method = "Distributed Motif"
DistCoinFlip_routing_method = "Distributed Coin Flip"
DistNaiveBasic_routing_method = "Distributed Naive Basic"

# disruption schedule arguments
no_disruption_schedule = None
type_I_disruption_schedule = "type_I"

# Standard sim arguments
interval_arg = "60" # Simulator updates every 1 minute
update_interval_arg = "2" # Satellites update every 2 minutes
num_increments_arg = "35" # 0.35 hours
num_packets_per_interval_arg = "10"#"10"

# Disruption arguments (static)
disruption_schedule_arg = type_I_disruption_schedule
disruption_option_start = "2"#"300" # 5 hours
disruption_option_end = "3"#"600" # 10 hours
disruption_option_overhead_angle = "30"

# Disruption arguments (dynamic)
routing_method_list = [DistNaiveBasic_routing_method, DistCoinFlip_routing_method, TriCoord_routing_method, DistDijkstarHop_routing_method, DistMotif_routing_method]
packet_schedule_list = [EW_equator_packet]
disruption_schedule_list = [no_disruption_schedule] #[no_disruption_schedule, type_I_disruption_schedule]
disruption_location_list = ["Reims"]
disruption_intensity_list = ["25", "75"]

current_run = 1
number_of_disruption_types = len([x for x in disruption_schedule_list if x != no_disruption_schedule])
if no_disruption_schedule in disruption_schedule_list:
    number_of_no_disruption_runs = len(routing_method_list) * len(packet_schedule_list)
else:
    number_of_no_disruption_runs = 0
number_of_disruption_runs = len(routing_method_list) * len(packet_schedule_list) * number_of_disruption_types * len(disruption_location_list) * len(disruption_intensity_list)
number_of_runs = number_of_disruption_runs + number_of_no_disruption_runs
print(f"Number of runs: {number_of_runs} ({number_of_no_disruption_runs} no disruption runs, {number_of_disruption_runs} disruption runs)")


print(f"Static Arguments:")
print(f"\tinterval_arg: {interval_arg}")
print(f"\tupdate_interval_arg: {update_interval_arg}")
print(f"\tnum_increments_arg: {num_increments_arg}")
print(f"\tnum_packets_per_interval_arg: {num_packets_per_interval_arg}")

print(f"\nDynamic Arguments:")
print(f"\trouting_method_list: {routing_method_list}")
print(f"\tpacket_schedule_list: {packet_schedule_list}")
print(f"\tdisruption_schedule_list: {disruption_schedule_list}")
print(f"\tdisruption_location_list: {disruption_location_list}")
print(f"\tdisruption_intensity_list: {disruption_intensity_list}")

for routing_method_arg in routing_method_list:
    for packet_schedule_arg in packet_schedule_list:
        for disruption_schedule_arg in disruption_schedule_list:
            if disruption_schedule_arg == no_disruption_schedule:
                # No disruptions
                # Output path
                if systemOS == 'Linux':
                    path = "/home/alex/repos/orbital_routing_basic_simulator/"
                    output_path = path + "outputs/" + routing_method_arg.replace(" ", "_") + "/"
                elif systemOS == 'Windows':
                    path = "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\"
                    output_path = path + "outputs\\" + routing_method_arg.replace(" ", "_") + "/"
                if not os.path.exists(output_path):
                    os.makedirs(output_path)
                # CSV output argument
                csv_path = output_path
                csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
                csv_output_name = csv_friendly_routing_method_arg + "_" + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + ".csv"
                csv_output_arg = csv_path + csv_output_name
                # Std output file path
                std_output_path = output_path + csv_output_name + "_std_output.txt"
                # Notify the user
                print(f"\n~~RUN NUMBER {current_run} OUT OF {number_of_runs}~~")
                print(f"\tRouting Method: {routing_method_arg}")
                print(f"\tPacket Schedule: {packet_schedule_arg}")
                print("  Running the simulator with the following arguments:")
                print(f"  {python} orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {specify_csv_output_arg} {csv_output_arg}")
                print(f"  Std output will be saved to {std_output_path}")
                start_time = datetime.now()
                print(f"  Start time is: {start_time.time()}")
                # Run the simulator
                with open (std_output_path, "w") as f:
                    subprocess.run([python, path +"orbit_generator.py",
                                    specify_routing_method_arg, routing_method_arg, 
                                    specify_packet_schedule_arg, packet_schedule_arg,
                                    specify_interval_arg, interval_arg,
                                    specify_update_interval_arg, update_interval_arg,
                                    specify_num_increments_arg, num_increments_arg,
                                    specify_num_packets_per_interval_arg, num_packets_per_interval_arg,
                                    specify_csv_output_arg, csv_output_arg], 
                                    stdout=f, stderr=subprocess.STDOUT)
                current_run += 1
                stop_time = datetime.now()
                print(f"  Run completed in {(stop_time - start_time).seconds / 60:.1f} minutes")
            else:
                for disruption_option_location in disruption_location_list:
                    for disruption_option_intensity in disruption_intensity_list:                    
                        # disruptions
                        disruption_option_arg = f"{disruption_option_start},{disruption_option_location},{disruption_option_intensity},{disruption_option_overhead_angle},{disruption_option_end}" #"15,Pontianak,25,30,60"
                        # Output path
                        if systemOS == 'Linux':
                            path = "/home/alex/repos/orbital_routing_basic_simulator/"
                            output_path = path + "outputs/" + routing_method_arg.replace(" ", "_") + "/"
                        elif systemOS == 'Windows':
                            path = "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\"
                            output_path = path + "outputs\\" + routing_method_arg.replace(" ", "_") + "/"
                        if not os.path.exists(output_path):
                            os.makedirs(output_path)
                        # CSV output argument
                        csv_path = output_path
                        csv_friendly_routing_method_arg = routing_method_arg.replace(" ", "_")
                        csv_friendly_disruption_option_arg = disruption_option_arg.replace(",", "_")
                        csv_output_name = csv_friendly_routing_method_arg + "_" + packet_schedule_arg + "_i_" + interval_arg + "_e_" + update_interval_arg + "_n_" + num_increments_arg + "_k_" + num_packets_per_interval_arg + "_d_l_" + disruption_schedule_arg + "_z_" + csv_friendly_disruption_option_arg + ".csv"
                        csv_output_arg = csv_path + csv_output_name
                        # Std output file path
                        std_output_path = output_path + csv_output_name + "_std_output.txt"
                        # Notify the user
                        print(f"\n~~RUN NUMBER {current_run} out of {number_of_runs}~~")
                        print(f"\tRouting Method: {routing_method_arg}")
                        print(f"\tPacket Schedule: {packet_schedule_arg}")
                        print(f"\tDisruption Schedule: {disruption_schedule_arg}")
                        print(f"\tDisruption Location: {disruption_option_location}")
                        print(f"\tDisruption Intensity: {disruption_option_intensity}")
                        print(f"\tDisruption Start Interval: {disruption_option_start}")
                        print(f"\tDisruption End Interval: {disruption_option_end}")
                        print(f"\tDisruption Overhead Angle: {disruption_option_overhead_angle}")
                        print("  Running the simulator with the following arguments:")
                        # disruptions
                        print(f"  {python} orbit_generator.py {specify_routing_method_arg} {routing_method_arg} {specify_packet_schedule_arg} {packet_schedule_arg} {specify_interval_arg} {interval_arg} {specify_update_interval_arg} {update_interval_arg} {specify_num_increments_arg} {num_increments_arg} {specify_num_packets_per_interval_arg} {num_packets_per_interval_arg} {do_disruptions_arg} {specify_disruption_schedule_arg} {disruption_schedule_arg} {specify_disruption_option_arg} {disruption_option_arg} {specify_csv_output_arg} {csv_output_arg}")
                        print(f"  Std output will be saved to {std_output_path}")
                        start_time = datetime.now()
                        print(f"  Start time is: {start_time.time()}")
                        # Run the simulator
                        with open (std_output_path, "w") as f:
                            subprocess.run([python, "C:\\Users\\xande\\source\\repos\\orbital_routing_basic_simulator\\orbit_generator.py ",
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
                        current_run += 1
                        stop_time = datetime.now()
                        print(f"  Run completed in {(stop_time - start_time).seconds / 60:.1f} minutes")
        
print(f"  Script completed at: {datetime.now().time()}")