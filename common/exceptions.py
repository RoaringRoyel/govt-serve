from rest_framework import status
from rest_framework.exceptions import APIException


class BusinessRuleViolation(APIException):
    """A well-formed request that conflicts with the current state of the system."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This action is not allowed in the current state."
    default_code = "business_rule_violation"


class InvalidTransition(BusinessRuleViolation):
    default_detail = "That status change is not allowed."
    default_code = "invalid_transition"
