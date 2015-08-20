ec2-nat-failover
================

Script that enables high availability IP and NAT management in EC2.

The problem: You need static IPs for incoming and outgoing traffic in your EC2
VPC, so you created NAT/reverse proxy instances in each availabiliy zone,
associate elastic IPs with each instance, and use them to route all traffic in
and out of your VPC.

Now, if one of your NATs goes down all your instances in that availability zone
will lose Internet connectivity. One way to resolve this problem is to detect
when it happens and re-route all outgoing traffic in that availability zone to
one of the remaining NAT instances.

This script does just that. Run the script on your NAT instances. Provide
through stdin a list of elastic ip, subnet and route table ids for each
availability zone you want to include:

```
eipalloc-f3acbd91,subnet-268a747f,rtb-d3e731b6
eipalloc-3f3c2c5d,subnet-8f59e4ea,rtb-d8e731bd
eipalloc-8e5242ec,subnet-2e33e959,rtb-dae731bf
```
IPs are optional, and if they are not included the script will not try to make
any IP assignments.

```
subnet-268a747f,rtb-d3e731b6
subnet-8f59e4ea,rtb-d8e731bd
subnet-2e33e959,rtb-dae731bf
```


When the script starts it will determine which subnet it is located in, assume
the corresponding IP and set its host instance as Internet gateway for its
route table.

Ater that, it will proceed to perform a liveness test on the other NAT
instances every couple of seconds. Should the test fail it will terminate the
instance and set itself as Internet gateway for the route table instead of the
failing instance.

The easiest way to get started with this is to create an autoscaling group of
Amazon Linux NAT instances and add the following to userdata:


```bash
#!/bin/bash

cat > /root/nat_configs.txt <<EOF
eipalloc-f3acbd91,subnet-268a747f,rtb-d3e731b6
eipalloc-3f3c2c5d,subnet-8f59e4ea,rtb-d8e731bd
eipalloc-8e5242ec,subnet-2e33e959,rtb-dae731bf
EOF

curl -sL https://raw.githubusercontent.com/wrapp/ec2-nat-failover/master/nat_monitor.py > /root/nat_monitor.py

nohup python -u /root/nat_monitor.py < /root/nat_configs.txt | logger -t nat_monitor &
```
