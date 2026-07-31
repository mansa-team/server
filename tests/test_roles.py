from main.utils.roles import Permission, Roles


class TestPermission:
    def test_permission_enum_values(self):
        assert Permission.NONE == 0
        assert Permission.USE_PROMETHEUS > 0
        assert Permission.GENERATE_API_KEYS > 0
        assert Permission.PROMETHEUS_EXTENDED_MEMORIES > 0

    def test_permission_all_includes_all(self):
        allPerms = Permission.ALL()
        assert allPerms & Permission.USE_PROMETHEUS
        assert allPerms & Permission.GENERATE_API_KEYS
        assert allPerms & Permission.PROMETHEUS_EXTENDED_MEMORIES


class TestRoles:
    def test_user_has_no_permissions(self):
        assert Roles.USER == Permission.NONE
        assert not (Roles.USER & Permission.USE_PROMETHEUS)
        assert not (Roles.USER & Permission.GENERATE_API_KEYS)

    def test_premium_has_prometheus_permissions(self):
        assert Roles.PREMIUM & Permission.USE_PROMETHEUS
        assert Roles.PREMIUM & Permission.PROMETHEUS_EXTENDED_MEMORIES

    def test_premium_missing_api_keys(self):
        assert not (Roles.PREMIUM & Permission.GENERATE_API_KEYS)

    def test_developer_starter_has_api_keys(self):
        assert Roles.DEVELOPER_STARTER & Permission.GENERATE_API_KEYS

    def test_developer_starter_missing_prometheus(self):
        assert not (Roles.DEVELOPER_STARTER & Permission.USE_PROMETHEUS)

    def test_developer_enterprise_matches_starter(self):
        assert Roles.DEVELOPER_ENTERPRISE == Roles.DEVELOPER_STARTER
        assert Roles.DEVELOPER_ENTERPRISE & Permission.GENERATE_API_KEYS

    def test_admin_has_all_permissions(self):
        assert Roles.ADMIN & Permission.ALL()
        assert Roles.ADMIN & Permission.USE_PROMETHEUS
        assert Roles.ADMIN & Permission.GENERATE_API_KEYS
        assert Roles.ADMIN & Permission.PROMETHEUS_EXTENDED_MEMORIES

    def test_check_access_admin_returns_true(self):
        result = Roles.checkAccess(["ADMIN"], Permission.GENERATE_API_KEYS)
        assert result is True

    def test_check_access_user_without_permission(self):
        result = Roles.checkAccess(["USER"], Permission.USE_PROMETHEUS)
        assert result is False

    def test_check_access_premium_has_prometheus(self):
        result = Roles.checkAccess(["PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_case_insensitive(self):
        assert Roles.checkAccess(["admin"], Permission.GENERATE_API_KEYS) is True

    def test_check_access_invalid_role_ignored(self):
        result = Roles.checkAccess(["INVALID_ROLE", "PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_empty_roles(self):
        result = Roles.checkAccess([], Permission.USE_PROMETHEUS)
        assert result is False

    def test_check_access_multiple_roles(self):
        result = Roles.checkAccess(["USER", "PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_role_composition_premium_and_user(self):
        assert Roles.PREMIUM & Roles.USER == Roles.USER

    def test_role_composition_enterprise_and_starter(self):
        assert Roles.DEVELOPER_ENTERPRISE & Roles.DEVELOPER_STARTER == Roles.DEVELOPER_STARTER
