#!/usr/bin/env python3
"""
Utility script to inspect saved debug states from LangGraph runs.

Usage:
    # List all saved states
    python inspect_debug_states.py list

    # List states for a specific repo
    python inspect_debug_states.py list --repo acme_my-api

    # Show full state for a specific file
    python inspect_debug_states.py show debug_states/state_acme_my-api_abc1234_20240315_123456.json

    # Show only specific fields
    python inspect_debug_states.py show debug_states/state_acme_my-api_abc1234_20240315_123456.json --fields skip_generation,overall_confidence

    # Export state to pretty JSON
    python inspect_debug_states.py export debug_states/state_acme_my-api_abc1234_20240315_123456.json output.json
"""

import argparse
import json
import sys
from pathlib import Path
from app.debug_state import list_debug_states, load_debug_state


def cmd_list(args):
    """List available debug states."""
    states = list_debug_states(repo=args.repo, limit=args.limit)
    
    if not states:
        print("No debug states found.")
        return
    
    print(f"Found {len(states)} debug state(s):\n")
    print(f"{'File':<60} {'Repo':<20} {'Commit':<10} {'Timestamp':<20}")
    print("-" * 115)
    
    for state in states:
        filename = Path(state['path']).name
        print(f"{filename:<60} {state['repo']:<20} {state['commit_id']:<10} {state['timestamp']:<20}")


def cmd_show(args):
    """Show contents of a debug state."""
    try:
        data = load_debug_state(args.filepath)
    except FileNotFoundError:
        print(f"Error: File not found: {args.filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file: {args.filepath}")
        sys.exit(1)
    
    print("=" * 80)
    print("METADATA")
    print("=" * 80)
    metadata = data.get('metadata', {})
    for key, value in metadata.items():
        print(f"{key:.<30} {value}")
    
    print("\n" + "=" * 80)
    print("STATE")
    print("=" * 80)
    
    state = data.get('state', {})
    
    if args.fields:
        # Show only specific fields
        fields = [f.strip() for f in args.fields.split(',')]
        for field in fields:
            if field in state:
                print(f"\n{field}:")
                print("-" * 80)
                print(json.dumps(state[field], indent=2))
            else:
                print(f"\n{field}: <not found>")
    else:
        # Show all fields
        for key, value in state.items():
            print(f"\n{key}:")
            print("-" * 80)
            if isinstance(value, (dict, list)):
                print(json.dumps(value, indent=2))
            else:
                print(value)


def cmd_export(args):
    """Export debug state to a new JSON file."""
    try:
        data = load_debug_state(args.filepath)
    except FileNotFoundError:
        print(f"Error: File not found: {args.filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file: {args.filepath}")
        sys.exit(1)
    
    output_path = Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"State exported to: {output_path}")
    print(f"Size: {output_path.stat().st_size} bytes")


def cmd_summary(args):
    """Show a summary of key state fields."""
    try:
        data = load_debug_state(args.filepath)
    except FileNotFoundError:
        print(f"Error: File not found: {args.filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file: {args.filepath}")
        sys.exit(1)
    
    metadata = data.get('metadata', {})
    state = data.get('state', {})
    
    print("=" * 80)
    print("STATE SUMMARY")
    print("=" * 80)
    print(f"Repo:              {metadata.get('repo', 'N/A')}")
    print(f"Commit:            {metadata.get('commit_id', 'N/A')}")
    print(f"Timestamp:         {metadata.get('timestamp', 'N/A')}")
    print()
    
    print("PIPELINE STATUS:")
    print(f"  Skip Generation: {state.get('skip_generation', False)}")
    print(f"  Error:           {state.get('error', None)}")
    print()
    
    print("RESULTS:")
    print(f"  PR Title:        {state.get('pr_title', 'N/A')}")
    print(f"  Confidence:      {state.get('overall_confidence', 'N/A')}")
    print(f"  Files Updated:   {len(state.get('generated_files', []))}")
    print()
    
    if state.get('changed_summaries'):
        print(f"CHANGED FILES ({len(state['changed_summaries'])}):")
        for summary in state['changed_summaries'][:5]:
            print(f"  - {summary.get('file_path', 'unknown')}")
        if len(state['changed_summaries']) > 5:
            print(f"  ... and {len(state['changed_summaries']) - 5} more")
        print()
    
    if state.get('retrieved_context'):
        print(f"RETRIEVED CONTEXT ({len(state['retrieved_context'])}):")
        for ctx in state['retrieved_context'][:5]:
            score = ctx.get('score', 0)
            print(f"  - {ctx.get('file_path', 'unknown')} (score: {score:.3f})")
        if len(state['retrieved_context']) > 5:
            print(f"  ... and {len(state['retrieved_context']) - 5} more")
        print()
    
    if state.get('impact_result'):
        impact = state['impact_result']
        print("IMPACT ANALYSIS:")
        print(f"  Labels:          {', '.join(impact.get('labels', []))}")
        print(f"  Relevance:       {impact.get('relevance_score', 0)}")
        print(f"  Reasoning:       {impact.get('reasoning', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(
        description='Inspect LangGraph debug states',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available debug states')
    list_parser.add_argument('--repo', help='Filter by repo name (e.g., acme_my-api)')
    list_parser.add_argument('--limit', type=int, default=10, help='Maximum number of states to show')
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Show full state contents')
    show_parser.add_argument('filepath', help='Path to state file')
    show_parser.add_argument('--fields', help='Comma-separated list of fields to show (e.g., skip_generation,pr_title)')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export state to new file')
    export_parser.add_argument('filepath', help='Path to state file')
    export_parser.add_argument('output', help='Output file path')
    
    # Summary command
    summary_parser = subparsers.add_parser('summary', help='Show state summary')
    summary_parser.add_argument('filepath', help='Path to state file')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'list':
        cmd_list(args)
    elif args.command == 'show':
        cmd_show(args)
    elif args.command == 'export':
        cmd_export(args)
    elif args.command == 'summary':
        cmd_summary(args)


if __name__ == '__main__':
    main()
