# peoples_coin/constants.py

from enum import Enum

class GoodwillStatus(Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class ApiResponseStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

