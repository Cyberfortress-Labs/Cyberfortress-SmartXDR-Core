"""
Text chunking and semantic processing utilities
"""
import json
import os
from typing import Dict, List, Any
from config import NETWORK_DIR, MITRE_DIR


def json_to_natural_text(data: Dict[str, Any], filename: str) -> List[str]:
    """Convert complex JSON to natural language paragraphs for better semantic understanding."""
    texts = []
    
    # Extract basic info
    device_id = data.get("id", "unknown")
    name = data.get("name", "Unknown Device")
    category = data.get("category", "Unknown")
    zone = data.get("zone", "Unknown")
    ip = data.get("ip", "N/A")
    role = data.get("role", "Unknown")
    description = data.get("description", "")
    
    # 1. Overview - Enhanced with more searchable keywords
    overview = f"""Device {device_id}: {name}
Type: {category}
Role: {role}
Zone: {zone}
IP Address: {ip}
Management IP: {ip}
Primary IP: {ip}
Description: {description}
Source: {filename}

Keywords: {name}, {device_id}, IP {ip}, {category}, {zone}, {role}"""
    texts.append(overview)
    
    # 1b. Zone/Category chunk for better filtering
    if zone == "SOC Subnet" or "SOC" in category:
        zone_chunk = f"""{name} ({device_id}) is a SOC component
Category: {category}
Located in: {zone} (192.168.100.0/24)
IP: {ip}
Role in SOC: {role}
This is part of the Security Operations Center infrastructure."""
        texts.append(zone_chunk)
    
    # 2. Network configuration
    if "subnet" in data or "ip_range" in data or "vmnet" in data:
        network_info = f"""Network config for {name} (ID: {device_id}):
"""
        if "subnet" in data:
            network_info += f"- Subnet: {data['subnet']}\n"
        if "ip_range" in data:
            network_info += f"- IP Range: {data['ip_range']}\n"
        if "vmnet" in data:
            vmnet = data['vmnet']
            if isinstance(vmnet, list):
                network_info += f"- VMnet: {', '.join(vmnet)}\n"
            else:
                network_info += f"- VMnet: {vmnet}\n"
        if "gateway" in data:
            network_info += f"- Gateway: {data['gateway']}\n"
        if "primary_ip" in data:
            network_info += f"- Primary IP: {data['primary_ip']}\n"
        texts.append(network_info.strip())
    
    # 3. Interfaces
    if "interfaces" in data and isinstance(data["interfaces"], list):
        for idx, iface in enumerate(data["interfaces"]):
            iface_text = f"""Interface {idx + 1} of {name}:
Name: {iface.get('name', 'N/A')}
IP: {iface.get('ip', 'N/A')}
Subnet: {iface.get('subnet', 'N/A')}
VMnet: {iface.get('vmnet', 'N/A')}
Type: {iface.get('type', 'N/A')}
Description: {iface.get('description', 'N/A')}"""
            texts.append(iface_text)
    
    # 4. Services and Components
    if "services" in data:
        services = data["services"]
        if isinstance(services, list):
            services_text = f"""Services running on {name}:
{', '.join(services)}"""
            texts.append(services_text)
    
    if "components" in data:
        components = data["components"]
        if isinstance(components, list):
            comp_text = f"""Components of {name}:
{', '.join(components)}"""
            texts.append(comp_text)
    
    # 5. Vulnerabilities
    if "vulnerabilities" in data:
        vulns = data["vulnerabilities"]
        if isinstance(vulns, list) and vulns:
            vuln_text = f"""Vulnerabilities on {name} (ID: {device_id}):
{', '.join(vulns)}
These are intentionally installed vulnerabilities for testing detection capabilities."""
            texts.append(vuln_text)
    
    # 6. Capabilities
    if "capabilities" in data:
        caps = data["capabilities"]
        if isinstance(caps, list) and caps:
            cap_text = f"""Capabilities of {name}:
{chr(10).join(f'- {cap}' for cap in caps)}"""
            texts.append(cap_text)
    
    # 7. Monitoring
    if "monitoring" in data:
        mon = data["monitoring"]
        if isinstance(mon, list) and mon:
            mon_text = f"""Monitoring for {name}:
{chr(10).join(f'- {m}' for m in mon)}"""
            texts.append(mon_text)
    
    # 8. Data sources (SIEM)
    if "data_sources" in data:
        sources = data["data_sources"]
        if isinstance(sources, list) and sources:
            source_text = f"""{name} collects logs from:
{chr(10).join(f'- {s}' for s in sources)}"""
            texts.append(source_text)
    
    # 9. Routing function
    if "routing_function" in data:
        routing_text = f"""Routing function of {name}:
{data['routing_function']}"""
        texts.append(routing_text)
    
    # 10. Attack vectors
    if "attack_vectors" in data:
        vectors = data["attack_vectors"]
        if isinstance(vectors, list) and vectors:
            attack_text = f"""Attack vectors from {name}:
{chr(10).join(f'- {v}' for v in vectors)}"""
            texts.append(attack_text)
    
    return texts


def mitre_to_natural_text(technique: Dict[str, Any]) -> str:
    """Convert MITRE ATT&CK technique to natural language for RAG."""
    mitre_id = technique.get("mitre_id", "Unknown")
    name = technique.get("name", "Unknown")
    description = technique.get("description", "")
    tactics = technique.get("tactics", [])
    platforms = technique.get("platforms", [])
    data_sources = technique.get("data_sources", [])
    is_subtechnique = technique.get("is_subtechnique", False)
    
    # Build natural language text
    text_parts = []
    
    # Header
    tech_type = "Sub-technique" if is_subtechnique else "Technique"
    text_parts.append(f"MITRE ATT&CK {tech_type}: {mitre_id} - {name}")
    text_parts.append("")
    
    # Tactics
    if tactics:
        text_parts.append(f"Tactics: {', '.join(tactics)}")
    
    # Platforms
    if platforms:
        text_parts.append(f"Platforms: {', '.join(platforms)}")
    
    # Description
    if description:
        text_parts.append("")
        text_parts.append(f"Description: {description}")
    
    # Data sources
    if data_sources:
        text_parts.append("")
        text_parts.append("Detection Data Sources:")
        for ds in data_sources:
            text_parts.append(f"  - {ds}")
    
    # Keywords for search
    text_parts.append("")
    keywords = [mitre_id, name]
    if tactics:
        keywords.extend(tactics)
    text_parts.append(f"Keywords: {', '.join(keywords)}")
    
    return "\n".join(text_parts)


def load_topology_context() -> str:
    """Load network topology to create traffic flow context."""
    topology_file = os.path.join(NETWORK_DIR, "topology.json")
    if not os.path.exists(topology_file):
        return ""
    
    try:
        with open(topology_file, "r", encoding="utf-8") as f:
            topology = json.load(f)
        
        context_parts = []
        
        if "routing_pipeline" in topology:
            pipeline = topology["routing_pipeline"]
            
            if "ingress_flow" in pipeline:
                flow = " → ".join(pipeline["ingress_flow"])
                context_parts.append(f"Ingress traffic flow from Internet:\n{flow}")
            
            if "east_west_flow" in pipeline:
                flow = " → ".join(pipeline["east_west_flow"])
                context_parts.append(f"East-West internal traffic flow:\n{flow}")
            
            if "endpoint_flow" in pipeline:
                flow = " → ".join(pipeline["endpoint_flow"])
                context_parts.append(f"Endpoint monitoring flow:\n{flow}")
        
        return "\n\n".join(context_parts)
    except Exception as e:
        print(f"⚠️ Cannot load topology: {e}")
        return ""
