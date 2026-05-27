"""
🧼 Advanced Data Cleaning Module
This module provides sophisticated data cleaning using multiple mathematical and ML approaches:
- Z-score for extreme value detection
- Interquartile Range (IQR) for robust outlier handling
- Isolation Forest for ML-based anomaly detection
- Linear Regression for predictive cleaning
- K-Nearest Neighbors for predictive cleaning
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.impute import SimpleImputer
import warnings

warnings.filterwarnings('ignore')

class AdvancedDataCleaner:
    """Comprehensive data cleaning system with multiple algorithms"""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.original_df = df.copy()
        self.cleaning_report = {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "actions_taken": [],
            "issues_found": {},
            "data_quality_score": 0.0
        }
        self.numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        self.categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
    
    def detect_missing_values(self) -> dict:
        """Detect and analyze missing values"""
        missing_info = {}
        missing_count = self.df.isnull().sum()
        missing_percent = (missing_count / len(self.df)) * 100
        
        for col in self.df.columns:
            if missing_count[col] > 0:
                missing_info[col] = {
                    "count": int(missing_count[col]),
                    "percentage": float(missing_percent[col])
                }
        
        if missing_info:
            self.cleaning_report["issues_found"]["missing_values"] = missing_info
            self.cleaning_report["actions_taken"].append(
                f"🔍 Found {len(missing_info)} columns with missing values"
            )
        
        return missing_info
    
    def handle_missing_values_knn(self, n_neighbors: int = 5) -> int:
        """Fill missing values using K-Nearest Neighbors (predictive imputation)"""
        imputed_count = 0
        
        for col in self.numeric_cols:
            if self.df[col].isnull().sum() > 0:
                # Create a dataset without missing values for training
                mask = self.df[col].notnull()
                
                if mask.sum() > n_neighbors:
                    # Use other numeric columns to predict missing values
                    X_train = self.df.loc[mask, self.numeric_cols].drop(columns=[col])
                    y_train = self.df.loc[mask, col]
                    
                    if len(X_train.columns) > 0:
                        knn = KNeighborsRegressor(n_neighbors=min(n_neighbors, mask.sum()))
                        knn.fit(X_train, y_train)
                        
                        # Predict missing values
                        X_missing = self.df.loc[~mask, self.numeric_cols].drop(columns=[col])
                        predicted = knn.predict(X_missing)
                        self.df.loc[~mask, col] = predicted
                        
                        imputed_count += (~mask).sum()
        
        if imputed_count > 0:
            self.cleaning_report["actions_taken"].append(
                f"🤖 KNN Imputation: Filled {imputed_count} missing values using K-Nearest Neighbors"
            )
        
        return imputed_count
    
    def handle_missing_values_regression(self) -> int:
        """Fill missing values using Linear Regression (predictive imputation)"""
        imputed_count = 0
        
        for col in self.numeric_cols:
            if self.df[col].isnull().sum() > 0:
                mask = self.df[col].notnull()
                
                if mask.sum() > 2:  # Need at least 2 data points for regression
                    X_train = self.df.loc[mask, self.numeric_cols].drop(columns=[col])
                    y_train = self.df.loc[mask, col]
                    
                    if len(X_train.columns) > 0:
                        lr = LinearRegression()
                        lr.fit(X_train, y_train)
                        
                        X_missing = self.df.loc[~mask, self.numeric_cols].drop(columns=[col])
                        predicted = lr.predict(X_missing)
                        self.df.loc[~mask, col] = predicted
                        
                        imputed_count += (~mask).sum()
        
        if imputed_count > 0:
            self.cleaning_report["actions_taken"].append(
                f"📈 Linear Regression: Filled {imputed_count} missing values using predictive regression"
            )
        
        return imputed_count
    
    def zscore_outlier_detection(self, threshold: float = 3.0) -> dict:
        """Detect extreme values using Z-score method"""
        outliers_info = {}
        
        for col in self.numeric_cols:
            if len(self.df[col].dropna()) > 0:
                z_scores = np.abs((self.df[col] - self.df[col].mean()) / self.df[col].std())
                outlier_mask = z_scores > threshold
                
                if outlier_mask.sum() > 0:
                    outliers_info[col] = {
                        "count": int(outlier_mask.sum()),
                        "percentage": float((outlier_mask.sum() / len(self.df)) * 100),
                        "method": "Z-Score"
                    }
        
        if outliers_info:
            self.cleaning_report["issues_found"]["zscore_outliers"] = outliers_info
        
        return outliers_info
    
    def iqr_outlier_detection(self, iqr_multiplier: float = 1.5) -> dict:
        """Detect outliers using Interquartile Range (IQR) method"""
        outliers_info = {}
        
        for col in self.numeric_cols:
            Q1 = self.df[col].quantile(0.25)
            Q3 = self.df[col].quantile(0.75)
            IQR = Q3 - Q1
            
            lower_bound = Q1 - iqr_multiplier * IQR
            upper_bound = Q3 + iqr_multiplier * IQR
            
            outlier_mask = (self.df[col] < lower_bound) | (self.df[col] > upper_bound)
            
            if outlier_mask.sum() > 0:
                outliers_info[col] = {
                    "count": int(outlier_mask.sum()),
                    "percentage": float((outlier_mask.sum() / len(self.df)) * 100),
                    "lower_bound": float(lower_bound),
                    "upper_bound": float(upper_bound),
                    "method": "IQR"
                }
        
        if outliers_info:
            self.cleaning_report["issues_found"]["iqr_outliers"] = outliers_info
        
        return outliers_info
    
    def isolation_forest_detection(self, contamination: float = 0.05) -> dict:
        """Detect anomalies using Isolation Forest (ML-based)"""
        outliers_info = {}
        
        if len(self.numeric_cols) > 0:
            X = self.df[self.numeric_cols].fillna(self.df[self.numeric_cols].mean())
            
            iso_forest = IsolationForest(contamination=min(contamination, 0.5), random_state=42)
            anomaly_labels = iso_forest.fit_predict(X)
            
            anomaly_mask = anomaly_labels == -1
            
            if anomaly_mask.sum() > 0:
                outliers_info["anomaly_count"] = int(anomaly_mask.sum())
                outliers_info["anomaly_percentage"] = float((anomaly_mask.sum() / len(self.df)) * 100)
                outliers_info["method"] = "Isolation Forest"
                
                # Store anomaly mask for potential removal
                self.df["_is_anomaly"] = anomaly_mask
        
        if outliers_info:
            self.cleaning_report["issues_found"]["isolation_forest_anomalies"] = outliers_info
        
        return outliers_info
    
    def handle_outliers_cap_floor(self, method: str = "iqr") -> int:
        """Handle outliers by capping/flooring them to reasonable bounds"""
        handled_count = 0
        
        for col in self.numeric_cols:
            if method == "iqr":
                Q1 = self.df[col].quantile(0.25)
                Q3 = self.df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
            else:  # z-score method
                mean = self.df[col].mean()
                std = self.df[col].std()
                lower_bound = mean - 3 * std
                upper_bound = mean + 3 * std
            
            # Cap outliers
            before = (self.df[col] < lower_bound) | (self.df[col] > upper_bound)
            self.df[col] = self.df[col].clip(lower=lower_bound, upper=upper_bound)
            after = (self.df[col] < lower_bound) | (self.df[col] > upper_bound)
            
            if before.sum() > 0:
                handled_count += before.sum()
        
        if handled_count > 0:
            self.cleaning_report["actions_taken"].append(
                f"🔧 Outlier Cap/Floor: {handled_count} extreme values capped to reasonable bounds ({method.upper()})"
            )
        
        return handled_count
    
    def remove_duplicates(self) -> int:
        """Remove duplicate rows"""
        before = len(self.df)
        self.df = self.df.drop_duplicates()
        after = len(self.df)
        
        removed = before - after
        if removed > 0:
            self.cleaning_report["actions_taken"].append(
                f"🗑️ Removed {removed} duplicate rows"
            )
        
        return removed
    
    def remove_anomalies(self) -> int:
        """Remove rows identified as anomalies by Isolation Forest"""
        if "_is_anomaly" in self.df.columns:
            before = len(self.df)
            self.df = self.df[~self.df["_is_anomaly"]].drop(columns=["_is_anomaly"])
            after = len(self.df)
            
            removed = before - after
            if removed > 0:
                self.cleaning_report["actions_taken"].append(
                    f"🚨 Removed {removed} anomalous rows detected by Isolation Forest"
                )
            
            return removed
        
        return 0
    
    def standardize_categorical_values(self) -> int:
        """Standardize categorical values"""
        changes = 0
        
        for col in self.categorical_cols:
            if self.df[col].dtype == 'object':
                # Convert to lowercase and strip whitespace
                before = self.df[col].nunique()
                self.df[col] = self.df[col].str.lower().str.strip()
                after = self.df[col].nunique()
                
                if before != after:
                    changes += 1
        
        if changes > 0:
            self.cleaning_report["actions_taken"].append(
                f"🔤 Standardized {changes} categorical columns (lowercase & trimmed)"
            )
        
        return changes
    
    def handle_inconsistent_datatypes(self) -> int:
        """Attempt to convert columns to appropriate data types"""
        changes = 0
        
        for col in self.df.columns:
            if col.startswith("_"):
                continue
            
            try:
                # Try to convert to numeric
                if self.df[col].dtype == 'object':
                    numeric_conversion = pd.to_numeric(self.df[col], errors='coerce')
                    non_null_count = numeric_conversion.notna().sum()
                    
                    if non_null_count / len(self.df) > 0.9:  # If 90% convertible
                        self.df[col] = numeric_conversion
                        changes += 1
            except:
                pass
        
        if changes > 0:
            self.cleaning_report["actions_taken"].append(
                f"📝 Fixed data types in {changes} columns"
            )
        
        return changes
    
    def calculate_data_quality_score(self) -> float:
        """Calculate overall data quality score (0-100)"""
        score = 100.0
        
        # Deduct for missing values
        missing_percent = (self.df.isnull().sum().sum() / (len(self.df) * len(self.df.columns))) * 100
        score -= min(missing_percent, 30)
        
        # Deduct for duplicates (if original had duplicates)
        duplicates = self.original_df.duplicated().sum()
        score -= min((duplicates / len(self.original_df)) * 100, 10)
        
        # Deduct for data type issues
        score -= 5 if len(self.numeric_cols) == 0 and len(self.df.columns) > 0 else 0
        
        # Bonus for completion
        if missing_percent == 0:
            score = min(score + 10, 100)
        
        return max(score, 0)
    
    def generate_quality_report(self) -> str:
        """Generate a comprehensive data quality report"""
        self.cleaning_report["data_quality_score"] = self.calculate_data_quality_score()
        self.cleaning_report["final_rows"] = len(self.df)
        
        report = "\n" + "="*60 + "\n"
        report += "📊 DATA QUALITY REPORT\n"
        report += "="*60 + "\n\n"
        
        report += f"📈 Dataset Size:\n"
        report += f"   • Original: {self.cleaning_report['total_rows']} rows × {self.cleaning_report['total_columns']} columns\n"
        report += f"   • Final: {self.cleaning_report['final_rows']} rows × {len(self.df.columns)} columns\n"
        report += f"   • Rows removed: {self.cleaning_report['total_rows'] - self.cleaning_report['final_rows']}\n\n"
        
        report += f"✨ Data Quality Score: {self.cleaning_report['data_quality_score']:.1f}/100\n\n"
        
        report += "🔧 Cleaning Actions Performed:\n"
        for i, action in enumerate(self.cleaning_report['actions_taken'], 1):
            report += f"   {i}. {action}\n"
        
        if self.cleaning_report["issues_found"]:
            report += "\n🔍 Issues Detected:\n"
            for issue_type, details in self.cleaning_report["issues_found"].items():
                report += f"   • {issue_type}:\n"
                if isinstance(details, dict):
                    for detail_key, detail_val in details.items():
                        if isinstance(detail_val, dict):
                            report += f"     - {detail_key}: {detail_val}\n"
                        else:
                            report += f"     - {detail_key}: {detail_val}\n"
        
        report += "\n" + "="*60 + "\n"
        
        return report
    
    def clean_full_pipeline(self, 
                           handle_missing_method: str = "knn",
                           remove_anomalies: bool = True,
                           cap_outliers: bool = True) -> str:
        """Execute complete cleaning pipeline with all techniques"""
        
        print("🧼 Starting Advanced Data Cleaning Pipeline...\n")
        
        # Step 1: Detect and report issues
        self.detect_missing_values()
        self.zscore_outlier_detection()
        self.iqr_outlier_detection()
        self.isolation_forest_detection()
        
        # Step 2: Clean the data
        self.standardize_categorical_values()
        self.handle_inconsistent_datatypes()
        self.remove_duplicates()
        
        # Step 3: Handle missing values (choose method)
        if handle_missing_method == "knn":
            self.handle_missing_values_knn()
        elif handle_missing_method == "regression":
            self.handle_missing_values_regression()
        else:
            # Fallback to simple imputation
            for col in self.numeric_cols:
                if self.df[col].isnull().sum() > 0:
                    self.df[col].fillna(self.df[col].median(), inplace=True)
            self.cleaning_report["actions_taken"].append(
                "📊 Filled missing values using median imputation"
            )
        
        # Step 4: Handle outliers
        if cap_outliers:
            self.handle_outliers_cap_floor(method="iqr")
        
        if remove_anomalies:
            self.remove_anomalies()
        
        # Step 5: Generate report
        report = self.generate_quality_report()
        print(report)
        
        return report
    
    def get_cleaned_dataframe(self) -> pd.DataFrame:
        """Return the cleaned dataframe"""
        return self.df.copy()


def clean_dataset(file_path: str, cleaning_method: str = "auto") -> tuple:
    """
    Main function to clean a dataset
    
    Args:
        file_path: Path to the CSV file
        cleaning_method: "auto" for full pipeline, or specific method
    
    Returns:
        Tuple of (cleaned_df, report_text)
    """
    try:
        # Read the dataset
        df = pd.read_csv(file_path)
        
        # Initialize cleaner
        cleaner = AdvancedDataCleaner(df)
        
        # Execute cleaning
        report = cleaner.clean_full_pipeline(
            handle_missing_method="knn",
            remove_anomalies=True,
            cap_outliers=True
        )
        
        # Get cleaned data
        cleaned_df = cleaner.get_cleaned_dataframe()
        
        # Save back to the same file
        cleaned_df.to_csv(file_path, index=False)
        print(f"\n✅ Cleaned dataset saved to: {file_path}")
        
        return cleaned_df, report
        
    except Exception as e:
        error_msg = f"❌ Error cleaning dataset: {str(e)}"
        print(error_msg)
        return None, error_msg
