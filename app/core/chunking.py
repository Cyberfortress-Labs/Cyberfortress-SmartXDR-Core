"""
Text chunking and semantic processing utilities
Using LangChain text splitters for token-aware, overlap-enabled chunking
"""
import json
import os
import logging
from typing import Dict, List, Any
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    MarkdownTextSplitter
)
from app.config import NETWORK_DIR, MITRE_DIR, MIN_CHUNK_SIZE, MAX_CHUNK_SIZE

# Setup logger
logger = logging.getLogger('smartxdr.chunking')

# Calculate chunk overlap (10-15% of max chunk size for good context continuity)
CHUNK_OVERLAP = min(200, int(MAX_CHUNK_SIZE * 0.15))

# Initialize LangChain text splitters with token-awareness
_markdown_splitter = MarkdownTextSplitter(
    chunk_size=MAX_CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    is_separator_regex=False
)

_recursive_splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],  # Smart boundary detection
    is_separator_regex=False
)


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
    
    # 1a. IP-first chunk for reverse lookup (IP -> Device name)
    # This helps when users ask "What device has IP X?" or "IP X belongs to which machine?"
    if ip and ip != "N/A" and ip != "multiple":
        ip_lookup = f"""IP Address Lookup:
IP {ip} belongs to: {name}
The IP address {ip} is assigned to device: {name} (ID: {device_id})
Device with IP {ip}: {name}
{ip} is the IP of: {name}
What device has IP {ip}? Answer: {name} ({device_id})
IP {ip} -> {name}
Máy có IP {ip} là: {name}
IP {ip} thuộc về máy: {name}
IP {ip} là của máy: {name}

Device Details:
- Name: {name}
- ID: {device_id}
- Category: {category}
- Role: {role}
- Zone: {zone}"""
        texts.append(ip_lookup)
    
    # 1b. Zone chunk for better filtering (dynamic - works for any zone)
    # Create zone-specific chunk if device has a defined zone
    if zone and zone != "Unknown":
        zone_chunk = f"""{name} ({device_id}) is part of {zone}
Category: {category}
Located in: {zone}
IP: {ip}
Role: {role}
This device is part of the {zone} infrastructure."""
        texts.append(zone_chunk)
    
    # 1c. OS/Version/Software chunk for system info queries
    # This helps when users ask "What OS does X run?" or "Version of X?"
    os_info = data.get("os", "")
    if os_info:
        os_chunk = f"""Operating System Information for {name}:
The operating system of {name} is: {os_info}
{name} runs on: {os_info}
OS of {name}: {os_info}
What OS does {name} use? Answer: {os_info}
{name} operating system: {os_info}
Hệ điều hành của {name} là: {os_info}
{name} chạy trên hệ điều hành: {os_info}
OS của máy {name}: {os_info}

Device Details:
- Name: {name}
- ID: {device_id}
- IP: {ip}
- Category: {category}
- Role: {role}
- Operating System: {os_info}

Keywords: {name}, OS, operating system, {os_info}, version, software
Source: {filename}"""
        texts.append(os_chunk)
    
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
    
    # 3. Interfaces - Individual chunks + Summary chunk
    if "interfaces" in data and isinstance(data["interfaces"], list):
        interfaces = data["interfaces"]
        
        # 3a. Individual interface chunks (with device context)
        for idx, iface in enumerate(interfaces):
            iface_text = f"""{name} ({device_id}) - Interface {idx + 1}/{len(interfaces)}:
Device: {name} (IP: {ip})
Interface Name: {iface.get('name', 'N/A')}
Interface IP: {iface.get('ip', 'N/A')}
Subnet: {iface.get('subnet', 'N/A')}
VMnet: {iface.get('vmnet', 'N/A')}
Type: {iface.get('type', 'N/A')}
Description: {iface.get('description', 'N/A')}
Source: {filename}"""
            texts.append(iface_text)
        
        # 3b. ALL INTERFACES SUMMARY chunk (ensures all interfaces retrieved together)
        if len(interfaces) > 1:
            iface_names = [i.get('name', 'N/A') for i in interfaces]
            iface_details = []
            for i in interfaces:
                detail = f"- {i.get('name', 'N/A')}"
                if i.get('ip'):
                    detail += f" (IP: {i.get('ip')})"
                if i.get('type'):
                    detail += f" [{i.get('type')}]"
                if i.get('description'):
                    detail += f": {i.get('description')}"
                iface_details.append(detail)
            
            summary_chunk = f"""{name} ({device_id}) Network Interfaces Summary:
Device: {name}
Primary IP: {ip}
Total Interfaces: {len(interfaces)}
Interface Names: {', '.join(iface_names)}

All Network Interfaces:
{chr(10).join(iface_details)}

Keywords: {name}, interfaces, {', '.join(iface_names)}, network cards, NICs
Source: {filename}"""
            texts.append(summary_chunk)
    
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
    
    # Header - Put MITRE ID first for better matching
    tech_type = "Sub-technique" if is_subtechnique else "Technique"
    text_parts.append(f"{mitre_id} - MITRE ATT&CK {tech_type}: {name}")
    text_parts.append(f"MITRE ID: {mitre_id}")
    text_parts.append(f"Technique Name: {name}")
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
    
    # Keywords for search - emphasize MITRE ID
    text_parts.append("")
    keywords = [mitre_id, name, f"technique {mitre_id}"]
    if tactics:
        keywords.extend(tactics)
    text_parts.append(f"Search Keywords: {', '.join(keywords)}")
    
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
                flow = " ".join(pipeline["ingress_flow"])
                context_parts.append(f"Ingress traffic flow from Internet:\n{flow}")
            
            if "east_west_flow" in pipeline:
                flow = " ".join(pipeline["east_west_flow"])
                context_parts.append(f"East-West internal traffic flow:\n{flow}")
            
            if "endpoint_flow" in pipeline:
                flow = " ".join(pipeline["endpoint_flow"])
                context_parts.append(f"Endpoint monitoring flow:\n{flow}")
        
        return "\n\n".join(context_parts)
    except Exception as e:
        logger.warning(f" Cannot load topology: {e}")
        return ""


def markdown_to_chunks(content: str, filename: str, max_chunk_size: int = None) -> List[str]:
    """
    Convert Markdown content to semantic chunks using LangChain.
    Uses MarkdownTextSplitter with chunk overlap for better context continuity.
    
    Features:
    - Chunk overlap for context continuity
    - Smart boundary detection (splits on headers, paragraphs)
    - Respects markdown structure
    
    Args:
        content: Raw markdown content
        filename: Source filename for context
        max_chunk_size: Maximum characters per chunk
    
    Returns:
        List of text chunks optimized for RAG
    """
    if max_chunk_size is None:
        max_chunk_size = MAX_CHUNK_SIZE
    
    if not content.strip():
        return []
    
    # Create splitter with custom size if needed
    if max_chunk_size != MAX_CHUNK_SIZE:
        splitter = MarkdownTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=min(200, int(max_chunk_size * 0.15)),
            length_function=len
        )
    else:
        splitter = _markdown_splitter
    
    # Split content using LangChain
    docs = splitter.create_documents([content])
    
    # Add source metadata to each chunk
    chunks = []
    for idx, doc in enumerate(docs):
        chunk_text = f"Source: {filename}\n\n{doc.page_content}"
        
        # Only include chunks that meet minimum size
        if len(chunk_text) > MIN_CHUNK_SIZE:
            chunks.append(chunk_text.strip())
    
    # Fallback: if no chunks created, use recursive splitter
    if not chunks:
        return text_to_chunks(content, filename, max_chunk_size)
    
    logger.debug(f"Markdown split into {len(chunks)} chunks with overlap={CHUNK_OVERLAP}")
    return chunks


def text_to_chunks(content: str, filename: str, max_chunk_size: int = None) -> List[str]:
    """
    Convert plain text content to semantic chunks using LangChain.
    Uses RecursiveCharacterTextSplitter for smart boundary detection.
    
    Features:
    - Chunk overlap for context continuity
    - Smart boundary detection (paragraphs > sentences > words)
    - Token-aware splitting
    
    Args:
        content: Raw text content
        filename: Source filename for context
        max_chunk_size: Maximum characters per chunk
    
    Returns:
        List of text chunks optimized for RAG
    """
    if max_chunk_size is None:
        max_chunk_size = MAX_CHUNK_SIZE
    
    if not content.strip():
        return []
    
    # Create splitter with custom size if needed
    if max_chunk_size != MAX_CHUNK_SIZE:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=min(200, int(max_chunk_size * 0.15)),
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    else:
        splitter = _recursive_splitter
    
    # Split content using LangChain
    docs = splitter.create_documents([content])
    
    # Add source metadata to each chunk
    chunks = []
    for idx, doc in enumerate(docs):
        chunk_text = f"Source: {filename}\n\n{doc.page_content}"
        
        # Only include chunks that meet minimum size
        if len(chunk_text) > MIN_CHUNK_SIZE:
            chunks.append(chunk_text.strip())
    
    # Fallback: if still no chunks, create one from full content (truncated)
    if not chunks and content.strip():
        truncated = content[:max_chunk_size]
        chunks.append(f"Source: {filename}\n\n{truncated}")
    
    logger.debug(f"Text split into {len(chunks)} chunks with overlap={CHUNK_OVERLAP}")
    return chunks


def playbook_json_to_chunks(data: Dict[str, Any], filename: str) -> List[str]:
    """
    Convert playbook JSON to semantic chunks.
    Each playbook becomes a searchable chunk with all steps.
    
    Args:
        data: Parsed JSON data (expected to have 'playbooks' key)
        filename: Source filename for context
    
    Returns:
        List of text chunks optimized for RAG
    """
    chunks = []
    
    if isinstance(data, dict) and "playbooks" in data:
        playbooks = data["playbooks"]
    elif isinstance(data, list):
        playbooks = data
    else:
        return []
    
    for playbook in playbooks:
        playbook_id = playbook.get("id", "unknown")
        name = playbook.get("name", "Unknown Playbook")
        description = playbook.get("description", "")
        trigger = playbook.get("trigger", {})
        steps = playbook.get("steps", [])
        
        # Build playbook text
        chunk_text = f"""Security Playbook: {name}
ID: {playbook_id}
Description: {description}

Trigger Conditions:
- Type: {trigger.get('type', 'manual')}
- Condition: {trigger.get('condition', 'N/A')}

Steps:
"""
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            step_action = step.get("action", "N/A")
            step_desc = step.get("description", "")
            chunk_text += f"{i}. {step_name}: {step_action}\n   {step_desc}\n"
        
        chunk_text += f"\nSource: {filename}"
        chunks.append(chunk_text)
    
    return chunks


def knowledge_base_json_to_chunks(data: Dict[str, Any], filename: str) -> List[str]:
    """
    Convert knowledge base JSON to semantic chunks.
    Each issue/solution pair becomes a searchable chunk.
    
    Args:
        data: Parsed JSON data (expected to have 'issues' or similar key)
        filename: Source filename for context
    
    Returns:
        List of text chunks optimized for RAG
    """
    chunks = []
    
    # Handle different possible structures
    if isinstance(data, dict):
        if "issues" in data:
            items = data["issues"]
        elif "entries" in data:
            items = data["entries"]
        elif "knowledge_base" in data:
            items = data["knowledge_base"]
        else:
            # Try to process as individual items
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return []
    
    for item in items:
        if not isinstance(item, dict):
            continue
            
        item_id = item.get("id", "unknown")
        title = item.get("title", item.get("name", "Unknown Issue"))
        description = item.get("description", item.get("problem", ""))
        solution = item.get("solution", item.get("resolution", ""))
        category = item.get("category", "General")
        tags = item.get("tags", [])
        
        chunk_text = f"""Knowledge Base Entry: {title}
ID: {item_id}
Category: {category}
Tags: {', '.join(tags) if tags else 'N/A'}

Problem/Description:
{description}

Solution/Resolution:
{solution}

Source: {filename}
Keywords: {title}, {category}, {', '.join(tags[:5]) if tags else ''}"""
        
        chunks.append(chunk_text)
    
    return chunks


def dataflow_to_natural_text(data: Dict[str, Any], filename: str) -> List[str]:
    """
    Convert dataflow/pipeline JSON to natural language chunks for RAG.
    
    Intelligently handles:
    - phases[] array: Creates summary chunk + individual phase chunks
    - nodes[] array: Creates summary and individual node chunks
    - edges[] array: Grouped by phase
    
    This ensures questions like "how many phases?" or "list all phases" 
    can be answered because ALL phases are in a single summary chunk.
    """
    chunks = []
    
    # Extract metadata
    metadata = data.get("metadata", {})
    doc_name = metadata.get("name", data.get("name", "Dataflow"))
    doc_desc = metadata.get("description", data.get("description", ""))
    
    # 1. PHASES SUMMARY CHUNK - Critical for "how many phases?" questions
    phases = data.get("phases", [])
    if phases:
        phase_list = []
        for i, phase in enumerate(phases):
            phase_name = phase.get("name", f"Phase {i+1}")
            phase_desc = phase.get("description", "")
            phase_list.append(f"  {i+1}. {phase_name}: {phase_desc[:150]}")
        
        phases_summary = f"""{doc_name}

PHASES SUMMARY:
This dataflow pipeline consists of {len(phases)} phases:

{chr(10).join(phase_list)}

Total number of phases: {len(phases)}
How many phases? Answer: {len(phases)} phases

Source: {filename}
Keywords: phases, pipeline, dataflow, {len(phases)} phases, workflow stages"""
        chunks.append(phases_summary)
        
        # 2. INDIVIDUAL PHASE CHUNKS - For detailed questions about specific phases
        for phase in phases:
            phase_id = phase.get("id", "")
            phase_name = phase.get("name", "Unknown Phase")
            phase_desc = phase.get("description", "")
            edge_ids = phase.get("edge_ids", [])
            
            phase_chunk = f"""{doc_name} - {phase_name}

Phase ID: {phase_id}
Phase Name: {phase_name}
Description: {phase_desc}

Related Data Flows: {', '.join(edge_ids) if edge_ids else 'N/A'}

Source: {filename}
Keywords: {phase_name}, {phase_id}, phase, pipeline stage"""
            chunks.append(phase_chunk)
    
    # 3. NODES SUMMARY CHUNK - For "what components?" questions
    nodes = data.get("nodes", [])
    if nodes:
        node_names = [n.get("role", n.get("id", "")) for n in nodes]
        nodes_summary = f"""{doc_name} - Components/Nodes

Total components in this dataflow: {len(nodes)}
Components: {', '.join(node_names[:20])}{'...' if len(node_names) > 20 else ''}

Source: {filename}
Keywords: nodes, components, devices, dataflow elements"""
        chunks.append(nodes_summary)
    
    # 4. ROUTING PIPELINES CHUNK - For traffic flow questions
    routing = data.get("routing_pipelines", {})
    if routing:
        routing_parts = []
        for flow_name, flow_nodes in routing.items():
            if isinstance(flow_nodes, list):
                routing_parts.append(f"  - {flow_name}: {' → '.join(flow_nodes)}")
        
        routing_chunk = f"""{doc_name} - Routing Pipelines

Traffic flow paths in this architecture:
{chr(10).join(routing_parts)}

Source: {filename}
Keywords: routing, traffic flow, data path, pipeline"""
        chunks.append(routing_chunk)
    
    return chunks
