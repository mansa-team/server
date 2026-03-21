from enum import IntFlag, auto
from fastapi import HTTPException, Depends

class Permission(IntFlag):
    NONE = 0

    # User
    VIEW_PROFILE = auto()
    USE_THOTH = auto()
    USE_MAAT = auto()
    
    # Premium
    USE_PROMETHEUS = auto()
    USE_OGUM = auto()

    # Developer - Startup
    GENERATE_API_KEYS = auto()
    VIEW_DEVELOPER_TAB = auto()
    API_STARTER_ACCESS = auto()
    EXPORT_BASIC_DATA = auto()
    USE_REALTIME_B3 = auto()
    
    # Developer - Enterprise
    API_ENTERPRISE_ACCESS = auto()
    EXPORT_BULK_DATA = auto()
    REQUEST_CUSTOM_FIELDS = auto()
    SUPPORT_CHAT_ACCESS = auto()
    VIEW_USAGE_ANALYTICS = auto()
    
    # Admin
    VIEW_STATS = auto()
    VIEW_ANALYTICS = auto()
    MANAGE_USERS = auto()
    SYSTEM_CONFIG = auto()

    @classmethod
    def ALL(cls):
        mask = cls.NONE
        for member in cls:
            mask |= member
        return mask

class Roles(IntFlag):
    USER = (
        Permission.VIEW_PROFILE | 
        Permission.USE_THOTH | 
        Permission.USE_MAAT
    )

    PREMIUM = (
        USER | 
        Permission.USE_PROMETHEUS | 
        Permission.USE_OGUM
    )

    DEVELOPER_STARTER = (
        USER | 
        Permission.GENERATE_API_KEYS | 
        Permission.VIEW_DEVELOPER_TAB |
        Permission.API_STARTER_ACCESS |
        Permission.EXPORT_BASIC_DATA |
        Permission.USE_REALTIME_B3
    )

    DEVELOPER_ENTERPRISE = (
        DEVELOPER_STARTER |
        Permission.API_ENTERPRISE_ACCESS |
        Permission.EXPORT_BULK_DATA |
        Permission.REQUEST_CUSTOM_FIELDS |
        Permission.SUPPORT_CHAT_ACCESS |
        Permission.VIEW_USAGE_ANALYTICS
    )
    
    ADMIN = Permission.ALL()

    @classmethod
    def checkAccess(cls, userRoles: list[str], required_perm: Permission) -> bool:
        userPerms = Permission.NONE
        for roleName in userRoles:
            try:
                if roleName.upper() == "ADMIN":
                    return True
                userPerms |= cls[roleName.upper()].value
            except KeyError:
                continue
        return (userPerms & required_perm) == required_perm

    def requirePermission(perm: Permission):
        from main.app.user.user import userManager
        def check(user: dict = Depends(userManager.getCurrentUser)):
            if not Roles.checkAccess(user.get('roles', []), perm):
                raise HTTPException(
                    status_code=403, 
                    detail=f"Missing required permission: {perm.name}"
                )
            return user
        return check
