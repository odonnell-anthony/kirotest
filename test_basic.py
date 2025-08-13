"""
Basic test to verify the application can start.
"""
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_imports():
    """Test that basic imports work."""
    try:
        from app.main import app
        print("✓ Main app import successful")
        
        from app.core.config import settings
        print("✓ Settings import successful")
        
        from app.api.health import router
        print("✓ Health router import successful")
        
        print("All basic imports successful!")
        return True
        
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)