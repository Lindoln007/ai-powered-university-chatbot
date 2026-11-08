from django.contrib.auth import authenticate, get_user_model, password_validation
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)
    account_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "role",
            "is_active", "account_status", "created_at", "last_login",
        ]
        read_only_fields = ["id", "username", "role", "is_active", "created_at", "last_login"]

    def get_account_status(self, obj) -> str:
        return "active" if obj.is_active else "inactive"

    def validate_email(self, value):
        value = value.strip().lower()
        queryset = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value


class AdminUserSerializer(UserSerializer):
    """Used by administrators to manage roles and account status."""

    class Meta(UserSerializer.Meta):
        read_only_fields = ["id", "username", "created_at", "last_login"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    role = serializers.ChoiceField(
        choices=[(role.value, role.label) for role in User.SELF_REGISTRATION_ROLES],
        default=User.Role.PROSPECTIVE_STUDENT,
    )

    class Meta:
        model = User
        fields = ["username", "email", "password", "password_confirm", "first_name", "last_name", "role"]
        extra_kwargs = {"email": {"required": True}}

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        candidate = User(
            username=attrs.get("username"),
            email=attrs.get("email"),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(help_text="Username or email address.")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        identifier = attrs["username"].strip()
        username = identifier
        if "@" in identifier:
            match = User.objects.filter(email__iexact=identifier).only("username").first()
            if match:
                username = match.username
        user = authenticate(self.context.get("request"), username=username, password=attrs["password"])
        if user is None:
            raise serializers.ValidationError("Invalid username/email or password.", code="authentication")
        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(attrs["new_password"], user=self.context["request"].user)
        return attrs


class AuthTokenResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    token = serializers.CharField()
    user = UserSerializer()
