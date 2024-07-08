from tqdm import tqdm
from solana.rpc.api import Client
from spl.token.client import Token
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from discord import SyncWebhook
from datetime import datetime
from vast_servers import *
from tensor_dock import *
from vultr import *
import ed25519
import base58
import threading
import subprocess
import configparser
import os
import time
import json
import platform
import itertools


class Send:
    def transfer_sol(self, json, to_address, amount, url):
        results = []
        try:
            command = f'solana transfer --from {json} {to_address} {amount} --allow-unfunded-recipient --url {url} --fee-payer {json}'
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            results.append([stdout, stderr])
            return results
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None
    
    def check_balance(self, address, url):
        try:
            command = f'solana balance {address} --url {url}'
            output = self.get_output(command)
            return output
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None
        
    def check_mint_balances(self, address, url):
        try:
            command = f'spl-token accounts --owner {address} --url {url}'
            output = self.get_output(command)
            amounts = self.extract_token_balances(output)
            return amounts
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None
        
    def get_output(self, command: str) -> str | None:
        try:
            output = subprocess.check_output(command, shell=True)
            return output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None
        
    def extract_token_balances(self, balance_output):
        lines = balance_output.strip().split('\n')
        token_balances = []
        for line in lines[2:]:
            tokens = line.split()
            if len(tokens) >= 2:
                token = tokens[0]
                try:
                    balance = float(tokens[-1])
                    token_balances.append([balance, token])
                except ValueError:
                    pass  # Skip lines that can't be converted to float
        return token_balances

    def transfer_tokens(self, token_to_send, token_progID, fromWallet, toWallet, amount, jsonID, rpc):
        mint       = Pubkey.from_string(token_to_send)
        program_id = Pubkey.from_string(token_progID)

        with open(jsonID, 'r') as f:
            private_key_integers = json.load(f)

        private_key_bytes = bytes(private_key_integers)
        key_pairs         = base58.b58encode(private_key_bytes).decode('utf-8')
        key_pair          = Keypair.from_base58_string(key_pairs)
        solana_client     = Client(rpc)
        spl_client        = Token(conn=solana_client, pubkey=mint, program_id=program_id, payer=key_pair)
        source            = Pubkey.from_string(fromWallet)
        dest              = Pubkey.from_string(toWallet)

        try:
            source_token_account = spl_client.get_accounts_by_owner(owner=source, commitment=None, encoding='base64').value[0].pubkey
        except:
            source_token_account = spl_client.create_associated_token_account(owner=source, skip_confirmation=False, recent_blockhash=None)
        try:
            dest_token_account = spl_client.get_accounts_by_owner(owner=dest, commitment=None, encoding='base64').value[0].pubkey
        except:
            dest_token_account = spl_client.create_associated_token_account(owner=dest, skip_confirmation=False, recent_blockhash=None)

        transaction = spl_client.transfer(source=source_token_account, dest=dest_token_account, owner=key_pair, amount=int(float(amount)*1000000000), multi_signers=None, opts=None, recent_blockhash=None)
        
        if transaction:
            print(f"Transaction: {transaction}")
            txn_signature = transaction
            print(f"Transaction: {txn_signature}")
            return txn_signature


class Ore:
    def __init__(self, pairs: str):
        config_dir = "config_files"
        settings_conf = os.path.join(config_dir, "settings.ini")
        settings = read_config(settings_conf)
        for i in range(int(settings.get("SERVERS", {}).get("rpc_count"))):
            i += 1
            rpc_list = []
            rpcs = settings.get("SERVERS", {}).get(f"rpc_{i}")
            rpc_list.append(rpcs)

        self.rpc             = rpc_list
        self.keypair_paths   = pairs

        self.priority_fee    = int(settings.get("MINERS", {}).get("priority_fee"))
        self.threads         = int(settings.get("MINERS", {}).get("threads"))
        self.buffer          = int(settings.get("MINERS", {}).get("buffer_time"))
        self.parallel_miners = int(settings.get("MINERS", {}).get("parallel_miners"))
        self.miners_pause    = float(settings.get("MINERS", {}).get("miners_pause"))
        self.miners_wave     = int(settings.get("MINERS", {}).get("miners_wave"))

    def get_output(self, command: str) -> str | None:
        try:
            output = subprocess.check_output(command, shell=True)
            return output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None

    def rewards(self, keypair: str, rpc: str, path: str):
        command = f"{path}/orz-cli/target/release/orz.exe --keypair {keypair} --rpc {rpc} rewards"
        output: str = self.get_output(command)

        if output is not None:
            rewards = float(output.split()[0])
        else:
            rewards = 0

        return rewards

    def rewards_multiple(self,keypair: str, rpc_path: str, path: str):
        rewards = 0
        rewards += self.rewards(keypair, rpc_path, path)
        return rewards

    def parallel_mining(self, rpc: str, keypair: str, path: str):
        results = []
        try:
            def command():
                cargo_command = f"{path}/orz-cli/target/release/orz.exe --rpc {rpc}" + \
                    f" --priority-fee {self.priority_fee} --keypair {keypair}" + \
                    f"mine --threads {self.threads} --buffer-time {self.buffer}"

                process = subprocess.Popen(
                    cargo_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()
                results.append([stdout, stderr])

            time.sleep(5)

            threads = []

            for i in tqdm(range(self.parallel_miners), desc="Deploying miners", unit="m"):
                if i != 0 and i % self.miners_wave == 0:
                    time.sleep(self.miners_phase)
                else:
                    time.sleep(5)

                t = threading.Thread(target=command)
                threads.append(t)
                t.start()

        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None
        
        return

    def force_claim(self, rpc: str, keypair: str, number: int, webhook_url: str, path: str):
        try:
            command = f'{path}/orz-cli/target/release/orz.exe --keypair {keypair} --priority-fee {self.priority_fee} --rpc {rpc} claim'
            attempts = 0
            success_msg = ''
            while attempts < 6:
                attempts += 1
                checking_rewards = self.rewards(keypair, rpc, path)

                if checking_rewards == 0:
                    print("You have no rewards to claim. Exiting.")
                    break
                else:
                    print(f"Trying to claim {checking_rewards:06f} ORE with Wallet #{number}")

                output = self.get_output(command)

                print(f"The output for claiming: {output}")

                if checking_rewards >= 0.1:
                    time.sleep(10)
                    continue

                success_msg = "Transaction landed!"

                if success_msg in output:
                    today = datetime.today()
                    print("Successfully claimed your ORE!!!")
                    discord_message(f"Succesfully claimed your ORE rewards: {checking_rewards:06f}!!!\n From Wallet #{number}\n Date: {today}\n", number, webhook_url)
                    break

                time.sleep(5)

            return success_msg

        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            return None


class ClaimThread(threading.Thread):
    def __init__(self, ore_instance, number, keypair_path, rpc, webhook, path):
        threading.Thread.__init__(self)
        self.ore_instance = ore_instance
        self.count = number
        self.keypair_path = keypair_path
        self.rpc_path = rpc
        self.webhook = webhook
        self.path = path

    def run(self):
        claiming = self.ore_instance.force_claim(self.rpc_path,self.keypair_path,self.count,self.webhook, self.path)

        if claiming == "Transaction landed!":
            return claiming
        else:
            return


def discord_message(messages,count,webhook_url):
    webhook = SyncWebhook.from_url(url=webhook_url)
    webhook.send(content=f"Wallet #{count}```{messages}```")

def save_wallets_to_files(pubkeys, privatekeys,path: str):
    id_jsons = 1
    if not os.path.exists("generated_wallets"):
        os.makedirs("generated_wallets")
    
    with open("generated_wallets/addresses.txt", "w") as addresses_file, open("generated_wallets/privatekeys.txt", "w") as privatekeys_file:
        for filename in os.listdir(path):
            if filename.endswith(".json"):
                id_jsons += 1
        
        for i, (pub, priv) in enumerate(zip(pubkeys, privatekeys), start=id_jsons):
            addresses_file.write(f"Address #{i}: {pub}\n")
            privatekeys_file.write(f"PrivateKey #{i}: {priv}\n")

def wallet_create(wallet_count: int, path: str):
    pubkeys = []
    privatekeys = []

    if wallet_count == 0:
        return

    import_wallets = input("Do you have wallets you want to import? (yes/no): ").strip().lower()

    if import_wallets == 'yes':
        # Ask for public and private keys to import
        for _ in range(wallet_count):
            pubkey = input("Enter the public key: ").strip()
            privatekey = input("Enter the private key: ").strip()
            pubkeys.append(pubkey)
            privatekeys.append(privatekey)
    else:
        # Generate new wallets
        for _ in range(wallet_count):
            account = Keypair()
            private_key = base58.b58encode(account.secret() + base58.b58decode(str(account.pubkey()))).decode('utf-8')
            pubkeys.append(account.pubkey())
            privatekeys.append(private_key)

    save_wallets_to_files(pubkeys, privatekeys, path)

def create_id_jsons(wc,path: str):
    jsons          = []
    json_paths     = []
    wallet_address = []
    id_jsons       = 1
    if wc != 0:
        if os.path.exists("generated_wallets"):
            with open("generated_wallets/privatekeys.txt", "r") as privatekeys_file:
                for private_key_base58 in privatekeys_file:
                    private_key        = private_key_base58.split(":")[1].strip()
                    private_key_bytes  = base58.b58decode(private_key.strip())
                    private_key_list   = list(private_key_bytes)
                    private_key_base58 = base58.b58encode(private_key_bytes).decode('utf-8')
                    jsons.append(str(private_key_list))
                    # private_key_base58 = base58.b58encode(private_key_bytes).decode('utf-8')

        if jsons:
            if not os.path.exists(path):
                print("You need to install Solana First")
                return None

            for filename in os.listdir(path):
                if filename.endswith(".json"):
                    id_jsons += 1

            for i, item in enumerate(jsons, start=id_jsons):
                json_name = f"{path}/id{i}.json"

                with open(json_name, "w") as json_file:
                    json_paths.append(json_name)
                    json_file.write(item)

                with open(json_name) as json_loads:
                    privatekeys_list = json.load(json_loads)
                    private_key_bytes = bytes(privatekeys_list)
                    private_key_base58 = base58.b58encode(private_key_bytes).decode('utf-8')
                    private_key_bytes = base58.b58decode(private_key_base58)
                    private_key = ed25519.SigningKey(private_key_bytes)
                    public_key_bytes = private_key.get_verifying_key().to_bytes()
                    wallet_address.append(base58.b58encode(public_key_bytes).decode('utf-8'))

            return json_paths, wallet_address

    else:
        json_files = [filename for filename in os.listdir(path) if filename.endswith(".json")]
        ids   = len(json_files)

        for i in range(ids):
            i += 1
            json_name = f"{path}/id{i}.json"
            with open(json_name) as json_loads:
                privatekeys_list = json.load(json_loads)
                private_key_bytes = bytes(privatekeys_list)
                private_key_base58 = base58.b58encode(private_key_bytes).decode('utf-8')
                private_key_bytes = base58.b58decode(private_key_base58)
                private_key = ed25519.SigningKey(private_key_bytes)
                public_key_bytes = private_key.get_verifying_key().to_bytes()
                wallet_address.append(base58.b58encode(public_key_bytes).decode('utf-8'))
            json_paths.append(json_name)

    return json_paths, wallet_address

def send_sol(settings, keypair, wall_address):
    initialize      = Send()
    id_jsons        = 0
    rpc             = settings.get("SERVERS", {}).get('rpc_1')
    mint_address    = settings.get("MINT", {}).get('mint_address')
    token_programID = settings.get("MINT", {}).get('token_programid')

    wallet_addy_fn  = "generated_wallets/addresses.txt"
    wallet_json_fn  = settings.get("SETTINGS", {}).get('json_path')
    wallet_address  = []
    wallet_jsons    = []

    if os.path.exists(wallet_addy_fn):
        with open(wallet_addy_fn) as read_addy:
            addys = read_addy.read()
            lines = addys.strip("[]").split("\n")
            stripped_addresses = [address.split(": ")[1] for address in lines if address]
            wallet_address.extend(stripped_addresses)
        
        for i, address in enumerate(wallet_address, start=1):
            file_path = f"{wallet_json_fn}/id{i}.json"
            wallet_jsons.append(file_path)
    else:
        for main in os.listdir(wallet_json_fn):
            if main.endswith(".json"):
                id_jsons += 1
                json_name = f"{wallet_json_fn}/id{id_jsons}.json"
                with open(json_name) as json_loads:
                    privatekeys_list = json.load(json_loads)
                    private_key_bytes = bytes(privatekeys_list)
                    private_key_base58 = base58.b58encode(private_key_bytes).decode('utf-8')
                    private_key_bytes = base58.b58decode(private_key_base58)
                    private_key = ed25519.SigningKey(private_key_bytes)
                    public_key_bytes = private_key.get_verifying_key().to_bytes()
                    wallet_address.append(base58.b58encode(public_key_bytes).decode('utf-8'))
                    wallet_jsons.append(json_name)

    main_Wallet    = wallet_address[0]
    main_address   = wallet_jsons[0]

    balance_output = initialize.check_balance(wall_address, rpc)
    balances       = float(balance_output.split()[0])
    balancess      = initialize.check_mint_balances(wall_address, rpc)

    print(f"SOL Balance output: {balances} for Wallet {wall_address}")
    
    if balances == 0.00000000:
        print("No sol in fresh wallet... Sending sol to start mining..")
        amount = 0.01
        #transfer_output = initialize.transfer_sol(main_address, wall_address, str(amount), rpc)
        #print("Transfer SOL output:", transfer_output)
        
    if balances <= 0.0005 and balances < 0.001:
        amount = 0.01 - balances
        #transfer_output = initialize.transfer_sol(main_address, wall_address, str(amount), rpc)
        #print("Transfer SOL output:", transfer_output)

    for amounts, address in balancess:
        if mint_address == address:
            if amounts < 1.005:
                break

            if wall_address == main_Wallet:
                break

            try:
                transfer_tokens = initialize.transfer_tokens(mint_address, token_programID, wall_address, main_Wallet, str(amounts), keypair, rpc)
                print("Transfer output Txn:", transfer_tokens)
                print(f"Amount sent to main wallet {float(amounts)}")
                time.sleep(10)
                break
            except Exception as e:
                print(e)
                break

    if balances > 0.005:
        return

def mining_iteration(ORE, rpc_path: str, keypair_path: str, number: int, full_time, initial_windows, settings, address: str):
    try:
        initial_rewards    = ORE.rewards(keypair_path, rpc_path, settings.get('SERVERS', {}).get('file_path'))
        starting_rewards   = initial_rewards
        previous_rewards   = initial_rewards
        start_time         = time.time()
        starting_rate_time = time.time()
        sent_tx_cnt        = 0

        print(f"Starting mining session with {initial_rewards:06f} ORZ on Wallet #{number}")

        if initial_rewards == 0.000000000:
            send_sol(settings, keypair_path, address)
            
        ORE.parallel_mining(rpc_path, keypair_path, settings.get('SERVERS', {}).get('file_path'))

        while True:
            since_last_tx = 0
            rewards       = 0
            gained_amount = 0
            balances      = 0
            rate          = 0
            rewards       = ORE.rewards(keypair_path, rpc_path, settings.get('SERVERS', {}).get('file_path'))

            if rewards >= 1.005:
                claim_thread = ClaimThread(ORE, number, keypair_path, rpc_path, settings.get('SERVERS', {}).get('webhook_url'), settings.get("SERVERS", {}).get('file_path'))
                claim_thread.start()
                claim_thread.join()

                if claim_thread == "Transaction landed!":
                    pass
                else:
                    claim_thread

                # Reset rate after claiming tokens
                start_time         = time.time()
                starting_rate_time = time.time()

            gained_amount = rewards - previous_rewards

            if gained_amount == float(0.000000):
                end_time = time.time()
                since_last_tx = end_time - start_time
                continue

            if previous_rewards == rewards:
                end_time = time.time()
                since_last_tx = end_time - start_time
                continue

            rewardsRate = ORE.rewards_multiple(keypair_path, rpc_path, settings.get('SERVERS', {}).get('file_path'))

            end_time          = time.time()
            elapsed_time      = end_time - start_time
            since_last_tx     = elapsed_time
            today             = datetime.today()
            formatted_today   = today.strftime("%I:%M:%S%p %m/%d/%Y")
            rewards_rate_time = datetime.now()

            minutes_elapsed   = (rewards_rate_time.timestamp() - starting_rate_time) / 60
            rate              = (rewardsRate - initial_rewards) / minutes_elapsed

            in_minutes        = int(elapsed_time // 60)
            in_seconds        = int(elapsed_time % 60)
            in_milliseconds   = int((elapsed_time - int(elapsed_time)) * 1000)

            initialize        = Send()
            balance_output    = initialize.check_balance(address, rpc_path)
            balances          = float(balance_output.split()[0])

            if balances < 0.001:
                send_sol(settings, keypair_path, address)

            check_mining_coin = initialize.check_mint_balances(address, rpc_path)
            for amounts, mint_address in check_mining_coin:
                if settings.get('MINT', {}).get('mint_address') == mint_address:
                    if amounts > 1.005:
                        if keypair_path != f"{settings.get('SERVERS', {}).get('json_path')}/id1.json":
                            send_sol(settings, keypair_path, address)

            sent_tx_cnt += 1

            print(f" --- [{rewards_rate_time.strftime('%H:%M:%S')}] --- Gained {gained_amount:06f} ORE, total {rewards:06f} ORE, in {since_last_tx:.2f} seconds. On Wallet #{number} - Rate {rate:06f} ORE/m {rate * 60:06f} ORE/h")
            
            discord_message(
                f"~~~~ Found in {in_minutes}m {in_seconds}s {in_milliseconds}ms ~~~~\n"
                f"SOL Bal  : {balances}\n"
                f"Gained   : {gained_amount:06f} ORE\n"
                f"Claimable: {rewards:06f} ORE\n"
                f"Date     : {formatted_today}\n"
                f"Lands    : {sent_tx_cnt}\n"
                f"Rate     : \n{rate:06f} ORE/m \n{rate * 60:06f} ORE/h \n{(rate * 60) * 24:06f} ORE/day\n"
                "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n", number, settings.get("SERVERS", {}).get("webhook_url")
            )
            
            rewards_rate_time = datetime.now()
            previous_rewards  = rewards
            rate              = 0
            since_last_tx     = 0

    except KeyboardInterrupt:
        print(" --- Manually ending mining session")
        if platform.system() == "Windows":
            import pygetwindow as pygw # type: ignore
            windows = pygw.getAllWindows()
            miners_windows = [window for window in windows if "cmd.exe" in window.title]
            for window in miners_windows:
                if window not in initial_windows:
                    window.close()
        # Allow time for threads to clean up and exit
        time.sleep(5)

    rewards           = ORE.rewards(keypair_path, rpc_path, settings.get('SERVERS', {}).get('file_path'))
    end_full_time     = time.time()
    elapsed_full_time = end_full_time - full_time
    days              = elapsed_full_time // (24 * 3600)
    remaining_seconds = elapsed_full_time % (24 * 3600)
    hours             = remaining_seconds // 3600
    remaining_seconds %= 3600
    minutes           = remaining_seconds // 60
    seconds           = remaining_seconds % 60

    print(
        f"\nGained a total of {starting_rewards - initial_rewards:06f} " +
        f"ORZ in this session, totaling to {rewards:06f} ORZ, Total Time: " +
        f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
    )
    discord_message(
        f"\nGained a total of {starting_rewards - initial_rewards:06f} " +
        f"ORZ in this session, totaling to {rewards:06f} ORZ, " +
        f"Total Time: {days} days, {hours} hours, {minutes} minutes, {seconds} seconds", 
        number, settings.get('SERVERS', {}).get('webhook_url')
    )

def create_config(config_path):
    config = configparser.ConfigParser()
    config.add_section("SETTINGS")
    config.add_section("SERVERS")
    config.add_section("MINT")
    config.add_section("TENSOR")
    config.add_section("VAST")
    config.add_section("VULTR")
    config.add_section("MINERS")

    server_choice = input("Choose what Server Company to choose from:\n"
                          "Vultr, Vast, Tensor\n").upper()
    
    if server_choice == 'VULTR':
        config.set("VULTR", "vultr_count", input("Enter the amount of servers: \n"))
        config.set("VULTR", "willing_to_pay", input("Enter the amount you're willing to pay daily: (10) for $10/day\n"))
        config.set("VULTR", "vultr_api", input("Enter in your Vultr API Key: \n"))
    
    if server_choice == 'VAST':
        config.set("VAST", "vast_count", input("Enter the amount of servers: \n"))
        config.set("VAST", "willing_to_pay", input("Enter the amount you're willing to pay daily: (10) for $10/day\n"))
        config.set("VAST", "vast_api", input("Enter in your Vast API Key: \n"))
        
    
    if server_choice == 'TENSOR':
        config.set("TENSOR", "tensor_count", input("Enter the amount of servers: \n"))
        config.set("TENSOR", "willing_to_pay", input("Enter the amount you're willing to pay daily: (10) for $10/day\n"))
        config.set("TENSOR", "key", input("Enter in your Key: \n"))
        config.set("TENSOR", "token", input("Enter in your Token: \n"))
        config.set("TENSOR", "name", input("Enter in your Server Name: \n"))
        config.set("TENSOR", "passw", input("Enter in your Password: \n"))
        config.set("TENSOR", "settings1", ",".join(map(str, [16, 32, 60])))
        config.set("TENSOR", "settings2", ",".join(map(str, [24, 48, 60])))
        config.set("TENSOR", "settings3", ",".join(map(str, [32, 64, 60])))
        config.set("TENSOR", "settings4", ",".join(map(str, [40, 80, 60])))
        options_choice = input(f"Choose what server options:\n"
              "Options 1: Cheap and low Hashrate"
              "Options 2: Cheap and faster Hashrate"
              "Options 3: Not Cheap and low Hashrate"
              "Options 4: Exspensive and fastest Hashrate\n"
              )
        config.set("TENSOR", "choice", options_choice)
    
    wallet_import = input("Do you have wallets to import? (yes/no)\n")
    if wallet_import == 'yes':
        wallet_count = 0
        pass
    else:
        wallet_count = input("Enter the number of wallets to generate: \n")
    
    config.set("SERVERS", "rpc_count", input("How many RPC's do you have: \n"))

    rpc_count = int(config.get("SERVERS", "rpc_count"))
    if rpc_count:
        for i in range(rpc_count):
            config.set("SERVERS", f"rpc_{i+1}", input(f"Enter RPC URL {i + 1} (press Enter to finish): \n"))

    config.set("MINT", "mint_address", input("Enter ORE Contract Address: \n"))
    config.set("MINT", "token_programID", input("Enter ORE ProgramID: \n"))
    
    config.set("SETTINGS", "json_path", input("Enter your path to your json files exp(home/user/.config/solana): \n"))

    webhook_bool = input("Do you want Webhook messages (True or False): \n").lower()
    config.set("SETTINGS", "webhook_bool", webhook_bool)
    
    if webhook_bool == "true":
        config.set("SETTINGS", "webhook_url", input("Enter Webhook URL: \n"))
    
    file_path = input("Enter File path where ORE is installed: \n")
    config.set("SETTINGS", "file_path", file_path)
    
    rsa_path = input("Enter File path where your SSH key is stored: \n")
    config.set("SETTINGS", "rsa_path", rsa_path)

    parallel_miners = input("Enter How many Parallel Miners you want per Wallet: \n")
    config.set("MINERS", "parallel_miners", parallel_miners)

    miners_pause = input("Enter How many Seconds to wait per Miners you want per Wallet: \n")
    config.set("MINERS", "miners_pause", miners_pause)

    miners_wave = input("Enter How many Miners to be deployed per wave: \n")
    config.set("MINERS", "miners_wave", miners_wave)

    priority_fee = input("Enter how much you want to pay per txn (in microlamports): (80000)\n")
    config.set("MINERS", "priority_fee", priority_fee)

    threads = input("Enter How many Threads you want to use per Miner (4 is standard): \n")
    config.set("MINERS", "threads", threads)

    buffer = input("Enter the buffer for each Miner (2 is standard): \n")
    config.set("MINERS", "buffer_time", buffer)

    with open(config_path, "w") as configfile:
        config.write(configfile)
        return wallet_count, server_choice

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

def edit_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path)

    wallet_count = 0

    print("Settings to change:")
    for section in config.sections():
        print(f"[{section}]")
        for option in config.options(section):
            value = config.get(section, option)
            print(f"{option} = {value}")

    print("If you want to add more wallets type: wallet")
    print("If you want to change or add something under a section\n"
          "Type the section you want and then the option you want to change like this:\n"
          "settings, rpc_count")
    what_settings = str(input("What settings you want to change?\n"))

    sections_options = {
        "SETTINGS": {"webhook_bool", "webhook_url", "file_path", "rsa_path", "json_path"},
        "SERVERS": {"rpc_count"},
        "TENSOR": {"tensor_count", "willing_to_pay", "key", "token", "name", "passw", "choice", "settings1", "settings2", "settings3", "settings4"},
        "VAST": {"vast_count", "willing_to_pay", "vast_api"},
        "VULTR": {"vultr_count", "willing_to_pay", "vultr_api"},
        "MINT": {"mint_address","token_programID"},
        "MINERS": {"parallel_miners", "miners_pause", "miners_wave", "priority_fee", "threads", "buffer_time"}
    }

    if what_settings.lower() == "wallet":
        wallet_count = input(f"Enter new value for wallet_count: ")
    else:
        try:
            section, option = what_settings.split(',')
            section = section.strip().upper()
            option = option.strip().lower()
            
            if section in sections_options and option in sections_options[section]:
                new_value = input(f"Enter new value for [{section}] {option}: ")
                config.set(section, option, new_value)
            else:
                print("Invalid section or option.")
        except ValueError:
            print("Invalid input format. Please use 'SECTION,option' format.")

    with open(config_path, "w") as configfile:
        config.write(configfile)

    return config, int(wallet_count)

def main():
    config_dir   = "config_files"
    config_path  = os.path.join(config_dir, "settings.ini")
    wallet_count = False

    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    if not os.path.exists(config_path):
        wallet_count, server_choice = create_config(config_path)
        time.sleep(2)

    if wallet_count:
        wc = int(wallet_count)
        settings = read_config(config_path)
    else:
        wc = 0
        settings = read_config(config_path)
    
    reset_settings = input("Do you want to change the settings? (y or n)\n").lower()
    
    if str(reset_settings) == "y":
        settings, wallet_count = edit_config(config_path)
    
    wallet_create(wc,settings.get("SETTINGS", {}).get("json_path"))
    file_paths, address = create_id_jsons(wc,settings.get("SETTINGS", {}).get("json_path"))

    try:
        full_time = time.time()
        ORE       = Ore(file_paths)
        number    = 0
        threads   = []

        if platform.system() == "Windows":
            import pygetwindow as pygw # type: ignore
            initial_windows = pygw.getAllWindows()
        else:
            initial_windows = None

        if settings.get("SETTINGS", {}).get("server_choice") == 'TENSOR':
            tensor_main()
        if settings.get("SETTINGS", {}).get("server_choice") == 'VULTR':
            vultr_main()
        if settings.get("SETTINGS", {}).get("server_choice") == 'VAST':
            vast_main()

        rpc_cycle = itertools.cycle(ORE.rpc)

        for keypair_path, addresses in zip(ORE.keypair_paths, address):
            number += 1
            rpc_path = next(rpc_cycle)
            t = threading.Thread(target=mining_iteration, args=(ORE, rpc_path, keypair_path, number, full_time, initial_windows, settings, addresses))
            threads.append(t)
            t.start()
            time.sleep(ORE.miners_pause)
        for thread in threads:
            thread.join()
    except Exception as e:
        print(f"Exception in main: {e}")

if __name__ == "__main__":
    main()
    # ./target/release/ore.exe --rpc https://api.devnet.solana.com --keypair C:/Users/Matthias/.config/solana/id1.json mine --threads 4 --buffer-time 2
    # "C:/Users/Matthias/Desktop/OreV2/ore-cli/target/release/ore.exe --rpc https://api.devnet.solana.com --keypair C:/Users/Matthias/.config/solana/id1.json mine --threads 4 --buffer-time 2"
    # ./target/release/ore --rpc https://api.devnet.solana.com --keypair /home/ubuntu/.config/solana/id1.json mine --threads 60 --buffer-time 12