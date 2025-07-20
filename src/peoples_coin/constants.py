# peoples_coin/constants.py

from enum import Enum

class GoodwillStatus(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"

class ApiResponseStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

