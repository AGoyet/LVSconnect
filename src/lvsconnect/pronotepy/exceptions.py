from typing import Optional, Tuple

__all__ = (
    "PronoteAPIError",
    "CryptoError",
    "ExpiredObject",
    "DateParsingError",
    "ENTLoginError",
    "UnsupportedOperation",
    "QRCodeDecryptError",
    "MFAError",
)


class PronoteAPIError(Exception):
    """
    Base exception for any pronote api errors
    """

    def __init__(
        self,
        *args: object,
        pronote_error_code: Optional[int] = None,
        pronote_error_msg: Optional[str] = None,
    ) -> None:
        super().__init__(*args)
        self.pronote_error_code = pronote_error_code
        self.pronote_error_msg = pronote_error_msg


class CryptoError(PronoteAPIError):
    """Exception for known errors in the cryptography."""

    pass


class QRCodeDecryptError(CryptoError):
    """Raised when the QR code cannot be decrypted."""

    pass


class ExpiredObject(PronoteAPIError):
    """Raised when pronote returns error 22. (unknown object reference)"""

    pass


class DateParsingError(PronoteAPIError):
    """Bad date string"""

    def __init__(self, message: str, date_string: str):
        super().__init__(message)
        self.date_string = date_string


class ENTLoginError(PronoteAPIError):
    """Error while logging in with an ENT"""

    pass


class UnsupportedOperation(PronoteAPIError):
    """The PRONOTE server does not have the functionality"""

    pass


class MFAError(PronoteAPIError):
    """Error while processing 2FA (MFA)"""

    pass
