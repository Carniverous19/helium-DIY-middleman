
import argparse
import os
import json
import logging
import time
import socket
import copy
from hashlib import md5

from src import messages
from src.vgateway import VirtualGateway



class GW2Miner:
    def __init__(self, port, vminer_configs_paths, keepalive_interval=10, stat_interval=30, debug=True, tx_power_adjustment=0.0, rx_power_adjustment=0.0):


        self.vgw_logger = logging.getLogger('VGW')
        self.vminer_logger = logging.getLogger('VMiner')
        self.tx_power_adjustment = tx_power_adjustment
        self.rx_power_adjustment = rx_power_adjustment

        # load virtual gateways configs
        # =============================
        self.vgateways_by_addr = dict()
        self.vgateways_by_mac = dict()
        for path in vminer_configs_paths:
            with open(path, 'r') as fd:
                config = json.load(fd)
                if 'gateway_conf' in config:
                    config = config['gateway_conf']

                mac = ''
                if 'gateway_ID' not in config or 'server_address' not in config:
                    self.vgw_logger.error(f"invalid config file {path}, missing required parameters")
                    continue
                try:
                    server_ip = socket.gethostbyname(config.get('server_address'))
                except socket.gaierror:
                    self.vgw_logger.error(f"invalid server_address \"{config.get('server_address')}\" in config {path}")
                    continue
                for i in range(0, len(config.get('gateway_ID')), 2):
                    mac += config.get('gateway_ID')[i:i+2] + ':'
                mac = mac[:-1].upper()

                vgw = VirtualGateway(
                        mac=mac,
                        server_address=server_ip,
                        port_dn=config.get('serv_port_down'),
                        port_up=config.get('serv_port_up'),
                        rx_power_adjustment=rx_power_adjustment
                    )
                self.vgateways_by_mac[mac] = vgw

                self.vgateways_by_addr[(server_ip, config.get('serv_port_down'))] = vgw
                self.vgateways_by_addr[(server_ip, config.get('serv_port_up'))] = vgw
                self.vgw_logger.info(f"added vgateway for miner at {server_ip} port: {config.get('serv_port_up')}(up)/{config.get('serv_port_down')}(dn)")
        # start listening socket
        # =============================
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        logging.info(f"listening on port {port}")

        # setup other class variables
        # =============================
        self.rxpk_cache = dict()
        self.gw_listening_addrs = dict() # keys = MAC, values = (ip, port) tuple
        self.keepalive_interval = keepalive_interval
        self.stat_interval = stat_interval
        self.last_stat_ts = 0
        self.last_keepalive_ts = 0

    def __rxpk_key__(self, rxpk):
        """
        get key for rx payload that will be unique for each transmission but the same regardless of gateway that
        received.  spreading factor, coding rate, frequency, and data
        :param rxpk: dictionary of rxpk
        :return:
        """
        hash = md5()
        hash.update(rxpk['data'].encode())
        key = (
            rxpk['datr'],
            rxpk['codr'],
            str(round(rxpk['freq'], 2)),
            rxpk['size'],
            rxpk['data'] if len(rxpk['data']) < 40 else hash.hexdigest()
        )
        return key


    def run(self):
        """
        infinite loop running code
        :return:
        """
        start_ts = time.time()
        while True:
            if time.time() - self.last_keepalive_ts > self.keepalive_interval:
                self.send_keepalive()
            if time.time() - self.last_stat_ts > self.stat_interval:
                self.send_stats()

            # logging.debug(f"loop time: {time.time() - start_ts:.4f}")

            msg, addr = self.get_message(timeout=5)

            start_ts = time.time()
            if not msg:
                continue

            if msg['_NAME_'] == messages.MsgPushData.NAME:
                self.handle_PUSH_DATA(msg, addr)
            elif msg['_NAME_'] == messages.MsgPullResp.NAME:
                self.handle_PULL_RESP(msg, addr)
            elif msg['_NAME_'] == messages.MsgPullData.NAME:
                self.handle_PULL_DATA(msg, addr)

    def handle_PUSH_DATA(self, msg, addr=None):
        """
        take PUSH_DATA message will come from real gateways interfacing with this middleman software.
        This function forwards de-duplicated received packets to all miners after potentially modifying metadata
        :param msg:
        :param addr:
        :return:
        """
        if 'rxpk' not in msg['data']:   # just a stat message
            return
        # filter payloads for new packets not in cache
        new_rxpks = []
        self.vminer_logger.debug(
            f"PUSH_DATA from GW:{msg['MAC'][-8:]}")
        for rxpk in msg['data']['rxpk']:

            key = self.__rxpk_key__(rxpk)

            is_duplicate = key in self.rxpk_cache
            description = f"from GW:{msg['MAC'][-8:]} [{rxpk.get('size')}B]: {key}; rssi:{rxpk['rssi']:.0f}dBm, snr:{rxpk['lsnr']:.0f}"

            if packet_is_poc_challenge(rxpk):
                log_level = 'info'
                if is_duplicate:
                    classification = 'repeat chlng.'
                else:
                    classification = 'new    chlng.'
            else:
                log_level = 'debug'
                if is_duplicate:
                    classification = 'repeated packet'
                else:
                    classification = 'new packet'

            if log_level == 'info':
                log = self.vminer_logger.info
            else:
                log = self.vminer_logger.debug

            log(f"{classification} {description}")

            if is_duplicate:
                continue

            self.rxpk_cache[key] = time.time()
            new_rxpks.append(rxpk)

        if not new_rxpks:
            return

        msg['data']['rxpk'] = new_rxpks
        # send rxpks from each gateway to miners
        for vgw in self.vgateways_by_mac.values():
            # ignore if this is a generated PUSH from this gateways transmission
            if msg.get('txMAC') == vgw.mac:
                self.vgw_logger.debug(f"ignoring rxpk for vGW {vgw.mac[-8:]}. Its generated from PULL_RESP from this vGW")
                continue

            data, addr = vgw.get_rxpks(copy.deepcopy(msg))
            if addr is None:
                continue
            self.sock.sendto(data, addr)

    def handle_PULL_RESP(self, msg, addr=None):
        """
        take PULL_RESP sent from a miner and forward to the appropriate gateway
        :param msg:
        :param addr:
        :return:
        """
        vgw = self.vgateways_by_addr.get(addr)
        if not vgw:
            self.vgw_logger.error(f"PULL_RESP from unknown miner at {addr}, dropping transmit command")
            return
        dest_addr = self.gw_listening_addrs.get(vgw.mac)
        if not dest_addr:
            self.vgw_logger.warning(f"PULL_RESP from {addr} has no matching real gateway, will only be received by Virtual Miners")
        txpk = msg['data'].get('txpk')

        txpk = self.adjust_tx_power(txpk)

        rawmsg = messages.encode_message(msg)
        if dest_addr:
            self.sock.sendto(rawmsg, dest_addr)
            self.vgw_logger.info(f"forwarding PULL_RESP from {addr} to gateway {vgw.mac[-8:]}, (freq:{round(txpk['freq'], 2)}, sf:{txpk['datr']}, codr:{txpk['codr']}, size:{txpk['size']})")



        # make fake PUSH_DATA and forward to vgateways
        fake_push = messages.PULL_RESP2PUSH_DATA(msg, src_mac=vgw.mac)
        self.vgw_logger.info(f"created fake rxpk for PULL_RESP from vgw:{vgw.mac[-8:]}")
        self.handle_PUSH_DATA(msg=fake_push, addr=None)

    def handle_PULL_DATA(self, msg, addr=None):
        """
        take PULL_DATA sent from gateways and record the destination (ip, port) where this gateway MAC can be reached
        :param msg: dictionary containing header and contents of PULL_DATA message
        :param addr: tuple of (ip, port) of message origin
        :return:
        """
        if msg['MAC'] not in self.gw_listening_addrs:
            self.vminer_logger.info(f"discovered gateway mac:{msg['MAC'][-8:]} at {addr}. {len(self.gw_listening_addrs) + 1} total gateways")
        self.gw_listening_addrs[msg['MAC']] = addr

    def get_message(self, timeout=None):
        """
        waits for a datagram to be received from socket.  Once received it parses datagram into PROTOCOL.txt defined
        payload.  If successful the parsed message and sending address is returned.  On socket timeout or parsing error
        None, None is returned.
        :param timeout: socket timeout if None will not timeout
        :return: tuple of (message, addr) or (None, None) on error/timeout
        """
        if timeout:
            self.sock.settimeout(timeout)
        try:
            data, addr = self.sock.recvfrom(1024)

        except (socket.timeout, BlockingIOError) as e:
            # if recv timed out, no new data but time to send PULL_DATA or stat message
            return None, None

        except ConnectionResetError as e:
            # from https://stackoverflow.com/questions/15228272/what-would-cause-a-connectionreset-on-an-udp-socket
            # indicates a previous send operation resulted in an ICMP Port Unreachable message.
            # I am ok suppressing these errors
            return None, None

        try:
            msg, ack = messages.decode_message(data, return_ack=True)
        except ValueError as e:
            # invalid payload, ignore
            return None, None

        # send ack if appropriate
        if ack:
            self.sock.sendto(ack, addr)

        return msg, addr

    def send_stats(self):
        """
        Sends stat PUSH_DATA messages from all virtual gateways to corresponding miners
        :return:
        """
        self.last_stat_ts = time.time()
        for gw in self.vgateways_by_mac.values():
            data, addr = gw.get_stat()
            self.sock.sendto(data, addr)

    def send_keepalive(self):
        """
        sends PULL_DATA messages from all virtual gateways
        :return:
        """
        self.last_keepalive_ts = time.time()
        for gw in self.vgateways_by_mac.values():
            data, addr = gw.get_PULL_DATA()
            self.sock.sendto(data, addr)

    def adjust_tx_power(self, pk: dict):
        pk['powe'] += self.tx_power_adjustment
        return pk

    def __del__(self):
        self.sock.close()


def packet_is_poc_challenge(rxpk: dict):
    return rxpk.get('size') == 52 and rxpk.get('datr') == 'SF9BW125'


def configure_logger(debug=False):
    # setup logger
    # =============================
    logformat = '%(asctime)s.%(msecs)03d %(name)-6s:[%(levelname)-8s] %(message)s'
    logging.basicConfig(
        format=logformat,
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG if debug else logging.INFO,
        filename='middleman.log',
        filemode='a'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    formatter = logging.Formatter(logformat, datefmt='%Y/%m/%d %H:%M:%S')
    # tell the handler to use this format
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)



def main():
    parser = argparse.ArgumentParser("forward data from multiple concentrators to multiple miners with coercing of metadata")
    parser.add_argument('-p', '--port', help='port to listen for gateway on', default=1680, type=int)
    parser.add_argument('-c', '--configs', help='path where to locate gateway configs', default='gw_configs/', type=str)
    parser.add_argument('-d', '--debug', action='store_true', help="print verbose debug messages")
    parser.add_argument('-k', '--keepalive', help='keep alive interval in seconds', default=10, type=int)
    parser.add_argument('-s', '--stat', help='stat interval in seconds', default=30, type=int)
    parser.add_argument('-t', '--tx-adjust', help='adjust transmit power by some constant (in dB).', type=float, metavar='<adjustment-db>', default=0.0)
    parser.add_argument('-r', '--rx-adjust', help='adjust reported receive power by some constant (in dB).', type=float, metavar='<adjustment-db>', default=0.0)

    args = parser.parse_args()

    configure_logger(args.debug)

    logging.info(f"info log messages are enabled")
    logging.debug(f"debug log messages are enabled")
    logging.debug(f"startup arguments: {args}")

    config_paths = []
    for f in os.listdir(args.configs):
        if os.path.isfile(os.path.join(args.configs, f)) and f[-4:].lower() == 'json':
            config_paths.append(os.path.join(args.configs, f))

    gw2miner = GW2Miner(args.port, config_paths, args.keepalive, args.stat,
        args.debug, args.tx_adjust, args.rx_adjust)
    logging.info(f"starting Gateway2Miner")
    try:
        gw2miner.run()
    except FileNotFoundError as e: # change to general Exception for release
        logging.fatal("Gateway2Miner returned, packets will no longer be forwarded")
        raise e

if __name__ == '__main__':
    main()
