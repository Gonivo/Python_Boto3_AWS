# Task definition:


**Write idempotent python3 script which should:**

* Create EC2 instance in existing VPC.

* Create security group which allows only 22 and 80 inbound ports and attach it to the instance.

* Create new EBS volume with "magnetic" type, 1GB size and attach it to the instance.

* Connect to the instance via ssh, format and mount additional volume.

**It should be possible to execute this script in a completely new and clean environment any number of times without any errors. Each resource should be created only once, in other words there should be only one state for each of the points above.**
