import os
import socket
import struct
import sys
import asyncore
import pyroute2
import netifaces

from enum import IntEnum
from oslo_log import log as logging
from pyroute2 import IPRoute

from pyroute2.netlink.rtnl.rtmsg import rtmsg
from pyroute2.netlink.rtnl import (RTM_NEWROUTE as RTNL_NEWROUTE,
                                   RTM_DELROUTE as RTNL_DELROUTE)
from pyroute2.netlink.rtnl import rt_proto as proto

LOG = logging.getLogger(__name__)
# To enable FPM module with netlink, the following option in
# /etc/frr/daemons needs to be added for zebra
# zebra_options="  -A 127.0.0.1 -s 90000000  -M fpm:netlink"

class FpmServerConnect(asyncore.dispatcher):
    def __init__(self, FPM_PORT):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('localhost', FPM_PORT))
        self.listen(1)

    def run(self):
        try:
            asyncore.loop()
        except:
            self.handle_error()

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            conn, client_addr = pair
            UpdateRoutes(conn)

class UpdateRoutes(asyncore.dispatcher):
    def update_FRR_route_to_NBDB(self, payload):
        offset = 0
        while offset < len(payload):
            msg = rtmsg(payload[offset:])
            msg.decode()
            offset += msg['header']['length']
            next_hop = ""
            prefix_len = msg['dst_len']
            for a in msg['attrs']:
                if a[0] == 'RTA_DST':
                    dst = (a[1])
            if msg['proto'] == proto['zebra']:
                if msg['header']['type'] == RTNL_NEWROUTE:
                    for a in msg['attrs']:
                        if a[0] == 'RTA_GATEWAY':
                            next_hop = (a[1])
                        elif a[0] == 'RTA_OIF':
                            inf_id = a[1]
                            ip = IPRoute()
                            if msg['family'] == socket.AF_INET:
                                next_hop = ip.get_addr(family=socket.AF_INET, index=inf_id)[0].get_attr('IFA_ADDRESS')
                            elif msg['family'] == socket.AF_INET6:
                                next_hop = ip.get_addr(family=socket.AF_INET6, index=inf_id)[0].get_attr('IFA_ADDRESS')

                    # TODO(spk): What if there is a route to be added/deleted
                    # with dst and prefix_len same as a route which is
                    # already added/deleted but next hop is different, use --ecmp
                    LOG.info(f"Adding route: dst={dst}/{prefix_len}, next_hop={next_hop}")
                    os.system("ovn-nbctl lr-route-add lr0 %s/%d %s " % (dst, prefix_len, next_hop))
            if msg['header']['type'] == RTNL_DELROUTE:
                LOG.info(f"Deleting route: dst={dst}/{prefix_len}")
                os.system("ovn-nbctl lr-route-del lr0 %s/%d " %(dst, prefix_len))
        return

    def handle_read(self):
        data = self.recv(4)
        version,msg_type,length = struct.unpack('!BBH', data)
        payload = self.recv(length-4)
        if msg_type == 2:
            LOG.error("Unexpected Protobuf message")
            self.handle_error()
            return
        self.update_FRR_route_to_NBDB(payload)

    def handle_error(self):
        self.close()
        raise asyncore.ExitNow("Shutting down FPM server")
