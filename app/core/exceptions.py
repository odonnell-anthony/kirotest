"""
Custom exceptions for the application.
"""


class ServiceException(Exception):
    """Base exception for service layer errors."""
    
    def __init__(self, message: str, code: str = "SERVICE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundError(ServiceException):
    """Exception raised when a resource is not found."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, "NOT_FOUND")


class PermissionDeniedError(ServiceException):
    """Exception raised when user lacks required permissions."""
    
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, "PERMISSION_DENIED")


class ValidationError(ServiceException):
    """Exception raised when validation fails."""
    
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, "VALIDATION_ERROR")


class DuplicateError(ServiceException):
    """Exception raised when trying to create a duplicate resource."""
    
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, "DUPLICATE_ERROR")


class InternalError(ServiceException):
    """Exception raised for internal server errors."""
    
    def __init__(self, message: str = "Internal server error"):
        super().__init__(message, "INTERNAL_ERROR")