import os
import sys
import codecs

def analyze_file_encoding(filename):
    """Analyze a file to determine its encoding and check for BOM."""
    print(f"\nAnalyzing file: {filename}")
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return
        
    # Check for BOM markers
    with open(filename, 'rb') as f:
        raw = f.read(4)    # Read first 4 bytes
        
    encodings = {
        b'\xef\xbb\xbf': 'UTF-8-BOM',
        b'\xff\xfe': 'UTF-16-LE',
        b'\xfe\xff': 'UTF-16-BE',
        b'\xff\xfe\x00\x00': 'UTF-32-LE',
        b'\x00\x00\xfe\xff': 'UTF-32-BE'
    }
    
    detected_encoding = None
    for bom, enc in encodings.items():
        if raw.startswith(bom):
            detected_encoding = enc
            print(f"Detected BOM: {enc}")
            break
    
    if not detected_encoding:
        print("No BOM detected, likely UTF-8 or ASCII")
        
    # Try to decode with various encodings
    encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'utf-16', 'utf-32']
    
    for enc in encodings_to_try:
        try:
            with codecs.open(filename, 'r', encoding=enc) as f:
                content = f.read()
                print(f"Successfully decoded with {enc} encoding")
                
                # Look for non-ASCII characters
                non_ascii = [c for c in content if ord(c) > 127]
                if non_ascii:
                    print(f"Contains {len(non_ascii)} non-ASCII characters")
                    print(f"First few: {non_ascii[:5]}")
                else:
                    print("Contains only ASCII characters")
                
                break
        except UnicodeDecodeError:
            print(f"Failed to decode with {enc} encoding")
        except Exception as e:
            print(f"Error reading with {enc} encoding: {str(e)}")
    
    return detected_encoding

def check_env_variables():
    """Check environment variables required by the application."""
    print("\nChecking environment variables:")
    critical_vars = [
        "QUICKBOOKS_CLIENT_ID",
        "QUICKBOOKS_CLIENT_SECRET",
        "QUICKBOOKS_REFRESH_TOKEN",
        "QUICKBOOKS_REALM_ID",
        "OPENAI_API_KEY"
    ]
    
    optional_vars = [
        "QUICKBOOKS_ENVIRONMENT",
        "COMPANY_NAME",
        "COMPANY_TAX_ID",
        "COMPANY_FISCAL_YEAR",
        "LOG_LEVEL",
        "DATA_RETENTION_DAYS",
        "CHAT_MODEL",
        "MAX_CONTEXT_WINDOW"
    ]
    
    for var in critical_vars:
        if var in os.environ:
            value = os.environ[var]
            masked_value = value[:4] + '*' * (len(value) - 4) if len(value) > 4 else '****'
            print(f"✅ {var} is set: {masked_value}")
        else:
            print(f"❌ Critical variable {var} is not set")
    
    for var in optional_vars:
        if var in os.environ:
            value = os.environ[var]
            print(f"✓ {var} is set: {value}")
        else:
            print(f"⚠️ Optional variable {var} is not set")

def analyze_dotenv_loading():
    """Analyze how python-dotenv is loading the .env file."""
    print("\nAnalyzing .env file loading:")
    
    try:
        import dotenv
        print(f"python-dotenv version: {dotenv.__version__}")
        
        # Try to load .env and see what happens
        loaded = dotenv.load_dotenv()
        if loaded:
            print("✅ dotenv.load_dotenv() successful")
        else:
            print("⚠️ dotenv.load_dotenv() returned False")
        
        # Check if .env file exists
        if os.path.exists(".env"):
            print("✅ .env file exists")
            analyze_file_encoding(".env")
        else:
            print("❌ .env file does not exist")
            
        # Check if .env.example file exists
        if os.path.exists(".env.example"):
            print("✅ .env.example file exists")
        else:
            print("❌ .env.example file does not exist")
        
    except ImportError:
        print("❌ python-dotenv is not installed")
    except Exception as e:
        print(f"❌ Error analyzing dotenv: {str(e)}")

if __name__ == "__main__":
    print("=== Environment Analysis Tool ===")
    print(f"Python version: {sys.version}")
    print(f"Current directory: {os.getcwd()}")
    
    analyze_dotenv_loading()
    check_env_variables()
    
    print("\nAnalysis complete.") 