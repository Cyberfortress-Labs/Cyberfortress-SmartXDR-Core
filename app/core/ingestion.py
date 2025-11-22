"""
Data ingestion utilities for RAG system
"""
import json
import os
import hashlib
import glob
from config import ASSETS_DIR, ECOSYSTEM_DIR, NETWORK_DIR, MITRE_DIR
from chunking import json_to_natural_text, load_topology_context, mitre_to_natural_text


def get_file_hash(filepath):
    """Calculate SHA256 hash to detect file changes."""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ingest_data(collection):
    """
    Smart data ingestion with semantic chunking
    Args:
        collection: ChromaDB collection instance
    """
    print(f"🔍 Scanning directory '{ASSETS_DIR}'...")
    
    if not os.path.exists(ASSETS_DIR):
        print(f"⚠️ Directory '{ASSETS_DIR}' not found!")
        return
    
    # Load topology context once
    topology_context = load_topology_context()
    if topology_context:
        print("✅ Loaded topology context")
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
    
    if not json_files:
        print("⚠️ No JSON files found.")
        return

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
                print(f"✅ {filename}: Unchanged. Skipped.")
                continue
            else:
                print(f"🔄 {filename}: Changed. Updating...")
                collection.delete(where={"source": filename})
        else:
            print(f"➕ {filename}: New file. Indexing...")

        # Read and process data
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            ids = []
            documents = []
            metadatas = []
            
            # Handle different file types
            if filename == "devices.json":
                # Inventory file - create overview
                if "devices" in data and isinstance(data["devices"], list):
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
                    
                    # SOC Subnet detailed summary
                    if "SOC Subnet" in zones:
                        soc_devices = zones["SOC Subnet"]
                        soc_summary = f"""SOC Subnet components (192.168.100.0/24):
{chr(10).join(f"- {d.get('name', 'N/A')} ({d.get('id', 'N/A')}): {d.get('role', 'N/A')}" for d in soc_devices)}

These are the core Security Operations Center infrastructure components responsible for monitoring, detection, analysis, and incident response."""
                        ids.append(f"{filename}-soc-summary")
                        documents.append(soc_summary)
                        metadatas.append({
                            "source": filename,
                            "file_hash": current_hash,
                            "type": "soc_components",
                            "zone": "SOC Subnet"
                        })
            
            elif filename == "network_map.json":
                # Network map - VMnet descriptions
                if "network_map" in data and isinstance(data["network_map"], list):
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
            
            # === MITRE ATT&CK DATA ===
            elif filename == "mitre_techniques_only.json":
                # Process techniques only file
                if isinstance(data, list):
                    print(f"   -> Processing {len(data)} MITRE techniques...")
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
            
            elif filename == "mitre_attack_clean.json":
                # Process full MITRE data (tactics, groups, software)
                if isinstance(data, dict):
                    # Process tactics
                    if "tactics" in data and isinstance(data["tactics"], list):
                        for tactic in data["tactics"]:
                            tactic_id = tactic.get("mitre_id", "unknown")
                            tactic_text = f"""MITRE ATT&CK Tactic: {tactic_id} - {tactic.get("name", "Unknown")}
Shortname: {tactic.get("shortname", "N/A")}

Description: {tactic.get("description", "")}

Keywords: {tactic_id}, {tactic.get("name", "")}, {tactic.get("shortname", "")}"""
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
                print(f"   -> Indexed {len(documents)} chunks.")
                
        except Exception as e:
            print(f"❌ Error reading {filename}: {e}")
    
    print(f"\n✅ Completed! Total {total_chunks} chunks indexed in ChromaDB.")
    print(f"📊 Total documents in collection: {collection.count()}")
