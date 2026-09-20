"""Example script demonstrating the encounters API.

Shows how to create, update, query, and complete encounters.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tracking import encounters, encounter_patterns


def demo_create_and_update():
    """Demo: create an encounter and add transcript messages."""
    print("=" * 60)
    print("DEMO: Create and update encounter")
    print("=" * 60)
    
    # Create a new encounter
    enc_id = encounters.create_encounter(status="located")
    if not enc_id:
        print("ERROR: Failed to create encounter (MongoDB not connected?)")
        return None
    
    print(f"✓ Created encounter: {enc_id}")
    
    # Add some transcript messages
    encounters.add_transcript_message(enc_id, "person", "Can anyone hear me?")
    encounters.add_transcript_message(enc_id, "driver", "Yes, we can hear you. What's your location?")
    encounters.add_transcript_message(enc_id, "person", "I'm in the basement, near the boiler room.")
    encounters.add_transcript_message(enc_id, "rover", "Thermal signature detected. Moving to location.")
    
    print(f"✓ Added 4 transcript messages")
    
    # Get the encounter back
    enc = encounters.get_encounter(enc_id)
    if enc:
        print(f"✓ Retrieved encounter: {len(enc['transcript'])} messages")
        for msg in enc['transcript'][:2]:
            print(f"    [{msg['speaker']}] {msg['text']}")
    
    return enc_id


def demo_complete_encounter(enc_id):
    """Demo: complete an encounter."""
    if not enc_id:
        return
    
    print("\n" + "=" * 60)
    print("DEMO: Complete encounter")
    print("=" * 60)
    
    success = encounters.complete_encounter(
        enc_id, 
        status="rescued",
        survivor_count=1,
        notes="Basement rescue successful"
    )
    
    if success:
        print(f"✓ Completed encounter {enc_id}: rescued")
        enc = encounters.get_encounter(enc_id)
        if enc:
            print(f"    Duration: {enc['duration_seconds']:.0f} seconds")
            print(f"    Survivors: {enc['survivor_count']}")
    else:
        print(f"✗ Failed to complete encounter")


def demo_list_encounters():
    """Demo: list recent encounters."""
    print("\n" + "=" * 60)
    print("DEMO: List encounters")
    print("=" * 60)
    
    all_encounters = encounters.list_encounters(limit=5)
    print(f"Recent encounters: {len(all_encounters)}")
    
    for enc in all_encounters[:3]:
        duration = f"{enc['duration_seconds']:.0f}s" if enc.get('duration_seconds') else "active"
        print(f"  {enc['encounter_id']}: {enc['status']} ({duration}), {len(enc['transcript'])} messages")
    
    # Filter by status
    rescued = encounters.list_encounters(status="rescued", limit=10)
    print(f"\nRescued encounters: {len(rescued)}")


def demo_stats_and_patterns():
    """Demo: get statistics and patterns."""
    print("\n" + "=" * 60)
    print("DEMO: Statistics and patterns")
    print("=" * 60)
    
    stats = encounters.get_encounter_stats()
    if stats.get("connected"):
        print(f"Total encounters: {stats['total']}")
        print(f"By status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")
        if stats.get('active_encounter_id'):
            print(f"Active encounter: {stats['active_encounter_id']}")
    
    # Compute patterns
    print("\nComputing patterns...")
    patterns = encounter_patterns.get_patterns(force_recompute=True)
    
    if patterns:
        print(f"✓ Analyzed {patterns['total_encounters']} encounters")
        if patterns.get('duration_stats'):
            ds = patterns['duration_stats']
            print(f"  Avg duration: {ds['avg_minutes']:.1f} minutes")
            print(f"  Range: {ds['min_minutes']:.1f} - {ds['max_minutes']:.1f} minutes")
        
        if patterns.get('insights'):
            print("  Insights:")
            for insight in patterns['insights']:
                print(f"    - {insight['value']}")


def main():
    print("\nEncounters API Demo")
    print("=" * 60)
    print("MongoDB connection required (set MONGODB_URI in .env)")
    print()
    
    # Check if there are existing encounters
    existing = encounters.list_encounters(limit=1)
    if not existing:
        print("No encounters found. Run 'python tracking/migrate_historical.py' first")
        print("to import historical encounters.\n")
    
    # Demo workflow
    enc_id = demo_create_and_update()
    demo_complete_encounter(enc_id)
    demo_list_encounters()
    demo_stats_and_patterns()
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
