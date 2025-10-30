#!/usr/bin/env python3
"""
Quick test script for the Fleet Optimization API endpoints.
"""
import requests
import sys
from pathlib import Path


def test_endpoints():
    """Test both API endpoints"""
    base_url = "http://localhost:8000"
    
    print("🧪 Testing Fleet Optimization API\n")
    
    # Check if API is running
    try:
        response = requests.get(base_url, timeout=5)
        if response.status_code == 200:
            print("✅ API is running")
            print(f"   Response: {response.json()}\n")
        else:
            print(f"❌ API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is it running?")
        print("   Run: python src/endpoints.py")
        return False
    
    # Prepare file paths
    data_dir = Path("data")
    config_file = Path("algorithm_config.json")
    
    if not data_dir.exists():
        print(f"❌ Data directory not found: {data_dir}")
        return False
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        return False
    
    # Open files
    files = {
        'locations': open(data_dir / 'locations.csv', 'rb'),
        'locations_relations': open(data_dir / 'locations_relations.csv', 'rb'),
        'routes': open(data_dir / 'routes.csv', 'rb'),
        'segments': open(data_dir / 'segments.csv', 'rb'),
        'vehicles': open(data_dir / 'vehicles.csv', 'rb'),
        'config': open(config_file, 'rb'),
    }
    
    try:
        # Test 1: Validate endpoint
        print("=" * 80)
        print("TEST 1: /upload/validate")
        print("=" * 80 + "\n")
        
        response = requests.post(f"{base_url}/upload/validate", files={
            k: v for k, v in files.items()
        })
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Validation endpoint successful")
            print(f"   Status: {result['status']}")
            print(f"   Files validated: {result['files_validated']}")
            print(f"   Files failed: {result['files_failed']}")
            
            # Show validation results
            for file_type, details in result['validation_results'].items():
                status_icon = "✅" if details['status'] == 'valid' else "❌"
                print(f"   {status_icon} {file_type}: {details['status']}")
                if details['status'] != 'valid':
                    print(f"      Error: {details.get('error', 'Unknown')}")
        else:
            print(f"❌ Validation failed with status {response.status_code}")
            print(f"   Response: {response.text}")
        
        print("\n")
        
        # Rewind files for second request
        for f in files.values():
            f.seek(0)
        
        # Test 2: Process endpoint
        print("=" * 80)
        print("TEST 2: /upload/process")
        print("=" * 80 + "\n")
        
        response = requests.post(f"{base_url}/upload/process", files={
            k: v for k, v in files.items()
        })
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Process endpoint successful")
            print(f"   Status: {result['status']}")
            print(f"   Ready for optimization: {result['ready_for_optimization']}")
            print(f"   Timestamp: {result['timestamp']}")
            
            # Show file processing results
            for file_type, details in result['files_processed'].items():
                status_icon = "✅" if details['status'] == 'loaded' else "❌"
                status_text = details['status']
                
                if details['status'] == 'loaded' and 'total_rows' in details:
                    status_text = f"{details['status']} ({details['total_rows']} rows)"
                
                print(f"   {status_icon} {file_type}: {status_text}")
        else:
            print(f"❌ Process failed with status {response.status_code}")
            print(f"   Response: {response.text}")
        
        print("\n")
        print("=" * 80)
        print("🎉 All tests completed!")
        print("=" * 80)
        
    finally:
        # Close all files
        for f in files.values():
            f.close()
    
    return True


if __name__ == "__main__":
    success = test_endpoints()
    sys.exit(0 if success else 1)

