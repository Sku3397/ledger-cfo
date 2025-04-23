import sys
import os
import traceback

def safe_import(module_name, symbol_name=None):
    """Safely import a module or symbol and report errors."""
    try:
        if symbol_name:
            print(f"Attempting to import {symbol_name} from {module_name}...")
            module = __import__(module_name, fromlist=[symbol_name])
            symbol = getattr(module, symbol_name)
            print(f"✅ Successfully imported {symbol_name} from {module_name}")
            return symbol
        else:
            print(f"Attempting to import {module_name}...")
            module = __import__(module_name)
            print(f"✅ Successfully imported {module_name}")
            return module
    except ImportError as e:
        print(f"❌ Import error: {str(e)}")
        traceback.print_exc()
        return None
    except AttributeError as e:
        print(f"❌ Symbol not found: {str(e)}")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        traceback.print_exc()
        return None

def repair_tax_module():
    """Attempt to repair the tax_module.py file if needed."""
    print("\nChecking tax_module.py for issues...")
    
    try:
        with open("tax_module.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if the file starts with indented methods instead of class definition
        lines = content.split("\n")
        
        if not any(line.startswith("class TaxModule") for line in lines):
            print("❌ TaxModule class definition not found")
            
            # Check if methods are defined at root level
            methods_at_root = [i for i, line in enumerate(lines) 
                              if line.strip() and not line.startswith(' ') and not line.startswith('\t') 
                              and not line.startswith('#') and not line.startswith('import') 
                              and not line.startswith('from') and "def " in line]
            
            if methods_at_root:
                print(f"Found {len(methods_at_root)} method definitions at root level")
                print("Attempting to repair file by adding class definition...")
                
                # Create repaired content
                repaired_content = "import os\nimport json\nfrom datetime import datetime, timedelta\nimport pandas as pd\nimport numpy as np\nfrom logger import cfo_logger\n\n"
                repaired_content += "class TaxModule:\n    \"\"\"Tax planning and preparation module for the CFO Agent.\n    \n    Handles tax estimation, deduction analysis, and filing preparation.\n    \"\"\"\n    \n"
                
                for i, line in enumerate(lines):
                    if i in methods_at_root:
                        # Add indentation to method definition
                        repaired_content += "    " + line + "\n"
                    elif line.strip() and not line.startswith("import") and not line.startswith("from"):
                        # Add indentation to everything else except imports
                        repaired_content += "    " + line + "\n"
                    else:
                        # Keep imports at root level
                        repaired_content += line + "\n"
                
                # Backup original file
                backup_name = "tax_module.py.bak"
                with open(backup_name, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Created backup of original file as {backup_name}")
                
                # Write repaired file
                with open("tax_module.py", "w", encoding="utf-8") as f:
                    f.write(repaired_content)
                print("Repaired tax_module.py file")
                
                return True
        else:
            print("✅ TaxModule class definition found")
        
        return False
            
    except Exception as e:
        print(f"❌ Error repairing tax_module.py: {str(e)}")
        traceback.print_exc()
        return False

def test_main_imports():
    """Test the imports as they occur in main.py."""
    print("\nTesting imports from main.py...")
    
    # Try importing required modules in order
    safe_import("streamlit")
    safe_import("pandas")
    safe_import("numpy")
    safe_import("plotly.express")
    safe_import("plotly.graph_objects") 