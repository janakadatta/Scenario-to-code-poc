package com.example.oms.security;

import lombok.Builder;
import lombok.Getter;

import java.util.Set;

/**
 * Holds authenticated user attributes extracted from request security header or JWT token.
 */
@Getter
@Builder
public class UserSecurityContext {
    private final String userId;
    private final String email;
    private final Set<String> roles;

    public boolean hasRole(String role) {
        return roles != null && roles.contains(role);
    }

    public boolean isAdmin() {
        return hasRole("ROLE_ADMIN");
    }
}