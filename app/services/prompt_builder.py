"""
Prompt Builder Service for SmartXDR
Loads and constructs system prompts with network context for LLM calls
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class PromptBuilder:
    """Builds prompts for Gemini/OpenAI with optional network context injection"""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize PromptBuilder
        
        Args:
            project_root: Root path of the project. If None, auto-detects from file location
        """
        if project_root is None:
            # Auto-detect: app/services/prompt_builder.py -> go up 2 levels
            self.project_root = Path(__file__).parent.parent.parent
        else:
            self.project_root = Path(project_root)
        
        self._context_cache = {}
        self.base_prompt = self._load_base_prompt()
    
    def _load_base_prompt(self) -> Dict[str, Any]:
        """Load base system prompt from JSON"""
        prompt_path = self.project_root / 'prompts' / 'system' / 'base_system.json'
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
    
    def build_system_prompt(self, include_full_context: bool = False) -> str:
        """
        Build complete system prompt for Gemini/OpenAI
        
        Args:
            include_full_context: If True, includes full JSON network documentation.
                                 If False, only uses quick_reference from base prompt (saves tokens)
        
        Returns:
            Complete system prompt text ready for LLM API call
        """
        sp = self.base_prompt['system_prompt']
        
        # Start with identity and role
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


# Convenience function for quick usage
def get_system_prompt(include_full_context: bool = False) -> str:
    """
    Quick function to get system prompt
    
    Args:
        include_full_context: Include full network JSON docs (True) or quick_reference only (False)
    
    Returns:
        System prompt string ready for Gemini/OpenAI
    """
    builder = PromptBuilder()
    return builder.build_system_prompt(include_full_context=include_full_context)


if __name__ == "__main__":
    # Test usage
    builder = PromptBuilder()
    
    # Compact version (for most cases)
    print("=" * 80)
    print("COMPACT SYSTEM PROMPT (quick_reference only)")
    print("=" * 80)
    compact = builder.build_system_prompt(include_full_context=False)
    print(f"Length: {len(compact)} chars")
    print(compact[:500] + "...")
    
    print("\n\n")
    
    # Full version (when detailed context needed)
    print("=" * 80)
    print("FULL SYSTEM PROMPT (with complete network docs)")
    print("=" * 80)
    full = builder.build_system_prompt(include_full_context=True)
    print(f"Length: {len(full)} chars")
    print(full[:500] + "...")
