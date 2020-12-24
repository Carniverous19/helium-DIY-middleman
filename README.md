# helium-DIY-middleman
Code here acts as a middleman between LoRa gateways running Semtech packet forwarders and servers ingesting packet forwarder data.
You would run this code instead of directly pointing gateways to miners for a few possible reasons:

- You want to send data from one gateway to multiple on-chain miners to potentially increase earnings by increasing witnessing and potential selection for "next hop" in PoC
- You have multiple DIY gateways but only a single on-chain DIY miner (in alpha program).  you can route data from all of your gateways to your single miner increasing the ability to receive data, challenges, etc.
- You have a gateway not located at its asserted location and you want to modify received metadata to avoid PoCv9/v10 thresholds.  
- Any combination of the above.

To test this capability I currently have 3 gateways (RAK2245, RAK2247 and RAK2287) all sharing data with six miners.
One gateway has a 8dBi omni on the east side of my building near the roofline, this is used for receive and transmit.
One gateway has a 16dBi yagi for long reach and is receive only. 
One gateway has an 11dBi panel antenna facing out a window on the west side of my building to receive from gateways the omni cannot hear due to building obstruction.

## Installation Instructions

There are two ways to use this code. The first way is to run it manually, while
the second way is to install it in the system and have it be run by `systemd`.
These options are described in detail in the following subsections.

In both cases, however, you must first clone the repository.

### Cloning

Clone this repository.  Note daily, maybe breaking changes may be pushed to master at any time.  
Some functional versions may be tagged and you may want to pull those

    git clone **<FIX-ME-I-AM-A-FORK>**/helium-DIY-middleman.git
 
 The only dependency is Python 3.7+ (developed and tested on 3.8.2)
    
### Manual Startup

To run the code manually, use the following command

    python3 gateways2miners.py -p 1680 -c ./gateways
    
This will listen for messages from any gateway running the semtech packet forwarder on port 1680. 
It will also create a virtual gateway that communicates with a miner based on all the configuration files located in `./gateways` 

Run

    python3 gateways2miners.py -h
for additional info on parameters and their meaning

### Permanent Installation and Startup

For more reliable and permanent operation, you can also install middleman in
its own working directory and have it started up by your system automatically
via `systemd`.  To do so, you must run

    sudo make install

This will install the source code and other necessary items in a new directory,
`/home/middleman`. If you wish to have middleman installed in a different
directory, run this modified version of the installation command:

    sudo make DESTROOT=/different/directory install

#### Run-time configuration

There are several options that you may wish to change about middleman's startup
behavior in a permanent installation. To make these eaiser to control without
having to modify the source code, the startup scripts will check for a text
file named `/home/middleman/middleman.conf`, which can contain the following
settings.

* `middleman_config_dir`

  The directory in which `middleman` should search for its
  upstream gateway configurations.  (See the **Configuration files for
  middleman** section).

  Default: `/home/middleman/configs`

* `middleman_python`

  The python interpreter to use when starting `middleman` if you need
  a very specific version to be used, or if it is installed in an unusual
  path.

  Default: `python3`

* `middleman_port`

  The UDP port on which `middleman` should listen for incoming packets
  from gateways.

  Default: `1681`

* `middleman_args`

  Additional arguments to pass to middleman when running. Make sure to
  use double quotes when setting this variable.
  
  Default: (none)
 
#### Example configuration

An example `middleman.conf` file might read:

    middleman_python=/usr/bin/python3.8
    middleman_port=1682
    middleman_args="--tx-adjust -4.0"

#### Enabling via systemd

Once installed, you will need to tell `systemd` that you'd like middleman to
automatically start every time the system is brought up. Do so by running

    sudo systemctl enable middleman


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
If you want transmit commands from a miner to actually be transmitted over LoRa the `"gateway_ID"` should match the MAC address for one of the physical gateways sending data to this software.
This limitation can be removed with additional software to allow independently mapping miners to transmitting gateways.

Note: all received packets from any gateway will be sent to ALL miners but transmit commands from a miner will be sent to at most one gateway.

### Configuration files for gateways
Each physical gateway should have a unique `gateway_ID`.  These don't have to match with any virtual gateway.  See limitations mentioned above for why you may want to match a virtual gateway MAC address.
The `serv_port_up` and `serv_port_down` of each gateway should match the port you set with the `-p` or `--port` arguement when starting `gateways2miners.py`.

### Example Setup
This guide assumes you have a single DIY hotspot running the semtech packet fowarding software per Helium Inc's [Build a Hotspot](https://developer.helium.com/hotspot/developer-setup) guide.
And also that you have a Miner running per Helium Inc's [Run Your Own Miner](https://developer.helium.com/blockchain/run-your-own-miner) guide.  Lets assume the miner is at IP address 18.218.135.176 and that you already verified the miner and gateway are communicating.

Also assume this software is running on an independent computer, either an additional raspberry pi or your laptop, etc.  Assume the computer running this `gateways2miners.py` code has IP address 192.168.1.100.

To start using this software perform the following:
- Go a command line on the gateway and copy the file `packet_forwarder/lora_pkt_fwd/global_conf.json` to `global_conf.json.old` to keep as a backup.
- Find the line `"server_address": "18.218.135.176"` in the  `global_conf.json` file and change it to `"server_address": "192.168.0.100"`.
    Now your gateway is pointing to this middleman software instead of directly to your miner.
- Also in `global_conf.json` (or possibly in `local_conf.json` if it exists) find the line `gateway_ID` and record the value. (example:`"gateway_ID": "AA555A0000001234"`)
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



## How It Works
This software listens for UDP datagrams on the specified port (defaults to `1680`).  
datagrams received on this port may be from gateways (PULL_DATA, PUSH_DATA, TX_ACK) or from miners (PULL_ACK, PUSH_ACK, PULL_RESP).
any ACK message is dropped as they are for information only.

**PULL_DATA** messages from gateways are used to ensure a communication path through any NAT or router is open.
These messages contain the MAC address (same as `Gateway_ID`) as well as the origin IP address and port.
This mapping of gateway MAC to (IP, Port) is saved so the software knows where to send PULL_RESP messages.

**PUSH_DATA** messages from gateways are used to inform the miner of received LoRa packets.
Each received LoRa packet, regardless of which gateway sent the message, is forwarded to all gateways.
Since multiple gateways may receive the same message, a cache is of recent messages is kept and duplicate LoRa packets are dropped.
The metadata such as gateway MAC address is modified so each miner thinks it is communicating with a unique gateway.
The RSSI, SNR, and timestamp (`tmst`) fields are also modified to be in acceptable ranges and to ensure the timestamps are in order and increment as expected regardless of real gateway (we cant assume timestamps are synchronized if gateway doesnt have GPS).

**PULL_RESP** messages received from miners contain data to transmit (usually for device JOINs or PoC).
These are forwarded unmodified to the gateway with the same MAC address as the virtual gateway interfacing with the miner, if it exists, and a PULL_DATA was received from the gateway.
This ensures transmit behavior of a miner remains consistent.  This restriction may be removed in later revisions.

To ensure PULL_RESPs are received by the other miners, a fake PUSH_DATA payload is created for every PULL_RESP with simulated RSSI, SNR, and timestamp (currently hardcoded RSSI and SNR).
This fake PUSH_DATA runs through the same process as real ones except it is not forwarded to the miner that sent the PULL_RESP (so gateways don't receive their own transmissions).

All PULL_DATA, PUSH_DATA, and PULL_RESP messages are immediately sent the corresponding ACK regardless of whether the data was actually delivered.
 
Additionally, all virtual gateways (interfaces for real miners) periodically send PULL_DATA and PUSH_DATA messages with `stat` payloads to the gateways.
These messages are required to ensure the software remains accessible to gateways and the behavior mimics the semtech packet forwarder.
To send valid stats messages each virtual gateway keeps track of the number of PUSH_DATA and PULL_RESP messages it received and increments a counter for each.
 
## Areas for Further Development 
 
  - More sophisticated metadata modification to adapt to PoC changes.  The framework exists for this and much more sophistication can be added to the separate `modify_rxpk.py` code.
    Advanced metadata modification could include queries to an ETL database, querying ML models (either specific to a gateway or global), etc.
    An important point is the entire blockchain history and challenge history for these gateways and miners are available for determining appropriate metadata.
  - Detection of dead miner or gateway (using ACKs).  There is no way to forget a miner or gateway without software restart.
  - Transmission errors are silently ignored, for reliable transmissions these should be fed back to miners.
  - Security: this code is vulnerable to lots of attacks.  One possible attack is spoofing gateways.
  
## Disclaimers

 - I have done very little testing.  
 I did run some fake data simulating multiple gateways and miners but I would want to do significantly more testing.
 I did check transmissions (from miner out gatways) using semtech's `util_tx_test`.
 Additionally I verified RX and TX with an on-chain DIY miner that earns for witnessing and PoC transmissions.
 - Software is 100% proof of concept.  No guarantees on reliability or accuracy only use for testing
 - This software can be used for "gaming" or "exploits".  Part of creating this software is to demo these exploits to encourage community discussion, expose limitations, and be a weak test for any exploit fixes.
   You should only use this software for testing purposes and not for widespread gaming or exploitation of the Helium network.
