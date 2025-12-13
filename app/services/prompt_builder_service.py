"""
Prompt Builder Service for SmartXDR
Loads and constructs system prompts with network context for LLM calls
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class PromptBuilder:
    """Builds prompts for Gemini/OpenAI with optional network context injection"""
    
    def __init__(self, project_root: Optional[Path] = None, prompt_file: str = 'base_system.json'):
        """
        Initialize PromptBuilder
        
        Args:
            project_root: Root path of the project. If None, auto-detects from file location
            prompt_file: Name of prompt file to load from prompts/system/ (default: base_system.json)
        """
        if project_root is None:
            # Auto-detect: app/services/prompt_builder.py -> go up 2 levels
            self.project_root = Path(__file__).parent.parent.parent
        else:
            self.project_root = Path(project_root)
        
        self.prompt_file = prompt_file
        self._context_cache = {}
        self.base_prompt = self._load_base_prompt()
    
    def _load_base_prompt(self) -> Dict[str, Any]:
        """Load base system prompt from JSON"""
        prompt_path = self.project_root / 'prompts' / 'system' / self.prompt_file
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_network_context(self) -> Dict[str, Any]:
        """Load network documentation files (topology, devices, network_map)"""
        if 'network' in self._context_cache:
            return self._context_cache['network']
        
        assets_path = self.project_root / 'assets' / 'network'
        
        context = {}
        files = ['topology.json', 'network_map.json', 'devices.json']
        
        for file in files:
            file_path = assets_path / file
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    key = file.replace('.json', '')
                    context[key] = json.load(f)
        
        self._context_cache['network'] = context
        return context
    
    def build_system_prompt(self, include_full_context: bool = False, format: str = 'json') -> str:
        """
        Build complete system prompt for Gemini/OpenAI
        
        Args:
            include_full_context: If True, includes full JSON network documentation.
                                 If False, only uses quick_reference from base prompt (saves tokens)
            format: Output format - 'json' (structured) or 'text' (markdown-style)
        
        Returns:
            Complete system prompt ready for LLM API call
        """
        sp = self.base_prompt['system_prompt']
        
        if format == 'json':
            # Build structured JSON prompt
            prompt_structure = {
                "identity": sp['identity'],
                "primary_role": sp['primary_role'],
                "lab_environment": {
                    "overview": sp['lab_environment']['overview'],
                    "platform": sp['lab_environment']['platform']
                },
                "knowledge_domains": sp['knowledge_domains'],
                "behavioral_guidelines": sp['behavioral_guidelines'],
                "operational_rules": sp['operational_rules'],
                "interaction_patterns": sp['interaction_patterns'],
                "constraints": sp['constraints']
            }
            
            # Add network context
            if include_full_context:
                context = self._load_network_context()
                prompt_structure['lab_environment']['network_documentation'] = context
            else:
                prompt_structure['lab_environment']['quick_reference'] = sp['lab_environment']['quick_reference']
            
            return json.dumps(prompt_structure, indent=2, ensure_ascii=False)
        
        else:
            # Build text/markdown format (original behavior)
            prompt_parts = [
                sp['identity'],
                "",
                "## Primary Mission",
                sp['primary_role'],
                ""
            ]
            
            # Lab Environment
            prompt_parts.append("## Lab Environment")
            prompt_parts.append(sp['lab_environment']['overview'])
            prompt_parts.append("")
            
            if include_full_context:
                # Include full network documentation
                context = self._load_network_context()
                
                prompt_parts.append("### Complete Network Documentation")
                prompt_parts.append("")
                
                if 'topology' in context:
                    prompt_parts.append("#### Network Topology")
                    prompt_parts.append("```json")
                    prompt_parts.append(json.dumps(context['topology'], indent=2))
                    prompt_parts.append("```")
                    prompt_parts.append("")
                
                if 'network_map' in context:
                    prompt_parts.append("#### VMware Network Configuration")
                    prompt_parts.append("```json")
                    prompt_parts.append(json.dumps(context['network_map'], indent=2))
                    prompt_parts.append("```")
                    prompt_parts.append("")
                
                if 'devices' in context:
                    prompt_parts.append("#### Device Inventory")
                    prompt_parts.append("```json")
                    prompt_parts.append(json.dumps(context['devices'], indent=2))
                    prompt_parts.append("```")
                    prompt_parts.append("")
            else:
                # Use compact quick_reference only
                qr = sp['lab_environment']['quick_reference']
                
                prompt_parts.append("### Network Quick Reference")
                prompt_parts.append("")
                
                prompt_parts.append("**Network Segments:**")
                for vmnet, desc in qr['network_segments'].items():
                    prompt_parts.append(f"- {vmnet}: {desc}")
                prompt_parts.append("")
                
                prompt_parts.append("**Key IP Addresses:**")
                for device, ip in qr['key_ips'].items():
                    prompt_parts.append(f"- {device}: {ip}")
                prompt_parts.append("")
                
                prompt_parts.append("**Traffic Flows:**")
                for flow_type, flow in qr['traffic_flows'].items():
                    prompt_parts.append(f"- {flow_type}: {flow}")
                prompt_parts.append("")
                
                prompt_parts.append("**Core Security Stack:**")
                for category, tools in qr['core_stack'].items():
                    prompt_parts.append(f"- {category}: {tools}")
                prompt_parts.append("")
            
            # Knowledge Domains
            prompt_parts.append("## Knowledge Domains")
            for domain, skills in sp['knowledge_domains'].items():
                prompt_parts.append(f"### {domain.replace('_', ' ').title()}")
                for skill in skills:
                    prompt_parts.append(f"- {skill}")
                prompt_parts.append("")
            
            # Behavioral Guidelines
            prompt_parts.append("## Behavioral Guidelines")
            prompt_parts.append(f"**Tone:** {sp['behavioral_guidelines']['tone']}")
            prompt_parts.append("")
            
            for guideline_type, items in sp['behavioral_guidelines'].items():
                if guideline_type == 'tone':
                    continue
                prompt_parts.append(f"### {guideline_type.replace('_', ' ').title()}")
                if isinstance(items, list):
                    for item in items:
                        prompt_parts.append(f"- {item}")
                prompt_parts.append("")
            
            # Operational Rules
            prompt_parts.append("## Operational Rules")
            for rule in sp['operational_rules']:
                prompt_parts.append(f"- {rule}")
            prompt_parts.append("")
            
            # Interaction Patterns
            prompt_parts.append("## Interaction Patterns")
            for pattern_type, description in sp['interaction_patterns'].items():
                prompt_parts.append(f"**{pattern_type.replace('_', ' ').title()}:** {description}")
            prompt_parts.append("")
            
            # Constraints
            prompt_parts.append("## Constraints")
            for constraint in sp['constraints']:
                prompt_parts.append(f"- {constraint}")
            
            return "\n".join(prompt_parts)
    
    def build_task_prompt(self, task_type: str, **kwargs) -> str:
        """
        Build task-specific prompt (for instructions/)
        
        Args:
            task_type: Type of task (e.g., 'ioc_enrichment', 'log_analysis')
            **kwargs: Additional parameters for the task prompt
        
        Returns:
            Task-specific instruction prompt
        """
        task_path = self.project_root / 'prompts' / 'instructions' / f'{task_type}.json'
        
        if not task_path.exists():
            raise FileNotFoundError(f"Task prompt not found: {task_type}")
        
        with open(task_path, 'r', encoding='utf-8') as f:
            task_prompt = json.load(f)
        
        # TODO: Template rendering with kwargs if needed
        return json.dumps(task_prompt, indent=2)
    
    def get_examples(self, example_type: str) -> Dict[str, Any]:
        """
        Load few-shot examples
        
        Args:
            example_type: Type of examples (e.g., 'alert_triage_examples')
        
        Returns:
            Dictionary containing examples
        """
        examples_path = self.project_root / 'prompts' / 'examples' / f'{example_type}.json'
        
        if not examples_path.exists():
            return {}
        
        with open(examples_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def build_rag_prompt(self) -> str:
        """
        Build compact RAG-optimized system prompt (minimal tokens)
        
        Returns:
            Lightweight system prompt for RAG use cases
        """
        sp = self.base_prompt['system_prompt']
        
        # Check if this is the RAG-optimized prompt format
        if 'capabilities' in sp and 'behavioral_rules' in sp:
            # New compact format (rag_system.json)
            prompt_parts = [
                sp['identity'],
                "",
                "**Capabilities:**"
            ]
            for cap in sp['capabilities']:
                prompt_parts.append(f"- {cap}")
            
            prompt_parts.append("")
            prompt_parts.append("**Behavioral Rules:**")
            for rule in sp['behavioral_rules']:
                prompt_parts.append(f"- {rule}")
            
            # Add Vietnamese support info
            if 'vietnamese_support' in sp and sp['vietnamese_support']['enabled']:
                prompt_parts.append("")
                prompt_parts.append("**Vietnamese Support:**")
                prompt_parts.append("- Auto-detect and respond in user's language")
                prompt_parts.append("- Common tools: " + ", ".join(
                    f"{k} ({v})" for k, v in sp['vietnamese_support']['common_tools'].items()
                ))
            
            # Context handling rules (if available)
            if 'context_handling' in sp:
                if 'relevance' in sp['context_handling']:
                    prompt_parts.append("")
                    prompt_parts.append(f"**Context Rules:** {sp['context_handling']['relevance']}")
            
            return "\n".join(prompt_parts)
        else:
            # Fallback to minimal version of base_system.json
            return f"""{sp['identity']}

**Primary Role:**
{sp.get('primary_role', 'Assist with SOC operations and cybersecurity analysis.')}

**Key Rules:**
- Match user's language (Vietnamese ↔ English)
- Use provided context when available
- Fall back to general cybersecurity knowledge when context is limited"""

    def build_user_input_prompt(self) -> str:
        """
        Build user input template for RAG queries
        
        Returns:
            User input template string with {context} and {query} placeholders
        """
        user_input_path = self.project_root / 'prompts' / 'system' / 'rag_user_input.json'
        
        if user_input_path.exists():
            with open(user_input_path, 'r', encoding='utf-8') as f:
                user_input_config = json.load(f)
                return user_input_config['user_input_template']['template']
        else:
            # Fallback template
            return """Answer the following question. Use CONTEXT if available, otherwise use your general knowledge.

CRITICAL INSTRUCTIONS:
1. **Language Matching**: 
   - Vietnamese question Vietnamese answer
   - English question English answer

2. **When NO context or LIMITED context**:
   - Still answer using your general cybersecurity knowledge
   - For tools like Suricata, pfSense, Wazuh, etc. - explain what they are
   - Be helpful even without specific Cyberfortress documentation

3. **When GOOD context available**:
   - Prioritize context information
   - Cite sources and anonymized tokens

4. **Vietnamese Examples**:
   - "Suricata là gì?" Explain Suricata in Vietnamese (general knowledge OK)
   - "Execution có tactics ID là gì?" Search context for "Execution" tactic
   - "TA0006 là gì?" Search context for TA0006

CONTEXT (may be limited or general):
{context}

QUESTION:
{query}

Provide a clear, helpful answer in the same language as the question. If context is limited, use your general knowledge about cybersecurity tools and concepts."""


# Convenience function for quick usage
def get_system_prompt(include_full_context: bool = False, format: str = 'json') -> str:
    """
    Quick function to get system prompt
    
    Args:
        include_full_context: Include full network JSON docs (True) or quick_reference only (False)
        format: 'json' for structured JSON or 'text' for markdown-style
    
    Returns:
        System prompt string ready for Gemini/OpenAI
    """
    builder = PromptBuilder()
    return builder.build_system_prompt(include_full_context=include_full_context, format=format)


if __name__ == "__main__":
    # Test usage
    builder = PromptBuilder()
    
    # JSON format (recommended for LLMs)
    print("=" * 80)
    print("JSON FORMAT (structured, better for LLM parsing)")
    print("=" * 80)
    json_prompt = builder.build_system_prompt(include_full_context=False, format='json')
    print(f"Length: {len(json_prompt)} chars")
    print(json_prompt[:800] + "...")
    
    print("\n\n")
    
    # Text format (markdown-style)
    print("=" * 80)
    print("TEXT FORMAT (markdown-style)")
    print("=" * 80)
    text_prompt = builder.build_system_prompt(include_full_context=False, format='text')
    print(f"Length: {len(text_prompt)} chars")
    print(text_prompt[:800] + "...")
    
    print("\n\n")
    
    # Full context JSON
    print("=" * 80)
    print("JSON FORMAT WITH FULL CONTEXT")
    print("=" * 80)
    full_json = builder.build_system_prompt(include_full_context=True, format='json')
    print(f"Length: {len(full_json)} chars")
    print(full_json[:800] + "...")
