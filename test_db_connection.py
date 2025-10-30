#!/usr/bin/env python3
"""
Test database connection and display connection info.
Run this to verify your database is properly configured.
"""
import os
import sys
from pathlib import Path

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ Loaded environment variables from .env")
except ImportError:
    print("⚠ python-dotenv not installed, using system environment variables")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.db_adapter import FleetDatabase
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def test_connection():
    """Test database connection and display info"""
    console.print("\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]          FLEET DATABASE CONNECTION TEST              [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n")
    
    # Display connection settings (without password)
    console.print("[bold yellow]Connection Settings:[/bold yellow]")
    settings_table = Table(show_header=False, box=None, padding=(0, 2))
    settings_table.add_column("Key", style="cyan")
    settings_table.add_column("Value", style="white")
    
    settings_table.add_row("Host", os.getenv('DB_HOST', 'not set'))
    settings_table.add_row("Port", os.getenv('DB_PORT', 'not set'))
    settings_table.add_row("Database", os.getenv('DB_NAME', 'not set'))
    settings_table.add_row("User", os.getenv('DB_USER', 'not set'))
    settings_table.add_row("Password", "***" if os.getenv('DB_PASSWORD') else "not set")
    
    console.print(settings_table)
    console.print()
    
    # Test connection
    console.print("[bold yellow]Testing Connection...[/bold yellow]")
    
    try:
        with FleetDatabase() as db:
            # Health check
            if db.health_check():
                console.print("[bold green]✓ Connection successful![/bold green]\n")
            else:
                console.print("[bold red]✗ Health check failed![/bold red]\n")
                return False
            
            # Get connection info
            info = db.get_connection_info()
            
            if 'error' in info:
                console.print(f"[bold red]Error getting database info: {info['error']}[/bold red]")
                return False
            
            # Display database info
            console.print("[bold yellow]Database Information:[/bold yellow]")
            db_table = Table(show_header=False, box=None, padding=(0, 2))
            db_table.add_column("Key", style="cyan")
            db_table.add_column("Value", style="white")
            
            db_table.add_row("Database", info.get('database', 'N/A'))
            db_table.add_row("User", info.get('user', 'N/A'))
            db_table.add_row("Size", info.get('size', 'N/A'))
            
            console.print(db_table)
            console.print()
            
            # Display table counts
            if 'table_counts' in info:
                console.print("[bold yellow]Table Counts:[/bold yellow]")
                count_table = Table(show_header=True, box=None, padding=(0, 2))
                count_table.add_column("Table", style="cyan")
                count_table.add_column("Rows", style="white", justify="right")
                
                counts = info['table_counts']
                count_table.add_row("locations", str(counts.get('locations', 0)))
                count_table.add_row("location_relations", str(counts.get('location_relations', 0)))
                count_table.add_row("vehicles", str(counts.get('vehicles', 0)))
                count_table.add_row("routes", str(counts.get('routes', 0)))
                count_table.add_row("segments", str(counts.get('segments', 0)))
                count_table.add_row("assignments", str(counts.get('assignments', 0)))
                
                console.print(count_table)
                console.print()
            
            # Display PostgreSQL version (short)
            version = info.get('version', '')
            if version:
                # Extract just the version number
                version_short = version.split('\n')[0][:80]
                console.print(f"[dim]{version_short}[/dim]\n")
            
            console.print("[bold green]═══════════════════════════════════════════════════════[/bold green]")
            console.print("[bold green]          DATABASE CONNECTION SUCCESSFUL!             [/bold green]")
            console.print("[bold green]═══════════════════════════════════════════════════════[/bold green]\n")
            
            return True
            
    except Exception as e:
        console.print(f"\n[bold red]✗ Connection failed![/bold red]")
        console.print(f"[red]Error: {str(e)}[/red]\n")
        
        # Provide helpful troubleshooting
        console.print("[bold yellow]Troubleshooting:[/bold yellow]")
        console.print("  1. Check that PostgreSQL is running")
        console.print("  2. Verify credentials in .env file")
        console.print("  3. Ensure database 'fleet_db' exists")
        console.print("  4. Check firewall/security group settings (for RDS)")
        console.print("  5. Run: pip install psycopg2-binary python-dotenv\n")
        
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

