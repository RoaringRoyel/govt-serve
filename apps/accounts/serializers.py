from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.audit.services import audit

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone", "role", "points")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Public sign-up. Always creates a citizen - a role can never be chosen by the caller."""

    role_to_create = Role.CITIZEN
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "email", "phone", "full_name", "password")

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], User(email=attrs.get("email"), full_name=attrs.get("full_name", "")))
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(role=self.role_to_create, **validated_data)


class OfficerCreateSerializer(RegisterSerializer):
    """Admin-only: creates an officer account."""

    role_to_create = Role.OFFICER


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs[self.username_field] = (attrs.get(self.username_field) or "").lower()
        request = self.context.get("request")
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            audit.log("auth.login_failed", metadata={"email": attrs[self.username_field]}, request=request)
            raise
        data["user"] = UserSerializer(self.user).data
        audit.log("auth.login", actor=self.user, target=self.user, request=request)
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "New password must be different from the current one."})
        validate_password(attrs["new_password"], user)
        return attrs
