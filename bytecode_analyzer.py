import sys
import os
import importlib
import traceback
import dis

def test_import(module_name):
    """Try to import a module and analyze the bytecode if it fails."""
    print(f"Testing import of '{module_name}'...")
    try:
        # First attempt direct import
        module = importlib.import_module(module_name)
        print(f"Import successful! Module: {module.__name__}")
        
        # Check if expected classes exist
        if module_name == "tax_module":
            if hasattr(module, "TaxModule"):
                print("TaxModule class found")
                return True
            else:
                print("ERROR: TaxModule class not found in module")
                return False
        
        return True
        
    except ImportError as e:
        print(f"Import error: {str(e)}")
        # Try to find the module file
        for path in sys.path:
            module_path = os.path.join(path, f"{module_name}.py")
            if os.path.exists(module_path):
                print(f"Found module file at: {module_path}")
                with open(module_path, 'r', encoding='utf-8') as f:
                    try:
                        source = f.read()
                        # Compile the module as code object
                        code = compile(source, module_path, 'exec')
                        print("Successfully compiled the source")
                        # Disassemble to check bytecode
                        print("\nBytecode Analysis:")
                        dis.dis(code)
                        return False
                    except Exception as e:
                        print(f"Error compiling source: {str(e)}")
                        return False
        
        return False
        
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return False

def test_circular_imports():
    """Test for circular import problems."""
    print("\nChecking for circular imports...")
    import sys
    original_modules = set(sys.modules.keys())
    
    # Attempt to load each module in isolation
    for module_name in ["logger", "config", "tax_module", "accounting_engine", "quickbooks_api"]:
        try:
            sys.modules = {k: v for k, v in sys.modules.items() if k in original_modules}
            __import__(module_name)
            print(f"✅ {module_name} imports without circular dependency")
        except ImportError as e:
            print(f"❌ {module_name} has import error: {str(e)}")
        except Exception as e:
            print(f"❌ {module_name} has other error: {str(e)}")

def check_tax_module_integrity():
    """Specifically check the tax_module.py file for structure issues."""
    print("\nChecking tax_module.py structure...")
    try:
        with open("tax_module.py", 'r', encoding='utf-8') as f:
            source = f.read()
            
        # Check for class definition
        if "class TaxModule" in source:
            print("✅ TaxModule class definition found")
        else:
            print("❌ TaxModule class definition missing")
            
        # Check for indentation issues - quick detection of major problems
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith(' ') and not line.startswith('\t') and not line.startswith('#') and "class" not in line and "import" not in line and "from" not in line and "def " in line:
                print(f"❌ Line {i+1} has method definition at root level: {line}")
                
        return "class TaxModule" in source
    except Exception as e:
        print(f"Error checking tax_module.py: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Python Import Diagnostic Tool ===")
    print(f"Python version: {sys.version}")
    print(f"Current directory: {os.getcwd()}")
    print("\nTesting critical imports:")
    
    # Test each required module
    modules_ok = all([
        test_import("logger"),
        test_import("config"),
        test_import("tax_module"),
        test_import("accounting_engine"),
        test_import("quickbooks_api")
    ])
    
    # Extra tests for tax_module
    if not modules_ok:
        test_circular_imports()
        check_tax_module_integrity()
        
    print("\nDiagnostic complete.") 