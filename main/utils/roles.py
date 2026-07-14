from enum import IntFlag, auto
from fastapi import HTTPException, Depends


class Permission(IntFlag):
    NONE = 0

    VIEW_PROFILE = auto()
    USE_THOTH = auto()
    USE_MAAT = auto()

    USE_PROMETHEUS = auto()
    USE_OGUM = auto()

    VIEW_DEVELOPER_TAB = auto()
    STARTER_API_ACCESS = auto()
    GENERATE_API_KEYS = auto()

    PROMETHEUS_EXTENDED_MEMORIES = auto()

    ENTERPRISE_API_ACCESS = auto()
    EXPORT_BULK_DATA = auto()
    REQUEST_CUSTOM_FIELDS = auto()
    API_SUPPORT_CHAT_ACCESS = auto()
    NO_API_ATTRIBUTION_NEEDED = auto()

    MANAGE_USERS = auto()
    SYSTEM_CONFIG = auto()
    SYSTEM_STATS = auto()

    @classmethod
    def ALL(cls):
        return sum(cls)


class Roles(IntFlag):
    USER = Permission.VIEW_PROFILE | Permission.USE_THOTH | Permission.USE_MAAT

    PREMIUM = USER | Permission.USE_PROMETHEUS | Permission.USE_OGUM | Permission.PROMETHEUS_EXTENDED_MEMORIES

    DEVELOPER_STARTER = USER | Permission.VIEW_DEVELOPER_TAB | Permission.STARTER_API_ACCESS

    DEVELOPER_ENTERPRISE = (
        DEVELOPER_STARTER
        | Permission.ENTERPRISE_API_ACCESS
        | Permission.EXPORT_BULK_DATA
        | Permission.REQUEST_CUSTOM_FIELDS
        | Permission.API_SUPPORT_CHAT_ACCESS
        | Permission.NO_API_ATTRIBUTION_NEEDED
    )

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

    @staticmethod
    def requirePermission(perm: Permission):
        from main.app.user.user import UserManager

        async def checker(user: dict = Depends(UserManager.getCurrentUser)):
            if not Roles.checkAccess(user.get("roles", []), perm):
                raise HTTPException(status_code=403, detail=f"Missing required permission: {perm.name}")
            return user

        return checker
