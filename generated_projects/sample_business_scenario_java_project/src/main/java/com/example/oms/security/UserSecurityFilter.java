package com.example.oms.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Lightweight mock authentication filter supporting header-based testing or JWT context extraction.
 * Pass headers:
 *   X-User-Id: customer_uuid or admin_uuid
 *   X-User-Email: user@example.com
 *   X-User-Roles: ROLE_CUSTOMER,ROLE_ADMIN
 */
@Component
public class UserSecurityFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        String userId = request.getHeader("X-User-Id");
        String email = request.getHeader("X-User-Email");
        String rolesHeader = request.getHeader("X-User-Roles");

        if (userId != null && !userId.isBlank()) {
            Set<String> roles = (rolesHeader != null && !rolesHeader.isBlank())
                    ? Arrays.stream(rolesHeader.split(",")).map(String::trim).collect(Collectors.toSet())
                    : Set.of("ROLE_CUSTOMER");

            UserSecurityContext userCtx = UserSecurityContext.builder()
                    .userId(userId)
                    .email(email != null ? email : "user@example.com")
                    .roles(roles)
                    .build();

            List<SimpleGrantedAuthority> authorities = roles.stream()
                    .map(SimpleGrantedAuthority::new)
                    .toList();

            UsernamePasswordAuthenticationToken auth = new UsernamePasswordAuthenticationToken(
                    userCtx, null, authorities
            );

            SecurityContextHolder.getContext().setAuthentication(auth);
        }

        filterChain.doFilter(request, response);
    }
}