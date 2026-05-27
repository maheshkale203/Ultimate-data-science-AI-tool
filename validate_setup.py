""" DataFlow Visualization Setup Validator.
This script checks if your Superset visualization setup is correctly configured.
Run it after installation to verify everything is working.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' module not found. Install it with: pip install requests")
    sys.exit(1)

class SetupValidator:
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []
    
    # Check if Docker is installed
    
    def check_docker_installed(self):
        
        print("\n📦 Checking Docker installation...")
        try:
            result = subprocess.run(['docker', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"   ✅ Docker installed: {version}")
                self.checks_passed += 1
                return True
            else:
                print("   ❌ Docker not found")
                self.checks_failed += 1
                return False
        except Exception as e:
            print(f"   ❌ Error checking Docker: {str(e)}")
            self.checks_failed += 1
            return False
    
    # Check if Docker Compose is installed
    
    def check_docker_compose_installed(self):

        

        print("\n📦 Checking Docker Compose installation...")
        try:
            result = subprocess.run(['docker-compose', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"   ✅ Docker Compose installed: {version}")
                self.checks_passed += 1
                return True
            else:
                print("   ❌ Docker Compose not found")
                self.checks_failed += 1
                return False
        except Exception as e:
            print(f"   ❌ Error checking Docker Compose: {str(e)}")
            self.checks_failed += 1
            return False
    
    #Check if required files exist

    def check_files_exist(self):
        
        print("\n📁 Checking required files...")
        
        required_files = [
            ('docker-compose.yml', 'Docker Compose config'),
            ('backend/superset_integration.py', 'Superset integration module'),
            ('backend/main.py', 'FastAPI backend'),
            ('SUPERSET_GUIDE.md', 'Superset guide'),
            ('VISUALIZATION_QUICK_START.md', 'Visualization guide')
        ]
        
        for file_path, description in required_files:
            if os.path.exists(file_path):
                print(f"   ✅ {description}: {file_path}")
                self.checks_passed += 1
            else:
                print(f"   ❌ {description} not found: {file_path}")
                self.checks_failed += 1
    
    #  Check if Docker containers are running
    
    def check_docker_containers_running(self):
       
        print("\n🐳 Checking Docker containers...")
        try:
            result = subprocess.run(['docker-compose', 'ps'], 
                                  capture_output=True, text=True)
            
            if 'superset_app' in result.stdout and 'Up' in result.stdout:
                print("   ✅ Superset container is running")
                self.checks_passed += 1
                return True
            else:
                print("   ⚠️ Superset container not running")
                self.warnings.append("Start with: docker-compose up -d")
                return False
        except Exception as e:
            print(f"   ⚠️ Could not check containers: {str(e)}")
            return False
    
    #  Check if Superset is accessible

    def check_superset_accessible(self):
        
        print("\n🌐 Checking Superset accessibility...")
        try:
            response = requests.get('http://localhost:8088/api/v1/health', timeout=5)
            if response.status_code == 200:
                print("   ✅ Superset is accessible at http://localhost:8088")
                self.checks_passed += 1
                return True
            else:
                print(f"   ⚠️ Superset returned status {response.status_code}")
                self.warnings.append("Superset may still be initializing")
                return False
        except requests.exceptions.ConnectionError:
            print("   ❌ Cannot connect to Superset")
            print("      Solution: docker-compose up -d")
            self.checks_failed += 1
            return False
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            self.checks_failed += 1
            return False
    
    #  Check if DataFlow API has visualization endpoints

    def check_dataflow_api(self):
        
        print("\n🔗 Checking DataFlow API endpoints...")
        try:
            response = requests.get('http://127.0.0.1:8000/visualization/status', timeout=5)
            if response.status_code == 200:
                print("   ✅ DataFlow visualization endpoints are available")
                self.checks_passed += 1
                return True
            else:
                print(f"   ⚠️ DataFlow returned status {response.status_code}")
                self.warnings.append("Make sure DataFlow backend is running: python backend/main.py")
                return False
        except requests.exceptions.ConnectionError:
            print("   ❌ Cannot connect to DataFlow API")
            print("      Solution: python backend/main.py")
            self.checks_failed += 1
            return False
        except Exception as e:
            print(f"   ⚠️ Error: {str(e)}")
            return False
    
    # Check if uploads folder exists

    def check_uploads_folder(self):
        
        print("\n📁 Checking uploads folder...")
        if os.path.exists('uploads'):
            print("   ✅ Uploads folder exists")
            self.checks_passed += 1
            return True
        else:
            print("   ❌ Uploads folder not found")
            os.makedirs('uploads', exist_ok=True)
            print("   ✅ Created uploads folder")
            self.checks_passed += 1
            return True
    
    # Run all validation checks
    
    def run_all_checks(self):
        
        print("\n" + "="*60)
        print("🔍 DataFlow Visualization Setup Validator")
        print("="*60)
        
        # File checks (can run anytime)
        self.check_files_exist()
        self.check_uploads_folder()
        
        # Docker checks
        self.check_docker_installed()
        self.check_docker_compose_installed()
        
        # Running service checks
        self.check_docker_containers_running()
        self.check_superset_accessible()
        self.check_dataflow_api()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        
        print("\n" + "="*60)
        print("📊 Validation Summary")
        print("="*60)
        
        print(f"\n✅ Passed: {self.checks_passed}")
        print(f"❌ Failed: {self.checks_failed}")
        
        if self.warnings:
            print(f"\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        # Determine overall status
        if self.checks_failed == 0:
            print("\n🎉 All checks passed! Your setup is ready.")
            print("\nNext steps:")
            print("1. Open http://localhost:8088 in your browser")
            print("2. Login with: admin / admin123")
            print("3. Clean a dataset using DataFlow")
            print("4. Register it for visualization")
            print("5. Create interactive dashboards!")
            return True
        else:
            print(f"\n⚠️  Please fix the {self.checks_failed} failed check(s) above.")
            print("\nCommon solutions:")
            print("• Docker: Install from https://www.docker.com/products/docker-desktop")
            print("• Superset: docker-compose up -d")
            print("• DataFlow: python backend/main.py")
            return False

def main():
    """Main entry point"""
    validator = SetupValidator()
    
    try:
        success = validator.run_all_checks()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Validation failed with error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
