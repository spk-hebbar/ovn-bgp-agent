# Copyright 2021 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from neutron_lib._i18n import _


class OVNBGPAgentException(Exception):
    """Base OVN BGP Agebt Exception.

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.
    """

    message = _("An unknown exception occurred.")

    def __init__(self, **kwargs):
        super().__init__(self.message % kwargs)
        self.msg = self.message % kwargs

    def __str__(self):
        return self.msg


class InvalidPortIP(OVNBGPAgentException):
    """OVN Port has Invalid IP.

    :param ip: The (wrong) IP of the port
    """

    message = _("OVN port with invalid IP: %(ip)s.")


class PortNotFound(OVNBGPAgentException):
    """OVN Port not found.

    :param port: The port name or UUID.
    """

    message = _("OVN port was not found: %(port)s.")
