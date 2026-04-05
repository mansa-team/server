import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.utils.roles import Permission, Roles

class TestPermission:
    def test_permission_enum_values(self):
        assert Permission.NONE == 0
        assert Permission.VIEW_PROFILE > 0
        assert Permission.USE_PROMETHEUS > 0

    def test_permission_all_includes_all(self):
        allPerms = Permission.ALL()
        assert allPerms & Permission.VIEW_PROFILE
        assert allPerms & Permission.USE_PROMETHEUS
        assert allPerms & Permission.MANAGE_USERS


class TestRoles:
    def test_user_role_has_basic_permissions(self):
        assert Roles.USER & Permission.VIEW_PROFILE
        assert Roles.USER & Permission.USE_THOTH
        assert Roles.USER & Permission.USE_MAAT

    def test_user_role_missing_premium_permissions(self):
        assert not (Roles.USER & Permission.USE_PROMETHEUS)
        assert not (Roles.USER & Permission.USE_OGUM)

    def test_premium_includes_user_permissions(self):
        assert Roles.PREMIUM & Permission.VIEW_PROFILE
        assert Roles.PREMIUM & Permission.USE_THOTH

    def test_premium_has_extra_permissions(self):
        assert Roles.PREMIUM & Permission.USE_PROMETHEUS
        assert Roles.PREMIUM & Permission.USE_OGUM

    def test_developer_starter_includes_user(self):
        assert Roles.DEVELOPER_STARTER & Permission.VIEW_PROFILE
        assert Roles.DEVELOPER_STARTER & Permission.STARTER_API_ACCESS

    def test_developer_enterprise_includes_all(self):
        assert Roles.DEVELOPER_ENTERPRISE & Permission.STARTER_API_ACCESS
        assert Roles.DEVELOPER_ENTERPRISE & Permission.ENTERPRISE_API_ACCESS

    def test_admin_has_all_permissions(self):
        assert Roles.ADMIN & Permission.ALL()
        assert Roles.ADMIN & Permission.VIEW_PROFILE
        assert Roles.ADMIN & Permission.MANAGE_USERS

    def test_check_access_admin_returns_true(self):
        result = Roles.checkAccess(["ADMIN"], Permission.MANAGE_USERS)
        assert result is True

    def test_check_access_user_with_permission(self):
        result = Roles.checkAccess(["USER"], Permission.VIEW_PROFILE)
        assert result is True

    def test_check_access_user_without_permission(self):
        result = Roles.checkAccess(["USER"], Permission.USE_PROMETHEUS)
        assert result is False

    def test_check_access_premium_has_prometheus(self):
        result = Roles.checkAccess(["PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_case_insensitive(self):
        assert Roles.checkAccess(["admin"], Permission.MANAGE_USERS) is True
        assert Roles.checkAccess(["user"], Permission.VIEW_PROFILE) is True

    def test_check_access_invalid_role_ignored(self):
        result = Roles.checkAccess(["INVALID_ROLE", "USER"], Permission.VIEW_PROFILE)
        assert result is True

    def test_check_access_empty_roles(self):
        result = Roles.checkAccess([], Permission.VIEW_PROFILE)
        assert result is False

    def test_check_access_multiple_roles(self):
        result = Roles.checkAccess(["USER", "PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True