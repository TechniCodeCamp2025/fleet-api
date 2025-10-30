#!/usr/bin/env python3
"""
Test script for the new /csv/upload endpoint.

Usage:
    python test_csv_upload.py <csv_file_path>

Example:
    python test_csv_upload.py data/locations.csv
    python test_csv_upload.py data/vehicles.csv
"""
import sys
import requests
from pathlib import Path


def upload_csv(file_path: str, api_url: str = "http://localhost:8000"):
    """
    Upload a single CSV file to the /csv/upload endpoint.
    
    Args:
        file_path: Path to the CSV file
        api_url: Base URL of the API (default: http://localhost:8000)
    """
    endpoint = f"{api_url}/csv/upload"
    
    # Check if file exists
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"❌ Error: File not found: {file_path}")
        return
    
    # Prepare file for upload
    with open(file_path_obj, 'rb') as f:
        files = {'file': (file_path_obj.name, f, 'text/csv')}
        
        print(f"📤 Uploading {file_path_obj.name}...")
        print(f"   Endpoint: {endpoint}")
        
        try:
            response = requests.post(endpoint, files=files)
            
            # Print response
            print(f"\n{'='*80}")
            print(f"Response Status: {response.status_code}")
            print('='*80)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success!")
                print(f"   Detected Type: {result.get('detected_type')}")
                print(f"   Rows Imported: {result.get('rows_imported')}")
                print(f"   Filename: {result.get('filename')}")
            else:
                print(f"❌ Error: {response.status_code}")
                print(f"   {response.text}")
            
            print('='*80 + "\n")
            
        except requests.exceptions.ConnectionError:
            print(f"❌ Error: Could not connect to API at {api_url}")
            print(f"   Make sure the API server is running (python src/endpoints.py)")
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_csv_upload.py <csv_file_path>")
        print("\nExamples:")
        print("  python test_csv_upload.py data/locations.csv")
        print("  python test_csv_upload.py data/vehicles.csv")
        print("  python test_csv_upload.py data/routes.csv")
        print("  python test_csv_upload.py data/segments.csv")
        print("  python test_csv_upload.py data/locations_relations.csv")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    api_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
    
    upload_csv(csv_file, api_url)


if __name__ == "__main__":
    main()

