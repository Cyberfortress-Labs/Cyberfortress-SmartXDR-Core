# Cyberfortress SOC Network Topology - IP Address Mapping

## Overview
This document provides a comprehensive IP address mapping for all devices in the Cyberfortress Intelligent SOC Ecosystem.

## Network Segments

### Internet Zone (VMnet 8 - 192.168.71.0/24)
- **External Attacker**: 192.168.71.100
- **NAT Gateway / Linux Router**: 192.168.71.5

### WAN Zone (VMnet 2 - 10.81.85.0/24)
- **pfSense Firewall WAN Interface**: 10.81.85.2
- **Linux Router WAN Interface**: 10.81.85.3

### SOC Management Network (VMnet 5 - 192.168.100.0/24)

#### Primary SOC Servers
- **192.168.100.128** - **SIEM Server (Elastic Stack / Elasticsearch)** - Central log storage and analytics platform
- **192.168.100.138** - **Wazuh Server** - Host-based intrusion detection and security monitoring
- **192.168.100.148** - **IRIS (DFIR-IRIS)** - Incident response and case management platform
- **192.168.100.130** - **MISP Server** - Threat intelligence sharing and analysis
- **192.168.100.158** - **n8n Server** - Workflow automation and orchestration
- **192.168.100.168** - **ElastAlert2 Server** - Alerting engine for Elasticsearch

#### Network Security Monitoring
- **192.168.100.171** - **Suricata Management Interface** - IDS/IPS management and monitoring
- **192.168.100.172** - **Zeek Management Interface** - Network security monitoring management

#### Network Infrastructure
- **192.168.100.2** - **pfSense SOC Interface** - Firewall management interface for SOC subnet

### LAN/XDR Subnet (VMnet 3/4 - 192.168.85.0/24)
- **192.168.85.2** - **pfSense LAN Interface**
- **192.168.85.111** - **WAF ModSecurity** - Web application firewall
- **192.168.85.112** - **DVWA (Damn Vulnerable Web Application)** - Vulnerable web server for testing
- **192.168.85.115** - **Windows Server** - Active Directory and target host

### Guest Subnet (VMnet 10 - 192.168.95.0/24)
- **192.168.95.2** - **pfSense Guest Interface**
- **192.168.95.100** - **Internal Attacker** - Insider threat simulation
- **192.168.95.10-200** - **Guest Devices** - User endpoints

## Quick IP Lookup

### What is IP 192.168.100.128?
**Answer**: IP 192.168.100.128 is the **SIEM Server running Elastic Stack (Elasticsearch)**.  
This is the central log storage and analytics platform for the entire SOC ecosystem.

### What is IP 192.168.100.138?
**Answer**: IP 192.168.100.138 is the **Wazuh Server**.  
This handles host-based intrusion detection and security monitoring.

### What is IP 192.168.100.148?
**Answer**: IP 192.168.100.148 is the **IRIS (DFIR-IRIS) Server**.  
This is the incident response and case management platform.

### What is IP 192.168.100.130?
**Answer**: IP 192.168.100.130 is the **MISP Server**.  
This handles threat intelligence sharing and analysis.

### What is IP 192.168.100.158?
**Answer**: IP 192.168.100.158 is the **n8n Server**.  
This provides workflow automation and orchestration capabilities.

### What is IP 192.168.100.168?
**Answer**: IP 192.168.100.168 is the **ElastAlert2 Server**.  
This is the alerting engine for Elasticsearch.

### What is IP 192.168.100.171?
**Answer**: IP 192.168.100.171 is the **Suricata Management Interface**.  
This is used for managing and monitoring the IDS/IPS system.

### What is IP 192.168.100.172?
**Answer**: IP 192.168.100.172 is the **Zeek Management Interface**.  
This is used for network security monitoring management.

## Device Roles
### Router
- **Name**: Router/Linux Router
- **IP**: 192.168.71.5,10.81.85.3
- **Subnet**: 192.168.71.0/24 (Internet Zone)
- **WAN IP**: 10.81.85.3 (WAN Management)
- **NAT IP**: 192.168.71.5 (NAT Management)
- **Role**: NAT Gateway
- **Purpose**: Provides Internet access via NAT gateway.

### pfSense
- **Name**: pfSense/Firewall
- **IP**:  10.81.85.2, 192.168.100.2, 192.168.85.2, 192.168.95.2
- **WAN IP**: 10.81.85.2 (WAN Management)
- **LAN IP**: 192.168.85.2 (LAN/XDR Management)
- **GUEST IP**: 192.168.95.2 (Guest Management)
- **SOC IP**: 192.168.100.2 (SOC Management)
- **Role**: Multi-Interface Firewall & Router
- **Purpose**: Routes and filters traffic between WAN, LAN, Guest, and SOC networks. Feeds LAN traffic into Suricata/Zeek inline inspection pipeline.


### SIEM Server (192.168.100.128)
- **Name**: SIEM Server (Elastic Stack)
- **IP**: 192.168.100.128
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Central Log Storage & Analytics
- **Components**: Elasticsearch, Kibana, Logstash
- **Purpose**: Aggregates and analyzes logs from all security tools and devices

### Wazuh Server (192.168.100.138)
- **Name**: Wazuh Server
- **IP**: 192.168.100.138
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Host-Based Intrusion Detection
- **Purpose**: Monitors endpoints for security threats and compliance

### IRIS Server (192.168.100.148)
- **Name**: IRIS (DFIR-IRIS)
- **IP**: 192.168.100.148
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Incident Response & Case Management
- **Purpose**: Manages security incidents and forensic investigations

### MISP Server (192.168.100.130)
- **Name**: MISP Server
- **IP**: 192.168.100.130
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Threat Intelligence Sharing
- **Purpose**: Collects and shares threat intelligence indicators

### n8n Server (192.168.100.158)
- **Name**: n8n Server
- **IP**: 192.168.100.158
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Workflow Automation
- **Purpose**: Automates security operations and response workflows

### ElastAlert2 Server (192.168.100.168)
- **Name**: ElastAlert2 Server
- **IP**: 192.168.100.168
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Alerting Engine
- **Purpose**: Generates alerts based on Elasticsearch data

### Suricata (192.168.100.171)
- **Name**: Suricata Inline IDPS
- **IP**: 192.168.100.171 (Management)
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Inline IDS/IPS
- **Mode**: Bridge Mode
- **Purpose**: Inspects network traffic for threats and blocks malicious activity

### Zeek (192.168.100.172)
- **Name**: Zeek NSM
- **IP**: 192.168.100.172 (Management)
- **Subnet**: 192.168.100.0/24 (SOC Management)
- **Role**: Network Security Monitoring
- **Mode**: Passive Monitoring
- **Purpose**: Monitors network traffic and generates security insights
