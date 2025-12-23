"""
Data ingestion utilities for RAG system
"""
import json
import os
import hashlib
import glob
from app.config import (
    ASSETS_DIR, ECOSYSTEM_DIR, NETWORK_DIR, MITRE_DIR,
    PLAYBOOKS_DIR, KNOWLEDGE_BASE_DIR, POLICIES_DIR
)
from app.core.chunking import (
    json_to_natural_text, load_topology_context, mitre_to_natural_text,
    markdown_to_chunks, text_to_chunks, playbook_json_to_chunks, knowledge_base_json_to_chunks
)
from app.utils.logger import ingestion_logger as logger
    """Calculate SHA256 hash to detect file changes."""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def ingest_data(collection):
    """
    Smart data ingestion with semantic chunking
    Args:
        collection: ChromaDB collection instance
    """
    logger.info(f"Scanning directory '{ASSETS_DIR}'...")
    
    if not os.path.exists(ASSETS_DIR):
        logger.warning(f"Directory '{ASSETS_DIR}' not found!")
        return
    
    # Load topology context once
    topology_context = load_topology_context()
    if topology_context:
        logger.info("Loaded topology context")
        # Add topology as a special document
        collection.upsert(
            ids=["topology_context"],
            documents=[topology_context],
            metadatas=[{"source": "topology.json", "type": "network_flow"}]
        )
    
    # Process all JSON files in ecosystem
    json_files = glob.glob(os.path.join(ECOSYSTEM_DIR, "*.json"))
    
    # Also include network files
    network_files = [
        os.path.join(NETWORK_DIR, "devices.json"),
        os.path.join(NETWORK_DIR, "network_map.json")
    ]
    json_files.extend([f for f in network_files if os.path.exists(f)])
    
    # Include MITRE ATT&CK data
    mitre_files = [
        os.path.join(MITRE_DIR, "mitre_attack_clean.json"),
        os.path.join(MITRE_DIR, "mitre_techniques_only.json")
    ]
    json_files.extend([f for f in mitre_files if os.path.exists(f)])
    
    # Include playbooks JSON files
    if os.path.exists(PLAYBOOKS_DIR):
        playbook_files = glob.glob(os.path.join(PLAYBOOKS_DIR, "*.json"))
        json_files.extend(playbook_files)
        logger.info(f"Found {len(playbook_files)} playbook JSON files.")
    
    # Include knowledge base JSON files
    if os.path.exists(KNOWLEDGE_BASE_DIR):
        kb_files = glob.glob(os.path.join(KNOWLEDGE_BASE_DIR, "*.json"))
        json_files.extend(kb_files)
        logger.info(f"Found {len(kb_files)} knowledge base JSON files.")
    
    if not json_files:
        logger.warning("No JSON files found.")
    else:
        logger.info(f"Found {len(json_files)} total JSON files to process.")

    total_chunks = 0
    for filepath in json_files:
        filename = os.path.basename(filepath)
        current_hash = get_file_hash(filepath)
        
        # Check if file already indexed and unchanged
        existing_items = collection.get(
            where={"source": filename},
            limit=1,
            include=["metadatas"]
        )
        
        if existing_items["ids"]:
            stored_hash = existing_items["metadatas"][0].get("file_hash") if existing_items["metadatas"] else None
            if stored_hash == current_hash:
                logger.debug(f"{filename}: Unchanged. Skipped.")
                continue
            else:
                logger.info(f"{filename}: Changed. Updating...")
                collection.delete(where={"source": filename})
        else:
            logger.info(f"{filename}: New file. Indexing...")

        # Read and process data
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            ids = []
            documents = []
            metadatas = []
            
            # Handle different file types BY CONTENT STRUCTURE (not filename)
            # === DEVICE INVENTORY (array of devices) ===
            if isinstance(data, dict) and "devices" in data and isinstance(data["devices"], list):
                # Inventory file - create overview
                    # General overview
                    overview = f"""Device list in SOC system:
{chr(10).join(f"- {d.get('name', 'N/A')} ({d.get('id', 'N/A')}): {d.get('category', 'N/A')} in {d.get('zone', 'N/A')}" for d in data["devices"])}"""
                    ids.append(f"{filename}-overview")
                    documents.append(overview)
                    metadatas.append({
                        "source": filename,
                        "file_hash": current_hash,
                        "type": "device_inventory"
                    })
                    
                    # Create zone-specific summaries
                    zones = {}
                    for d in data["devices"]:
                        zone = d.get("zone", "Unknown")
                        if zone not in zones:
                            zones[zone] = []
                        zones[zone].append(d)
                    
                    # Create summary for EACH zone (dynamic, not hardcoded)
                    for zone_name, zone_devices in zones.items():
                        if zone_name == "Unknown":
                            continue
                        zone_summary = f"""{zone_name} components:
{chr(10).join(f"- {d.get('name', 'N/A')} ({d.get('id', 'N/A')}): {d.get('role', 'N/A')}" for d in zone_devices)}

Total devices in {zone_name}: {len(zone_devices)}
These are infrastructure components in the {zone_name} zone."""
                        ids.append(f"{filename}-{zone_name.lower().replace(' ', '-')}-summary")
                        documents.append(zone_summary)
                        metadatas.append({
                            "source": filename,
                            "file_hash": current_hash,
                            "type": "zone_components",
                            "zone": zone_name
                        })
            
            # === NETWORK MAP (detect by content, not filename) ===
            elif isinstance(data, dict) and "network_map" in data and isinstance(data["network_map"], list):
                # Network map - VMnet descriptions
                    for net in data["network_map"]:
                        net_text = f"""VMware Virtual Network: {net.get('vmnet', 'N/A')}
Type: {net.get('type', 'N/A')}
Subnet: {net.get('subnet', 'N/A')}
Gateway: {net.get('gateway', 'N/A')}
Purpose: {net.get('description', 'N/A')}"""
                        ids.append(f"{filename}-{net.get('vmnet', 'unknown')}")
                        documents.append(net_text)
                        metadatas.append({
                            "source": filename,
                            "file_hash": current_hash,
                            "type": "network_config"
                        })
            
            # === PLAYBOOKS JSON ===
            elif filepath.startswith(PLAYBOOKS_DIR) or "playbook" in filename.lower():
                text_chunks = playbook_json_to_chunks(data, filename)
                for idx, chunk in enumerate(text_chunks):
                    ids.append(f"{filename}-playbook-{idx}")
                    documents.append(chunk)
                    metadatas.append({
                        "source": filename,
                        "file_hash": current_hash,
                        "type": "playbook"
                    })
            
            # === KNOWLEDGE BASE JSON ===
            elif filepath.startswith(KNOWLEDGE_BASE_DIR) or "knowledge" in filename.lower():
                text_chunks = knowledge_base_json_to_chunks(data, filename)
                for idx, chunk in enumerate(text_chunks):
                    ids.append(f"{filename}-kb-{idx}")
                    documents.append(chunk)
                    metadatas.append({
                        "source": filename,
                        "file_hash": current_hash,
                        "type": "knowledge_base"
                    })
            
            elif isinstance(data, dict) and "id" in data:
                # Individual device file - use semantic chunking
                text_chunks = json_to_natural_text(data, filename)
                for idx, chunk in enumerate(text_chunks):
                    ids.append(f"{filename}-chunk-{idx}")
                    documents.append(chunk)
                    metadatas.append({
                        "source": filename,
                        "file_hash": current_hash,
                        "device_id": data.get("id", "unknown"),
                        "device_name": data.get("name", "Unknown"),
                        "type": "device_detail"
                    })
            
            # === MITRE ATT&CK DATA (detect by content structure, not filename) ===
            # MITRE techniques list: array of objects with mitre_id
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "mitre_id" in data[0]:
                # Process techniques only file
                if isinstance(data, list):
                    logger.info(f"   -> Processing {len(data)} MITRE techniques...")
                    for technique in data:
                        if not technique.get("deprecated", False):
                            mitre_id = technique.get("mitre_id", "unknown")
                            chunk_text = mitre_to_natural_text(technique)
                            ids.append(f"{filename}-{mitre_id}")
                            documents.append(chunk_text)
                            metadatas.append({
                                "source": filename,
                                "file_hash": current_hash,
                                "type": "mitre_technique",
                                "mitre_id": mitre_id,
                                "is_subtechnique": technique.get("is_subtechnique", False)
                            })
            
            # MITRE full data: dict with tactics/groups/techniques keys
            elif isinstance(data, dict) and ("tactics" in data or "groups" in data):
                # Process full MITRE data (tactics, groups, software)
                if isinstance(data, dict):
                    # Process tactics
                    if "tactics" in data and isinstance(data["tactics"], list):
                        for tactic in data["tactics"]:
                            tactic_id = tactic.get("mitre_id", "unknown")
                            tactic_name = tactic.get("name", "Unknown")
                            tactic_shortname = tactic.get("shortname", "N/A")
                            
                            # Create bidirectional search text - can search by ID or name
                            tactic_text = f"""MITRE ATT&CK Tactic
ID: {tactic_id}
Name: {tactic_name}
Shortname: {tactic_shortname}

{tactic_id} is the tactic ID for "{tactic_name}"
{tactic_name} has tactic ID {tactic_id}
The {tactic_shortname} tactic is identified as {tactic_id}

Description: {tactic.get("description", "")}

Keywords for search: {tactic_id}, {tactic_name}, {tactic_shortname}, tactic {tactic_id}, {tactic_name} tactic, {tactic_name} ID"""
                            ids.append(f"{filename}-tactic-{tactic_id}")
                            documents.append(tactic_text)
                            metadatas.append({
                                "source": filename,
                                "file_hash": current_hash,
                                "type": "mitre_tactic",
                                "mitre_id": tactic_id
                            })
                    
                    # Process threat groups (limit to top 50 for efficiency)
                    if "groups" in data and isinstance(data["groups"], list):
                        for group in data["groups"][:50]:  # Top 50 groups
                            group_id = group.get("mitre_id", "unknown")
                            aliases = group.get("aliases", [])
                            group_text = f"""MITRE ATT&CK Threat Group: {group_id} - {group.get("name", "Unknown")}
Aliases: {', '.join(aliases) if aliases else 'None'}

Description: {group.get("description", "")}

Keywords: {group_id}, {group.get("name", "")}, {', '.join(aliases[:3])}"""
                            ids.append(f"{filename}-group-{group_id}")
                            documents.append(group_text)
                            metadatas.append({
                                "source": filename,
                                "file_hash": current_hash,
                                "type": "mitre_group",
                                "mitre_id": group_id
                            })
            
            else:
                # Fallback for other formats
                text_content = f"Source: {filename}\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                ids.append(f"{filename}-raw")
                documents.append(text_content)
                metadatas.append({
                    "source": filename,
                    "file_hash": current_hash,
                    "type": "raw"
                })
            
            if documents:
                collection.add(ids=ids, documents=documents, metadatas=metadatas)
                total_chunks += len(documents)
                logger.info(f"   -> Indexed {len(documents)} chunks.")
                
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")
    
    # ============ PROCESS MARKDOWN FILES ============
    logger.info("Processing Markdown (.md) files...")
    md_files = []
    
    # Policies directory
    if os.path.exists(POLICIES_DIR):
        md_files.extend(glob.glob(os.path.join(POLICIES_DIR, "*.md")))
    
    # Also search in other common locations
    for subdir in ["docs", "documentation", "guides"]:
        subdir_path = os.path.join(ASSETS_DIR, subdir)
        if os.path.exists(subdir_path):
            md_files.extend(glob.glob(os.path.join(subdir_path, "*.md")))
    
    logger.info(f"Found {len(md_files)} Markdown files.")
    
    for filepath in md_files:
        filename = os.path.basename(filepath)
        current_hash = get_file_hash(filepath)
        
        # Check if file already indexed and unchanged
        existing_items = collection.get(
            where={"source": filename},
            limit=1,
            include=["metadatas"]
        )
        
        if existing_items["ids"]:
            stored_hash = existing_items["metadatas"][0].get("file_hash") if existing_items["metadatas"] else None
            if stored_hash == current_hash:
                logger.debug(f"{filename}: Unchanged. Skipped.")
                continue
            else:
                logger.info(f"{filename}: Changed. Updating...")
                collection.delete(where={"source": filename})
        else:
            logger.info(f"{filename}: New file. Indexing...")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            text_chunks = markdown_to_chunks(content, filename)
            
            ids = []
            documents = []
            metadatas = []
            
            # Determine type based on directory
            doc_type = "policy" if POLICIES_DIR in filepath else "documentation"
            
            for idx, chunk in enumerate(text_chunks):
                ids.append(f"{filename}-md-{idx}")
                documents.append(chunk)
                metadatas.append({
                    "source": filename,
                    "file_hash": current_hash,
                    "type": doc_type,
                    "format": "markdown"
                })
            
            if documents:
                collection.add(ids=ids, documents=documents, metadatas=metadatas)
                total_chunks += len(documents)
                logger.info(f"   -> Indexed {len(documents)} chunks.")
        
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")
    
    # ============ PROCESS PLAIN TEXT FILES ============
    logger.info("Processing Plain Text (.txt) files...")
    txt_files = []
    
    # Search all assets subdirectories for .txt files
    for root, dirs, files in os.walk(ASSETS_DIR):
        for file in files:
            if file.endswith(".txt"):
                txt_files.append(os.path.join(root, file))
    
    logger.info(f"Found {len(txt_files)} Text files.")
    
    for filepath in txt_files:
        filename = os.path.basename(filepath)
        current_hash = get_file_hash(filepath)
        
        # Check if file already indexed and unchanged
        existing_items = collection.get(
            where={"source": filename},
            limit=1,
            include=["metadatas"]
        )
        
        if existing_items["ids"]:
            stored_hash = existing_items["metadatas"][0].get("file_hash") if existing_items["metadatas"] else None
            if stored_hash == current_hash:
                logger.debug(f"{filename}: Unchanged. Skipped.")
                continue
            else:
                logger.info(f"{filename}: Changed. Updating...")
                collection.delete(where={"source": filename})
        else:
            logger.info(f"{filename}: New file. Indexing...")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            text_chunks = text_to_chunks(content, filename)
            
            ids = []
            documents = []
            metadatas = []
            
            for idx, chunk in enumerate(text_chunks):
                ids.append(f"{filename}-txt-{idx}")
                documents.append(chunk)
                metadatas.append({
                    "source": filename,
                    "file_hash": current_hash,
                    "type": "text_document",
                    "format": "plain_text"
                })
            
            if documents:
                collection.add(ids=ids, documents=documents, metadatas=metadatas)
                total_chunks += len(documents)
                logger.info(f"   -> Indexed {len(documents)} chunks.")
        
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")
    
    logger.info(f"Completed! Total {total_chunks} chunks indexed in ChromaDB.")
    logger.info(f"Total documents in collection: {collection.count()}")

