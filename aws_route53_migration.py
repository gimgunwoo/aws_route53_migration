import json
import os
import yaml
import boto3

# list zones
legacy_session = boto3.Session(profile_name='legacy')
legacy_client = legacy_session.client('route53')
legacy_zones = legacy_client.list_hosted_zones()

prod_session = boto3.Session(profile_name='prod-infra')
prod_client = prod_session.client('route53')
prod_zones = prod_client.list_hosted_zones()

# get Name, Id, CallerReference, Config/PrivateZone
for lz in legacy_zones['HostedZones']:
    callref = lz['CallerReference']
    privzone = lz['Config']['PrivateZone']
    zoneId = lz['Id'].rsplit("/", 1)[1]
    zoneName = lz['Name'].rsplit(".", 1)[0]

# create zone
    prod_zone_response = prod_client.create_hosted_zone(
        Name=zoneName,
        CallerReference=str(os.system("date '+%Y%m%d%H%M'"))+str(zoneName),
        HostedZoneConfig={
            'Comment': zoneName,
            'PrivateZone': privzone
        },
    )

    prod_zoneId = prod_zone_response['HostedZone']['Id']

    # list records in zones
    legacy_records = None
    os.system("aws route53 list-resource-record-sets --hosted-zone-id " + zoneId + " --max-items 300 --profile legacy > " + zoneName + ".json")

    # get A, MX, CNAME, TXT records from each zone
    with open(zoneName + '.json') as file:
        legacy_records = yaml.safe_load(file)

    prod_zoneId = None

    for pz in prod_zones['HostedZones']:
        if lz['Name'] == pz['Name']:
            prod_zoneId = pz['Id'].rsplit("/", 1)[1]

    for lr in legacy_records['ResourceRecordSets']:
        Type = lr['Type']
        recName = lr['Name'].rsplit(".", 1)[0]
        if "ResourceRecords" in lr and Type in  ["A", "MX", "TXT"]:
            TTL = lr['TTL']
            for v in lr['ResourceRecords']:
                prod_rec_response = prod_client.change_resource_record_sets(
                    HostedZoneId = prod_zoneId,
                    ChangeBatch={
                        'Comment': recName,
                        'Changes': [
                            {
                                'Action': 'UPSERT',
                                'ResourceRecordSet': {
                                    'Name': recName,
                                    'Type': Type,
                                    'TTL': TTL,
                                    'ResourceRecords': [
                                        {
                                            'Value': v['Value']
                                        },
                                    ],
                                }
                            },
                        ]
                    }
                )
        elif "ResourceRecords" in lr and Type in  ["CNAME"]:
            TTL = lr['TTL']
            for v in lr['ResourceRecords']:
                prod_rec_response = prod_client.change_resource_record_sets(
                    HostedZoneId = prod_zoneId,
                    ChangeBatch={
                        'Comment': recName,
                        'Changes': [
                            {
                                'Action': 'UPSERT',
                                'ResourceRecordSet': {
                                    'Name': lr['Name'],
                                    'Type': Type,
                                    'TTL': TTL,
                                    'ResourceRecords': [
                                        {
                                            'Value': v['Value']
                                        },
                                    ],
                                }
                            },
                        ]
                    }
                )
        elif "AliasTarget" in lr:
            hostedZoneId = lr['AliasTarget']['HostedZoneId']
            evalTargetHealth = lr['AliasTarget']['EvaluateTargetHealth']
            dns = lr['AliasTarget']['DNSName']
            prod_rec_response = prod_client.change_resource_record_sets(
                HostedZoneId = prod_zoneId,
                ChangeBatch={
                    'Comment': recName,
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': recName,
                                'Type': Type,
                                'AliasTarget': {
                                    'HostedZoneId': hostedZoneId,
                                    'DNSName': dns,
                                    'EvaluateTargetHealth': evalTargetHealth
                                },
                            }
                        },
                    ]
                }
            )
