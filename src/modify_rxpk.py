

"""
This is mostly a placeholder for more sophisticated modification but I want it in the flow
Things like syncronizing timestamps between multiple gateways (so timestamps appear in order) and
better mapping of input RSSI/SNR to output RSSI/SNR, etc
"""


import json
import time
import datetime as dt



class RXMetadataModification:
    def __init__(self):
        self.min_rssi = -120
        self.max_rssi = -90  # valid to 50 miles via FSPL filter
        self.max_snr = 0
        self.min_snr = -20


    def modify_rxpk(self, rxpk, tmst_offset=0):
        """
        JSON object
        :param rxpk: per PUSH_DATA https://github.com/Lora-net/packet_forwarder/blob/master/PROTOCOL.TXT
        :return: object with metadata modified
        """

        # simple clipping low and high, could be a lot more sophisticated to add randomness or better mapping
        rxpk['rssi'] = min(self.max_rssi, max(self.min_rssi, rxpk['rssi']))
        rxpk['lsnr'] = min(self.max_snr,  max(self.min_snr,  rxpk['lsnr']))

        # modify tmst (Internal timestamp of "RX finished" event (32b unsigned)) to be aligned to uS since midnight UTC
        # this will be discontinuous once a day but that is basically same effect as a gateay reset / forwarder reboot
        ts_str = rxpk['time']
        if ts_str[-1] == 'Z':
            ts_str = ts_str[:-1]

        ts_dt = dt.datetime.fromisoformat(ts_str)
        ts_midnight = dt.datetime(year=ts_dt.year, month=ts_dt.month, day=ts_dt.day, hour=0, minute=0, second=0, microsecond=0)
        elapsed_us = int((ts_dt-ts_midnight).total_seconds() * 1e6)

        rxpk['tmst'] = (elapsed_us + tmst_offset) % (2**32)


        return rxpk

