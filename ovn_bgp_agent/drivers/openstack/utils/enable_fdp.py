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

RTPROT_BGP = 186
LOG = logging.getLogger(__name__)
# To enable FPM module with netlink, the following option in
# /etc/frr/daemons needs to be added for zebra
# zebra_options="  -A 127.0.0.1 -s 90000000  -M fpm:netlink"

class FpmServerConnect(asyncore.dispatcher):
    def __init__(self, FPM_PORT, nb_idl):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('localhost', FPM_PORT))
        self.listen(1)
        self.nb_idl = nb_idl

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            conn, client_addr = pair
            UpdateRoutes(conn, self.nb_idl)

class UpdateRoutes(asyncore.dispatcher):
    def __init__(self, conn, nb_idl):
        asyncore.dispatcher.__init__(self, conn)
        self.nb_idl = nb_idl
        self.proto = 'static'

    def add_route_NBDB(self, dst, prefix_len, next_hop):
        # TODO(spk): What if there is a route to be added/deleted
        # with dst and prefix_len same as a route which is
        # already added/deleted but next hop is different, use --ecmp
        columns = {'external_ids': {'routing_proto': self.proto}}
        lrouter_name = 'lr0'
        with self.nb_idl.transaction(check_error=True) as txn:
            LOG.info(f"Adding route: dst={dst}/{prefix_len}, next_hop={next_hop}")
            txn.add(self.nb_idl.add_static_route(lrouter_name,
                ip_prefix=dst, nexthop=next_hop, **columns))

    def del_route_NBDB(self, dst, prefix_len=0, next_hop=''):
        lrouter_name = 'lr0'
        with self.nb_idl.transaction(check_error=True) as txn:
            LOG.info(f"Deleting route: dst={dst}/{prefix_len} next_hop={next_hop}")
            txn.add(self.nb_idl.delete_static_route(lrouter_name,
                ip_prefix=dst, nexthop=next_hop, if_exists=True))

    def update_FRR_route_to_NBDB(self, payload):
        offset = 0
        while offset < len(payload):
            msg = rtmsg(payload[offset:])
            msg.decode()
            offset += msg['header']['length']
            next_hop = ""
            if msg['proto'] == RTPROT_BGP:
                self.proto = "bgp"
            prefix_len = 0
            prefix_len = msg['dst_len']
            if prefix_len == 0:
                if msg['family'] == socket.AF_INET:
                    prefix_len = 32
                elif msg['family'] == socket.AF_INET6:
                    prefix_len = 64
            for a in msg['attrs']:
                if a[0] == 'RTA_DST':
                    dst = (a[1])
                elif a[0] == 'RTA_GATEWAY':
                    next_hop = (a[1])
                elif a[0] == 'RTA_OIF':
                    inf_id = a[1]
                    ip = IPRoute()
                    if msg['family'] == socket.AF_INET:
                        next_hop = ip.get_addr(family=socket.AF_INET, index=inf_id)[0].get_attr('IFA_ADDRESS')
                    elif msg['family'] == socket.AF_INET6:
                        next_hop = ip.get_addr(family=socket.AF_INET6, index=inf_id)[0].get_attr('IFA_ADDRESS')
            LOG.debug(f"Route from FRR: {dst}/{prefix_len} {next_hop}")
            if ((msg['header']['type'] == RTNL_NEWROUTE) and
                    (msg['proto'] == RTPROT_BGP)):
                self.add_route_NBDB(dst, prefix_len, next_hop)
            if msg['header']['type'] == RTNL_DELROUTE:
                self.del_route_NBDB(dst, prefix_len, next_hop)

    def handle_read(self):
        data = self.recv(4)
        version,msg_type,length = struct.unpack('!BBH', data)
        payload = self.recv(length-4)
        if msg_type == 2:
            LOG.error("Unexpected Protobuf message")
            self.handle_error()
            return
        self.update_FRR_route_to_NBDB(payload)
        self.loop_control = True

    def handle_error(self):
        self.close()
        raise asyncore.ExitNow("Shutting down FPM server")

def run(nb_idl):
    fpm = FpmServerConnect(FPM_PORT=2620, nb_idl=nb_idl)
    fpm.loop_control = False
    try:
        while True:
            asyncore.loop(count=1)
            if fpm.loop_control:
                handler.loop_control = False
    except:
        self.handle_error()
