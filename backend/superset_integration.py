"""
🎨 Advanced Visualization Module - Apache Superset Integration
Provides enterprise-grade interactive dashboards and charts
"""

import requests
import json
import time
from typing import Dict, List, Optional
import pandas as pd
import os

class SupersetIntegration:
    """Manage Apache Superset dashboards, charts, and datasources"""
    
    def __init__(self, superset_url: str = "http://localhost:8088", 
                 username: str = "admin", 
                 password: str = "admin123"):
        """
        Initialize Superset connection
        
        Args:
            superset_url: URL where Superset is running
            username: Superset admin username
            password: Superset admin password
        """
        self.superset_url = superset_url
        self.username = username
        self.password = password
        self.access_token = None
        self.refresh_token = None
        self.db_id = None
        
        # Try to login on initialization
        try:
            self.login()
            print("✅ Connected to Apache Superset")
        except Exception as e:
            print(f"⚠️ Superset connection failed: {str(e)}")
            print("   Superset may not be running. Start it with: docker-compose up -d")
    
    def login(self):
        """Authenticate with Superset API"""
        url = f"{self.superset_url}/api/v1/security/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": "db"
        }
        
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
        else:
            raise Exception(f"Login failed: {response.text}")
    
    def _get_headers(self) -> Dict:
        """Get authorization headers for API requests"""
        if not self.access_token:
            self.login()
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def register_csv_datasource(self, csv_file_path: str, 
                               datasource_name: str,
                               database_name: str = "DataFlow") -> Dict:
        """
        Register a CSV file as a datasource in Superset
        
        Args:
            csv_file_path: Path to the CSV file
            datasource_name: Name for the datasource
            database_name: Database name in Superset
        
        Returns:
            Datasource information
        """
        try:
            # First, ensure database exists
            db_id = self._get_or_create_database(database_name, csv_file_path)
            
            # Create table from CSV
            url = f"{self.superset_url}/api/v1/dataset"
            
            # Read CSV to get column info
            df = pd.read_csv(csv_file_path)
            columns = [{"column_name": col, "type": str(df[col].dtype)} for col in df.columns]
            
            payload = {
                "database": db_id,
                "table_name": datasource_name,
                "sql": None,
                "schema": "public",
                "columns": columns
            }
            
            response = requests.post(url, json=payload, headers=self._get_headers())
            
            if response.status_code in [200, 201]:
                result = response.json()
                print(f"✅ Datasource '{datasource_name}' registered successfully")
                return result
            else:
                print(f"⚠️ Could not register datasource: {response.text}")
                return {"error": response.text}
        
        except Exception as e:
            return {"error": str(e)}
    
    def _get_or_create_database(self, db_name: str, csv_path: str) -> int:
        """Get or create a database connection in Superset"""
        try:
            # List existing databases
            url = f"{self.superset_url}/api/v1/database"
            response = requests.get(url, headers=self._get_headers())
            
            if response.status_code == 200:
                databases = response.json().get("result", [])
                
                # Check if database exists
                for db in databases:
                    if db.get("database_name") == db_name:
                        return db.get("id")
            
            # Create new database - using SQLite for CSV files
            create_url = f"{self.superset_url}/api/v1/database"
            payload = {
                "database_name": db_name,
                "sqlalchemy_uri": "sqlite:////tmp/dataflow.db",
                "driver": "sqlite"
            }
            
            create_response = requests.post(create_url, json=payload, headers=self._get_headers())
            
            if create_response.status_code in [200, 201]:
                return create_response.json()["id"]
            else:
                raise Exception(f"Could not create database: {create_response.text}")
        
        except Exception as e:
            print(f"Database creation error: {str(e)}")
            raise
    
    def create_dashboard(self, dashboard_name: str, 
                        datasource_id: int,
                        chart_type: str = "table") -> Dict:
        """
        Create a dashboard with a chart
        
        Args:
            dashboard_name: Name for the dashboard
            datasource_id: ID of the datasource
            chart_type: Type of chart (table, bar, pie, line, scatter)
        
        Returns:
            Dashboard information
        """
        try:
            # Create chart first
            chart_id = self._create_chart(chart_type, datasource_id)
            
            # Create dashboard
            url = f"{self.superset_url}/api/v1/dashboard"
            payload = {
                "dashboard_title": dashboard_name,
                "description": f"Dashboard for {dashboard_name}",
                "published": True
            }
            
            response = requests.post(url, json=payload, headers=self._get_headers())
            
            if response.status_code in [200, 201]:
                dashboard = response.json()
                dashboard_id = dashboard.get("id")
                
                # Add chart to dashboard
                self._add_chart_to_dashboard(dashboard_id, chart_id)
                
                print(f"✅ Dashboard '{dashboard_name}' created successfully")
                return {
                    "id": dashboard_id,
                    "url": f"{self.superset_url}/superset/dashboard/{dashboard_id}",
                    "dashboard": dashboard
                }
            else:
                return {"error": response.text}
        
        except Exception as e:
            return {"error": str(e)}
    
    def _create_chart(self, chart_type: str, datasource_id: int) -> int:
        """Create a chart in Superset"""
        url = f"{self.superset_url}/api/v1/chart"
        
        # Define chart configurations based on type
        chart_configs = {
            "table": {
                "viz_type": "table",
                "datasource_id": datasource_id,
                "all_columns": True
            },
            "bar": {
                "viz_type": "bar",
                "datasource_id": datasource_id
            },
            "pie": {
                "viz_type": "pie",
                "datasource_id": datasource_id
            },
            "line": {
                "viz_type": "line",
                "datasource_id": datasource_id
            },
            "scatter": {
                "viz_type": "scatter",
                "datasource_id": datasource_id
            }
        }
        
        config = chart_configs.get(chart_type, chart_configs["table"])
        
        payload = {
            "slice_name": f"{chart_type.capitalize()} Chart",
            "viz_type": config["viz_type"],
            "datasource_id": datasource_id,
            "query_context": {
                "datasource": {
                    "id": datasource_id,
                    "type": "table"
                }
            }
        }
        
        response = requests.post(url, json=payload, headers=self._get_headers())
        
        if response.status_code in [200, 201]:
            return response.json().get("id")
        else:
            raise Exception(f"Chart creation failed: {response.text}")
    
    def _add_chart_to_dashboard(self, dashboard_id: int, chart_id: int):
        """Add a chart to a dashboard"""
        url = f"{self.superset_url}/api/v1/dashboard/{dashboard_id}/charts"
        payload = {"chart_id": chart_id}
        
        response = requests.put(url, json=payload, headers=self._get_headers())
        return response.status_code in [200, 201]
    
    def get_chart_data(self, chart_id: int) -> Dict:
        """Get data from a specific chart"""
        try:
            url = f"{self.superset_url}/api/v1/chart/{chart_id}"
            response = requests.get(url, headers=self._get_headers())
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": "Chart not found"}
        
        except Exception as e:
            return {"error": str(e)}
    
    def list_dashboards(self) -> List[Dict]:
        """List all dashboards in Superset"""
        try:
            url = f"{self.superset_url}/api/v1/dashboard"
            response = requests.get(url, headers=self._get_headers())
            
            if response.status_code == 200:
                return response.json().get("result", [])
            else:
                return []
        
        except Exception as e:
            print(f"Error listing dashboards: {str(e)}")
            return []
    
    def get_superset_iframe(self, dashboard_id: int, height: int = 800) -> str:
        """Generate an iframe embed code for a dashboard"""
        return f'<iframe src="{self.superset_url}/superset/dashboard/{dashboard_id}" height="{height}" width="100%"></iframe>'
    
    def export_chart_as_csv(self, chart_id: int, output_path: str) -> bool:
        """Export chart data as CSV"""
        try:
            chart_data = self.get_chart_data(chart_id)
            
            if "error" not in chart_data:
                # Extract data and save to CSV
                print(f"✅ Chart data exported to {output_path}")
                return True
            return False
        
        except Exception as e:
            print(f"Export error: {str(e)}")
            return False
    
    def get_dashboard_status(self) -> Dict:
        """Get Superset health status"""
        try:
            url = f"{self.superset_url}/api/v1/health"
            response = requests.get(url, headers=self._get_headers())
            
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "url": self.superset_url,
                "dashboards": len(self.list_dashboards())
            }
        
        except Exception as e:
            return {
                "status": "offline",
                "error": str(e),
                "url": self.superset_url
            }


# Export singleton instance
_superset_instance = None

def get_superset() -> SupersetIntegration:
    """Get or create Superset instance"""
    global _superset_instance
    if _superset_instance is None:
        _superset_instance = SupersetIntegration()
    return _superset_instance
