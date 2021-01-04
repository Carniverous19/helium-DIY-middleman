# helium-DIY-middleman
Initially this was written by folks who know what they're doing.  I more or less don't, but guided by wizards I managed to muddle through.  You can do the same.

Code here acts as a middleman between LoRa gateways running Semtech packet forwarders and servers ingesting packet forwarder data.

I run it because I have antennas with higher than stock gain (6, 9, and 13 db), and currently (Dec 2020) Helium rules make it so many tx and rx are invalid with higher gain antennas.

## Installation Instructions

There are two ways to use this code. The first way is to run it manually, while
the second way is to install it in the system and have it be run by `systemd`.  I have it run by systemd because it, at least, knows what it's doing.
These options are described in detail in the following subsections.

In both cases, however, you must first clone the repository.

### Cloning

Clone this repository.  Note daily, maybe breaking changes may be pushed to master at any time.  
Some functional versions may be tagged and you may want to pull those

    git clone https://github.com/curiousfokker/helium-DIY-middleman.git
 
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

#### Set Up

There are several options that you may wish to change about middleman's startup
behavior in a permanent installation. To make these eaiser to control without
having to modify the source code, you'll need to create configs directory and then config.json file in home/middleman.

#### Middleman Settings

In the directory /middleman (which was created with the git pull.)

* `sudo mkdir configs`
* `cd configs`
* `nano config.json`

Then copy/paste in this:

```{
        "gateway_conf": {
                "gateway_ID": "AA555A0000000000",
                "server_address": "localhost",
                "serv_port_up": 1680,
                "serv_port_down": 1680
         }
}
```

IMPORTANT:  If you've got a local.conf file in your packet forwarder (miner & gateway on same device, like a RAK7244), make sure the gateway_ID above matches what's in the packet forwarder. 

Next, make the middleman.conf file.  
In /middleman

`sudo nano middleman.conf`

Then enter your arguments.  
Example 1 (for a Nearson 9 db anteanna)  `middleman_args="--rx-adjust -9” `. 
Example 2 (an antenna over 13 db) `middleman_args="--tx-adjust -4 --rx-adjust -13"`. 

Next we'll enable Middleman:

`sudo systemctl enable middleman`. 
and then reboot the miner.  You might not have to reboot.  I did it anyway.

`sudo reboot`. 

Now, over in the Gateway you're going to change the UDP port from the default (1680) to that of Middlema (1681).  This tells the gateway to talk to Middleman instead of the miner.  First, on your gateway check to see where your packet forwarder config file is.

`ps -efww | grep lora_pkt`

In my gateway the path is ` /sx1302_hal/bin/ `

Once you're in the bin (or whatever directory you found the packet forwarder config file), then

`cp global_conf.json global_conf.json.old`

This makes a copy of your old global_conf settings in case you want to revert back to them.  With a backup made, nothing could possibly go wrong. It's time to change things up!

`sudo nano global_conf.json`

In there (probably down at the bottom) look for this:  

``` 
"gateway_conf": {
        "gateway_ID": "AA555A0000000101",
        /* change with default server address/ports, or overwrite in local_conf.json */
        "server_address": "localhost",
        "serv_port_up": 1681,
        "serv_port_down": 1681,
        /* adjust the following parameters for your network */
        "keepalive_interval": 10,
        "stat_interval": 30,
        "push_timeout_ms": 100,
        /* forward only valid packets */
        "forward_crc_valid": true,
```

Then change
`serv_port_up: 1680` and `serv_port_down: 1680` from 1680 --> 1681.

Now your gateway is pointing to Middleman (1681) instead of to your miner (1680).  

Reboot your gateway.

`sudo reboot`

then make sure you've restarted the lora_pkt_fwd.service with

`sudo systemctl restart lora_pkt_fwd.service`

Now, back on your miner:

`sudo systemctl start middleman`

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
  
  Default: (none)
 



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
