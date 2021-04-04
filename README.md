# Middleman for Helium
Initially this was written by folks who know what they're doing.  I more or less don't, but guided by wizards I managed to muddle through.  You can do the same.

Code here acts as a middleman between LoRa gateways running Semtech packet forwarders and servers ingesting packet forwarder data.  For you non-geeks, what this code does is tell your miner to report different signals to the blockchain than what the packet forwarder is actually receiving.  

I run it because I have antennas with higher than stock gain (6, 9, and 13 db), and currently (Jan 2020) Helium rules make it so many tx and rx are invalid with higher gain antennas.  Those rules are why many times a higher gain antenna (like a Nearson 9) will perform worse than a lower gain antenna.  

This could technically be considered gaming.  So there's that.  I consider it a way to provide the network with a service and earn reward commensurate with the service.  

## Installation Instructions

There are two ways to use this code. The first way is to run it manually, while
the second way is to install it in the system and have it be run by `systemd`.  If you want to run it manually, you are sophisticated enough to figure it out from Carniverous19's code and don't need this.  For the rest of us enthusiasts...      

These instructions are for running it automatically with `systemd`.  

### Cloning

Clone this repository onto the machine running your miner. 

    git clone https://github.com/curiousfokker/helium-DIY-middleman.git
 
 The only dependency is Python 3.7+ (developed and tested on 3.8.2)
    
### Installation and Startup

You may need to get Make.

`sudo apt-get install make`

Now install Middleman in its own working directory. Go to /helium-DIY-middleman and

    sudo make install

This will install the source code and other necessary items in a new directory,
`/home/middleman`. 


#### Middleman Settings (on the miner)

In the directory /middleman 

* `sudo mkdir configs`. 
This creates your configs directory.  Now change into that directory:  

* `cd configs`
and create the config file:  
* `sudo nano config.json`

Then copy/paste in this into the config.json:

```{
        "gateway_conf": {
                "gateway_ID": "AA555A0000000000",
                "server_address": "localhost",
                "serv_port_up": 1680,
                "serv_port_down": 1680
         }
}
``` 
CTRL-X to Exit, then "Y" to save and "Enter" to seal the deal.

IMPORTANT:  Make sure the gateway_ID above matches what's in the packet forwarder's global_conf.json and, if it exists, local_conf.json. 

Great, so now you've told Middleman where to "listen" when it comes to the miner.  

Next, make the middleman.conf file in /middleman and tell it what to do with what it hears from the packet forwarder. 

`sudo nano middleman.conf`. 

Then enter your arguments.  
Example 1 (for a Nearson 9 db antenna where you'd want to drop the rx receipts by 9)  
`middleman_args="--rx-adjust -9" `. 
  
Example 2 (an antenna over 13 db where you need to drop the tx by 4 in order to not break FSPL and adjust the RX by 13 to keep within RSSI boundaries) `middleman_args="--tx-adjust -4 --rx-adjust -13"`. 

Next, we'll enable Middleman on the miner:

`sudo systemctl enable middleman`. 

and then reboot the miner.  You might not have to reboot.  I did it anyway.  

`sudo reboot`. 

#### On the Gateway
Now, on the gateway you're going to change the UDP port from the default (1680) to that of Middleman (1681).  This tells the gateway to talk to Middleman instead of the miner.  
First, on your gateway check to see where your packet forwarder config file is.

`ps -efww | grep lora_pkt`

In my gateway the path is ` /sx1302_hal/bin/ `

Once you're in the bin (or whatever directory you found the packet forwarder config file) make a backup copy of your global conf file, just in case.

`cp global_conf.json global_conf.json.old`

With a backup made, nothing could possibly go wrong. It's time to change things up!

`sudo nano global_conf.json`

In there (probably way down at the bottom) look for this:  

``` 
"gateway_conf": {
        "gateway_ID": "AA555A0000000101",
        /* change with default server address/ports, or overwrite in local_conf.json */
        "server_address": "localhost",
        "serv_port_up": 1680,
        "serv_port_down": 1680,
        /* adjust the following parameters for your network */
        "keepalive_interval": 10,
        "stat_interval": 30,
        "push_timeout_ms": 100,
        /* forward only valid packets */
        "forward_crc_valid": true,
```

Then on the 4th & 5th line down, change the ports:  
`serv_port_up: 1680` and `serv_port_down: 1680` from 1680 --> 1681.  

Now your gateway is pointing to Middleman (1681) instead of to your miner (1680).  

Reboot your gateway.

`sudo reboot`

You MAY need to restart the lora_pkt_fwd.service with:  

`sudo systemctl restart lora_pkt_fwd.service`

Now that the gateway is directed to your miner, you'll need to start Middleman on the miner, so:    

#### Back on your Miner:

`sudo systemctl start middleman`. 

Check your work with:  

`systemctl status middleman`

and

`sudo journalctl -u middleman`

this mirrors the output of the middleman.log file and you can use the command `q` to quit it.

#### Details & What the Startup Scripts Do

The startup scripts will check for a text
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
 - This is technically considered gaming.  
 - I have done very little testing.  
 - Software is 100% proof of concept.  No guarantees on reliability or accuracy only use for testing
 - This software can be used for "gaming" or "exploits".  Part of creating this software is to demo these exploits to encourage community discussion, expose limitations, and be a weak test for any exploit fixes.
   You should only use this software for testing purposes and not for widespread gaming or exploitation of the Helium network.
