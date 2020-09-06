# helium-DIY-middleman
Code here acts as a middleman between LoRa gateways running Semtech packet forwarders and servers ingesting packet forwarder data 
## Installation Instructions
Clone this repository.  Note daily, maybe breaking changes may be pushed to master at any time.  
Some functional versions may be tagged and you may want to pull those

    git clone https://github.com/Carniverous19/helium-DIY-middleman.git
 
 The only dependency is python3 3.6+
    
## Usage instructions
To run use the following command

    python3 ManyGW2ManyMiner.py -p 1680 -c ./gateways
    
This will listen for messages from any gateway running the semtech packet forwarder on port 1680. 
It will also create a virtual gateway that communicates with a miner based on all the configuration files located in `./gateways` 

### Configuration files for midleman
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

Note that all received packets from any gateway will be sent to ALL miners but transmit commands from a miner will be sent to at most one gateway.

### Configuration files for gateways
Each gateway should have a unique `gateway_ID`.  These dont have to match with any virtual gateway.  See limitations mentioned above for why you may want to match a virtual gateway MAC address.
The `serv_port_up` and `serv_port_down` of each gateway should match that you will set with the `-p` or `--port` in when starting `ManyGW2ManyMiner.py`.

## How it works

There are four threads that communicate with eachother via two queues.  

 - A `tx_queue` is used to take transmit commands (PULL_RESP) from any miner and send to the appropriate concentrator
 - A `rx_queue` is used to take received LoRa packets (PUSH_DATA) from any concentrator and forward to all miners.  

There are also two listening ports, a single port for all communication between real gateways and the middleman software. 
A second port for all communication between the middleman software and all miners.  
All data received from concentrators have their metadata (RSSI, SNR, Timestamp) as well as source MAC address modified to appear as originating from the configured virtual miner.
See *thread flowcharts.pdf* in attached directory for functional flow charts of each thred.
 
 
 ## Areas for further development 
 
  - More sophisticate metadata modification to adapt to PoC changes 
  - Ensure transmit commands are received by all miners (but the transmitter).  Currently transmits are only sent to miners if received by one of the gateways
  - Detection of dead miner or gateway (using ACKs).  There is no way to forget a miner or gateway without software restart

  
## Disclaimers

 - I have done very little testing.  I have only one real gateway and one miner VM.  I did run some fake data simulating multiple gateways and miners but I would want to do significantly more testing.  I did check transmissions (from miner out gatways) using semtech's `util_tx_test`
 - Software is 100% proof of concept.  No guarantees on reliability or accuracy only use for testing
 - This software can be used for "gaming" / "exploits".  Part of creating this software is to demo these exploits to encourage community discussion, expose limitations, and be a weak test for any exploit fixes.
 - 