#!/usr/bin/env python3
"""
Test runner script for the wiki documentation app.
"""
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run tests for the wiki documentation app")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--security", action="store_true", help="Run security tests only")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--parallel", "-n", type=int, help="Number of parallel workers")
    
    args = parser.parse_args()
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
    
    # Add coverage if requested
    if args.coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-fail-under=90"
        ])
    
    # Skip slow tests if requested
    if args.fast:
        cmd.extend(["-m", "not slow"])
    
    # Determine which tests to run
    test_paths = []
    
    if args.unit:
        test_paths.append("tests/unit")
    elif args.integration:
        test_paths.append("tests/integration")
    elif args.performance:
        test_paths.append("tests/performance")
    elif args.security:
        test_paths.append("tests/security")
    else:
        # Run all tests if no specific type specified
        test_paths.extend([
            "tests/unit",
            "tests/integration",
            "tests/performance",
            "tests/security"
        ])
    
    # Add test paths to command
    cmd.extend(test_paths)
    
    # Run the tests
    success = run_command(cmd, "Test Suite")
    
    if success:
        print(f"\n🎉 All tests passed!")
        
        if args.coverage:
            print(f"\n📊 Coverage report generated in htmlcov/index.html")
        
        # Print test summary
        print(f"\n📋 Test Summary:")
        print(f"   Unit Tests: {'✅' if not args.integration and not args.performance and not args.security else '⏭️'}")
        print(f"   Integration Tests: {'✅' if not args.unit and not args.performance and not args.security else '⏭️'}")
        print(f"   Performance Tests: {'✅' if not args.unit and not args.integration and not args.security else '⏭️'}")
        print(f"   Security Tests: {'✅' if not args.unit and not args.integration and not args.performance else '⏭️'}")
        
        return 0
    else:
        print(f"\n❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())