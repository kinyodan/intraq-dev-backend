#!/usr/bin/env python3
"""
Test script for DFE Automation Service

Usage:
    python run_dfe_test.py --client-id CLIENT_ID --file /path/to/file.csv
    python run_dfe_test.py --client-id CLIENT_ID  # Process all files for client
    python run_dfe_test.py --test-only  # Test imports without running
"""

import sys
import os
import argparse

# Add parent path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from services.dfe_automation_service import dfe_service, DFEAutomationService
        print("✅ DFE service imported successfully")
    except Exception as e:
        print(f"❌ Failed to import DFE service: {e}")
        return False
    
    try:
        # Check if DFE modules are available
        if dfe_service.dfe_modules:
            print(f"✅ DFE modules loaded: {list(dfe_service.dfe_modules.keys())}")
        else:
            print("⚠️ DFE automation modules not available (expected if ~/dev/dfe doesn't exist)")
    except Exception as e:
        print(f"⚠️ Could not check DFE modules: {e}")
    
    print("\n✅ All imports successful!")
    return True


def test_pipeline(input_file: str, split_by: str = "caw"):
    """Test running the pipeline on a file"""
    from services.dfe_automation_service import dfe_service
    
    print(f"\n🚀 Testing pipeline on: {input_file}")
    print(f"   Split by: {split_by}")
    print("=" * 60)
    
    try:
        result = dfe_service.process_file_pipeline(
            input_file=input_file,
            split_by=split_by
        )
        
        print("\n✅ Pipeline completed!")
        print(f"   Status: {result['status']}")
        print(f"   Cleaned: {result.get('cleaned')}")
        print(f"   Normalized: {result.get('normalized')}")
        print(f"   Split files: {len(result.get('split_files', []))}")
        
        for f in result.get('split_files', [])[:5]:  # Show first 5
            print(f"      - {f}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_automation(client_id: str, input_file: str = None):
    """Test running automation for a client"""
    from services.dfe_automation_service import dfe_service
    
    print(f"\n🚀 Testing automation for client: {client_id}")
    if input_file:
        print(f"   File: {input_file}")
    print("=" * 60)
    
    try:
        result = dfe_service.run_automation_for_client(
            client_id=client_id,
            user_id="test_user",
            input_file=input_file
        )
        
        print("\n✅ Automation completed!")
        print(f"   Job ID: {result.get('job_id')}")
        print(f"   Status: {result['status']}")
        print(f"   Files processed: {len(result.get('files_processed', []))}")
        
        if result.get('errors'):
            print(f"   Errors: {len(result['errors'])}")
            for err in result['errors']:
                print(f"      - {err}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Automation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Test DFE Automation Service")
    parser.add_argument("--test-only", action="store_true", help="Only test imports")
    parser.add_argument("--client-id", help="Client ID for testing")
    parser.add_argument("--file", help="Input file path")
    parser.add_argument("--split-by", default="caw", choices=["caw", "center", "constituency", "rows"])
    parser.add_argument("--pipeline-only", action="store_true", help="Only run pipeline, not full automation")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DFE Automation Service Test")
    print("=" * 60)
    
    # Test imports first
    if not test_imports():
        sys.exit(1)
    
    if args.test_only:
        print("\n✅ Import test completed!")
        return
    
    # Validate required args
    if not args.client_id:
        print("\n❌ --client-id is required (unless using --test-only)")
        parser.print_help()
        sys.exit(1)
    
    # Run tests
    if args.pipeline_only and args.file:
        # Test pipeline only
        success = test_pipeline(args.file, args.split_by)
    else:
        # Test full automation
        success = test_automation(args.client_id, args.file)
    
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
