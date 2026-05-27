from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
import uvicorn
import io
import contextlib
import traceback
import models
import time
import os
import shutil
from database import engine, get_db
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from fastapi.responses import FileResponse
from data_cleaner import AdvancedDataCleaner, clean_dataset
from superset_integration import get_superset
import pandas as pd
import re
from prophet import Prophet
import uuid
from dotenv import load_dotenv

# Create a folder to store datasets!
os.makedirs("uploads", exist_ok=True)

# 1. Automatically build the tables in your Neon Database!
print("🔄 Connecting to Neon and verifying tables...")

models.Base.metadata.create_all(bind=engine)
print("✅ Database tables are ready!")

app = FastAPI(title="AI Backend API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# ==========================================
# 🧠 THE AI BRAIN (GROQ & LLaMA 3.3)
# ==========================================

# Initialize Groq client
load_dotenv()

# 2. Grab the key securely
groq_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=groq_key)
# ==========================================
# 💪 ENHANCED INSTRUCTION PARSER
# ==========================================

def extract_null_fill_values(prompt: str) -> dict:
    """
    Extract exact null-fill values from user instructions.
    Examples:
    - "fill null values as 125.99, 459.99, 4586.99" → {"values": [125.99, 459.99, 4586.99], "strategy": "exact"}
    - "fill missing with 99.5" → {"values": [99.5], "strategy": "single"}
    - "fill column Age as 30 and Salary as 50000" → {"columns": {"Age": 30, "Salary": 50000}, "strategy": "column_specific"}
    """
    result = {"values": [], "column_mappings": {}, "strategy": None, "raw_instruction": prompt}
    
    # Pattern 1: Direct list of values (most common)

    pattern1 = r"fill\s+(?:the\s+)?(?:null|missing)\s+(?:values?\s+)?(?:in\s+[A-Za-z_][A-Za-z0-9_]*\s+column\s+)?(?:as|with)\s*([-\d.,\s]+)(?:\s+or\s+|$|\.|\s+and\s+|\s+using\s+|\s+for)"
    match1 = re.search(pattern1, prompt, re.IGNORECASE)
    if match1:
        values_str = match1.group(1).strip()
        try:
            values = [float(v.strip()) for v in values_str.split(",") if v.strip()]
            if values:
                result["values"] = values
                result["strategy"] = "exact_list"
                print(f"✅ Extracted exact null-fill values: {values}")
                return result
        except ValueError:
            pass
    
    # Pattern 2: Column-specific mappings
    
    pattern2 = r"fill\s+(?:column\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:as|=|with)\s*([-\d.]+)(?:\s+and|,)?(?:\s+(?:column\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:as|=|with)\s*([-\d.]+))?"
    matches2 = re.finditer(pattern2, prompt, re.IGNORECASE)
    column_mappings = {}
    for match in matches2:
        col1, val1 = match.group(1).strip(), match.group(2).strip()
        try:
            column_mappings[col1] = float(val1)
        except ValueError:
            pass
        if match.group(3):
            col2, val2 = match.group(3).strip(), match.group(4).strip()
            try:
                column_mappings[col2] = float(val2)
            except ValueError:
                pass
    
    if column_mappings:
        result["column_mappings"] = column_mappings
        result["strategy"] = "column_specific"
        print(f"✅ Extracted column-specific null-fill mappings: {column_mappings}")
        return result
    
    # Pattern 3: Single value fill

    pattern3 = r"fill\s+(?:null|missing|nan|na)\s+(?:with|using)\s*([-\d.]+)"
    match3 = re.search(pattern3, prompt, re.IGNORECASE)
    if match3:
        try:
            value = float(match3.group(1).strip())
            result["values"] = [value]
            result["strategy"] = "single_value"
            print(f"✅ Extracted single null-fill value: {value}")
            return result
        except ValueError:
            pass
    
    return result

def validate_code_uses_exact_values(code: str, required_values: list, column_mappings: dict = None) -> tuple[bool, str]:
    """
    Validate that generated code uses the EXACT null-fill values specified.
    Returns (is_valid, validation_message)
    """
    if not required_values and not column_mappings:
        return True, "No specific values to validate"
    
    # Check if required values appear in code as literals
    for val in required_values:
        
        if f"{val}" in code or f"{int(val)}" in code:
            continue
        else:
            return False, f"Code does NOT use exact value {val}. Generated code must include this literal value."
    
    # Check column-specific mappings
    if column_mappings:
        for col, val in column_mappings.items():
            col_pattern = f"\\[{re.escape(col)}\\].*?=.*?{re.escape(val)}"
            if not re.search(col_pattern, code, re.IGNORECASE):
                
                if f"{col}" not in code or f"{val}" not in code:
                    return False, f"Code does NOT correctly fill column '{col}' with value {val}."
    
    return True, "✅ Code uses exact specified values!"

def is_visualization_requested(prompt: str) -> bool:
    visualization_terms = [
        "chart", "graph", "plot", "pie", "bar", "line", "scatter", "histogram", "visualization", "visualise", "visualize", "trend"
    ]
    return any(re.search(rf"\b{term}\b", prompt, re.IGNORECASE) for term in visualization_terms)


def contains_plot_code(code: str) -> bool:
    plot_terms = ["matplotlib", "plt.", "seaborn", "sns.", "plt.savefig", "figure(", "plot(", "bar(", "pie(", "scatter(", "histplot", "histogram"]
    return any(term in code.lower() for term in plot_terms)


def real_ai_generate_code(prompt: str, extracted_values: dict = None, retry_count: int = 0) -> str:
    
    if extracted_values is None:
        extracted_values = extract_null_fill_values(prompt)
    
    is_visualization = is_visualization_requested(prompt)

    if is_visualization:
        system_instruction = """
        You are an ENTERPRISE-GRADE Prescriptive AI and Visualization Engine.
        You DO NOT chat. You ONLY write python code.

        CRITICAL RULES:
        1. Read the [SYSTEM COMMAND] to find the EXACT file path. YOU MUST USE IT.
        2. NEVER write 'try/except' blocks for the file. Assume the file is there.
        3. ALWAYS set matplotlib to 'Agg' mode to prevent crashes!
        4. NEVER GUESS COLUMN NAMES! Use `df.columns` to find the closest match.

        === ANTI-CRASH MACHINE LEARNING RULES (ABSOLUTE PRIORITY) ===
        Before fitting any ML model (Prophet, XGBoost, Sklearn), you MUST:
        1. HANDLE TEXT: Dynamically select a purely NUMERIC column to predict. Ignore strings.
        2. HANDLE NaNs: You MUST fill missing values (`df.fillna(method='ffill').fillna(0)`) before training.
        3. HANDLE DATES: If using Prophet, you MUST have a 'ds' (datetime) and 'y' (numeric) column. If the user's dataset DOES NOT have a date column, you MUST synthetically generate a daily date range starting from '2023-01-01' and assign it to 'ds'.

        === PRO-LEVEL VISUALIZATION RULES ===
        - You MUST use `seaborn` for styling. Set the theme: `sns.set_theme(style="darkgrid", palette="mako")`
        - Generate HIGH-RESOLUTION charts: `plt.figure(figsize=(12, 8), dpi=300)`
        - Save as 'uploads/chart.png' using `plt.savefig('uploads/chart.png', bbox_inches='tight', dpi=300)`.

        === CONDITIONAL OUTPUT RULES ===
        
        A) IF USER ASKS TO DRAW A STANDARD CHART:
        - Generate exactly what they asked for using seaborn.
        - PRINT a Feynman Technique explanation (Executive Summary, Real-World Translation, Action Plan).
        - PRINT exactly: "![Data Chart](http://127.0.0.1:8000/download/chart.png?t={timestamp})"
        - PRINT exactly: "<br><a href='http://127.0.0.1:8000/download/chart.png?t={timestamp}' target='_blank' style='display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #00e5ff, #0097b2); color: #000; text-decoration: none; border-radius: 8px; font-weight: 700; margin-top: 10px; box-shadow: 0 4px 15px rgba(0,229,255,0.2); transition: 0.2s;'>📊 Download Chart</a>"
        
        B) IF USER ASKS FOR FUTURE PREDICTION OR GROWTH ADVICE:
        - ADVANCED FORECASTING REQUIRED: You MUST use `prophet`, `xgboost`, or `scikit-learn` to forecast the future. Plot historical data, the future trendline, AND a shaded Confidence Interval (`plt.fill_between`).
        - PRINT A MASSIVE PRESCRIPTIVE GROWTH STRATEGY (Baseline Forecast, Sensitivity Analysis, and 3 Action Steps).
        - PRINT exactly: "![Data Chart](http://127.0.0.1:8000/download/chart.png?t={timestamp})"
        - PRINT exactly: "<br><a href='http://127.0.0.1:8000/download/chart.png?t={timestamp}' target='_blank' style='display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #7c3aed, #9333ea); color: #fff; text-decoration: none; border-radius: 8px; font-weight: 700; margin-top: 10px; box-shadow: 0 4px 15px rgba(124,58,237,0.3); transition: 0.2s;'>📈 Download Prediction</a>"
        EXAMPLE OF PRESCRIPTIVE GROWTH CODE:
        ```python
        import pandas as pd
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        from prophet import Prophet
        import numpy as np
        import time

        file_path = 'uploads/YOUR_ACTUAL_FILE.csv' 
        df = pd.read_csv(file_path)
        
        # --- ANTI-CRASH DATA PREP ---
        df = df.fillna(0)
        numeric_col = df.select_dtypes(include=[np.number]).columns[0]
        date_col = next((col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()), None)
        if date_col:
            df['ds'] = pd.to_datetime(df[date_col])
        else:
            df['ds'] = pd.date_range(start='2023-01-01', periods=len(df), freq='D')
        df['y'] = df[numeric_col]
        
        # Pro-level styling
        sns.set_theme(style="darkgrid", palette="mako")
        plt.figure(figsize=(12, 8), dpi=300)
        
        # ... (AI WRITES PROPHET CODE HERE) ...
        
        plt.savefig('uploads/chart.png', bbox_inches='tight', dpi=300)
        plt.close()

        timestamp = int(time.time())
        print("### 🚀 Enterprise Prescriptive Growth Strategy\\n")
        print("**1. Baseline Future Forecast:** Our models indicate a 14% growth trajectory. Remaining on this baseline leaves revenue on the table.\\n")
        print("**2. The Growth Lever:** The metric with the highest elasticity is your 'Operational Uptime' column. For every 2% increase, profit scales by 8.4%.\\n")
        print("**3. Exact Advice for Maximum Growth:**\\n   * **Step 1:** Deploy automated data cleaning.\\n   * **Step 2:** Shift 15% of OPEX budget into infrastructure.\\n   * **Step 3:** Trigger aggressive scale-out protocols.\\n")
        
        - PRINT exactly: "💾 [Download the chart](http://127.0.0.1:8000/download/chart.png?t={timestamp})"
        ...
        -PRINT exactly: "💾 [Download the prediction chart](http://127.0.0.1:8000/download/chart.png?t={timestamp})"
        ```
        """
    else:
        system_instruction = f"""
        You are an ENTERPRISE-GRADE Data Science execution engine.
        You DO NOT chat. You ONLY write python code.
        ⚠️ VIOLATION OF ANY RULE = CODE FAILURE. BE PRECISE.

        CRITICAL RULES (ABSOLUTE):
        1. Read the [SYSTEM COMMAND] to find the EXACT file path. USE IT EXACTLY.
        2. Do NOT generate charts or visualizations unless explicitly requested.
        3. Save modified dataframe BACK to exact same file using `df.to_csv(file_path, index=False)`.

        === PRO-LEVEL DATA MANIPULATION & MATH ===
        - EXACT CELL EDITING: Convert human rows to 0-based Pandas indexes. 
        - SMART COLUMN MATCHING: Dynamically find the closest real column using case-insensitive matching before editing!

        === MASTER-LEVEL EXPLANATION RULES ===
        Whenever you modify data, explain WHY it matters using an analogy.

        EXAMPLE OF EXACT CELL EDITING & SMART MATCHING:
        ```python
        import pandas as pd
        import os
        import urllib.parse
        import time
        import numpy as np

        file_path = 'uploads/YOUR_ACTUAL_FILE.csv' 
        filename = os.path.basename(file_path)
        safe_filename = urllib.parse.quote(filename)
        
        df = pd.read_csv(file_path)
        
        target_col = 'sale' 
        actual_col = next((col for col in df.columns if target_col.lower() in col.lower()), df.columns[0])
        
        df.at[1, actual_col] = 100
        df.to_csv(file_path, index=False)
        
        timestamp = int(time.time())
        print("### 🧠 Advanced Data Manipulation Insight\\n")
        print(f"**1. Executive Summary:** Updated the cell at row 2 to 100 in column '{{actual_col}}'.\\n")
        print("**2. The Real-World Translation:** Imagine repairing a broken coordinate on a map. The models will no longer trip over this error.\\n")
        print("**3. Next Steps:** The dataset is now structurally sound.\\n")
        
        print("Do you want to download the updated dataset, or make more changes?")
        print("<br>")
        print(f"<a href='http://127.0.0.1:8000/download/{{safe_filename}}?t={{timestamp}}' style='display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #10b981, #059669); color: #fff; text-decoration: none; border-radius: 8px; font-weight: 700; margin-top: 10px; box-shadow: 0 4px 15px rgba(16,185,129,0.2);'>💾 Download Updated Dataset</a>")
        ```
        """
        
        if retry_count > 0:
            system_instruction += f"\n ⚠️ RETRY ATTEMPT {retry_count}: Previous attempt FAILED. Follow rules EXACTLY or it will fail again."
        

    for attempt in range(3):
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Task: {prompt}"}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.6,  
                max_tokens=4096,  
                top_p=0.9,        
            )

            raw_response = chat_completion.choices[0].message.content.strip()
            
            # 🛡️ THE EXTRACTION SHIELD
            import re
            match = re.search(r'```python\s*(.*?)\s*```', raw_response, re.DOTALL)
            if match:
                code = match.group(1)
            else:
                match = re.search(r'```\s*(.*?)\s*```', raw_response, re.DOTALL)
                if match:
                    code = match.group(1)
                else:
                    code = raw_response

            # 💪 ENHANCED VALIDATION: Check for unwanted plot code
            if not is_visualization and contains_plot_code(code):
                prompt = prompt + "\n\n🔴 CRITICAL: Do NOT create charts or graphs. Only modify data. No matplotlib, plt, seaborn, or plotting code."
                continue
            
            # 💪 ENHANCED VALIDATION: Verify exact null-fill values if specified
            if not is_visualization and extracted_values.get("strategy") in ["exact_list", "single_value"]:
                is_valid, validation_msg = validate_code_uses_exact_values(
                    code,
                    extracted_values.get("values", []),
                    extracted_values.get("column_mappings", {})
                )
                if not is_valid:
                    print(f"⚠️ Validation failed: {validation_msg}")
                    prompt = prompt + f"\n\n🔴 CRITICAL FAILURE: {validation_msg} You MUST use these exact values: {extracted_values.get('values')}. Retry with values as literals in the code."
                    continue
            
            return code.strip()

        except Exception as e:
            if attempt == 2:
                raise e
            import time
            time.sleep(2)
            continue



def execute_with_self_healing(user_prompt: str, max_retries: int = 3):
    print(f"\n🤖 Starting autonomous task: {user_prompt}")
    
    # Extract null-fill values once at the beginning
    extracted_values = extract_null_fill_values(user_prompt)
    
    current_code = real_ai_generate_code(user_prompt, extracted_values=extracted_values, retry_count=0)
    
    for attempt in range(1, max_retries + 1):
        print(f"\n🔄 Attempt {attempt} running code:\n{current_code}")
        output_bucket = io.StringIO()
        
        try:
            with contextlib.redirect_stdout(output_bucket):
                exec(current_code, {}) 
            
            final_result = output_bucket.getvalue()
            print(f"✅ Success on attempt {attempt}! Result: {final_result.strip()}")
            return {"status": "success", "result": final_result.strip()}
            
        except Exception as e:
            error_message = traceback.format_exc()
            print(f"❌ Crash on attempt {attempt}. The AI made a mistake.")
            
            if attempt == max_retries:
                return {"status": "failed", "error": "AI failed to fix it."}
            
            # 🛠️ CRITICAL FIX: Keep the original prompt attached so the AI doesn't switch modes or forget the file
            repair_prompt = f"{user_prompt}\n\n[SYSTEM ALERT: Your previous code crashed with this error:\n{error_message}\nFIX THE CODE. Make sure you use the EXACT file path from the system command! Do not guess column names!]"
            
            current_code = real_ai_generate_code(repair_prompt, extracted_values=extracted_values, retry_count=attempt)

    return {"status": "failed"}
# ==========================================
# 🌐 API ENDPOINTS (UI CONNECTION)
# ==========================================

@app.post("/users/")
def create_user(email: str, db: Session = Depends(get_db)):
    """Creates a new user in the database."""
    db_user = db.query(models.User).filter(models.User.email == email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = models.User(email=email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created!", "user_id": new_user.id}

@app.get("/users/{email}")
def login_user(email: str, db: Session = Depends(get_db)):
    """Logs in an existing user by checking their email."""
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please sign up!")
    return {"message": "Login successful", "user_id": user.id}

import mimetypes

@app.get("/download/{filename}")
def download_file(filename: str):
    """Allows the user to download CSVs OR view Image Charts directly!"""
    file_path = f"uploads/{filename}"
    if os.path.exists(file_path):
        
        if filename.endswith(".png"):
            return FileResponse(path=file_path, filename=filename, media_type='image/png')
        else:
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type='text/csv',
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
    return {"error": "File not found"}

# ==========================================
# 🎨 VISUALIZATION ENDPOINTS (Apache Superset)
# ==========================================

@app.get("/visualization/status")
def get_superset_status():
    """Get Apache Superset health and status"""
    superset = get_superset()
    return superset.get_dashboard_status()

@app.post("/visualization/register-dataset/")
async def register_visualization_dataset(
    user_id: int = Form(...),
    filename: str = Form(...)
):
    """
    Register a cleaned dataset in Superset for interactive visualization
    
    Args:
        user_id: User ID
        filename: CSV filename from uploads folder
    
    Returns:
        Superset datasource information and visualization URLs
    """
    try:
        file_path = f"uploads/{filename}"
        
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File not found: {filename}"
            }
        
        superset = get_superset()
        
        # Check Superset status
        status = superset.get_dashboard_status()
        if status["status"] != "healthy":
            return {
                "status": "warning",
                "message": "Apache Superset is not running. Start it with: docker-compose up -d",
                "instructions": "After starting Superset, you can register datasets for visualization."
            }
        
        # Register the dataset as a datasource
        datasource_name = filename.replace(".csv", "").replace("-", "_").lower()
        result = superset.register_csv_datasource(
            csv_file_path=file_path,
            datasource_name=datasource_name
        )
        
        if "error" in result:
            return {
                "status": "error",
                "message": result.get("error"),
                "file": filename
            }
        
        print(f"\n📊 Registered dataset '{datasource_name}' for visualization")
        
        return {
            "status": "success",
            "message": f"✅ Dataset '{datasource_name}' registered in Apache Superset!",
            "datasource_name": datasource_name,
            "superset_url": "http://localhost:8088",
            "instructions": "Go to http://localhost:8088 to create interactive dashboards",
            "default_charts": {
                "table": f"http://localhost:8088 → Create Table Chart",
                "bar": f"http://localhost:8088 → Create Bar Chart",
                "pie": f"http://localhost:8088 → Create Pie Chart",
                "line": f"http://localhost:8088 → Create Line Chart"
            }
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error registering dataset: {str(e)}",
            "error_details": str(e)
        }

@app.post("/visualization/create-dashboard/")
async def create_visualization_dashboard(
    user_id: int = Form(...),
    dashboard_name: str = Form(...),
    datasource_name: str = Form(...),
    chart_type: str = Form(default="table")
):
    """
    Create a dashboard in Apache Superset with automatic chart generation
    
    Args:
        user_id: User ID
        dashboard_name: Name for the dashboard
        datasource_name: Name of the registered datasource
        chart_type: Type of chart (table, bar, pie, line, scatter)
    
    Returns:
        Dashboard URL and access information
    """
    try:
        superset = get_superset()
        
        # Check if Superset is running
        status = superset.get_dashboard_status()
        if status["status"] != "healthy":
            return {
                "status": "offline",
                "message": "Apache Superset is not running",
                "instructions": "Start Superset: docker-compose up -d"
            }
        
        # Create dashboard
        result = superset.create_dashboard(
            dashboard_name=dashboard_name,
            datasource_id=1,  
            chart_type=chart_type
        )
        
        if "error" in result:
            return {
                "status": "error",
                "message": result.get("error")
            }
        
        print(f"\n📈 Created dashboard '{dashboard_name}' with {chart_type} chart")
        
        return {
            "status": "success",
            "message": f"✅ Dashboard '{dashboard_name}' created successfully!",
            "dashboard_name": dashboard_name,
            "chart_type": chart_type,
            "dashboard_url": result.get("url"),
            "superset_url": "http://localhost:8088",
            "instructions": [
                "1. Visit the dashboard URL to view interactive charts",
                "2. Use Superset's tools to drill down and explore data",
                "3. Add more charts to customize your dashboard",
                "4. Share dashboards with team members"
            ]
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error creating dashboard: {str(e)}"
        }

@app.get("/visualization/dashboards/")
def list_dashboards():
    """List all available dashboards in Superset"""
    try:
        superset = get_superset()
        dashboards = superset.list_dashboards()
        
        return {
            "status": "success",
            "dashboards": dashboards,
            "count": len(dashboards),
            "superset_url": "http://localhost:8088"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error fetching dashboards: {str(e)}"
        }

@app.get("/visualization/embed/{dashboard_id}")
def get_dashboard_embed(dashboard_id: int):
    """Get HTML embed code for a Superset dashboard"""
    try:
        superset = get_superset()
        iframe = superset.get_superset_iframe(dashboard_id)
        
        return {
            "status": "success",
            "embed_code": iframe,
            "dashboard_url": f"http://localhost:8088/superset/dashboard/{dashboard_id}"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error generating embed code: {str(e)}"
        }

@app.post("/clean-data/")
async def clean_data(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    cleaning_prompt: str = Form(default="Clean the dataset using all available methods")
):
    """
    Advanced data cleaning endpoint using multiple mathematical and ML techniques:
    - Z-score for extreme value detection
    - Interquartile Range (IQR) for robust outlier handling
    - Isolation Forest for ML-based anomaly detection
    - Linear Regression for predictive cleaning
    - K-Nearest Neighbors for predictive imputation
    """
    try:
        # Save the uploaded file
        file_path = f"uploads/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        print(f"\n🧼 Data Cleaning Request from User {user_id}")
        print(f"📁 File: {file.filename}")
        print(f"📝 Request: {cleaning_prompt}\n")
        
        # Initialize the advanced cleaner
        df = pd.read_csv(file_path)
        cleaner = AdvancedDataCleaner(df)
        
        # Execute the full cleaning pipeline
        report = cleaner.clean_full_pipeline(
            handle_missing_method="knn",
            remove_anomalies=True,
            cap_outliers=True
        )
        
        # Get cleaned data and save it back
        cleaned_df = cleaner.get_cleaned_dataframe()
        cleaned_df.to_csv(file_path, index=False)
        
        print(f"\n✅ Successfully cleaned and saved: {file_path}")
        
        return {
            "status": "success",
            "filename": file.filename,
            "message": "✨ Your dataset has been cleaned and improved!",
            "report": report,
            "quality_score": cleaner.cleaning_report["data_quality_score"],
            "download_url": f"http://127.0.0.1:8000/download/{file.filename}",
            "stats": {
                "rows_processed": cleaner.cleaning_report["total_rows"],
                "rows_final": cleaner.cleaning_report["final_rows"],
                "rows_removed": cleaner.cleaning_report["total_rows"] - cleaner.cleaning_report["final_rows"],
                "actions_performed": len(cleaner.cleaning_report["actions_taken"])
            }
        }
        
    except Exception as e:
        error_msg = f"❌ Error during data cleaning: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return {
            "status": "error",
            "message": error_msg,
            "error": traceback.format_exc()
        }


# ==========================================
# 🚀 SERVER STARTUP
# ==========================================

from fastapi import HTTPException, Form, UploadFile, File, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

# ==========================================
# 1. THE SAVE ROUTE (100% Complete & Unbroken)
# ==========================================
@app.post("/chats/")
async def create_chat(
    user_id: int = Form(...), 
    prompt: str = Form(...), 
    session_id: str = Form(None),
    file: UploadFile = File(None), 
    db: Session = Depends(get_db)
):
    try:

        if not session_id or session_id == "null":
            session_id = str(uuid.uuid4())
        print(f"\n📩 New message from User {user_id}: {prompt}")
        
        # Fetch or auto-create the user
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            user = models.User(id=user_id, email=f"testuser{user_id}@test.com")
            db.add(user)
            db.commit()
            db.refresh(user)

        enhanced_prompt = prompt
        has_dataset = False

        # Handle File Uploads & Memory
        if file:
            file_path = f"uploads/{file.filename}"
            with open(file_path, "wb") as buffer:
                import shutil
                shutil.copyfileobj(file.file, buffer)
            
            user.active_file = file_path
            db.commit() 
            enhanced_prompt += f"\n\n[SYSTEM COMMAND: New file saved at '{file_path}'.]"
            has_dataset = True
            
        elif user.active_file:
            enhanced_prompt += f"\n\n[SYSTEM COMMAND: Using active dataset at '{user.active_file}'.]"
            has_dataset = True

        # SMART ROUTER
        is_casual_chat = prompt.strip().lower() in ["hi", "hello", "hey", "help", "sup", "good morning"]

        if has_dataset and not is_casual_chat:
            
            agent_response = execute_with_self_healing(enhanced_prompt)
            
            
            if agent_response["status"] == "success":
                final_text = f"🤖 **Data Analysis Complete:**\n\n{agent_response['result']}"
            else:
                final_text = "🚨 **Agent Error:** I tried to write Python code to fix your dataset, but it crashed. Please try different instructions."
        
        else:
            # Send to the Standard Chat AI (for saying "hi" or general questions)
            print("💬 Routing to standard conversational AI...")
            try:
                past_chats = db.query(models.ChatHistory).filter(models.ChatHistory.user_id == user_id).order_by(models.ChatHistory.id.desc()).limit(3).all()
                history_text = "\n".join([f"User: {c.prompt}\nAI: {c.response}" for c in reversed(past_chats)])
                
                system_msg = f"You are a helpful Data Science AI assistant for the DataFlow platform. If they say hi, greet them and ask them to upload a CSV file so you can analyze it. Context:\n{history_text}"
                
                normal_response = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama-3.1-8b-instant", 
                )
                # ⚠️ final_text is defined here!
                final_text = normal_response.choices[0].message.content.strip()
            except Exception as e:
                
                final_text = f"Error in standard chat: {str(e)}"

       # ⚠️ (Now actually saves the thread ID!)
        new_chat = models.ChatHistory(user_id=user_id, session_id=session_id, prompt=prompt, response=final_text)
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        
        return {"id": new_chat.id, "session_id": new_chat.session_id, "response": final_text}
    

    except Exception as e:
        # Crash Safety Net
        import traceback
        from fastapi.responses import JSONResponse
        error_details = traceback.format_exc()
        print(f"🔥 MASSIVE CRASH IN POST /chats/: {error_details}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/chats/history")
def get_chat_history(db: Session = Depends(get_db)):
    try:
        # Fetch chats, but only keep ONE per session_id for the sidebar
        chats = db.query(models.ChatHistory).order_by(desc(models.ChatHistory.id)).all()
        
        seen_sessions = set()
        history_list = []
        
        for chat in chats:
            if chat.session_id not in seen_sessions:
                seen_sessions.add(chat.session_id)
                # Save the very first prompt to use as the title!
                history_list.append({"session_id": chat.session_id, "prompt": chat.prompt})
                if len(history_list) >= 20: 
                    break
                    
        return history_list
    except Exception as e:
        print(f"Error fetching history: {e}")
        return []

@app.get("/chats/{session_id}")
def get_single_chat(session_id: str, db: Session = Depends(get_db)):
    # ⚠️ Fetch ALL messages that share this session_id, ordered chronologically
    chats = db.query(models.ChatHistory).filter(models.ChatHistory.session_id == session_id).order_by(models.ChatHistory.id.asc()).all()
    
    if not chats:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    return [{"prompt": chat.prompt, "response": chat.response} for chat in chats]

# ==========================================
# 🚀 SERVER STARTUP
# ==========================================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)