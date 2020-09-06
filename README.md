# helium-DIY-middleman
Code here acts as a middleman between LoRa gateways running Semtech packet forwarders and servers ingesting packet forwarder data 
## Installation Instructions
Clone this repository.  Note daily, maybe breaking changes may be pushed to master at any time.  
Some functional versions may be tagged and you may want to pull those

    git clone https://github.com/Carniverous19/helium-DIY-middleman.git
 
 The only dependency is Python 3.6+
    
## Usage instructions
To run use the following command

    python3 gateways2miners.py -p 1680 -c ./gateways
    
This will listen for messages from any gateway running the semtech packet forwarder on port 1680. 
It will also create a virtual gateway that communicates with a miner based on all the configuration files located in `./gateways` 

Run

    python3 gateways2miners.py -h
for additional info on parameters and their meaning

### Configuration files for middleman
The configuration files are the same used by the semtech packet forwarder but only require a subset of fields.  A minimal example is:

    {
      "gateway_conf": {
        "gateway_ID": "AA555A0000000002",
        "server_address": "127.0.0.1",
        "serv_port_up": 1680,
        "serv_port_down": 1680
      }
    }

Each gateway should have a unique `"gateway_ID"` or MAC address.
These will be the MAC addresses of the virtual gateways that interface with miners.
These don't have to match the MAC address of any physical gateway but if they dont it means they cannot transmit actual RF packets.  The corresponding miner would be *receive only*.
If you want transmit commands from a miner to actually be transmitted over LoRa the `"gateway_ID"` should match the MAC address for one of the real miners sending data to this software.
This limitation can be removed with additional software to allow independently mapping miners to transmitting gateways.

Note that all received packets from any gateway will be sent to ALL miners but transmit commands from a miner will be sent to at most one gateway.

### Configuration files for gateways
Each gateway should have a unique `gateway_ID`.  These dont have to match with any virtual gateway.  See limitations mentioned above for why you may want to match a virtual gateway MAC address.
The `serv_port_up` and `serv_port_down` of each gateway should match that you will set with the `-p` or `--port` in when starting `ManyGW2ManyMiner.py`.

### Example Setup
This guide assumes you have a single DIY hotspot running the semtech packet fowarding software per Helium Inc's [Build a Hotspot](https://developer.helium.com/hotspot/developer-setup) guide.
And also that you have a Miner running per Helium Inc's [Run Your Own Miner](https://developer.helium.com/blockchain/run-your-own-miner) guide.  Lets assume the miner is at IP address 18.218.135.176 and that you already verified the miner and gateway are communicating.

Also assume this software is running on an independent computer, either an additional raspberry pi or your laptop, etc.  Assume the computer running this `gateways2miners.py` code has IP address 192.168.1.100.

To start using this software perform the following:
- Go a command line on the gateway and copy the file `packet_forwarder/lora_pkt_fwd/global_conf.json` to `global_conf.json.old` to keep as a backup.
- Find the line `"server_address": "18.218.135.176"` in the  `global_conf.json` file and change it to `"server_address": "192.168.0.100"`.
    Now your gateway is pointng to this middleman software instead of directly to your miner.
- Also in `global_conf.json` (or possibly in `local_conf.json` if it exists) find the line `gateway_ID` and record the value example:`"gateway_ID": "AA555A0000001234"`.
- Go the computer where you want to run the middleman software and create a folder in your home directory called `gateways` and change directory into the newly created folder:


    cd ~
    mkdir gateways
    cd gateways

- you can either copy the original `global_conf.json.old` file from the gateway and put it in this directory (deleting .old from the filename). or create a new config file and add the required lines:


    nano gateway1.json

The contents of `gateway1.json` should match whats shown below.  Note you need to change gateway_ID and server_address to match your original config files form the gateway:

    {
      "gateway_conf": {
        "gateway_ID": "AA555A0000001234",   /*This should match the gateway_ID you recorded*/
        "server_address": "18.218.135.176", /*This should match the IP of your miner*/
        "serv_port_up": 1680,
        "serv_port_down": 1680
      }
    }



## How it works
This software listens for UDP datagrams on the specified port (defaults to `1680`).  
datagrams received on this port may be from gatways (PULL_DATA, PUSH_DATA, TX_ACK) or from miners (PULL_ACK, PUSH_ACK, PULL_RESP).
any ACK message is dropped as they are for information only.

**PULL_DATA** messages from gateways are used to ensure a communication path through any NAT or router is open.
These messages contain the MAC address (same as `Gateway_ID`) as well as the origin IP address and port.
This mapping of gateway MAC to (IP, Port) is saved so the software knows where to send PULL_RESP messages.

**PUSH_DATA** messages from gateways are used to inform the miner of received LoRa packets.
Each received LoRa packet, regardless of which gateway send the message is forwarded to all gateways.
Since multiple gateways may receive the same message, a cache is of recent messages is kept and duplicate LoRa packets are dropped.
The metadata such as gateway MAC address is modified so each miner thinks it is communicating with a unique gateway.
The RSSI, SNR, and timestamp (`tmst`) fields are also modified to be in acceptable ranges and to ensure the timestamps.
are in order an increment as expected regardless of real gateway (we cant assume timestamps are syncronized if gatway doesnt have GPS).

**PULL_RESP** messages received from miners contain data to transmit (usually for device JOINs or PoC).
These are forwarded unmodified to the gateway with the same MAC address as the virtual gateway interfacing with the miner.
This ensures transmit behavior of a miner remains consistent.  This restriction may be removed in later revisions.

All PULL_DATA, PUSH_DATA, and PULL_RESP messages are immediately sent the corresponding ACK regardless of whether the data was actually delivered.
 
 ## Areas for further development 
 
  - More sophisticate metadata modification to adapt to PoC changes.  The framework exists for this and much more sophistication can be added to teh separate `modify_rxpk.py` code.
  - Ensure transmit commands are received by all miners (but the transmitter).  Currently transmits are only sent to miners if received by one of the gateways.
    A better system would build dummy PUSH_DATA message for every transmission to ensure transmissions are witnessed by all miners.  
    This would also allow there to be zero real gateways and all miners could communicate in an isolated island through this software.  This is **In Work**.
  - Detection of dead miner or gateway (using ACKs).  There is no way to forget a miner or gateway without software restart.

  
## Disclaimers

 - I have done very little testing.  I have only one real gateway and one miner VM.  I did run some fake data simulating multiple gateways and miners but I would want to do significantly more testing.  I did check transmissions (from miner out gatways) using semtech's `util_tx_test`
 - Software is 100% proof of concept.  No guarantees on reliability or accuracy only use for testing
 - This software can be used for "gaming" / "exploits".  Part of creating this software is to demo these exploits to encourage community discussion, expose limitations, and be a weak test for any exploit fixes.
   You should only use this software for testing purposes and not for widespread gaming or exploitation of the Helium network.
 - 