"""
User management module.

This module provides user authentication, profile management, and identity linking.
"""

# Legacy models (to be deprecated)
from src.users.models import APIKey, AuditLog, RefreshToken, User

# New profile models for refactored authentication
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

# New profile schemas for refactored authentication
from src.users.profile_schemas import (
    AuthProvider,
    CommunityMemberCreate,
    CommunityMemberInDB,
    CommunityMemberResponse,
    CommunityMemberStats,
    CommunityMemberUpdate,
    CommunityRole,
    UserIdentityCreate,
    UserIdentityInDB,
    UserIdentityResponse,
    UserIdentityUpdate,
    UserProfileAdminUpdate,
    UserProfileCreate,
    UserProfileInDB,
    UserProfileResponse,
    UserProfileSelfUpdate,
    UserProfileStats,
    UserProfileUpdate,
)

__all__ = [
    "APIKey",
    "AuditLog",
    "AuthProvider",
    "CommunityMember",
    "CommunityMemberCreate",
    "CommunityMemberInDB",
    "CommunityMemberResponse",
    "CommunityMemberStats",
    "CommunityMemberUpdate",
    "CommunityRole",
    "RefreshToken",
    "User",
    "UserIdentity",
    "UserIdentityCreate",
    "UserIdentityInDB",
    "UserIdentityResponse",
    "UserIdentityUpdate",
    "UserProfile",
    "UserProfileAdminUpdate",
    "UserProfileCreate",
    "UserProfileInDB",
    "UserProfileResponse",
    "UserProfileSelfUpdate",
    "UserProfileStats",
    "UserProfileUpdate",
]
