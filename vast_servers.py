import subprocess
import time
import json
import paramiko
import threading
import os
import re
import configparser
import requests
from discord import SyncWebhook
from queue import Queue



MAIN_SERVER_LIST = []

def read_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path)
    settings = {}
    
    for section in config.sections():
        section_settings = {}
        for key, value in config.items(section):
            section_settings[key] = value
        settings[section] = section_settings
    
    return settings


def discord_message(messages,webhook_url): # No Sleeps
    webhook = SyncWebhook.from_url(url=webhook_url)
    webhook.send(content=f"```{messages}```")


def find_servers(): # No sleeps
    """
        Used for finding a server
    """
    command = 'vastai search offers "reliability > 0.99"'
    # Execute the command and capture the output
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    # Check if the command executed successfully
    if result.returncode == 0:
        # Output of the command
        output = result.stdout
        # Split the output into lines
        lines = output.strip().split('\n')
        # Initialize an empty list to store server details
        servers = []
        # Iterate over each line
        for line in lines:
            # Split the line by whitespace
            parts = line.split()
            # Extract ID, CUDA, Model, and $/hr
            server_info = {
                "ID": parts[0],
                "CUDA": parts[1],
                "vCPUs": parts[6],
                "Model": ''.join(parts[3]),
                "N": parts[2].strip('x'),
                "$/hr": parts[9]
            }
            # Append server info to the list
            servers.append(server_info)
        return servers
    else:
        # Error message if the command failed
        print("Error:", result.stderr)


def buy_servers(ids): # 2mins
    """
        Used for Buying a new Servers
    """
    command = ''
    ids_send = []
    for settings in ids:
        for servers in settings:
            _id = str(servers)
            # Command to execute
            command = f"vastai create instance {_id} --image nvidia/cuda:12.0.1-devel-ubuntu22.04 --disk 60 --ssh --direct"
            # Execute the command
            subprocess.run(command, shell=True, capture_output=True, text=True)
            time.sleep(10)
            ids_send.append(_id)
    start_servers(_id)
    return


def create_server(skip: bool, hr_cost: float, server_qty: int): # No Sleeps
    """
        Used for finding a Server and Sending over the id
    """
    finding_servers = find_servers()
    checking_out = []
    models = ['RTX_4090', 'RTX_4070_Ti', 'RTX_A6000', 'RTX_6000Ada', 'RTX_A5000',
              'A100_SXM4', 'RTX_A5000', 'RTX_5000Ada', 'RTX_3090', 'RTX_3090_Ti', 'A100X', 'A40']

    sorted_servers = sorted(finding_servers, key=lambda x: float(x['$/hr']) if x['$/hr'].replace('.', '', 1).isdigit() else float('inf'))

    for server in sorted_servers:
        for gpus in models:
            if gpus in server['Model'] and int(server['N']) >= 1:
                checking_price = float(server['$/hr']) / int(server['N'])
                if checking_price < 0.50 and server['Model'] in ['RTX_4090', 'RTX_3090', 'RTX_3090_Ti']:
                    print(f"Checking for Servers... {server['Model']}, Cost: ${(float(server['$/hr'])/int(server['N']))}/hr, GPUs: {server['N']}")
                    checking_out.append([server['ID'], server['vCPUs'], server['Model'], server['N'], server['$/hr'], time.time()])
                    break

    servers_selected = 0

    for buying_server in checking_out:
        if servers_selected >= server_qty:
            break
        if skip:
            skip = False
            continue
        
        _id, cpus, name, gpu_amount, cost = buying_server[0], buying_server[1], buying_server[2], buying_server[3], float(buying_server[4])
        if cost < hr_cost:
            MAIN_SERVER_LIST.append([_id, cpus])
            servers_selected += 1

            print(
                f'Going to buy this one now\n'
                f'Name: {name} * {gpu_amount}\n'
                f'ID: {_id}\n'
                f'Cost: ${cost * 24}/day\n'
                f'CPUS: {cpus}'
            )

    return MAIN_SERVER_LIST


def start_servers(_id): # No Sleeps
    """
        Only used for Starting new Servers
    """
    for ids in _id:
        command = f"ssh $(vastai ssh-url {ids})"
        time.sleep(30)
        # Execute the command
        subprocess.run(command, shell=True)
    return


def destroy_servers(id): # No Sleeps
    """
        Used for Destroying a Servers
    """
    # Command to execute
    command = f"vastai destroy instance {id}"
    # Execute the command
    subprocess.run(command, shell=True)
    return


def attach_or_create_tmux_session(shell, ip, port, gpu): # No Sleeps
    # Replace periods with underscores in the session name
    session_name = f"ssh_session_{ip.replace('.', '_')}_{port}_gpu{gpu}"

    # Check if tmux is installed and running
    check_tmux_installed_command = "tmux -V"
    tmux_installed = execute_remote_command(shell, check_tmux_installed_command, 10)
    print(tmux_installed)
    if not 'tmux' in tmux_installed:
        print("tmux is not installed on the remote server.")
        return shell
    
    # Check if the session exists
    check_tmux_session_command = f"tmux list-sessions"
    session_check_out = execute_remote_command(shell, check_tmux_session_command, 10)
    print(f"Checking Tmux for Sessions:\n{session_check_out}")

    if session_name in session_check_out:
        # Session exists, attach to it
        attach_tmux_session_command = f"tmux attach-session -t {session_name}"
        attach_out = execute_remote_command(shell, attach_tmux_session_command, 10)
        print(f"Attaching to existing Tmux Session:\n{attach_out}")
    else:
        # Session does not exist, create a new one
        create_tmux_session_command = f"tmux new-session -d -s {session_name}"
        create_out = execute_remote_command(shell, create_tmux_session_command, 10)
        print(f"Starting Tmux Session:\n{create_out}")
        
        # Attach to the newly created session
        attach_tmux_session_command = f"tmux attach-session -t {session_name}"
        attach_out = execute_remote_command(shell, attach_tmux_session_command, 10)
        print(f"Attaching to new Tmux Session:\n{attach_out}")

    return shell


def establish_ssh_connection(ssh_host:str, ssh_port:int, ssh_ip, ssh_key_file:str, ssh_gpus:int): # No Sleeps
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connect to the SSH server
        print(f"Attempting to connect to {ssh_ip} on port {ssh_port}")
        ssh.connect(hostname=ssh_host, port=ssh_port, username='root', key_filename=ssh_key_file)
        # Attach to or create a tmux session
        shell = ssh.invoke_shell()
        shell = attach_or_create_tmux_session(shell, ssh_ip, ssh_port, ssh_gpus)
        print("SSH connection established successfully.")
        return ssh, shell

    except Exception as e:
        print(f"Error connecting to SSH: {e}")
        return None, None


def check_remote_directory_exists(ssh_client, directory_path): # No Sleeps
    # Define the command to check if the directory exists
    check_command = f'[ -f "{directory_path}" ] && echo "Directory exists" || echo "Directory does not exist"'
    
    # Execute the command on the server
    stdin, stdout, stderr = ssh_client.exec_command(check_command)

    # Read the output from the command
    stdout_result = stdout.read().decode().strip()
    stderr_result = stderr.read().decode().strip()

    # Check the output to determine if the directory exists
    if "Directory exists" in stdout_result:
        print(f"The directory {directory_path} exists on the server.")
        return True
    else:
        print(f"The directory {directory_path} does not exist on the server.")
        return False


def execute_remote_command(shell, command, timeout): # No Sleeps
    """
    Execute a single command on the remote server using the shell.
    """
    shell.send(command + '\n')
    output = ""
    start_time = time.time()
    starts_with = '$'

    while True:
        # Check if there is data to receive
        if shell.recv_ready():
            output += shell.recv(65535).decode()

        # Check if the exit status is ready
        if shell.exit_status_ready():
            # Read any remaining output
            remaining_output = shell.recv(65535).decode()
            if remaining_output:
                output += remaining_output
            return output  # Exit the function if exit status is ready
        
        # Check if timeout has been reached
        if time.time() - start_time >= timeout:
            return output


def starting_commands(ssh_client,shell,cores,webhook,clien_data): # 15mins
    retries          = 0
    ran_setup        = False
    all_updates_done = False

    while not ran_setup and retries < 3:
        # Run the initial upgrade command
        upgrade_command = "sudo apt update && sudo apt upgrade --assume-yes"
        stdout = execute_remote_command(shell, upgrade_command,timeout=200)
        print(f"Output of upgrade command:\n{stdout}")
        additional_output = execute_remote_command(shell, "", timeout=5)
        print("Additional Output to get exho:\n", additional_output)
        if "Package configuration" in additional_output:
            for attempt in range(5):
                print(f"Sending ENTER keystroke {attempt + 1}.")
                print("Restart prompt detected. Sending first ENTER keystroke.")
                enter1 = execute_remote_command(shell, "", timeout=5)
                print(f"Reboot command1:\n{enter1}")
                if "Package configuration" in enter1:
                    continue
                else:
                    break

        if "E: Unmet dependencies" in stdout:
            # Fix broken dependencies
            fix_command = "sudo apt --fix-broken install --assume-yes"
            stdout = execute_remote_command(shell, fix_command,timeout=80)
            print(f"Output of upgrade command:\n{stdout}")
            if "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded" in stdout:
                print("All broken dependencies fixed.")
            else:
                print("Failed to fix broken dependencies.")

        # Check if Solana is installed correctly
        sol_command = 'solana --version'
        stdout = execute_remote_command(shell, sol_command,timeout=5)
        print(f"Output of upgrade command:\n{stdout}")
        if "command not found" in stdout:
            print("Should be downloading Solana")
            # Solana is not installed, proceed with installation
            solana_install_command = 'sh -c "$(curl -sSfL https://release.solana.com/v1.18.12/install)"'
            stdout = execute_remote_command(shell, solana_install_command,timeout=180)
            print(f"Output of upgrade command:\n{stdout}")
            if 'PATH="/root/.local/share/solana/install/active_release/bin:$PATH"' in stdout:
                set_path = 'export PATH="/root/.local/share/solana/install/active_release/bin:$PATH"'
                stdout = execute_remote_command(shell, set_path,timeout=5)
                print("Solana installed and set successfully.")
            else:
                print("Failed to install Solana.")
        else:
            print("Solana is already installed and PATH set.")

        # Install cargo
        cargo_command = 'sudo apt install cargo --assume-yes'
        stdout = execute_remote_command(shell, cargo_command,timeout=200)
        print(f"Output of upgrade command:\n{stdout}")
        
        # Check remote directory existence and create if needed
        if not check_remote_directory_exists(ssh_client, '/root/.config/solana/id.json'):
            keygen_command = 'solana-keygen new'
            stdout = execute_remote_command(shell, keygen_command,timeout=10)
            print(f"Output of upgrade command:\n{stdout}")
            if 'BIP39 Passphrase (empty for none):' in stdout:
                stdout = execute_remote_command(shell, '\n',timeout=5)
        
        if not check_remote_directory_exists(ssh_client, '/home/OreV2'):
            create_folder = 'sudo mkdir -m 777 /home/OreV2'
            stdout = execute_remote_command(shell, create_folder,timeout=5)
            print(f"Output of upgrade command:\n{stdout}")
        
        ## Reboot Server here

        print("About to run through the rest of the commands now")

        # Execute a series of commands
        commands = [
            'cd /home/OreV2',
            'git clone https://github.com/hardhatchad/ore',
            'git clone https://github.com/hardhatchad/ore-cli',
            'git clone https://github.com/hardhatchad/drillx',
            'cd ore',
            'git checkout hardhat/v2',
            'cd ..',
            'cd ore-cli',
            'git checkout hardhat/v2',
            'cd ..',
            'solana config set --url d',
            'solana airdrop 1',  # Will be deleted for Mainnet
            'cd ore-cli',
            'cargo build --release'
            #f'./target/release/ore --rpc https://api.devnet.solana.com --keypair ~/.config/solana/id.json mine --threads {cores[2]} --buffer-time 2'
        ]
        for command in commands:            
            if command == 'solana airdrop 1':
                stdout = execute_remote_command(shell, command, timeout=10)
                # Print the output of the command
                print(f"Output of command ({command}):\n{stdout}")
                if not 'Signature:' in stdout:
                    print("Should be sending another request for an airdrop!")
                    re_commands = 'solana airdrop 1'
                    stdout = execute_remote_command(shell, re_commands, timeout=10)
                    print(f"Output of last command:\n{stdout}")

                # Check if the cargo build command was executed
            if command == 'cargo build --release':
                print("Building Cargo..")
                stdout = execute_remote_command(shell, command, timeout=300)
                print(f"Output of Cargo Build command:\n{stdout}")
            if command.startswith("./target/release/ore"):
                print("Last Command to start the Miner")
                stdout = execute_remote_command(shell, command, timeout=15)
                print(f"Output of last commands:\n{stdout}")
                if 'No such file or directory' in stdout:
                    continue
                else:
                    print(f"No more Commands...")
                    discord_message(
                        f"Miner has started..\n",
                        webhook
                    )
                    all_updates_done = True
                    break
            else:
                stdout = execute_remote_command(shell, command, timeout=5)
                print(f"Output of commands:\n{stdout}")
        
            if shell.closed:
                print("Socket is closed, attempting to reconnect...")
                ssh.close()
                ssh, shell = establish_ssh_connection(clien_data[0], clien_data[1], clien_data[2], clien_data[3], clien_data[4])
                if ssh is None or shell is None:
                    print("Reconnection failed.")
                    break
        
        time.sleep(1)  # Sleep briefly to avoid tight loop

        # If all updates and installations are done, break the loop
        if all_updates_done:
            print("All upgrades, updates, and installations are done.")
            ran_setup = True
            break
        else:
            print("Some upgrades and updates are still pending.. Waiting 60 secs..")
            time.sleep(60)

    return ran_setup, 'running'


def restarted_commands(shell,cpu):
    error_count = 0
    time_to_wait = 0
    remaining_time_pattern = re.compile(r'\((\d+) sec remaining\)')
    attempt_pattern = re.compile(r'attempt (\d+)')
    attempt_counter = 0
    attempt_count = 0
    restart_command = (
        './target/release/ore --rpc https://api.devnet.solana.com --keypair ~/.config/solana/id.json'
        f'mine --threads {(cpu*2)-2} --buffer-time 2'
    )
    stop_command = 'pgrep ore'
    
    while True:
        checking_command = 'echo'
        if remaining_time_pattern == 0:
            remaining_time_pattern + 10
        checking_cmd = execute_remote_command(shell, checking_command, 0, 1)

        for line in checking_cmd.split('\n'):
            if 'ERROR' in line:
                error_count += 1
            if 'Mining' in line:
                match = remaining_time_pattern.search(line)
                if match:
                    time_to_wait = match.group(1)
            if 'attempt' in line:
                attempts = attempt_pattern.findall(line)
                if attempts:
                    for attempt in attempts:
                        attempt_count = attempt
                        print(f"Attempt: {attempt_count}")

        if attempt_count >= 50:
            attempt_counter += 1

        if attempt_counter >= 10:
            stdout = execute_remote_command(shell, stop_command, 0, timeout=10)
            print(f"Restart Command:\n{stdout}")
            kill_pid = stdout
            kill_command = f'kill -KILL {kill_pid}'
            stdout = execute_remote_command(shell, kill_command, 0, timeout=10)
            print(f"Kill Command:\n{stdout}")
            time.sleep(15)
            stdout = execute_remote_command(shell, restart_command, 0, timeout=10)
            print(f"Restarted Miner Command:\n{stdout}")

        
        if error_count >= 4:
            stdout = execute_remote_command(shell, stop_command, 0, timeout=10)
            print(f"Restart Command:\n{stdout}")
            kill_pid = stdout
            kill_command = f'kill -KILL {kill_pid}'
            stdout = execute_remote_command(shell, kill_command, 0, timeout=10)
            print(f"Kill Command:\n{stdout}")
            time.sleep(15)
            stdout = execute_remote_command(shell, restart_command, 0, timeout=10)
            print(f"Restarted Miner Command:\n{stdout}")


        print("Remaining time:", time_to_wait)
        time.sleep(int(time_to_wait))


def check_instances(): # No Sleeps
    """
        Used for Check for Servers
    """

    command = f"vastai show instances --raw"
    results = subprocess.run(command, shell=True, capture_output=True, text=True)

    # Check if the subprocess command was successful
    if results.returncode == 0:
        # Access the stdout attribute to get the output
        output = results.stdout

        # Parse the JSON data
        json_data      = json.loads(output)
        processed_data = []
        for item in json_data:
            instance_data           = item.get("instance", {})
            disk_hour_value         = instance_data.get('diskHour', None)
            gpu_cost_per_hour_value = instance_data.get('gpuCostPerHour', None)
            total_hour_value        = instance_data.get('totalHour', None)
            reliability2_value      = item.get("reliability2", None)
            public_ipaddr           = item.get("public_ipaddr", None)
            ssh_host                = item.get("ssh_host", None)
            machine_id              = item.get("machine_id", None)
            actual_status           = item.get("actual_status", None)
            gpu_name                = item.get("gpu_name", None)
            num_gpus                = item.get("num_gpus", None)
            id_value                = item.get("id", None)
            start_date              = item.get("start_date", None)
            direct_port_start       = item.get("direct_port_start", None)
            ssh_port                = item.get("ssh_port", None)
            actual_cpu_cores        = item.get("cpu_cores_effective", None)

        
            processed_data.append({
                "disk_cost": disk_hour_value,
                "gpu_cost": gpu_cost_per_hour_value,
                "total_value": total_hour_value,
                "rel_value": reliability2_value,
                "public_ipaddr": public_ipaddr,
                "ssh_host": ssh_host,
                "machine_id": machine_id,
                "actual_status": actual_status,
                "cpu_cores": actual_cpu_cores,
                "gpu_name": gpu_name,
                "num_gpus": num_gpus,
                "id": id_value,
                "start_date": start_date,
                "direct_port_start": direct_port_start,
                "ssh_port": ssh_port
            })

        return json.dumps(processed_data)
    else:
        # Handle the case where the subprocess command failed
        print("Error:", results.stderr)

        return None


def check_server_balance(key:str): # No Sleeps
    url = "https://console.vast.ai/api/v0/users/current"
	
    headers = {
	  'Accept': 'application/json',
	  'Authorization': f'Bearer {key}'
	}
	
    response  = requests.get(url, headers=headers)
    json_data = response.json()
    balance   = json_data.get('credit')

    return balance


def server_setup_thread(ssh_host, ssh_port, ssh_ip, local_ssh, webhook, ssh_gpus, ssh_cores, instances,bad_ip):
    try:
        ssh, shell = establish_ssh_connection(ssh_host,ssh_port,ssh_ip,local_ssh,ssh_gpus)
        if ssh is False:
            bad_ip.append([[instances,ssh_port,ssh_host]])
            return
        clien_data = [ssh_host,ssh_port,ssh_ip,local_ssh,ssh_gpus]
        ran_setup, message = starting_commands(ssh, shell, ssh_cores, webhook, clien_data)

        if ssh is True:
            bad_ip.append([[instances,ssh_port,ssh_host]])
            rebooted   = False
            new_server = False
            ran_setup  = False
            return bad_ip, ran_setup, new_server, rebooted
        if message == 'reboot':
            time.sleep(10)
            rebooted   = True
            new_server = False
            ran_setup  = False
            return None, ran_setup, new_server, rebooted
        if message == 'running':
            ran_setup  = True
            new_server = False
            rebooted   = False
            return None, ran_setup, new_server, rebooted
    except Exception as e:
        print(e)
        return None, None, None


def create_and_buy_server_thread(willing_to_pay, server_qty):
    data = create_server(False, willing_to_pay, server_qty)
    buy_servers(data)
    return data
        

def vast_main(): # Total Time to run and setup: 17mins
    config_dir      = "config_files"
    config_path     = os.path.join(config_dir, "settings.ini")
    settings        = read_config(config_path)

    local_ssh       = settings.get("SETTINGS", {}).get("rsa_path")
    keys            = settings.get("VAST", {}).get("vast_api")
    webhook         = settings.get("SETTINGS", {}).get("webhook_url")
    balance         = check_server_balance(keys)
    
    willing_to_pay  = float(settings.get("VAST", {}).get("willing_to_pay"))/24
    server_qty      = int(settings.get("VAST", {}).get("vast_count"))

    new_server      = True
    ran_setup       = False
    rebooted        = False
    started         = False

    bad_ip          = []
    threads         = []

    if webhook != None:
        discord_message(
            f"Vast.AI Balance: ${balance}\n"
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n", webhook
        )

    while True:
        try:
            if ran_setup == False:
                instances = check_instances()
                if instances is not None:
                    if started == False:
                        started = True
                        parsed_data = json.loads(instances)
                        for item in parsed_data:
                            ssh_port  = item["ssh_port"]
                            ssh_host  = item["ssh_host"]
                            ssh_ip    = item["public_ipaddr"]
                            ssh_cores = item["cpu_cores"]
                            ssh_cost  = float(item["total_value"])
                            ssh_gpus  = item["num_gpus"]
                            ssh_id    = item["id"]

                            if webhook != None:
                                discord_message(
                                    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
                                    f"Vast.ai Server $/hr: ${round(ssh_cost,2)}\n"
                                    f"Vast.ai Server $/day: ${round((ssh_cost*24),2)}\n"
                                    "Command to get into Server:\n"
                                    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                                    webhook
                                )
                                discord_message(
                                    f"ssh -p {ssh_port} root@{ssh_host} -L 8080:localhost:8080\n",
                                    webhook
                                )

                                thread = threading.Thread(
                                    target=server_setup_thread,
                                    args=(ssh_host, ssh_port, ssh_ip, local_ssh, webhook, ssh_gpus, ssh_cores, instances, bad_ip)
                                )
                                threads.append(thread)

                        # Start all threads
                        for thread in threads:
                            thread.start()

                        # Join all threads
                        for thread in threads:
                            thread.join()
        except Exception as e:
            print(f"Servers are pressent, error happened: {e}")
        
        try:
            if new_server:
                data = create_and_buy_server_thread(willing_to_pay, server_qty)
                instances = check_instances()
                started = True
                if instances is not None:
                    parsed_data = json.loads(instances)
                    for item in parsed_data:
                        ssh_port  = item["ssh_port"]
                        ssh_host  = item["ssh_host"]
                        ssh_ip    = item["public_ipaddr"]
                        ssh_cores = data[0]
                        ssh_cost  = float(item["total_value"])
                        ssh_gpus  = item["num_gpus"]
                        ssh_id    = item["id"]

                        new_server = False
                        
                        if webhook != None:
                            discord_message(
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
                                f"Vast.ai Server $/hr: ${round(ssh_cost,2)}\n"
                                f"Vast.ai Server $/day: ${round((ssh_cost),2)*24}\n"
                                "Command to get into Server:\n"
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                                webhook
                            )
                            discord_message(
                                f"ssh -p {ssh_port} root@{ssh_host} -L 8080:localhost:8080\n",
                                webhook
                            )

                        thread = threading.Thread(
                            target=server_setup_thread,
                            args=(ssh_host, ssh_port, ssh_ip, local_ssh, webhook, ssh_gpus, ssh_cores, instances, bad_ip)
                        )
                        threads.append(thread)

                    # Start all threads
                    for thread in threads:
                        thread.start()

                    # Join all threads
                    for thread in threads:
                        thread.join()

        except Exception as e:
            print(f"Servers being built, error happened: {e}")

        if balance < 2:
            print("Send Message through Discord to warn")
            if webhook != None:
                discord_message(
                    f"Vast.AI Balance: ${balance}\n"
                    "You need to add more Money into Vast before Servers get Deleted."
                    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                    webhook
                )
            if balance < .50:
                break

        if len(bad_ip) > 0:
            time.sleep(2)

        if rebooted:
            print("Reboot detected, restarting setup process...")
            rebooted = False
            time.sleep(2)
        
        for del_Servers in bad_ip:
            destroy_servers(del_Servers)
            break

        time.sleep(1)

#if __name__ == "__main__":
#    main()