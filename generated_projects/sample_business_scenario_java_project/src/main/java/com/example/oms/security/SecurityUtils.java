package com.example.oms.security;

import com.example.oms.common.exception.UnauthorizedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * Utility helper methods to retrieve details of the currently authenticated principal.
 */
public final class SecurityUtils {

    private SecurityUtils() {
    }

    public static UserSecurityContext getCurrentUser() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof UserSecurityContext userSecurityContext) {
            return userSecurityContext;
        }
        throw new UnauthorizedException("User is not authenticated or security context is missing.");
    }
}