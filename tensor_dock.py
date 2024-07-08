import subprocess
import time
import json
import paramiko
import requests
import configparser
from discord import SyncWebhook
import os
import ast
import re
import threading

MAIN_SERVER_LIST         = []
PURCHASED_SERVER_DETAILS = []


def discord_message(messages,webhook_url):
    webhook = SyncWebhook.from_url(url=webhook_url)
    webhook.send(content=f"```{messages}```")


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


def process_server_data(server_data):
    extracted_info = []
    hostnodes = server_data.get("hostnodes", {})
    for server_id, server_info in hostnodes.items():
        extracted_server = {
            "UUID": server_id,
            "country": server_info.get("location", {}).get("country"),
            "city": server_info.get("location", {}).get("city"),
            "region": server_info.get("location", {}).get("region"),
            "id": server_info.get("location", {}).get("id"),
            "ports": server_info.get("networking", {}).get("ports", []),
            "cpu_amount": server_info.get("specs", {}).get("cpu", {}).get("amount"),
            "cpu_price": server_info.get("specs", {}).get("cpu", {}).get("price"),
            "cpu_specs": server_info.get("specs", {}).get("cpu", {}).get("type"),
            "ram_amount": server_info.get("specs", {}).get("ram", {}).get("amount"),
            "ram_price": server_info.get("specs", {}).get("ram", {}).get("price"),
            "gpu_specs": list(server_info.get("specs", {}).get("gpu", {}).keys()),
            "storage_amount": server_info.get("specs", {}).get("storage", {}).get("amount"),
            "storage_price": server_info.get("specs", {}).get("storage", {}).get("price"),
            "listed": server_info.get("status", {}).get("listed"),
            "online": server_info.get("status", {}).get("online"),
            "report": server_info.get("status", {}).get("report"),
            "reserved": server_info.get("status", {}).get("reserved"),
            "uptime": server_info.get("status", {}).get("uptime")
        }
        extracted_info.append(extracted_server)
    return extracted_info


def find_servers(key, token):
    url = f"https://marketplace.tensordock.com/api/v0/client/deploy/hostnodes?api_key={key}api_token={token}?minRAM=32&minStorage=80&maxGPUCount=0"

    payload = f"curl --location --request GET {url}"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.get(url, headers=headers, data=payload)
    data = response.json()

    servers_data = process_server_data(data)
    return servers_data


def buy_servers(key:str, token:str, passw:str, name:str, servers, data, settings):
    """
    Used for Buying new Servers
    """
    for daduh in servers:
        if len(servers) >= 1:
            host_node   = daduh[0]
            ports       = daduh[2]
            ex_ports    = "{" + ", ".join(map(str, ports[-3:])) + "}"
            in_ports    = "{" + ", ".join(map(str, [22, 3389, 8888])) + "}"
            ram         = data[0]
            cpus        = data[1]
            store       = data[2]
            url         = "https://marketplace.tensordock.com/api/v0/client/deploy/single"

            # Request payload as a URL-encoded string
            payload = (
                f'api_key={key}&'
                f'api_token={token}&'
                f'password={passw}&'
                f'name={name}&'
                f'vcpus={cpus}&'
                f'ram={ram}&'
                f'external_ports={ex_ports}&'
                f'internal_ports={in_ports}&'
                f'hostnode={host_node}&'
                f'storage={store}&'
                'operating_system=Ubuntu 22.04 LTS'
            )

            # Making the POST request with the URL-encoded payload
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            # Attempt to parse JSON response
            try:
                response = requests.post(url, headers=headers, data=payload)
                response_json = response.json()
                print(response_json)
            except ValueError as e:
                print("Failed to parse JSON response:", e)
                print("Trying another Server")
                continue
            
            cost        = response_json["cost"]["total_price"]
            ip          = response_json["ip"]
            port_for    = response_json["port_forwards"]
            server      = response_json["server"]

            PURCHASED_SERVER_DETAILS.append([host_node, cost, ip, port_for, server])
            return True
        else:
            print("Adding more Servers")
            return


def create_server(key, token, hr_cost: float, server_qty, cpus: int, ram: int, store: int):
    """
        Used for finding a Server and Sending over the id
    """
    new_server_list = []
    same_same = False

    finding_servers = find_servers(key, token)
    
    for server_info in finding_servers:
        if server_info["country"]:
            if int(server_info["cpu_amount"]) >= cpus:
                if int(server_info["ram_amount"]) >= ram:
                    if int(server_info["storage_amount"]) >= store:
                        if server_info["listed"]:
                            if server_info["online"]:
                                if not server_info["reserved"]:
                                    new_server_list.append(
                                        [
                                            server_info["UUID"],
                                            server_info["country"],
                                            server_info["cpu_amount"],
                                            server_info["cpu_price"],
                                            server_info["ram_amount"],
                                            server_info["ram_price"],
                                            server_info["storage_amount"],
                                            server_info["storage_price"],
                                            server_info["ports"],
                                            server_info["gpu_specs"]
                                        ]
                                    )

    servers_selected = 0
    for servers in new_server_list:
        #if servers_selected >= server_qty:
        #    break

        uid           = servers[0]
        ports         = servers[8]
        cpu_price     = float(servers[3]) * cpus
        ram_price     = float(servers[5]) * ram
        storage_price = float(servers[7]) * store
        total_cost    = cpu_price + ram_price + storage_price
        total_daily   = total_cost * 24

        # 13121b1e-eb21-4460-8d35-ab5d9d0ccca5
        # dc74ae1d-ac3e-434f-a6aa-3409733d8c36
        #if len(bad_ip) >= 1:
        #    for uuid in bad_ip:
        #        print(uid)
        #        print(uuid[0])
        #        print(uuid[1])
        #        time.sleep(30)
        #        if uuid[1] == uid:
        #            print(f"Same UUIDs and a bad Host.. Next... Bought {uid}: Old {uuid}")
        #            same_same = True
        #            break
        #    if same_same:
        #        same_same = False
        #        break

        if total_cost <= hr_cost:
            MAIN_SERVER_LIST.append([uid, total_daily, ports])
            servers_selected += 1

    return MAIN_SERVER_LIST


def destroy_servers(data):
    for settings in data:
        print(settings)
        uuid = str(settings[0][0])
        print(uuid)
        time.sleep(30)
        key = settings[1]
        token = settings[2]
        url = "https://marketplace.tensordock.com/api/v0/client/delete/single"
        payload = f'api_key={key}&api_token={token}&server={uuid}'
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(url, headers=headers, data=payload)
        data = response.json()
        print(data)
    return True


def attach_or_create_tmux_session(shell, ip, port, gpu, cpu):
    # Replace periods with underscores in the session name
    if gpu == 0:
        session_name = f"ssh_session_{ip.replace('.', '_')}_{port}_cpu{cpu}"
    else:
        if cpu > 0:
            session_name = f"ssh_session_{ip.replace('.', '_')}_{port}_gpu{gpu}_cpu{cpu}"
        else:
            session_name = f"ssh_session_{ip.replace('.', '_')}_{port}_gpu{gpu}"

    # Check if tmux is installed and running
    check_tmux_installed_command = "tmux -V"
    tmux_installed = execute_remote_command(shell, check_tmux_installed_command, 10)
    if 'command not found' in tmux_installed:
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


def establish_ssh_connection(ssh_ip,ssh_port,ssh_host, ssh_key_file:str, ssh_gpus:int, ssh_cores: int): # No Sleeps
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connect to the SSH server
        print(f"Attempting to connect to {ssh_ip} on port {ssh_port}")
        ssh.connect(hostname=ssh_ip, port=ssh_port, username='user', key_filename=ssh_key_file)
        # Attach to or create a tmux session
        shell = ssh.invoke_shell()
        shell = attach_or_create_tmux_session(shell, ssh_ip, ssh_port, ssh_gpus, ssh_cores)
        print("SSH connection established successfully.")
        return ssh, shell
    except Exception as e:
        print(f"Error connecting to SSH: {e}")
        return None, None


def check_remote_directory_exists(ssh_client, directory_path):
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


def execute_remote_command(shell, command, timeout):
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
            enter1 = execute_remote_command(shell, "sudo reboot", timeout=10)
            print(f"Reboot command1:\n{enter1}")
            time.sleep(30)
            return False, 'rebooted'

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


def check_instances(key:str,token:str):
    """
        Used for Check for Servers
    """

    url      = "https://marketplace.tensordock.com/api/v0/client/list"
    payload  = f"api_key={key}&api_token={token}"
    headers  = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, headers=headers, data=payload)
    data = response.json()
    # Check if 'virtualmachines' exists and is not empty
    if 'virtualmachines' in data and data['virtualmachines']:
        machines = data['virtualmachines']

        #print("Machines:", machines)
        return machines
    else:
        machines = None
        return machines
        

def check_server_balance(key:str,token:str):
    url = "https://marketplace.tensordock.com/api/v0/billing/balance"

    payload  = f"api_key={key}&api_token={token}"
    headers  = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response    = requests.post(url, headers=headers, data=payload)
    portfolio   = response.json()
    balance     = portfolio.get("balance")

    return balance


def server_setup_thread(ssh_ip,ssh_port,ssh_host,local_ssh,webhook,ssh_gpus,ssh_cores,instances,bad_ip):
    time.sleep(60)
    try:
        ssh, shell = establish_ssh_connection(ssh_ip,ssh_port,ssh_host,local_ssh,ssh_gpus,ssh_cores)
        if ssh is False:
            bad_ip.append([[instances,ssh_port,ssh_host]])
            return
        clien_data = [ssh_host,ssh_port,ssh_ip,local_ssh,ssh_gpus]
        ran_setup, message = starting_commands(ssh, shell, ssh_cores, webhook, clien_data)
            # ssh,shell,cpus
        if ssh is True:
            bad_ip.append([[instances,ssh_port,ssh_host]])
            rebooted   = False
            new_server = False
            ran_setup  = False
            return bad_ip, ran_setup, new_server, rebooted
        if message == 'reboot':
            print("Rebooted")
            time.sleep(30)
            ssh, shell = establish_ssh_connection(ssh_ip,ssh_port,ssh_host,local_ssh,ssh_gpus,ssh_cores)
            if ssh is False:
                bad_ip.append([[instances,ssh_port,ssh_host]])
                return
            clien_data = [ssh_host,ssh_port,ssh_ip,local_ssh,ssh_gpus]
            ran_setup, message = starting_commands(ssh, shell, ssh_cores, webhook, clien_data)
        if message == 'running':
            ran_setup  = True
            new_server = False
            rebooted   = False
            return None, ran_setup, new_server, rebooted
    except Exception as e:
        print(e)
        return None, None, None


def create_and_buy_server_thread(key, token, passw, data, name, willing_to_pay, settings, server_qty, cpus, ram, store):
    servers = create_server(key, token, willing_to_pay, server_qty, cpus, ram, store)
    #buy_servers(key,token,passw,name,servers_ids)
    buy_servers(key,token,passw,name,servers,data,settings)
    return


def tensor_main():
    config_dir      = "config_files"
    config_path     = os.path.join(config_dir, "settings.ini")
    settings        = read_config(config_path)
    key             = f"{settings.get('TENSOR', {}).get('key')}"
    token           = f"{settings.get('TENSOR', {}).get('token')}"
    bot_settings    = settings.get("TENSOR", {}).get("choice")
    passw           = settings.get("TENSOR", {}).get("passw")
    name            = settings.get("TENSOR", {}).get("name")
    local_ssh       = settings.get("SETTINGS", {}).get("rsa_path")
    webhook         = settings.get("SETTINGS", {}).get("webhook_url")
    
    balance         = check_server_balance(key,token)
    willing_to_pay  = float(settings.get("TENSOR", {}).get("willing_to_pay"))/24
    server_qty      = int(settings.get("TENSOR", {}).get("tensor_count"))

    rebooted        = False
    new_server      = False
    ran_setup       = False
    
    bad_ip          = []
    threads         = []

    if webhook != None:
        discord_message(
            f"TensorDock Balance: ${balance}\n"
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n", webhook
        )

    while not ran_setup:
        try:
            if not ran_setup:
                instances = check_instances(key,token)
                if instances is not None:
                    for vm_id, vm_data in instances.items():
                        ssh_ports  = vm_data["port_forwards"]
                        ssh_ip     = vm_data["ip_address"]
                        ssh_cost   = float(vm_data["total_price"])
                        ssh_host   = vm_data["hostname"]
                        ssh_gpus   = vm_data["specs"]['gpu']['amount']
                        ssh_cores  = vm_data["specs"]["vcpus"]
                        ssh_port   = next(iter(ssh_ports))

                        if webhook != None:
                            discord_message(
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
                                f"TensorDock Server $/hr: ${round(ssh_cost,4)}\n"
                                f"TensorDock Server $/day: ${round((ssh_cost*24),4)}\n"
                                "Command to get into Server:\n"
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                                webhook
                            )
                            discord_message(
                                f"ssh -p {ssh_port} user@{ssh_ip}\n",
                                webhook
                            )

                        thread = threading.Thread(
                            target=server_setup_thread,
                            args=(ssh_ip, ssh_port, ssh_host, local_ssh, webhook, ssh_gpus, ssh_cores, instances, bad_ip)
                        )
                        threads.append(thread)

                    # Start all threads
                    for thread in threads:
                        thread.start()
                    # Join all threads
                    for thread in threads:
                        thread.join()
                else:
                    new_server = True
        except Exception as e:
            print(f"Error happened in Rerun {e}")
        
        try:
            if new_server:
                if int(bot_settings) == 1:
                    get_data = settings.get("TENSOR", {}).get("settings1")
                    cleaned_data = get_data.strip()
                    data  = ast.literal_eval(cleaned_data)
                    ram   = data[0]
                    cpus  = data[1]
                    store = data[2]
                elif int(bot_settings) == 2:
                    get_data = settings.get("TENSOR", {}).get("settings2")
                    cleaned_data = get_data.strip()
                    data  = ast.literal_eval(cleaned_data)
                    cpus  = data[1]
                    ram   = data[0]
                    store = data[2]
                elif int(bot_settings) == 3:
                    get_data = settings.get("TENSOR", {}).get("settings3")
                    cleaned_data = get_data.strip()
                    data  = ast.literal_eval(cleaned_data)
                    cpus  = data[1]
                    ram   = data[0]
                    store = data[2]
                elif int(bot_settings) == 4:
                    get_data = settings.get("TENSOR", {}).get("settings4")
                    cleaned_data = get_data.strip()
                    data  = ast.literal_eval(cleaned_data)
                    cpus  = data[1]
                    ram   = data[0]
                    store = data[2]
                else:
                    print("Something messed up")

                create_and_buy_server_thread(key, token, passw, data, name, willing_to_pay, settings, server_qty, cpus, ram, store)
                new_server = True
                
                instances = check_instances(key,token)
                if instances is not None:
                    for vm_id, vm_data in instances.items():
                        ssh_ports  = vm_data["port_forwards"]
                        ssh_ip    = vm_data["ip_address"]
                        ssh_cost  = float(vm_data["total_price"])
                        ssh_host  = vm_data["hostname"]
                        ssh_gpus  = vm_data["specs"]['gpu']['amount']
                        ssh_cores = vm_data["specs"]["vcpus"]
                        ssh_port  = next(iter(ssh_ports))
                        
                        if webhook != None:
                            discord_message(
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
                                f"TensorDock Server $/hr: ${round(ssh_cost,4)}\n"
                                f"TensorDock Server $/day: ${round((ssh_cost*24),4)}\n"
                                "Command to get into Server:\n"
                                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n",
                                webhook
                            )
                            discord_message(
                                f"ssh -p {ssh_port} user@{ssh_ip}\n",
                                webhook
                            )

                            thread = threading.Thread(
                                target=server_setup_thread,
                                args=(ssh_ip, ssh_port, ssh_host, local_ssh, webhook, ssh_gpus, ssh_cores, instances, bad_ip)
                            )
                            threads.append(thread)

                    # Start all threads
                    for thread in threads:
                        thread.start()
                    # Join all threads
                    for thread in threads:
                        thread.join()
        except Exception as e:
            print(f"Error in Creating Servers: {e}")

        if balance < 4:
            print("Send Message through Discord to warn")
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

#curl --location 'https://marketplace.tensordock.com/api/v0/client/deploy/single' \
#> --data-urlencode 'api_key=812fc11f-6da9-41b6-8a9f-c644258939a4' \
#> --data-urlencode 'api_token=UzQJLZpzjDXZICRAid9M2cW6I9TXBsWQ' \
#> --data-urlencode 'password=Mjt42391!' \
#> --data-urlencode 'name=OreV2' \
#> --data-urlencode 'vcpus=8' \
#> --data-urlencode 'ram=16' \
#> --data-urlencode 'external_ports={46394, 46395, 46396}' \
#> --data-urlencode 'internal_ports={22, 3389, 8888}' \
#> --data-urlencode 'hostnode=015d9961-77dc-47f1-8933-cc32af37c544' \
#> --data-urlencode 'storage=20' \
#> --data-urlencode 'operating_system=Ubuntu 22.04 LTS'