import boto.ec2
import boto.vpc
import boto.utils

from collections import namedtuple
from subprocess import Popen, PIPE
from sys import stdin
from time import sleep
from traceback import print_exc


NUM_PINGS = 3
PING_TIMEOUT = 1
WAIT_BETWEEN_CHECKS = 60


def main():
    host_info = HostInfo()
    ec2 = EC2(host_info)

    def read_configs():
        rows = stdin.read().split()
        return [RouteConfig(*row.split(',')) for row in rows]

    def get_host_config():
        host_subnet_ids = host_info.subnet_ids
        matches = [c for c in configs if c.subnet_id in host_subnet_ids]
        return matches[0]

    def log(message):
        print 'nat-monitor/%s: %s' % (host_info.availabiliy_zone, message)

    # Read the config
    configs = read_configs()
    host_config = get_host_config()

    # Create the monitor and setup NAT for this host.
    nm = NatMonitor(host_info, ec2, configs)
    nm.setup_nat(host_config)

    # Check all nat instances forever.
    while True:
        try:
            for config in configs:
                rerouted = nm.reroute_if_necessary(config)
                if rerouted:
                    log('assumed NAT for route table %s' % config.route_table_id)
            log('all routes checked successfully.')
        except Exception:
            print_exc()
        sleep(WAIT_BETWEEN_CHECKS)



class NatMonitor(object):
    def __init__(self, host_info, ec2, configs):
        self.ec2 = ec2
        self.host_info = host_info

    def setup_nat(self, config):
        self.ec2.assign_elastic_ip(self.host_info.instance_id, config.elastic_ip_allocation_id)
        self.ec2.set_source_dest_check(self.host_info.instance_id, False)
        self.ec2.replace_route(config.route_table_id, '0.0.0.0/0', self.host_info.instance_id)
        print 'nat setup for this instance.'

    def reroute_if_necessary(self, config):
        ''' Reroutes if necessary. Returns True if reroute was performed, otherwise False. '''
        nat_alive = self._check_nat(config)
        if not nat_alive:
            self._reroute(config)
            return True
        return False

    def _check_nat(self, config):
        ''' Checks that a NAT is serving the given route. '''
        nat_instance_id = self.ec2.get_instance_id_for_route(
            config.route_table_id, '0.0.0.0/0')
        if nat_instance_id == self.host_info.instance_id:
            # I am serving this route. Since I am clearly running this script I
            # will assume that I am alive.
            return True
        if nat_instance_id:
            nat_instance_ip = self.ec2.get_instance_ip(nat_instance_id)
            alive = self._check_instance_is_alive(nat_instance_ip)
        if nat_instance_id and alive:
            return True
        return False

    def _reroute(self, config):
        ''' Reroutes the given route to use this instance as NAT. '''
        self.ec2.replace_route(config.route_table_id, '0.0.0.0/0',
                self.host_info.instance_id)

    def _check_instance_is_alive(self, instance_ip):
        ''' Pings an IP and returns True if successful, False otherwise. '''

        cmd = 'ping -c %(num_pings)s -W %(ping_timeout)s %(instance_ip)s | grep time= | wc -l'
        cmd = cmd % {
            'num_pings': NUM_PINGS,
            'ping_timeout': PING_TIMEOUT,
            'instance_ip': instance_ip
        }
        p = Popen(cmd, shell=True, stdout=PIPE)
        out, err = p.communicate()
        return out.strip() != '0'



class HostInfo(object):
    ''' Information about the instance running this script. '''

    def __init__(self):
        self.metadata = boto.utils.get_instance_metadata()

    @property
    def instance_id(self):
        return self.metadata['instance-id']

    @property
    def availabiliy_zone(self):
        return self.metadata['placement']['availability-zone']

    @property
    def region(self):
        region = self.availabiliy_zone[:-1]
        return region

    @property
    def subnet_ids(self):
        macs = self.metadata['network']['interfaces']['macs']
        return [x['subnet-id'] for x in macs.values()]



class EC2(object):
    ''' Performs EC2 operations in the given region. '''

    def __init__(self, host_info):
        self.host_info = host_info
        self.ec2 = boto.ec2.connect_to_region(host_info.region)
        self.vpc = boto.vpc.connect_to_region(host_info.region)

    def assign_elastic_ip(self, instance_id, elastic_ip_allocation_id):
        instance_id = self.host_info.instance_id
        self.ec2.associate_address(
                instance_id, allocation_id=elastic_ip_allocation_id)

    def replace_route(self, route_table_id, cidr_ip, instance_id):
        self.vpc.replace_route(route_table_id, cidr_ip, instance_id=instance_id)

    def get_instance_id_for_route(self, route_table_id, cidr):
        rt, = self.vpc.get_all_route_tables([route_table_id])
        r, = [x for x in rt.routes if x.destination_cidr_block == cidr]
        return r.instance_id

    def get_instance_ip(self, instance_id):
        instance, = self.ec2.get_only_instances([instance_id])
        return instance.private_ip_address

    def terminate_instance(self, instance_id):
        self.ec2.terminate_instances([instance_id])

    def set_source_dest_check(self, instance_id, boolean):
        self.ec2.modify_instance_attribute(instance_id, 'sourceDestCheck', boolean)



RouteConfig = namedtuple('RouteConfig',
        ['elastic_ip_allocation_id', 'subnet_id', 'route_table_id'])



if __name__ == '__main__':
    main()
