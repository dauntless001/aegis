from fastapi import status

class AppException(Exception):
    """Base exception for application specific error"""

    def __init__(
            self, 
            message: str,
            status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail: str | None = None
        ):
            """
            Args:
                message: error message
                status_code: status code of the error
                datail: optional error description
            """

            self.message = message
            self.status_code = status_code
            self.detail = detail
            super().__init__(self.message)


class ValidationError(AppException):

    def __init__(self, message: str, detail: str | None = None):

        """
        Initialize validation error

        Args:
            message: error message
            datail: optional error description
        """

        self.message = message
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = detail
        super().__init__(self.message)


class AuthenticationError(AppException):

    def __init__(self, message: str, detail: str | None = None):

        """
        Initialize authentication error

        Args:
            message: error message
            datail: optional error description
        """

        self.message = message
        self.status_code = status.HTTP_401_UNAUTHORIZED
        self.detail = detail
        super().__init__(self.message)


class AuthorizationError(AppException):

    def __init__(self, message: str, detail: str | None = None):

        """
        Initialize authorization error

        Args:
            message: error message
            datail: optional error description
        """

        self.message = message
        self.status_code = status.HTTP_403_FORBIDDEN
        self.detail = detail
        super().__init__(self.message)


class ConflictError(AppException):

    def __init__(self, message: str, detail: str | None = None):

        """
        Initialize conflict error

        Args:
            message: error message
            datail: optional error description
        """

        self.message = message
        self.status_code = status.HTTP_409_CONFLICT
        self.detail = detail
        super().__init__(self.message)


class DatabaseError(AppException):

    def __init__(self, message: str, detail: str | None = None):

        """
        Initialize database error

        Args:
            message: error message
            datail: optional error description
        """

        self.message = message
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = detail
        super().__init__(self.message)


class NotFoundError(AppException):

    def __init__(self, message: str, detail: str | None = None):

        """
        Initialize not-found error

        Args:
            message: error message
            datail: optional error description
        """

        self.message = message
        self.status_code = status.HTTP_404_NOT_FOUND
        self.detail = detail
        super().__init__(self.message)
