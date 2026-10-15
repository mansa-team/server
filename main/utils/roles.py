from enum import IntFlag, auto


class Permission(IntFlag):
    NONE = 0

    USE_ORUNMILA = auto()

    ORUNMILA_EXTENDED_MEMORIES = auto()

    WALLET = auto()

    @classmethod
    def ALL(cls):
        return sum(cls)


class Roles(IntFlag):
    USER = Permission.WALLET

    PREMIUM = USER | Permission.USE_ORUNMILA | Permission.ORUNMILA_EXTENDED_MEMORIES

    # Loopback identity that exists to reach wallet routes.
    SERVICE = Permission.WALLET

    DEVELOPER_STARTER = USER

    DEVELOPER_ENTERPRISE = DEVELOPER_STARTER

    ADMIN = Permission.ALL()

    @classmethod
    def checkAccess(cls, userRoles: list[str], requiredPerm: Permission) -> bool:
        userPerms = Permission.NONE
        for roleName in userRoles:
            role = roleName.upper()
            if role == "ADMIN":
                return True
            try:
                userPerms |= cls[role]
            except KeyError:
                continue
        return bool(userPerms & requiredPerm)
