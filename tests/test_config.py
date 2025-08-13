"""
Test configuration and utilities.
"""
import os
import pytest
from typing import Dict, Any


class TestConfig:
    """Test configuration settings."""
    
    # Database settings
    TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    
    # Performance test thresholds
    PERFORMANCE_THRESHOLDS = {
        "autocomplete_max_time_ms": 100,
        "search_max_time_ms": 500,
        "document_create_max_time_ms": 1000,
        "concurrent_user_success_rate": 0.9,
        "memory_increase_limit_mb": 500,
    }
    
    # Security test settings
    SECURITY_SETTINGS = {
        "max_login_attempts": 5,
        "session_timeout_minutes": 30,
        "password_min_length": 8,
        "jwt_expiry_minutes": 60,
    }
    
    # Load test settings
    LOAD_TEST_SETTINGS = {
        "concurrent_users": 20,
        "operations_per_user": 10,
        "max_response_time_ms": 5000,
        "stress_test_users": 100,
    }
    
    @classmethod
    def get_performance_threshold(cls, metric: str) -> float:
        """Get performance threshold for a metric."""
        return cls.PERFORMANCE_THRESHOLDS.get(metric, 1000)
    
    @classmethod
    def get_security_setting(cls, setting: str) -> Any:
        """Get security setting value."""
        return cls.SECURITY_SETTINGS.get(setting)
    
    @classmethod
    def get_load_test_setting(cls, setting: str) -> Any:
        """Get load test setting value."""
        return cls.LOAD_TEST_SETTINGS.get(setting)
    
    @classmethod
    def is_performance_test_enabled(cls) -> bool:
        """Check if performance tests should run."""
        return os.getenv("RUN_PERFORMANCE_TESTS", "false").lower() == "true"
    
    @classmethod
    def is_security_test_enabled(cls) -> bool:
        """Check if security tests should run."""
        return os.getenv("RUN_SECURITY_TESTS", "true").lower() == "true"
    
    @classmethod
    def is_integration_test_enabled(cls) -> bool:
        """Check if integration tests should run."""
        return os.getenv("RUN_INTEGRATION_TESTS", "true").lower() == "true"


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "performance: Performance tests"
    )
    config.addinivalue_line(
        "markers", "security: Security tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on environment settings."""
    skip_performance = pytest.mark.skip(reason="Performance tests disabled")
    skip_security = pytest.mark.skip(reason="Security tests disabled")
    skip_integration = pytest.mark.skip(reason="Integration tests disabled")
    
    for item in items:
        # Skip performance tests if disabled
        if "performance" in item.keywords and not TestConfig.is_performance_test_enabled():
            item.add_marker(skip_performance)
        
        # Skip security tests if disabled
        if "security" in item.keywords and not TestConfig.is_security_test_enabled():
            item.add_marker(skip_security)
        
        # Skip integration tests if disabled
        if "integration" in item.keywords and not TestConfig.is_integration_test_enabled():
            item.add_marker(skip_integration)


# Test utilities
class TestMetrics:
    """Utility class for collecting test metrics."""
    
    def __init__(self):
        self.metrics = {}
    
    def record_metric(self, name: str, value: float, unit: str = "ms"):
        """Record a performance metric."""
        if name not in self.metrics:
            self.metrics[name] = []
        
        self.metrics[name].append({
            "value": value,
            "unit": unit
        })
    
    def get_average(self, name: str) -> float:
        """Get average value for a metric."""
        if name not in self.metrics:
            return 0.0
        
        values = [m["value"] for m in self.metrics[name]]
        return sum(values) / len(values) if values else 0.0
    
    def get_max(self, name: str) -> float:
        """Get maximum value for a metric."""
        if name not in self.metrics:
            return 0.0
        
        values = [m["value"] for m in self.metrics[name]]
        return max(values) if values else 0.0
    
    def print_summary(self):
        """Print metrics summary."""
        print("\n" + "="*60)
        print("TEST METRICS SUMMARY")
        print("="*60)
        
        for name, measurements in self.metrics.items():
            if measurements:
                values = [m["value"] for m in measurements]
                unit = measurements[0]["unit"]
                
                print(f"{name}:")
                print(f"  Count: {len(values)}")
                print(f"  Average: {sum(values)/len(values):.2f} {unit}")
                print(f"  Min: {min(values):.2f} {unit}")
                print(f"  Max: {max(values):.2f} {unit}")
                print()


# Global test metrics instance
test_metrics = TestMetrics()


@pytest.fixture(scope="session", autouse=True)
def print_test_summary():
    """Print test summary at the end of test session."""
    yield
    test_metrics.print_summary()


@pytest.fixture
def metrics():
    """Provide test metrics fixture."""
    return test_metrics