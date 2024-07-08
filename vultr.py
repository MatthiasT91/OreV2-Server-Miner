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


def find_servers(key:str, server_qty:int): # No sleeps
    """
        Used for finding a server
    """
    url = "https://api.vultr.com/v2/plans"
    # Execute the command and capture the output
    headers = {
	  'Accept': 'application/json',
	  'Authorization': "Bearer {}".format(key)
	}
	
    response  = requests.get(url, headers=headers)
    json_data = response.json()
    # Sort the plans first by vcpu_count, then by monthly_cost
    sorted_plans = sorted(json_data['plans'], key=lambda x: (x['vcpu_count'], x['monthly_cost']))

    plans_with_12_cpus = [
        {'id': plan['id'], 'vcpu_count': plan['vcpu_count'], 
         'ram': plan['ram'], 'disk': plan['disk'], 
         'monthly_cost': plan['monthly_cost'], 
         'locations': plan['locations']
        } for plan in sorted_plans if plan['vcpu_count'] == 12
    ]
    cheapest_plans = plans_with_12_cpus[0]
    lax_location   = cheapest_plans['locations'][cheapest_plans['locations'].index('lax')]

    data = {
        "region": lax_location,
        "plan": cheapest_plans.get("id"),
        "label": "OreV2",
        "os_id": 1743
    }
    return data


def buy_servers(ids): # 2mins
    """
        Used for Buying a new Servers
    """
    command = ''
    for settings in ids:
        for servers in settings:
            _id = str(servers)
            # Command to execute
            command = f"vastai create instance {_id} --image nvidia/cuda:12.0.1-devel-ubuntu22.04 --disk 60 --ssh --direct"
            # Execute the command
            subprocess.run(command, shell=True, capture_output=True, text=True)
            time.sleep(120) # Wait for Server to be created, 2mins
            start_servers(_id)
    return


def create_server(key: bool, server_qty: int): # No Sleeps
    """
        Used for finding a Server and Sending over the id
    """
    finding_servers = find_servers(key,server_qty)
    print(finding_servers)

    time.sleep(600)

    return


def start_servers(_id): # No Sleeps
    """
        Only used for Starting new Servers
    """
    command = f"ssh $(vastai ssh-url {_id})"
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


def manage_connections(ssh_host, ssh_port, ssh_ip, ssh_key_file, ssh_gpus): # No Sleeps
    threads = []
    result_queue = Queue()

    if int(ssh_gpus) > 1:
        for x in range(int(ssh_gpus)):
            thread = threading.Thread(
                target = establish_ssh_connection,
                args   = (ssh_host, ssh_port, ssh_ip, ssh_key_file, x, result_queue)
            )
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Collect results from the queue
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        # Sort results by GPU id
        results.sort(key=lambda x: x[0])
        ssh_shell_pairs = [(ssh, shell) for ssh, shell in results]
        
        # Assuming we want to return ssh and shell of the first GPU
        if ssh_shell_pairs:
            ssh, shell = ssh_shell_pairs[0]
            return ssh, shell
        else:
            return None, None

    else:
        result_queue = Queue()
        establish_ssh_connection(ssh_host, ssh_port, ssh_ip, ssh_key_file, 1, result_queue)
        ssh, shell = result_queue.get()
        return ssh, shell


def establish_ssh_connection(ssh_host:str, ssh_port:int, ssh_ip, ssh_key_file:str, ssh_gpus:int, result_queue: Queue): # No Sleeps
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
        result_queue.put((ssh, shell)) 
        print("SSH connection established successfully.")
        return result_queue

    except Exception as e:
        print(f"Error connecting to SSH: {e}")
        return None


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


def starting_commands(ssh_client,shell,cores,webhook): # 15mins
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
            #f'./target/release/ore --rpc https://api.devnet.solana.com --keypair ~/.config/solana/id.json mine --threads {int(cores)} --buffer-time 2'
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


def check_instances(key:str): # No Sleeps
    """
        Used for Check for Servers
    """

    url = "https://api.vultr.com/v2/instances"
    headers = {
	  'Accept': 'application/json',
	  'Authorization': f'Bearer {key}'
	}
	
    response  = requests.get(url, headers=headers)
    json_data = response.json()

    # Check if the subprocess command was successful
    if json_data:
        # Access the stdout attribute to get the output
        # Parse the JSON data
        processed_data = []
        print(json_data)
        for item in json_data:
            if isinstance(item, dict):
                print(item)
                instance_data           = item.get("instances", {})
                meta                    = item.get("meta", None)

                processed_data.append({
                    "instance_data": instance_data,
                    "meta": meta
                })

                return json.dumps(processed_data)
    else:
        # Handle the case where the subprocess command failed
        print("Error:", json_data)

        return None


def check_server_balance(key:str): # No Sleeps
    url = "https://api.vultr.com/v2/account"
	
    headers = {
	  'Accept': 'application/json',
	  'Authorization': f'Bearer {key}'
	}
	
    response  = requests.get(url, headers=headers)
    json_data = response.json()
    account   = json_data.get("account")
    balance   = account.get('balance')

    return balance


def vultr_main(): # Total Time to run and setup: 17mins
    config_dir      = "config_files"
    config_path     = os.path.join(config_dir, "settings.ini")
    settings        = read_config(config_path)

    local_ssh       = settings.get("SETTINGS", {}).get("rsa_path")
    keys            = settings.get("VULTR", {}).get("vultr_api")
    webhook         = settings.get("SETTINGS", {}).get("webhook_url")
    balance         = check_server_balance(keys)
    
    willing_to_pay  = float(settings.get("VULTR", {}).get("willing_to_pay"))/24
    server_num      = int(settings.get("VULTR", {}).get("vast_count"))
    
    rebooted        = False
    new_server      = True
    ran_setup       = False
    
    servers_ids     = []
    bad_ip          = []

    server_qty      = 1

    if webhook != None:
        discord_message(
            f"Vultr Balance: ${balance}\n"
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n", webhook
        )

    while not ran_setup:
        try:
            if not ran_setup:
                instances = check_instances(keys)
                if instances is not None:
                    parsed_data = json.loads(instances)
                    for item in parsed_data:
                        ssh_port  = item["ssh_port"]
                        ssh_host  = item["ssh_host"]
                        ssh_ip    = item["public_ipaddr"]
                        ssh_cores = item["cpu_cores"]
                        ssh_cost  = float(item["total_value"])
                        ssh_gpus  = item["num_gpus"]

                        if webhook != None:
                            discord_message(
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
                                f"Vast.ai Server $/hr: ${ssh_cost}\n"
                                f"Vast.ai Server $/day: ${ssh_cost*24}\n"
                                "Command to get into Server:\n"
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                                webhook
                            )
                            discord_message(
                                f"ssh -p {ssh_port} root@{ssh_host} -L 8080:localhost:8080\n",
                                webhook
                            )

                        ## A new Thread for each GPU it has
                        ssh, shell  = manage_connections(ssh_host,ssh_port,ssh_ip,local_ssh,ssh_gpus)
                        if ssh == False:
                            print("Hitting down here")
                            bad_ip.append([[instances,ssh_port,ssh_host]])
                            break
                        
                        new_server = False
                        if ssh:
                            ran_setup, message = starting_commands(ssh,shell,ssh_cores,webhook)
                            #ran_setup = restarted_commands(shell,cpus)
                            if ssh == True:
                                bad_ip.append([[instances,ssh_port,ssh_host]])
                                ran_setup = False
                                new_server = True
                                break
                            if message == 'reboot':
                                time.sleep(10)
                                rebooted = True
                                new_server = False
                                break
                            if message == 'running':
                                ran_setup  = True
                                new_server = False
                                break
                            else:
                                ran_setup = True
                                new_server = False
                                break
                    
                        for del_Servers in bad_ip:
                            destroy_servers(del_Servers)
                            break
                        
                        if ran_setup:
                            break

            if new_server:
                # WIll need to add a spot so you can add more based off funds and days of running.. MATH..
                if len(MAIN_SERVER_LIST) == 0:
                    create_server(keys,willing_to_pay,server_qty)
                    new_server = True
                    if len(MAIN_SERVER_LIST) >= 1:
                        for servers in MAIN_SERVER_LIST:
                            servers_ids.append([servers[0],servers[1]])
                            ran_setup = True
                            print("About to add data to list")
                            if new_server:
                                print("About to buy a server", servers_ids[0])
                                buy_servers(servers_ids)
                                instances = check_instances(keys)
                                if instances is not None:
                                    parsed_data = json.loads(instances)
                                    for item in parsed_data:
                                        ssh_port  = item["ssh_port"]
                                        ssh_host  = item["ssh_host"]
                                        ssh_ip    = item["public_ipaddr"]
                                        ssh_cores = servers_ids[0][1]
                                        ssh_cost  = float(item["total_value"])
                                        ssh_gpus  = item["num_gpus"]
                                        if webhook != None:
                                            discord_message(
                                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
                                                f"Vast.ai Server $/hr: ${ssh_cost}\n"
                                                f"Vast.ai Server $/day: ${ssh_cost*24}\n"
                                                "Command to get into Server:\n"
                                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                                                webhook
                                            )
                                            discord_message(
                                                f"ssh -p {ssh_port} root@{ssh_host} -L 8080:localhost:8080\n",
                                                webhook
                                            )
                                        
                                        ssh, shell  = manage_connections(ssh_host,ssh_port,ssh_ip,local_ssh,ssh_gpus)
                                        if ssh == False:
                                            bad_ip.append([[instances,ssh_port,ssh_host]])
                                            ran_setup = False
                                            new_server = True
                                            break
                                        
                                        ran_setup, message = starting_commands(ssh,shell,ssh_cores,webhook)
                                        if message == 'reboot':
                                            time.sleep(10)
                                            rebooted = True
                                            new_server = False
                                            break
                                        if message == 'running':
                                            ran_setup = True
                                            new_server = False
                                            break
                                        else:
                                            ran_setup = True
                                            new_server = False
                                            break
                                        
                            for del_Servers in bad_ip:
                                destroy_servers(del_Servers)
                                break
            
            if balance < 2 and balance > 0:
                print("Send Message through Discord to warn")
                if webhook != None:
                    discord_message(
                        f"Vultr Balance: ${balance}\n"
                        "You need to add more Money into Vultr before Servers get Deleted."
                        "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                        webhook
                    )
                if balance < .50:
                    break

        except Exception as e:
            print(e)

        if len(bad_ip) > 0:
            time.sleep(2)

        if rebooted:
            print("Reboot detected, restarting setup process...")
            rebooted = False
            time.sleep(2)
        
        time.sleep(1)

#if __name__ == "__main__":
#    main()