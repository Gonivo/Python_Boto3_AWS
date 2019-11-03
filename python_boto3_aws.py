#!/usr/bin/env python3
import boto3
import paramiko
import json
from botocore.exceptions import ClientError
import time

ec2 = boto3.resource('ec2')
ec2_client = boto3.client('ec2')
my_name = 'evgeniy-deyneko'
zone = 'eu-west-1a'

def is_instance_created():
    my_instances = ec2.instances.filter(
        Filters=[{
            'Name': 'tag:Name',
            'Values': [my_name],
            },
            {
            'Name': 'instance-state-name',
            'Values': ['running'],
            }]
        )
    tagged_instances = list(my_instances)
    if len(tagged_instances) == 0:
        return False
    else:
        instance_id = tagged_instances[0].id
        return instance_id

def is_security_group_created():
    try:
        my_security_groups = ec2_client.describe_security_groups(GroupNames=[my_name])
        my_security_groups = my_security_groups['SecurityGroups']
        if len(my_security_groups) > 0:
            for sg in my_security_groups:
                security_group_id = sg['GroupId']
            return security_group_id
    except:
        return False

def is_key_pair_created():
    try:
        key_pair = ec2_client.describe_key_pairs(KeyNames=[my_name])
        if len(key_pair) > 0:
            return my_name
    except:
        return False

def is_ebs_created():
    my_volumes = ec2.volumes.all().filter(
        Filters=[{
            'Name': 'tag:Name',
            'Values': [my_name]
            }]
        )
    tagged_volumes = list(my_volumes)
    if len(tagged_volumes) > 0:
        ebs_id = tagged_volumes[0].volume_id
        return ebs_id
    else:
        return False

def is_ebs_attached(ebs_id):
    my_volumes = ec2.volumes.all().filter(
        Filters=[{
            'Name': 'tag:Name',
            'Values': [my_name]
            }]
        )
    tagged_volumes = list(my_volumes)
    ebs_status = tagged_volumes[0].state
    if ebs_status == 'in-use':
        return True
    else:
        return False

def create_keys():
    outfile = open('ec2-key-' + my_name + '.pem','w')
    key_pair = ec2_client.create_key_pair(KeyName=my_name)
    # print(key_pair)
    KeyPairOut = str(key_pair['KeyMaterial'])
    outfile.write(KeyPairOut)
    return True

def create_instance():
    new_instance = ec2.create_instances(
         ImageId='ami-0c224e30f7a997d9f',
         MinCount=1,
         MaxCount=1,
         InstanceType='t2.micro',
         KeyName=my_name,
         Placement={'AvailabilityZone': zone},
         SecurityGroups=[my_name]
    )
    instance_id = new_instance[0].instance_id
    print('Wait until instance running...')
    instance = ec2.Instance(instance_id)
    instance.wait_until_running()
    response = ec2.create_tags(
        Resources=[
            instance_id,
        ],
        Tags=[
            {
                'Key': 'Name',
                'Value': my_name
            },
        ]
    )
    return instance_id

def create_security_group():
    try:
        response = ec2_client.create_security_group(GroupName=my_name, Description='Ingress 22 and 80 ports')
        security_group_id = response['GroupId']
        data = ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                 'FromPort': 80,
                 'ToPort': 80,
                 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp',
                 'FromPort': 22,
                 'ToPort': 22,
                 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
    except ClientError as e:
        print(e)
    return security_group_id

def create_ebs():
    ebs_vol = ec2_client.create_volume(
        Size=1,
        AvailabilityZone=zone,
        VolumeType='standard',
        TagSpecifications=[
            {
                'ResourceType': 'volume',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': my_name
                    },
                ]
            },
        ]
    )
    volume_id = ebs_vol['VolumeId']
    print('Waiting for volume state available')
    volume_alailable_waiter = ec2_client.get_waiter('volume_available')
    volume_alailable_waiter.wait(VolumeIds=[volume_id,],)
    return volume_id

def get_instance_ip():
    for instance in ec2.instances.all():
        if instance.key_name == my_name and instance.state['Name'] == 'running':
            instance_ip = instance.public_ip_address
            return instance_ip

def attach_ebs(instance_id, ebs_id):
    ec2_client.attach_volume(
        Device='/dev/sdf',
        InstanceId=instance_id,
        VolumeId=ebs_id,
    )
    return True

def manage_ebs_via_ssh(instance_ip):
    print('Connecting via SSH to IP:', instance_ip)
    key = paramiko.RSAKey.from_private_key_file('ec2-key-' + my_name + '.pem')
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh_client.connect(hostname=instance_ip, username='ubuntu', pkey=key)
        stdin, stdout, stderr = ssh_client.exec_command('lsblk -J')
        fsdata = json.loads(stdout.read())
        for volume in fsdata['blockdevices']:
            if volume['name'] == 'xvdf':
                if 'children' in volume:
                    children = volume['children']
                    for child in children:
                        if child['name'] == 'xvdf1':
                            print('Partition_already_created')
                            stdin, stdout, stderr = ssh_client.exec_command("sudo mkfs.ext4 /dev/xvdf1")
                            stdout.flush()
                            data = stdout.read().splitlines()
                            for line in data:
                                if line:
                                    print(line)
                            stdin, stdout, stderr = ssh_client.exec_command("mountpoint /dev/xvdf1 | grep \"is not a mountpoint\"")
                            stdout.flush()
                            data = stdout.read().splitlines()
                            for line in data:
                                if line:
                                    stdin, stdout, stderr = ssh_client.exec_command("sudo mkdir /mnt/hdd")
                                    stdin, stdout, stderr = ssh_client.exec_command("sudo chmod 777 /mnt/hdd")
                                    stdin, stdout, stderr = ssh_client.exec_command("sudo mount /dev/xvdf1 /mnt/hdd -t ext4 -o rw")
                else:
                    print('Creating partition...')
                    time.sleep(15)
                    stdin, stdout, stderr = ssh_client.exec_command("sudo fdisk /dev/xvdf")
                    stdin.write('n\n')
                    stdin.write('p\n')
                    stdin.write('1\n')
                    stdin.write('\n')
                    stdin.write('\n')
                    stdin.write('w\n')
                    stdout.flush()
                    time.sleep(15)
                    stdin, stdout, stderr = ssh_client.exec_command("sudo mkfs.ext4 /dev/xvdf1")
                    stdin, stdout, stderr = ssh_client.exec_command("sudo mkdir /mnt/hdd")
                    stdin, stdout, stderr = ssh_client.exec_command("sudo chmod 777 /mnt/hdd")
                    print('Mounting...')
                    stdin, stdout, stderr = ssh_client.exec_command("sudo mount /dev/xvdf1 /mnt/hdd -t ext4 -o rw")

        ssh_client.close()
        print('Partition /dev/xvdf1 mounted in /mnt/hdd')
        return True
    except Exception as e:
        print(e)
        return False

################# Execute ######################

key_pair_name = is_key_pair_created()
if key_pair_name == False:
    print('Creating key pair...')
    key_pair_name = create_keys()
else:
    print('Key pair already created, name:', key_pair_name)

security_group_id = is_security_group_created()
if security_group_id == False:
    print('Security group not found, creating security group...')
    security_group_id = create_security_group()
    print('Security group created, ID:', security_group_id,)
else:
    print('Security group already created, ID:', security_group_id)

instance_id = is_instance_created()
if instance_id == False:
    instance_id = create_instance()
    print('New instance created, ID:', instance_id)
else:
    print('Instance already created, ID:', instance_id)

ebs_id = is_ebs_created()
if ebs_id == False:
    print('Creating EBS volume...')
    ebs_id = create_ebs()
    print('EBS volume created, ID:', ebs_id)
    attach_ebs(instance_id, ebs_id)
    print('EBS volume attached')
else:
    print('EBS volume already created, ID:', ebs_id)
    ebs_attached = is_ebs_attached(ebs_id)
    if ebs_attached == False:
        attach_ebs(instance_id, ebs_id)
    else:
        print('EBS volume already attached')
instance_ip = get_instance_ip()
manage_ebs_via_ssh = manage_ebs_via_ssh(instance_ip)
if manage_ebs_via_ssh == True:
    print('Done')
else:
    print('Something went wrong')